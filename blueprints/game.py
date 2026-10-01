import time
import json
import random
import re
import secrets
import chess
from flask import Blueprint, jsonify, request, session
from core.db import get_db, cleanup_ephemeral_sessions
from core.security import rate_limit, validate_uci_move, validate_fen
from core.engine import (
    check_fide_end_conditions, check_timeout_fide, get_bot_move_fide,
    categorize_time_control, apply_fide_rating_update, get_bot_strength_profile
)
from core.constants import BOT_SEALS, CLASSIC_MODES, MISSION_DEFINITIONS

game_bp = Blueprint('game', __name__)

@game_bp.before_request
def validate_game_path_id():
    view_args = request.view_args or {}
    game_id = view_args.get('game_id')
    if game_id is not None and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', game_id) is None:
        return jsonify({"error": "ID de partida inválido."}), 400

def resolve_game_actor(conn, supplied_username: str = '') -> str | None:
    authenticated_username = session.get('username')
    if authenticated_username:
        return authenticated_username
    candidate = str(supplied_username or '').strip()
    if not candidate:
        return None
    registered_user = conn.execute(
        "SELECT 1 FROM users WHERE username = ?",
        (candidate,)
    ).fetchone()
    return None if registered_user else candidate

def update_pvp_rating_transaction(conn, white_user: str, black_user: str, winner: str):
    if not white_user or not black_user or white_user.startswith('Bot:') or black_user.startswith('Bot:'):
        return
    row_w = conn.execute("SELECT rating, calibrated FROM users WHERE username = ?", (white_user,)).fetchone()
    row_b = conn.execute("SELECT rating, calibrated FROM users WHERE username = ?", (black_user,)).fetchone()
    if row_w and row_b and row_w['calibrated'] and row_b['calibrated']:
        r_w, r_b = row_w['rating'], row_b['rating']
        score_w = 1.0 if winner == 'white' else (0.5 if winner == 'draw' else 0.0)
        score_b = 1.0 - score_w
        apply_fide_rating_update(conn.cursor(), white_user, r_b, score_w)
        apply_fide_rating_update(conn.cursor(), black_user, r_w, score_b)

def parse_request_integer(data: dict, field: str, default: int) -> int | None:
    value = data.get(field, default)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None

def update_initial_calibration_result(
    conn, game_type: str, white_user: str, black_user: str, bot_number: int,
    bot_rating: int, winner: str
) -> tuple[int, int | None]:
    if game_type != 'bot' or not winner or bot_number not in {1, 2, 3, 4, 5}:
        return 0, None

    bot_is_white = bool(white_user and white_user.startswith('Bot:'))
    username = black_user if bot_is_white else white_user
    if not username or username.startswith('Bot:'):
        return 0, None

    user = conn.execute(
        "SELECT rating, calibrated, calibration_games FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    if not user:
        return 0, None
    if user['calibrated'] or (user['calibration_games'] or 0) >= 2:
        return 0, user['rating']

    player_color = 'black' if bot_is_white else 'white'
    player_won = (winner == 'white' and player_color == 'white') or (winner == 'black' and player_color == 'black')
    score = 1.0 if player_won else (0.5 if winner == 'draw' else 0.0)
    return apply_fide_rating_update(conn.cursor(), username, bot_rating, score)

def update_classic_rating_result(
    conn, game_type: str, classic_mode: str, classic_bot_number: int,
    bot_rating: int, white_user: str, black_user: str, winner: str
) -> int:
    if game_type != 'bot' or classic_mode not in CLASSIC_MODES or not classic_bot_number or not winner:
        return 0

    bot_is_white = bool(white_user and white_user.startswith('Bot:'))
    player_user = black_user if bot_is_white else white_user
    player_color = 'black' if bot_is_white else 'white'
    if not player_user or player_user.startswith('Bot:'):
        return 0

    profile = conn.execute(
        "SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?",
        (player_user, classic_mode)
    ).fetchone()
    if not profile:
        return 0

    player_won = (winner == 'white' and player_color == 'white') or (winner == 'black' and player_color == 'black')
    score = 1.0 if player_won else (0.5 if winner == 'draw' else 0.0)
    rating = profile['rating']
    difference = max(-400, min(400, bot_rating - rating))
    expected = 1.0 / (1.0 + 10.0 ** (difference / 400.0))
    new_rating = max(100, round(rating + 20 * (score - expected)))
    conn.execute(
        "UPDATE classic_profiles SET rating = ?, games_played = games_played + 1 WHERE username = ? AND mode = ?",
        (new_rating, player_user, classic_mode)
    )
    return new_rating - rating
def update_missions_progress(
    conn, username: str, mode: str, bot_rating: int, result: str,
    player_color: str, termination_status: str, history: list[dict]
) -> list[int]:
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR IGNORE INTO missions (username, mission_id) VALUES (?, ?)",
        [(username, mission[0]) for mission in MISSION_DEFINITIONS]
    )
    p_row = cursor.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
    profile_rating = p_row['rating'] if p_row else 1200
    player_turn = 'w' if player_color == 'white' else 'b'
    player_moves = [move for move in history if move.get('turn') == player_turn]
    player_san = [move.get('san', '') for move in player_moves]
    captures = sum('x' in san for san in player_san)
    is_win = result == 'win'
    events = {
        'games': 1,
        'wins': int(is_win),
        'wins_blitz': int(is_win and mode == 'blitz'),
        'wins_bullet': int(is_win and mode == 'bullet'),
        'wins_rapid': int(is_win and mode == 'rapid'),
        'wins_black': int(is_win and player_color == 'black'),
        'wins_white': int(is_win and player_color == 'white'),
        'upset_wins': int(is_win and bot_rating >= profile_rating + 200),
        'games_blitz': int(mode == 'blitz'),
        'games_rapid': int(mode == 'rapid'),
        'draws': int(result == 'draw'),
        'wins_1000': int(is_win and bot_rating >= 1000),
        'wins_1500': int(is_win and bot_rating >= 1500),
        'checkmate_wins': int(is_win and termination_status == 'checkmate'),
        'quick_wins': int(is_win and len(player_moves) <= 20),
        'promotion_games': int(any(len(move.get('uci', '')) == 5 for move in player_moves)),
        'capture_rich_games': int(captures >= 5),
        'castling_games': int(any(san.startswith('O-O') for san in player_san)),
        'check_games': int(sum(san.endswith(('+', '#')) for san in player_san) >= 3),
        'wins_2000': int(is_win and bot_rating >= 2000),
        'no_capture_wins': int(is_win and captures == 0),
        'black_wins_2000': int(is_win and player_color == 'black' and bot_rating >= 2000),
    }
    progress_rows = cursor.execute(
        "SELECT mission_id, progress, completed FROM missions WHERE username = ?",
        (username,)
    ).fetchall()
    progress_by_id = {row['mission_id']: row for row in progress_rows}
    newly_completed = []
    for mission_id, _title, target, _reward, _difficulty, event_key in MISSION_DEFINITIONS:
        current = progress_by_id.get(mission_id)
        if not current or current['completed'] or not events[event_key]:
            continue
        progress = min(target, current['progress'] + events[event_key])
        completed = int(progress >= target)
        cursor.execute(
            "UPDATE missions SET progress = ?, completed = ? WHERE username = ? AND mission_id = ?",
            (progress, completed, username, mission_id)
        )
        if completed:
            newly_completed.append(mission_id)
    return newly_completed

def update_bot_missions_for_result(
    conn, game_type: str, white_user: str, black_user: str, bot_rating: int,
    time_initial: int, time_increment: int, winner: str, termination_status: str,
    history: list[dict]
) -> list[int]:
    if game_type != 'bot' or not winner:
        return []

    bot_is_white = bool(white_user and white_user.startswith('Bot:'))
    player_user = black_user if bot_is_white else white_user
    if not player_user or player_user.startswith('Bot:'):
        return []

    player_color = 'black' if bot_is_white else 'white'
    player_won = (winner == 'white' and player_color == 'white') or (winner == 'black' and player_color == 'black')
    result = 'win' if player_won else ('draw' if winner == 'draw' else 'loss')
    mode = categorize_time_control(time_initial, time_increment)
    if mode == 'custom':
        mode = 'blitz'
    return update_missions_progress(
        conn, player_user, mode, bot_rating, result, player_color,
        termination_status, history
    )

@game_bp.route('/game/create', methods=['POST'])
def game_create():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        username = f"Convidado_{secrets.token_hex(2)}"

    mode = data.get('mode', 'bot')
    color_choice = data.get('color', 'random')
    time_control = data.get('time_control', '180,2')
    bot_number = parse_request_integer(data, 'bot_number', 1)
    bot_rating = parse_request_integer(data, 'bot_rating', 500)
    rated_value = data.get('rated', True)

    if not isinstance(mode, str) or mode not in {'bot', 'pvp'}:
        return jsonify({"error": "Modo de partida inválido."}), 400
    if not isinstance(color_choice, str) or color_choice not in {'white', 'black', 'random'}:
        return jsonify({"error": "Cor inválida."}), 400
    if bot_number is None or not 1 <= bot_number <= 700:
        return jsonify({"error": "Número do bot inválido."}), 400
    if bot_rating is None or not 500 <= bot_rating <= 3000:
        return jsonify({"error": "Rating do bot deve estar entre 500 e 3000 Elo."}), 400
    if not isinstance(rated_value, bool):
        return jsonify({"error": "A opção de rating deve ser booleana."}), 400
    rated = int(rated_value)

    supported_time_controls = {
        '60,0', '60,1', '120,0', '120,1', '180,0', '180,2', '300,0',
        '600,0', '600,3', '600,5', '900,10', '1800,0', '1800,30'
    }
    if time_control == 'random':
        time_control = random.choice(tuple(supported_time_controls))
    if not isinstance(time_control, str) or time_control not in supported_time_controls:
        return jsonify({"error": "Controle de tempo inválido."}), 400

    if mode == 'pvp' and rated:
        authenticated_username = session.get('username')
        if not authenticated_username:
            return jsonify({"error": "Entre na sua conta e conclua a calibração antes do modo ranqueado."}), 401
        with get_db() as conn:
            user = conn.execute(
                "SELECT calibrated FROM users WHERE username = ?",
                (authenticated_username,)
            ).fetchone()
        if not user or not user['calibrated']:
            return jsonify({"error": "Conclua duas partidas de calibração antes do modo ranqueado."}), 403

    authenticated_username = session.get('username')
    if mode == 'bot' and authenticated_username:
        with get_db() as conn:
            user = conn.execute(
                "SELECT calibrated FROM users WHERE username = ?",
                (authenticated_username,)
            ).fetchone()
        if user and not user['calibrated']:
            calibration_ratings = {1: 500, 2: 1000, 3: 1500, 4: 2100, 5: 2150}
            if bot_number not in calibration_ratings:
                return jsonify({"error": "Durante a calibração, escolha um dos cinco bots oficiais iniciais."}), 403
            bot_rating = calibration_ratings[bot_number]

    time_initial, time_increment = (int(part) for part in time_control.split(',', 1))

    game_id = secrets.token_urlsafe(8)

    with get_db() as conn:
        cursor = conn.cursor()
        if mode == 'bot':
            bot_names = {1: "Capivarão", 2: "Pirata", 3: "Marinheiro", 4: "Governador", 5: "Imperador",
                         6: "Pedro", 7: "Dill", 8: "Erick", 9: "Anonimus", 10: "Camargo", 11: "Fish", 12: "Rafachess"}
            bot_seals = {1: "C", 2: "P", 3: "M", 4: "G", 5: "I", 6: "NM", 7: "FM", 8: "IM", 9: "GM", 10: "SP", 11: "ST", 12: "RF"}
            classic_mode = str(data.get('classic_mode', ''))
            classic_opponent = None
            if bot_number > 12:
                if classic_mode not in CLASSIC_MODES:
                    return jsonify({"error": "Adversário clássico inválido."}), 400
                name_language = data.get('language', 'pt')
                name_column = f"name_{name_language}" if name_language in {'pt', 'en', 'es', 'fr'} else 'name_pt'
                classic_opponent = cursor.execute(
                    f"SELECT rating, {name_column} AS bot_name FROM classic_bots WHERE username = ? AND mode = ? AND bot_number = ?",
                    (username, classic_mode, bot_number)
                ).fetchone()
                if not classic_opponent:
                    return jsonify({"error": "O bot clássico não pertence ao seu catálogo de rating."}), 404
                bot_rating = classic_opponent['rating']
                bot_name = f"Bot: {classic_opponent['bot_name']}"
                seal = ''
            else:
                bot_name = f"Bot: {bot_names.get(bot_number, f'Capy_{bot_rating}')}"
                seal = bot_seals.get(bot_number, "C")

            assigned_color = color_choice
            if assigned_color == 'random':
                assigned_color = random.choice(['white', 'black'])

            if assigned_color == 'white':
                white_user = username
                black_user = bot_name
            else:
                white_user = bot_name
                black_user = username

            board = chess.Board()
            history = []
            turn = 'w'
            status = 'active'
            last_move_time = time.time()

            if white_user == bot_name:
                try:
                    bot_uci, _ = get_bot_move_fide(board, bot_rating, remaining_time=float(time_initial))
                except RuntimeError as error:
                    return jsonify({"error": str(error)}), 503
                if bot_uci:
                    bot_move_obj = chess.Move.from_uci(bot_uci)
                    san = board.san(bot_move_obj)
                    board.push(bot_move_obj)
                    history.append({"uci": bot_uci, "san": san, "turn": 'w'})
                    turn = 'b'
                    last_move_time = time.time()

            cursor.execute('''
                INSERT INTO games (id, white_user, black_user, creator_user, creator_color, game_type,
                                  time_initial, time_increment, white_time, black_time, last_move_time,
                                                                    fen, history, turn, status, bot_number, bot_rating, bot_seal,
                                                                    classic_mode, classic_bot_number, rated)
                                VALUES (?, ?, ?, ?, ?, 'bot', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, white_user, black_user, username, color_choice, time_initial, time_increment,
                  float(time_initial), float(time_initial), last_move_time, board.fen(),
                                    json.dumps(history), turn, status, bot_number, bot_rating, seal,
                                    classic_mode if classic_opponent else '', bot_number if classic_opponent else 0, rated))

            return jsonify({
                "success": True,
                "game_id": game_id,
                "game_type": "bot",
                "time_initial": time_initial,
                "bot_number": bot_number,
                "bot_rating": bot_rating,
                "bot_strength_level": get_bot_strength_profile(bot_rating)['level'],
                "bot_seal": seal,
                "classic_mode": classic_mode if classic_opponent else '',
                "white_user": white_user,
                "black_user": black_user,
                "player_color": assigned_color,
                "fen": board.fen(),
                "history": history,
                "turn": turn,
                "status": status,
                "white_time": float(time_initial),
                "black_time": float(time_initial),
                "time_increment": time_increment
            })
        else:
            white_user = None
            black_user = None
            if color_choice == 'white':
                white_user = username
            elif color_choice == 'black':
                black_user = username

            cursor.execute('''
                INSERT INTO games (id, white_user, black_user, creator_user, creator_color, game_type,
                                  time_initial, time_increment, white_time, black_time, last_move_time,
                                  fen, history, turn, status, rated)
                VALUES (?, ?, ?, ?, ?, 'pvp', ?, ?, ?, ?, NULL, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', '[]', 'w', 'waiting', ?)
            ''', (game_id, white_user, black_user, username, color_choice, time_initial, time_increment,
                  float(time_initial), float(time_initial), rated))

            challenge_url = f"{request.host_url}?join={game_id}"
            return jsonify({
                "success": True,
                "game_id": game_id,
                "status": "waiting",
                "creator": username,
                "color_choice": color_choice,
                "challenge_url": challenge_url
            })

@game_bp.route('/game/<game_id>/join', methods=['POST'])
def game_join(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            if session.get('username'):
                return jsonify({"error": "Não autenticado."}), 401
            username = f"Convidado_{secrets.token_hex(2)}"
        row = conn.execute("SELECT id, white_user, black_user, creator_user, creator_color, status, rated FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        creator_user = row['creator_user']
        creator_color = row['creator_color']
        status = row['status']
        if row['rated']:
            user = conn.execute("SELECT calibrated FROM users WHERE username = ?", (username,)).fetchone()
            if not user or not user['calibrated']:
                return jsonify({"error": "Conclua duas partidas de calibração antes de entrar em uma partida ranqueada."}), 403

        if status == 'active':
            player_color = 'white' if white_user == username else ('black' if black_user == username else 'spectator')
            return jsonify({"success": True, "already_joined": True, "player_color": player_color})

        if status != 'waiting':
            return jsonify({"error": "Esta partida já terminou ou foi cancelada."}), 400

        if username == creator_user and not white_user and not black_user:
            return jsonify({"success": True, "waiting": True})

        if creator_color == 'white':
            white_user = creator_user
            black_user = username
        elif creator_color == 'black':
            black_user = creator_user
            white_user = username
        else:
            if random.random() < 0.5:
                white_user = creator_user
                black_user = username
            else:
                white_user = username
                black_user = creator_user

        now = time.time()
        conn.execute("""
            UPDATE games SET white_user = ?, black_user = ?, status = 'active', last_move_time = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (white_user, black_user, now, game_id))

    my_color = 'white' if white_user == username else 'black'
    return jsonify({
        "success": True,
        "game_id": game_id,
        "white_user": white_user,
        "black_user": black_user,
        "player_color": my_color,
        "status": "active"
    })

@game_bp.route('/matchmaking/ranked/join', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def ranked_queue_join():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Entre na sua conta para buscar uma partida ranqueada."}), 401

    data = request.get_json(silent=True) or {}
    time_control = str(data.get('time_control', '180,2'))
    controls = {
        '60,0': (60, 0), '60,1': (60, 1), '180,0': (180, 0),
        '180,2': (180, 2), '300,0': (300, 0), '600,0': (600, 0),
        '900,10': (900, 10), '1800,0': (1800, 0)
    }
    if time_control not in controls:
        time_control = '180,2'

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT rating, calibrated FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404
        if not user['calibrated']:
            return jsonify({"error": "Conclua duas partidas de calibração antes do modo ranqueado."}), 403

        active_game = conn.execute("""
            SELECT id, game_type, rated FROM games
            WHERE status = 'active' AND (white_user = ? OR black_user = ?)
            ORDER BY created_at DESC LIMIT 1
        """, (username, username)).fetchone()
        if active_game:
            if active_game['game_type'] == 'pvp' and active_game['rated']:
                return jsonify({"success": True, "status": "matched", "game_id": active_game['id']})
            return jsonify({"error": "Conclua sua partida atual antes de entrar na fila ranqueada."}), 409

        conn.execute("""
            INSERT INTO user_presence (username, last_seen_at) VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(username) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP
        """, (username,))
        cleanup_ephemeral_sessions(conn, username)
        existing_queue = conn.execute(
            "SELECT status, time_control, game_id FROM ranked_queue WHERE username = ?",
            (username,)
        ).fetchone()
        if existing_queue and existing_queue['status'] == 'waiting' and existing_queue['time_control'] == time_control:
            return jsonify({"success": True, "status": "queued", "rating": user['rating']})
        conn.execute("DELETE FROM ranked_queue WHERE username = ?", (username,))

        candidates = conn.execute("""
            SELECT q.username, q.rating, q.queued_at,
                   CAST((julianday('now') - julianday(q.queued_at)) * 86400 AS INTEGER) AS waited
            FROM ranked_queue q
            JOIN users u ON u.username = q.username
            JOIN user_presence p ON p.username = q.username
            WHERE q.status = 'waiting' AND q.time_control = ? AND q.username != ?
              AND u.calibrated = 1 AND p.last_seen_at >= datetime('now', '-45 seconds')
              AND NOT EXISTS (
                  SELECT 1 FROM games g WHERE g.status = 'active'
                    AND (g.white_user = q.username OR g.black_user = q.username)
              )
            ORDER BY ABS(q.rating - ?), q.queued_at ASC
        """, (time_control, username, user['rating'])).fetchall()

        opponent = next((
            candidate for candidate in candidates
            if abs(candidate['rating'] - user['rating']) <= min(600, 100 + (max(0, candidate['waited']) // 15) * 50)
        ), None)

        if not opponent:
            conn.execute("""
                INSERT INTO ranked_queue (username, rating, time_control, status, game_id, queued_at)
                VALUES (?, ?, ?, 'waiting', NULL, CURRENT_TIMESTAMP)
            """, (username, user['rating'], time_control))
            return jsonify({"success": True, "status": "queued", "rating": user['rating']})

        time_initial, time_increment = controls[time_control]
        game_id = secrets.token_urlsafe(8)
        white_user, black_user = (username, opponent['username']) if random.random() < 0.5 else (opponent['username'], username)
        creator_color = 'white' if white_user == username else 'black'
        conn.execute("""
            INSERT INTO games (
                id, white_user, black_user, creator_user, creator_color, game_type,
                time_initial, time_increment, white_time, black_time, last_move_time,
                fen, history, turn, status, rated
            ) VALUES (?, ?, ?, ?, ?, 'pvp', ?, ?, ?, ?, ?,
                      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', '[]', 'w', 'active', 1)
        """, (
            game_id, white_user, black_user, username, creator_color,
            time_initial, time_increment, float(time_initial), float(time_initial), time.time()
        ))
        conn.execute(
            "UPDATE ranked_queue SET status = 'matched', game_id = ? WHERE username = ?",
            (game_id, opponent['username'])
        )
        conn.execute("""
            INSERT INTO ranked_queue (username, rating, time_control, status, game_id, queued_at)
            VALUES (?, ?, ?, 'matched', ?, CURRENT_TIMESTAMP)
        """, (username, user['rating'], time_control, game_id))

    return jsonify({"success": True, "status": "matched", "game_id": game_id})

@game_bp.route('/matchmaking/ranked/status', methods=['GET'])
def ranked_queue_status():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    with get_db() as conn:
        cleanup_ephemeral_sessions(conn, username)
        queued = conn.execute(
            "SELECT status, game_id FROM ranked_queue WHERE username = ?",
            (username,)
        ).fetchone()
        if not queued:
            return jsonify({"status": "idle"})
        if queued['status'] == 'matched' and queued['game_id']:
            game = conn.execute("SELECT status FROM games WHERE id = ?", (queued['game_id'],)).fetchone()
            if game and game['status'] == 'active':
                return jsonify({"status": "matched", "game_id": queued['game_id']})
            conn.execute("DELETE FROM ranked_queue WHERE game_id = ?", (queued['game_id'],))
            return jsonify({"status": "idle"})
        return jsonify({"status": queued['status']})

@game_bp.route('/matchmaking/ranked/leave', methods=['POST'])
def ranked_queue_leave():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    with get_db() as conn:
        conn.execute("DELETE FROM ranked_queue WHERE username = ? AND status = 'waiting'", (username,))
    return jsonify({"success": True})

@game_bp.route('/game/<game_id>/state', methods=['GET'])
def game_state(game_id):
    supplied_username = request.args.get('username', '').strip()
    with get_db() as conn:
        authenticated_user = session.get('username')
        current_user = resolve_game_actor(conn, supplied_username)
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        gid = row['id']
        white_user = row['white_user']
        black_user = row['black_user']
        game_type = row['game_type']
        time_initial = row['time_initial']
        time_increment = row['time_increment']
        white_time = row['white_time']
        black_time = row['black_time']
        last_move_time = row['last_move_time']
        fen = row['fen']
        history = json.loads(row['history'] or '[]')
        turn = row['turn']
        status = row['status']
        winner = row['winner']
        termination_reason = row['termination_reason']
        bot_number = row['bot_number']
        bot_rating = row['bot_rating']
        classic_mode = row['classic_mode']
        classic_bot_number = row['classic_bot_number']
        bot_seal = row['bot_seal']
        rated = row['rated']
        draw_offered_by = row['draw_offered_by']
        missions_completed = []
        rating_change = 0
        new_user_rating = None
        classic_rating_change = 0

        is_participant = current_user in (white_user, black_user)
        if not is_participant:
            if not authenticated_user or status == 'waiting':
                return jsonify({"error": "Apenas os participantes ou amigos autenticados podem assistir a esta partida."}), 403
            friendship = conn.execute("""
                SELECT 1 FROM friend_requests
                WHERE status = 'accepted' AND (
                    (sender = ? AND recipient IN (?, ?)) OR
                    (recipient = ? AND sender IN (?, ?))
                ) LIMIT 1
            """, (
                authenticated_user, white_user, black_user,
                authenticated_user, white_user, black_user
            )).fetchone()
            if not friendship:
                return jsonify({"error": "Somente amigos aceitos podem assistir a esta partida."}), 403

        now = time.time()
        w_time = float(white_time)
        b_time = float(black_time)

        if status == 'active' and time_initial > 0 and last_move_time:
            elapsed = max(0.0, now - float(last_move_time))
            board = chess.Board(fen)
            if turn == 'w':
                w_time = max(0.0, white_time - elapsed)
                if w_time <= 0 and is_participant:
                    winner, termination_reason = check_timeout_fide(board, 'white')
                    status = 'timeout'
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, white_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, termination_reason, game_id))
                    if rated and game_type == 'pvp':
                        update_pvp_rating_transaction(conn, white_user, black_user, winner)
                    rating_change, new_user_rating = update_initial_calibration_result(
                        conn, game_type, white_user, black_user, bot_number,
                        bot_rating or 0, winner
                    )
                    missions_completed = update_bot_missions_for_result(
                        conn, game_type, white_user, black_user, bot_rating,
                        time_initial, time_increment, winner, 'timeout', history
                    )
                    classic_rating_change = update_classic_rating_result(
                        conn, game_type, classic_mode, classic_bot_number,
                        bot_rating or 0, white_user, black_user, winner
                    )
                elif w_time <= 0:
                    winner, termination_reason = check_timeout_fide(board, 'white')
                    status = 'timeout'
            elif turn == 'b':
                b_time = max(0.0, black_time - elapsed)
                if b_time <= 0 and is_participant:
                    winner, termination_reason = check_timeout_fide(board, 'black')
                    status = 'timeout'
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, termination_reason, game_id))
                    if rated and game_type == 'pvp':
                        update_pvp_rating_transaction(conn, white_user, black_user, winner)
                    rating_change, new_user_rating = update_initial_calibration_result(
                        conn, game_type, white_user, black_user, bot_number,
                        bot_rating or 0, winner
                    )
                    missions_completed = update_bot_missions_for_result(
                        conn, game_type, white_user, black_user, bot_rating,
                        time_initial, time_increment, winner, 'timeout', history
                    )
                    classic_rating_change = update_classic_rating_result(
                        conn, game_type, classic_mode, classic_bot_number,
                        bot_rating or 0, white_user, black_user, winner
                    )
                elif b_time <= 0:
                    winner, termination_reason = check_timeout_fide(board, 'black')
                    status = 'timeout'

    player_color = 'white' if current_user and white_user == current_user else ('black' if current_user and black_user == current_user else 'spectator')

    return jsonify({
        "game_id": gid,
        "white_user": white_user or 'Aguardando...',
        "black_user": black_user or 'Aguardando...',
        "player_color": player_color,
        "game_type": game_type,
        "time_initial": time_initial,
        "time_increment": time_increment,
        "white_time": round(w_time, 1),
        "black_time": round(b_time, 1),
        "fen": fen,
        "history": history,
        "turn": turn,
        "status": status,
        "winner": winner,
        "termination_reason": termination_reason,
        "bot_number": bot_number,
        "bot_rating": bot_rating,
        "bot_strength_level": get_bot_strength_profile(bot_rating)['level'] if game_type == 'bot' else None,
        "bot_seal": bot_seal,
        "rated": bool(rated),
        "draw_offered_by": draw_offered_by,
        "missions_completed": missions_completed,
        "rating_change": rating_change,
        "new_rating": new_user_rating,
        "classic_rating_change": classic_rating_change
    })

@game_bp.route('/game/<game_id>/move', methods=['POST'])
@rate_limit(max_requests=60, window_seconds=60)
def game_move(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()
    move_uci = str(data.get('move', '')).strip().lower()

    if not supplied_username and not session.get('username') or not validate_uci_move(move_uci):
        return jsonify({"error": "Lance ou jogador inválido."}), 400

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            return jsonify({"error": "Autenticação necessária para mover com uma conta registrada."}), 401
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        gid = row['id']
        white_user = row['white_user']
        black_user = row['black_user']
        game_type = row['game_type']
        time_initial = row['time_initial']
        time_increment = row['time_increment']
        white_time = row['white_time']
        black_time = row['black_time']
        last_move_time = row['last_move_time']
        fen = row['fen']
        history = json.loads(row['history'] or '[]')
        turn = row['turn']
        status = row['status']
        bot_rating = row['bot_rating']
        bot_number = row['bot_number']
        bot_seal = row['bot_seal']
        classic_mode = row['classic_mode']
        classic_bot_number = row['classic_bot_number']
        rated = row['rated']

        if status != 'active':
            return jsonify({"error": "Esta partida não está ativa."}), 400

        # Validação estrita de identidade e turno (Anti-Cheat)
        if turn == 'w' and white_user != username:
            return jsonify({"error": "Não é a sua vez de jogar (Turno das Brancas)."}), 403
        if turn == 'b' and black_user != username:
            return jsonify({"error": "Não é a sua vez de jogar (Turno das Pretas)."}), 403

        now = time.time()
        w_time = float(white_time)
        b_time = float(black_time)
        board = chess.Board(fen)

        if time_initial > 0 and last_move_time:
            elapsed = max(0.0, now - float(last_move_time))
            if turn == 'w':
                w_time -= elapsed
                if w_time <= 0:
                    winner, reason = check_timeout_fide(board, 'white')
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, white_time = 0 WHERE id = ?", (winner, reason, game_id))
                    rating_change, new_user_rating = update_initial_calibration_result(
                        conn, game_type, white_user, black_user, bot_number,
                        bot_rating or 0, winner
                    )
                    missions_completed = update_bot_missions_for_result(
                        conn, game_type, white_user, black_user, bot_rating,
                        time_initial, time_increment, winner, 'timeout', history
                    )
                    classic_rating_change = update_classic_rating_result(
                        conn, game_type, classic_mode, classic_bot_number,
                        bot_rating or 0, white_user, black_user, winner
                    )
                    return jsonify({"error": reason, "game_over": True, "status": "timeout", "winner": winner, "missions_completed": missions_completed, "rating_change": rating_change, "new_rating": new_user_rating, "classic_rating_change": classic_rating_change})
                w_time += time_increment
            else:
                b_time -= elapsed
                if b_time <= 0:
                    winner, reason = check_timeout_fide(board, 'black')
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0 WHERE id = ?", (winner, reason, game_id))
                    rating_change, new_user_rating = update_initial_calibration_result(
                        conn, game_type, white_user, black_user, bot_number,
                        bot_rating or 0, winner
                    )
                    missions_completed = update_bot_missions_for_result(
                        conn, game_type, white_user, black_user, bot_rating,
                        time_initial, time_increment, winner, 'timeout', history
                    )
                    classic_rating_change = update_classic_rating_result(
                        conn, game_type, classic_mode, classic_bot_number,
                        bot_rating or 0, white_user, black_user, winner
                    )
                    return jsonify({"error": reason, "game_over": True, "status": "timeout", "winner": winner, "missions_completed": missions_completed, "rating_change": rating_change, "new_rating": new_user_rating, "classic_rating_change": classic_rating_change})
                b_time += time_increment

        try:
            move_obj = chess.Move.from_uci(move_uci)
        except Exception:
            return jsonify({"error": "Formato de lance UCI inválido."}), 400

        if move_obj not in board.legal_moves:
            return jsonify({"error": "Lance ilegal segundo as regras da FIDE."}), 400

        san = board.san(move_obj)
        board.push(move_obj)
        history.append({"uci": move_uci, "san": san, "turn": turn})
        next_turn = 'w' if board.turn == chess.WHITE else 'b'
        last_move_time = time.time()

        is_over, end_status, winner, reason = check_fide_end_conditions(board)

        bot_moved = None
        if not is_over and game_type == 'bot':
            bot_time = w_time if board.turn == chess.WHITE else b_time
            try:
                bot_uci, think_ms = get_bot_move_fide(board, bot_rating, remaining_time=bot_time)
            except RuntimeError as error:
                return jsonify({"error": str(error)}), 503
            if bot_uci:
                bot_obj = chess.Move.from_uci(bot_uci)
                bot_san = board.san(bot_obj)
                board.push(bot_obj)
                history.append({"uci": bot_uci, "san": bot_san, "turn": next_turn})
                bot_moved = {"uci": bot_uci, "san": bot_san, "think_time_ms": think_ms}

                if next_turn == 'w':
                    w_time += time_increment
                else:
                    b_time += time_increment

                next_turn = 'w' if board.turn == chess.WHITE else 'b'
                last_move_time = time.time()
                is_over, end_status, winner, reason = check_fide_end_conditions(board)

        earned_coins = 0
        missions_completed = []
        classic_rating_change = 0
        fide_delta = 0
        new_user_rating = None

        if is_over:
            conn.execute("""
                UPDATE games SET fen = ?, history = ?, turn = ?, status = ?, winner = ?,
                                 termination_reason = ?, white_time = ?, black_time = ?, last_move_time = ?,
                                 draw_offered_by = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (board.fen(), json.dumps(history), next_turn, end_status, winner, reason, w_time, b_time, last_move_time, game_id))

            tc_mode = categorize_time_control(time_initial, time_increment)

            if game_type == 'bot' and winner:
                player_is_white = (white_user == username)
                player_won = (winner == 'white' and player_is_white) or (winner == 'black' and not player_is_white)
                is_draw = (winner == 'draw')
                res_key = 'win' if player_won else ('draw' if is_draw else 'loss')

                offline_coins = {'bullet': {'win': 3, 'draw': 1, 'loss': 0}, 'blitz': {'win': 5, 'draw': 1, 'loss': 0}, 'rapid': {'win': 8, 'draw': 2, 'loss': 0}, 'custom': {'win': 5, 'draw': 1, 'loss': 0}}
                earned_coins = offline_coins.get(tc_mode, offline_coins['blitz']).get(res_key, 0)
                if earned_coins > 0:
                    conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (earned_coins, username))

                if player_won and bot_seal:
                    conn.execute("INSERT OR IGNORE INTO achievements (username, seal) VALUES (?, ?)", (username, bot_seal))

                fide_delta, new_user_rating = update_initial_calibration_result(
                    conn, game_type, white_user, black_user, bot_number,
                    bot_rating or 0, winner
                )
                missions_completed = update_bot_missions_for_result(
                    conn, game_type, white_user, black_user, bot_rating,
                    time_initial, time_increment, winner, end_status, history
                )
                classic_rating_change = update_classic_rating_result(
                    conn, game_type, classic_mode, classic_bot_number,
                    bot_rating or 0, white_user, black_user, winner
                )

            elif game_type == 'pvp' and winner:
                online_coins = {'bullet': {'win': 15, 'draw': 5, 'loss': 0}, 'blitz': {'win': 30, 'draw': 10, 'loss': 0}, 'rapid': {'win': 50, 'draw': 15, 'loss': 0}, 'custom': {'win': 25, 'draw': 5, 'loss': 0}}
                w_coins = online_coins.get(tc_mode, online_coins['blitz'])['win'] if winner == 'white' else (online_coins.get(tc_mode, online_coins['blitz'])['draw'] if winner == 'draw' else 0)
                b_coins = online_coins.get(tc_mode, online_coins['blitz'])['win'] if winner == 'black' else (online_coins.get(tc_mode, online_coins['blitz'])['draw'] if winner == 'draw' else 0)

                if w_coins > 0 and white_user and not white_user.startswith('Bot:'):
                    conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (w_coins, white_user))
                if b_coins > 0 and black_user and not black_user.startswith('Bot:'):
                    conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (b_coins, black_user))

                earned_coins = w_coins if username == white_user else b_coins
                if rated:
                    update_pvp_rating_transaction(conn, white_user, black_user, winner)
        else:
            conn.execute("""
                UPDATE games SET fen = ?, history = ?, turn = ?, white_time = ?, black_time = ?,
                                 last_move_time = ?, draw_offered_by = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (board.fen(), json.dumps(history), next_turn, w_time, b_time, last_move_time, game_id))

    return jsonify({
        "success": True,
        "fen": board.fen(),
        "history": history,
        "turn": next_turn,
        "white_time": round(w_time, 1),
        "black_time": round(b_time, 1),
        "status": end_status if is_over else "active",
        "winner": winner,
        "termination_reason": reason,
        "bot_move": bot_moved,
        "game_over": is_over,
        "earned_coins": earned_coins,
        "missions_completed": missions_completed,
        "rating_change": fide_delta,
        "new_rating": new_user_rating,
        "classic_rating_change": classic_rating_change
    })

@game_bp.route('/game/<game_id>/resign', methods=['POST'])
def game_resign(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            return jsonify({"error": "Autenticação necessária para desistir com uma conta registrada."}), 401
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        status = row['status']
        game_type = row['game_type']
        rated = row['rated']
        history = json.loads(row['history'] or '[]')

        if status != 'active':
            return jsonify({"error": "Partida não está ativa."}), 400

        if username == white_user:
            winner = 'black'
            reason = f"Vitória das Pretas por desistência de {white_user}."
        elif username == black_user:
            winner = 'white'
            reason = f"Vitória das Brancas por desistência de {black_user}."
        else:
            return jsonify({"error": "Você não é participante desta partida."}), 403

        conn.execute("""
            UPDATE games SET status = 'resigned', winner = ?, termination_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (winner, reason, game_id))

        missions_completed = update_bot_missions_for_result(
            conn, game_type, white_user, black_user, row['bot_rating'] or 0,
            row['time_initial'], row['time_increment'], winner, 'resigned', history
        )
        rating_change, new_user_rating = update_initial_calibration_result(
            conn, game_type, white_user, black_user, row['bot_number'],
            row['bot_rating'] or 0, winner
        )
        classic_rating_change = update_classic_rating_result(
            conn, game_type, row['classic_mode'], row['classic_bot_number'],
            row['bot_rating'] or 0, white_user, black_user, winner
        )

        if game_type == 'pvp' and rated:
            update_pvp_rating_transaction(conn, white_user, black_user, winner)

    return jsonify({"success": True, "status": "resigned", "winner": winner, "reason": reason, "missions_completed": missions_completed, "rating_change": rating_change, "new_rating": new_user_rating, "classic_rating_change": classic_rating_change})

@game_bp.route('/game/<game_id>/draw_offer', methods=['POST'])
def game_draw_offer(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()
    action = data.get('action', 'offer')

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            return jsonify({"error": "Autenticação necessária para alterar uma partida de conta registrada."}), 401
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        status = row['status']
        game_type = row['game_type']
        draw_offered_by = row['draw_offered_by']
        fen = row['fen']
        rated = row['rated']
        history = json.loads(row['history'] or '[]')

        if status != 'active':
            return jsonify({"error": "Partida não está ativa."}), 400
        if username not in (white_user, black_user):
            return jsonify({"error": "Você não é participante desta partida."}), 403

        opponent = black_user if username == white_user else white_user

        if game_type == 'bot':
            board = chess.Board(fen)
            bot_accepts = board.is_insufficient_material() or len(board.piece_map()) <= 6 or random.random() < 0.25
            if bot_accepts:
                reason = "Empate aceito pelo Bot por mútuo acordo."
                conn.execute("UPDATE games SET status = 'draw_agreed', winner = 'draw', termination_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (reason, game_id))
                rating_change, new_rating = update_initial_calibration_result(
                    conn, game_type, white_user, black_user, row['bot_number'],
                    row['bot_rating'] or 0, 'draw'
                )
                classic_rating_change = update_classic_rating_result(
                    conn, game_type, row['classic_mode'], row['classic_bot_number'],
                    row['bot_rating'] or 0, white_user, black_user, 'draw'
                )
                missions_completed = update_bot_missions_for_result(
                    conn, game_type, white_user, black_user, row['bot_rating'] or 0,
                    row['time_initial'], row['time_increment'], 'draw', 'draw_agreed', history
                )
                return jsonify({"success": True, "accepted": True, "status": "draw_agreed", "reason": reason, "rating_change": rating_change, "new_rating": new_rating, "classic_rating_change": classic_rating_change, "missions_completed": missions_completed})
            else:
                return jsonify({"success": True, "accepted": False, "message": "O Bot recusou a proposta de empate."})

        if action == 'offer':
            if draw_offered_by == opponent:
                reason = "Empate aceito por mútuo acordo."
                conn.execute("UPDATE games SET status = 'draw_agreed', winner = 'draw', termination_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (reason, game_id))
                if rated:
                    update_pvp_rating_transaction(conn, white_user, black_user, 'draw')
                return jsonify({"success": True, "status": "draw_agreed", "reason": reason})
            else:
                conn.execute("UPDATE games SET draw_offered_by = ? WHERE id = ?", (username, game_id))
                return jsonify({"success": True, "message": "Proposta de empate enviada ao adversário."})

        elif action == 'accept':
            if draw_offered_by == opponent:
                reason = "Empate aceito por mútuo acordo."
                conn.execute("UPDATE games SET status = 'draw_agreed', winner = 'draw', termination_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (reason, game_id))
                if rated:
                    update_pvp_rating_transaction(conn, white_user, black_user, 'draw')
                return jsonify({"success": True, "status": "draw_agreed", "reason": reason})
            else:
                return jsonify({"error": "Nenhuma proposta de empate pendente do adversário."}), 400

        elif action == 'decline':
            conn.execute("UPDATE games SET draw_offered_by = NULL WHERE id = ?", (game_id,))
            return jsonify({"success": True, "message": "Proposta de empate recusada."})

    return jsonify({"error": "Ação inválida."}), 400

@game_bp.route('/game/<game_id>/takeback', methods=['POST'])
def game_takeback(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            return jsonify({"error": "Autenticação necessária para alterar uma partida de conta registrada."}), 401
        row = conn.execute("SELECT white_user, black_user, status, game_type, history FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        status = row['status']
        game_type = row['game_type']
        history_raw = row['history']

        if status != 'active':
            return jsonify({"error": "Partida não está ativa."}), 400
        if game_type != 'bot':
            return jsonify({"error": "Voltar lances não é permitido em partidas online entre humanos."}), 403

        history = json.loads(history_raw or '[]')
        if len(history) < 2:
            return jsonify({"error": "Não há lances suficientes para voltar."}), 400

        history.pop()
        history.pop()

        new_board = chess.Board()
        for item in history:
            new_board.push(chess.Move.from_uci(item['uci']))

        next_turn = 'w' if new_board.turn == chess.WHITE else 'b'
        conn.execute("""
            UPDATE games SET fen = ?, history = ?, turn = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_board.fen(), json.dumps(history), next_turn, game_id))

    return jsonify({
        "success": True,
        "fen": new_board.fen(),
        "history": history,
        "turn": next_turn
    })

@game_bp.route('/game/<game_id>/claim_timeout', methods=['POST'])
def game_claim_timeout(game_id):
    data = request.get_json(silent=True) or {}
    supplied_username = str(data.get('username', '')).strip()
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        username = resolve_game_actor(conn, supplied_username)
        if not username:
            return jsonify({"error": "Autenticação necessária para reivindicar timeout."}), 401
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        if username not in (white_user, black_user):
            return jsonify({"error": "Somente os participantes podem reivindicar timeout."}), 403
        status = row['status']
        time_initial = row['time_initial']
        white_time = row['white_time']
        black_time = row['black_time']
        last_move_time = row['last_move_time']
        fen = row['fen']
        turn = row['turn']
        rated = row['rated']
        game_type = row['game_type']
        time_increment = row['time_increment']
        bot_rating = row['bot_rating'] or 0
        bot_number = row['bot_number']
        classic_mode = row['classic_mode']
        classic_bot_number = row['classic_bot_number']
        history = json.loads(row['history'] or '[]')

        if status != 'active' or time_initial <= 0 or not last_move_time:
            return jsonify({"error": "Partida sem relógio ativo."}), 400

        now = time.time()
        elapsed = max(0.0, now - float(last_move_time))
        board = chess.Board(fen)

        if turn == 'w':
            current_w_time = white_time - elapsed
            if current_w_time <= 0:
                winner, reason = check_timeout_fide(board, 'white')
                conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, white_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, reason, game_id))
                if rated and game_type == 'pvp':
                    update_pvp_rating_transaction(conn, white_user, black_user, winner)
                rating_change, new_user_rating = update_initial_calibration_result(
                    conn, game_type, white_user, black_user, bot_number,
                    bot_rating, winner
                )
                missions_completed = update_bot_missions_for_result(
                    conn, game_type, white_user, black_user, bot_rating,
                    time_initial, time_increment, winner, 'timeout', history
                )
                classic_rating_change = update_classic_rating_result(
                    conn, game_type, classic_mode, classic_bot_number,
                    bot_rating, white_user, black_user, winner
                )
                return jsonify({"success": True, "status": "timeout", "winner": winner, "reason": reason, "missions_completed": missions_completed, "rating_change": rating_change, "new_rating": new_user_rating, "classic_rating_change": classic_rating_change})
        else:
            current_b_time = black_time - elapsed
            if current_b_time <= 0:
                winner, reason = check_timeout_fide(board, 'black')
                conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, reason, game_id))
                if rated and game_type == 'pvp':
                    update_pvp_rating_transaction(conn, white_user, black_user, winner)
                rating_change, new_user_rating = update_initial_calibration_result(
                    conn, game_type, white_user, black_user, bot_number,
                    bot_rating, winner
                )
                missions_completed = update_bot_missions_for_result(
                    conn, game_type, white_user, black_user, bot_rating,
                    time_initial, time_increment, winner, 'timeout', history
                )
                classic_rating_change = update_classic_rating_result(
                    conn, game_type, classic_mode, classic_bot_number,
                    bot_rating, white_user, black_user, winner
                )
                return jsonify({"success": True, "status": "timeout", "winner": winner, "reason": reason, "missions_completed": missions_completed, "rating_change": rating_change, "new_rating": new_user_rating, "classic_rating_change": classic_rating_change})

    return jsonify({"success": False, "message": "O tempo ainda não expirou."})

@game_bp.route('/bot_move', methods=['POST'])
@rate_limit(max_requests=30, window_seconds=60)
def bot_move():
    data = request.get_json(silent=True) or {}
    fen = data.get('fen')
    bot_rating = parse_request_integer(data, 'rating', 500)
    if bot_rating is None or not 500 <= bot_rating <= 3000:
        return jsonify({"error": "Rating do bot deve estar entre 500 e 3000 Elo."}), 400
    if not validate_fen(fen):
        return jsonify({"error": "Posição FEN inválida."}), 400
    try:
        b = chess.Board(fen)
        if b.is_game_over():
            return jsonify({"error": "A partida já terminou."}), 400
        move_uci, think_ms = get_bot_move_fide(b, bot_rating)
        return jsonify({"move": move_uci, "think_time_ms": think_ms})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
