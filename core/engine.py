import random
import logging
from threading import Lock
import chess
from stockfish import Stockfish
from core.config import STOCKFISH_PATH

logger = logging.getLogger("capybara_engine")

_engine_lock = Lock()

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

def get_bot_move_fide(board: chess.Board, bot_rating: int, fast: bool = False):
    """
    Calcula o lance do bot com Stockfish isolado por thread lock e tempo de reflexão realista.
    """
    if board.is_game_over():
        return None, 0

    move_num = board.fullmove_number
    # Tempo de reflexão realista: ~2s na abertura (lances 1 a 4), média de 4.5s no meio-jogo
    if fast:
        think_time_ms = random.randint(500, 1100)
    elif move_num <= 4:
        think_time_ms = random.randint(1800, 2400)
    else:
        think_time_ms = random.randint(3800, 5200)

    try:
        with _engine_lock:
            engine = Stockfish(path=STOCKFISH_PATH)
            engine.set_fen_position(board.fen())

            clamped_rating = max(500, min(3000, bot_rating))
            skill_level = max(0, min(20, round((clamped_rating - 500) * 20 / 2500)))
            engine.set_skill_level(skill_level)

            stockfish_elo = max(1320, min(3190, clamped_rating))
            engine.set_elo_rating(stockfish_elo)

            search_time = min(500, max(50, int(think_time_ms * 0.15)))
            best_move = engine.get_best_move_time(search_time)

            if best_move and chess.Move.from_uci(best_move) in board.legal_moves:
                return best_move, think_time_ms
    except Exception as e:
        logger.warning(f"Stockfish execution fallback: {e}")

    legal_moves = list(board.legal_moves)
    tactical_moves = [m for m in legal_moves if board.is_capture(m) or board.gives_check(m)]
    chosen = random.choice(tactical_moves if tactical_moves and bot_rating >= 1200 else legal_moves)
    return chosen.uci(), think_time_ms
