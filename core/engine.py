import asyncio
import logging
import random
import time
from contextlib import contextmanager
from subprocess import TimeoutExpired
from threading import BoundedSemaphore
import chess
import chess.engine
from core.config import STOCKFISH_CANDIDATES

logger = logging.getLogger("capybara_engine")

# Match Gunicorn's four request threads while keeping independent games concurrent.
_engine_slots = BoundedSemaphore(value=4)

def _open_simple_engine(command: str, timeout: float) -> chess.engine.SimpleEngine:
    async def initialize(future):
        transport = None
        protocol = None
        engine = None
        try:
            transport, protocol = await chess.engine.UciProtocol.popen(command)
            engine = chess.engine.SimpleEngine(transport, protocol, timeout=timeout)
            await asyncio.wait_for(protocol.initialize(), timeout)
        except BaseException:
            if engine:
                engine.close()
            elif transport:
                transport.close()
            if transport and protocol:
                process = transport.get_extra_info('subprocess')
                if process and process.returncode is None:
                    completed, _ = await asyncio.wait({protocol.returncode}, timeout=1.0)
                    if not completed:
                        process.terminate()
                        completed, _ = await asyncio.wait({protocol.returncode}, timeout=1.0)
                    if not completed:
                        process.kill()
                        await asyncio.wait({protocol.returncode}, timeout=1.0)
            raise

        future.set_result(engine)
        try:
            returncode = await protocol.returncode
            engine.returncode.set_result(returncode)
        finally:
            engine.close()
        await engine.shutdown_event.wait()

    return chess.engine.run_in_background(
        initialize,
        name=f"SimpleEngine (command={command!r})",
    )

BOT_STRENGTH_TIERS = (
    (500, 0, 100, 0.35),
    (650, 0, 150, 0.28),
    (800, 1, 250, 0.22),
    (950, 2, 400, 0.17),
    (1100, 4, 550, 0.12),
    (1250, 5, 750, 0.07),
    (1400, 6, 1100, 0.0),
    (1550, 7, 1300, 0.0),
    (1700, 8, 1500, 0.0),
    (1850, 9, 1700, 0.0),
    (2000, 10, 1900, 0.0),
    (2150, 12, 2100, 0.0),
    (2300, 14, 2300, 0.0),
    (2500, 16, 2500, 0.0),
    (2750, 18, 2800, 0.0),
    (3000, 20, 3000, 0.0),
)

def get_bot_strength_profile(bot_rating: int) -> dict[str, int | float]:
    rating = max(500, min(3000, int(bot_rating)))
    tier_index = min(
        range(len(BOT_STRENGTH_TIERS)),
        key=lambda index: abs(BOT_STRENGTH_TIERS[index][0] - rating)
    )
    tier_rating, skill_level, think_time_ms, random_move_chance = BOT_STRENGTH_TIERS[tier_index]
    return {
        "level": tier_index + 1,
        "rating": tier_rating,
        "skill_level": skill_level,
        "think_time_ms": think_time_ms,
        "random_move_chance": random_move_chance,
    }

def _shutdown_simple_engine(engine: chess.engine.SimpleEngine) -> None:
    # Wait for UCI quit, then escalate to terminate/kill and reap a stuck child.
    process = engine.protocol.transport.get_extra_info('subprocess')
    try:
        engine.quit()
    except Exception as error:
        logger.warning("Stockfish graceful shutdown failed: %s", error)
        engine.close()

    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=1.0)
    except TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)

@contextmanager
def stockfish_engine(timeout: float = 10.0):
    with _engine_slots:
        engine = None
        startup_errors = []
        for candidate in STOCKFISH_CANDIDATES:
            try:
                engine = _open_simple_engine(candidate, timeout)
                break
            except Exception as error:
                startup_errors.append((candidate, error))
                logger.exception("Falha ao iniciar Stockfish em %s", candidate)
        if engine is None:
            details = '; '.join(f'{path}: {error!r}' for path, error in startup_errors)
            raise RuntimeError(f"Não foi possível iniciar Stockfish: {details}") from (startup_errors[-1][1] if startup_errors else None)
        try:
            yield engine
        finally:
            _shutdown_simple_engine(engine)

def elo_expected(rating_a: float, rating_b: float) -> float:
    diff = max(-400.0, min(400.0, float(rating_b - rating_a)))
    return 1.0 / (1.0 + 10.0 ** (diff / 400.0))

def apply_fide_rating_update(cursor, username: str, opponent_rating: int, score: float):
    """
    Atualiza rating segundo as regras oficiais da FIDE (Handbook B.02).
    Calibração estritamente nas primeiras 2 partidas (K=40).
    Após 2 partidas: K=20 (ou K=10 se >= 2400).
    """
    cursor.execute("SELECT rating, calibrated, calibration_games FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        return 0, 1200
    current_rating = row['rating']
    calibrated = row['calibrated']
    cal_games = row['calibration_games'] or 0

    diff = max(-400.0, min(400.0, float(opponent_rating - current_rating)))
    expected = 1.0 / (1.0 + 10.0 ** (diff / 400.0))

    if cal_games < 2:
        k = 40
        new_cal_games = cal_games + 1
        new_calibrated = 1 if new_cal_games >= 2 else 0
    elif current_rating >= 2400:
        k = 10
        new_cal_games = cal_games
        new_calibrated = 1
    else:
        k = 20
        new_cal_games = cal_games
        new_calibrated = 1

    delta = round(k * (score - expected))
    new_rating = max(100, current_rating + delta)
    cursor.execute(
        "UPDATE users SET rating = ?, calibrated = ?, calibration_games = ? WHERE username = ?",
        (new_rating, new_calibrated, new_cal_games, username)
    )
    return delta, new_rating

def check_fide_end_conditions(board: chess.Board):
    """
    Retorna (is_over, status, winner, reason) segundo as regras FIDE oficiais:
    - Xeque-mate
    - Afogamento (Stalemate)
    - Insuficiência de material
    - 75 lances sem captura/peão (compulsório FIDE)
    - 5 repetições de posição (compulsório FIDE)
    - 50 lances e repetição tríplice
    """
    if board.is_checkmate():
        winner = 'black' if board.turn == chess.WHITE else 'white'
        return True, 'checkmate', winner, 'Vitória por Xeque-mate!'

    if board.is_stalemate():
        return True, 'stalemate', 'draw', 'Empate por Afogamento (Stalemate)!'

    if board.is_insufficient_material():
        return True, 'insufficient_material', 'draw', 'Empate por Material Insuficiente!'

    if board.is_seventyfive_moves():
        return True, 'seventy_five_moves', 'draw', 'Empate compulsório FIDE (Regra dos 75 lances)!'

    if board.is_fivefold_repetition():
        return True, 'fivefold_repetition', 'draw', 'Empate compulsório FIDE (5 repetições de posição)!'

    if board.can_claim_fifty_moves():
        return True, 'fifty_moves', 'draw', 'Empate pela Regra dos 50 lances!'

    if board.can_claim_threefold_repetition():
        return True, 'threefold_repetition', 'draw', 'Empate por Repetição Tripla de posição!'

    return False, 'active', None, None

def check_timeout_fide(board: chess.Board, side_flagged: str):
    """
    Regra FIDE 6.9:
    Se o tempo de um jogador expira, o oponente vence, EXCETO se o oponente
    tiver material insuficiente para aplicar xeque-mate legal.
    Nesse caso, o resultado é EMPATE.
    """
    opponent_color = chess.BLACK if side_flagged == 'white' else chess.WHITE
    if board.has_insufficient_material(opponent_color):
        return 'draw', 'Tempo esgotado! Empate FIDE automático (adversário sem material para dar mate).'
    else:
        winner = 'black' if side_flagged == 'white' else 'white'
        return winner, f'Tempo esgotado! Derrota por tempo das {"Brancas" if side_flagged == "white" else "Pretas"}.'

def categorize_time_control(time_initial: int, time_increment: int = 0) -> str:
    total = time_initial + 40 * time_increment
    if total < 180:
        return 'bullet'
    elif total < 600:
        return 'blitz'
    elif total <= 1800:
        return 'rapid'
    return 'custom'

UCI_ELO_FLOOR = 1320

def blunder_chance(rating: int) -> float:
    """Chance of a random legal move below the UCI_Elo floor (300 -> 65%, 1320 -> 5%)."""
    points = ((300, 0.65), (500, 0.50), (700, 0.38), (900, 0.27), (1100, 0.16), (1320, 0.05))
    rating = max(points[0][0], min(points[-1][0], rating))
    for (r1, p1), (r2, p2) in zip(points, points[1:]):
        if rating <= r2:
            return p1 + (p2 - p1) * (rating - r1) / (r2 - r1)
    return points[-1][1]

def _pick_bot_move(engine, board: chess.Board, bot_rating: int, profile: dict, think_time_ms: int) -> str:
    rating = max(100, int(bot_rating))
    legal_moves = list(board.legal_moves)
    if rating >= UCI_ELO_FLOOR:
        engine.configure({'UCI_LimitStrength': True, 'UCI_Elo': min(3190, rating)})
        result = engine.play(board, chess.engine.Limit(time=think_time_ms / 1000), info=chess.engine.INFO_NONE)
        if result.move and result.move in board.legal_moves:
            return result.move.uci()
        raise RuntimeError("Stockfish não retornou um lance legal para a posição.")

    if len(legal_moves) == 1:
        return legal_moves[0].uci()
    if random.random() < blunder_chance(rating):
        return random.choice(legal_moves).uci()
    # Shallow search, then often pick a lower-ranked candidate, like a weak human would.
    infos = engine.analyse(board, chess.engine.Limit(depth=2), multipv=min(4, len(legal_moves)))
    candidates = [info['pv'][0] for info in infos if info.get('pv')]
    if not candidates:
        return random.choice(legal_moves).uci()
    best_weight = 0.30 + 0.55 * (rating - 300) / (UCI_ELO_FLOOR - 300)
    weights = [best_weight] + [(1 - best_weight) / max(1, len(candidates) - 1)] * (len(candidates) - 1)
    return random.choices(candidates, weights=weights[:len(candidates)])[0].uci()

# O bot "pensa" pelo menos isso antes de jogar, exceto com o relógio quase no fim.
BOT_MIN_THINK_SECONDS = 4.0
BOT_INSTANT_BELOW_SECONDS = 10.0


def get_bot_move_fide(board: chess.Board, bot_rating: int, remaining_time: float | None = None):
    """
    Calcula lances em processos UCI limitados por timeout e slots concorrentes.
    """
    if board.is_game_over():
        return None, 0

    profile = get_bot_strength_profile(bot_rating)
    fast = remaining_time is not None and remaining_time <= BOT_INSTANT_BELOW_SECONDS
    started_at = time.monotonic()
    think_time_ms = 1 if fast else profile['think_time_ms']
    if not STOCKFISH_CANDIDATES:
        error = RuntimeError("Stockfish não está instalado ou não tem permissão de execução.")
        logger.error("Nenhum binário Stockfish executável encontrado nos caminhos conhecidos.")
        raise error

    try:
        with _engine_slots:
            timeout_seconds = max(5.0, think_time_ms / 1000 + 5.0)
            engine = None
            startup_errors = []
            for candidate in STOCKFISH_CANDIDATES:
                try:
                    engine = _open_simple_engine(candidate, timeout_seconds)
                    break
                except Exception as error:
                    startup_errors.append((candidate, error))
                    logger.exception("Falha ao iniciar Stockfish em %s", candidate)
            if engine is None:
                details = '; '.join(f'{path}: {error!r}' for path, error in startup_errors)
                raise RuntimeError(f"Não foi possível iniciar Stockfish em nenhum caminho: {details}") from (startup_errors[-1][1] if startup_errors else None)

            try:
                move = _pick_bot_move(engine, board, bot_rating, profile, think_time_ms)
            finally:
                _shutdown_simple_engine(engine)
        if not fast:
            time.sleep(max(0.0, BOT_MIN_THINK_SECONDS - (time.monotonic() - started_at)))
        return move, think_time_ms
    except Exception as error:
        logger.exception("Falha ao calcular lance com Stockfish.")
        raise RuntimeError("O motor Stockfish não conseguiu calcular um lance.") from error
