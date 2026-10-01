import time
import json
import random
import secrets
import chess
from flask import Blueprint, jsonify, request, session
from core.db import get_db
from core.security import rate_limit, validate_uci_move, validate_fen
from core.engine import (
    check_fide_end_conditions, check_timeout_fide, get_bot_move_fide,
    categorize_time_control, apply_fide_rating_update
)
from core.constants import BOT_SEALS

game_bp = Blueprint('game', __name__)

def update_pvp_rating_transaction(conn, white_user: str, black_user: str, winner: str):
    if not white_user or not black_user or white_user.startswith('Bot:') or black_user.startswith('Bot:'):
        return
    row_w = conn.execute("SELECT rating FROM users WHERE username = ?", (white_user,)).fetchone()
    row_b = conn.execute("SELECT rating FROM users WHERE username = ?", (black_user,)).fetchone()
    if row_w and row_b:
        r_w, r_b = row_w['rating'], row_b['rating']
        score_w = 1.0 if winner == 'white' else (0.5 if winner == 'draw' else 0.0)
        score_b = 1.0 - score_w
        apply_fide_rating_update(conn.cursor(), white_user, r_b, score_w)
        apply_fide_rating_update(conn.cursor(), black_user, r_w, score_b)

def update_missions_progress(conn, username: str, mode: str, bot_rating: int, result: str):
    cursor = conn.cursor()
    if result == 'win':
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = CASE WHEN progress + 1 >= 1 THEN 1 ELSE completed END WHERE username = ? AND mission_id = 1", (username,))
    if mode == 'blitz' and result == 'win':
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = CASE WHEN progress + 1 >= 1 THEN 1 ELSE completed END WHERE username = ? AND mission_id = 2", (username,))
    if mode == 'bullet' and result == 'win':
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = CASE WHEN progress + 1 >= 1 THEN 1 ELSE completed END WHERE username = ? AND mission_id = 3", (username,))
    if mode == 'rapid' and result == 'win':
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = CASE WHEN progress + 1 >= 1 THEN 1 ELSE completed END WHERE username = ? AND mission_id = 4", (username,))
    if result == 'win':
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = CASE WHEN progress + 1 >= 3 THEN 1 ELSE completed END WHERE username = ? AND mission_id = 6", (username,))
    
    p_row = cursor.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
    p_rating = p_row['rating'] if p_row else 1200
    if result == 'win' and bot_rating >= p_rating + 200:
        cursor.execute("UPDATE missions SET progress = progress + 1, completed = 1 WHERE username = ? AND mission_id = 8", (username,))

@game_bp.route('/game/create', methods=['POST'])
def game_create():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        username = f"Convidado_{secrets.token_hex(2)}"

    mode = data.get('mode', 'bot')
    color_choice = data.get('color', 'random')
    time_control = data.get('time_control', '180,2')
    bot_number = int(data.get('bot_number', 1))
    bot_rating = int(data.get('bot_rating', 500))
    rated = 1 if data.get('rated', True) else 0

    try:
        t_parts = time_control.split(',')
        time_initial = int(t_parts[0])
        time_increment = int(t_parts[1]) if len(t_parts) > 1 else 0
    except Exception:
        time_initial = 180
        time_increment = 2

    game_id = secrets.token_urlsafe(8)

    with get_db() as conn:
        cursor = conn.cursor()
        if mode == 'bot':
            bot_names = {1: "Capivarão", 2: "Pirata", 3: "Marinheiro", 4: "Governador", 5: "Imperador",
                         6: "Pedro", 7: "Dill", 8: "Erick", 9: "Anonimus", 10: "Camargo", 11: "Fish", 12: "Rafachess"}
            bot_seals = {1: "C", 2: "P", 3: "M", 4: "G", 5: "I", 6: "NM", 7: "FM", 8: "IM", 9: "GM", 10: "SP", 11: "ST", 12: "RF"}
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
                bot_uci, _ = get_bot_move_fide(board, bot_rating, fast=False)
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
                                  fen, history, turn, status, bot_number, bot_rating, bot_seal, rated)
                VALUES (?, ?, ?, ?, ?, 'bot', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, white_user, black_user, username, color_choice, time_initial, time_increment,
                  float(time_initial), float(time_initial), last_move_time, board.fen(),
                  json.dumps(history), turn, status, bot_number, bot_rating, seal, rated))

            return jsonify({
                "success": True,
                "game_id": game_id,
                "game_type": "bot",
                "time_initial": time_initial,
                "bot_number": bot_number,
                "bot_rating": bot_rating,
                "bot_seal": seal,
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
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        username = f"Convidado_{secrets.token_hex(2)}"

    with get_db() as conn:
        row = conn.execute("SELECT id, white_user, black_user, creator_user, creator_color, status FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        creator_user = row['creator_user']
        creator_color = row['creator_color']
        status = row['status']

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

@game_bp.route('/game/<game_id>/state', methods=['GET'])
def game_state(game_id):
    current_user = session.get('username') or request.args.get('username', '').strip()
    with get_db() as conn:
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
        bot_seal = row['bot_seal']
        rated = row['rated']
        draw_offered_by = row['draw_offered_by']

        now = time.time()
        w_time = float(white_time)
        b_time = float(black_time)

        if status == 'active' and time_initial > 0 and last_move_time:
            elapsed = max(0.0, now - float(last_move_time))
            board = chess.Board(fen)
            if turn == 'w':
                w_time = max(0.0, white_time - elapsed)
                if w_time <= 0:
                    winner, termination_reason = check_timeout_fide(board, 'white')
                    status = 'timeout'
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, white_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, termination_reason, game_id))
                    if rated and game_type == 'pvp':
                        update_pvp_rating_transaction(conn, white_user, black_user, winner)
            elif turn == 'b':
                b_time = max(0.0, black_time - elapsed)
                if b_time <= 0:
                    winner, termination_reason = check_timeout_fide(board, 'black')
                    status = 'timeout'
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, termination_reason, game_id))
                    if rated and game_type == 'pvp':
                        update_pvp_rating_transaction(conn, white_user, black_user, winner)

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
        "bot_seal": bot_seal,
        "rated": bool(rated),
        "draw_offered_by": draw_offered_by
    })

@game_bp.route('/game/<game_id>/move', methods=['POST'])
@rate_limit(max_requests=60, window_seconds=60)
def game_move(game_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    move_uci = str(data.get('move', '')).strip().lower()

    if not username or not validate_uci_move(move_uci):
        return jsonify({"error": "Lance ou jogador inválido."}), 400

    with get_db() as conn:
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
        bot_seal = row['bot_seal']
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
                    return jsonify({"error": reason, "game_over": True, "status": "timeout", "winner": winner})
                w_time += time_increment
            else:
                b_time -= elapsed
                if b_time <= 0:
                    winner, reason = check_timeout_fide(board, 'black')
                    conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0 WHERE id = ?", (winner, reason, game_id))
                    return jsonify({"error": reason, "game_over": True, "status": "timeout", "winner": winner})
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
            bot_uci, think_ms = get_bot_move_fide(board, bot_rating, fast=(b_time < 10 or w_time < 10))
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

                offline_coins = {'bullet': {'win': 5, 'draw': 2, 'loss': 0}, 'blitz': {'win': 10, 'draw': 3, 'loss': 0}, 'rapid': {'win': 20, 'draw': 5, 'loss': 0}, 'custom': {'win': 10, 'draw': 2, 'loss': 0}}
                earned_coins = offline_coins.get(tc_mode, offline_coins['blitz']).get(res_key, 0)
                if earned_coins > 0:
                    conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (earned_coins, username))

                if player_won and bot_seal:
                    conn.execute("INSERT OR IGNORE INTO achievements (username, seal) VALUES (?, ?)", (username, bot_seal))

                score = 1.0 if player_won else (0.5 if is_draw else 0.0)
                fide_delta, new_user_rating = apply_fide_rating_update(conn.cursor(), username, bot_rating, score)
                update_missions_progress(conn, username, 'blitz' if tc_mode == 'custom' else tc_mode, bot_rating, res_key)

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
        "rating_change": fide_delta,
        "new_rating": new_user_rating
    })

@game_bp.route('/game/<game_id>/resign', methods=['POST'])
def game_resign(game_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        return jsonify({"error": "Usuário não autenticado."}), 401

    with get_db() as conn:
        row = conn.execute("SELECT white_user, black_user, status, game_type, rated FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        status = row['status']
        game_type = row['game_type']
        rated = row['rated']

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

        if game_type == 'pvp' and rated:
            update_pvp_rating_transaction(conn, white_user, black_user, winner)

    return jsonify({"success": True, "status": "resigned", "winner": winner, "reason": reason})

@game_bp.route('/game/<game_id>/draw_offer', methods=['POST'])
def game_draw_offer(game_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    action = data.get('action', 'offer')

    with get_db() as conn:
        row = conn.execute("SELECT white_user, black_user, status, game_type, draw_offered_by, fen, rated FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        status = row['status']
        game_type = row['game_type']
        draw_offered_by = row['draw_offered_by']
        fen = row['fen']
        rated = row['rated']

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
                return jsonify({"success": True, "accepted": True, "status": "draw_agreed", "reason": reason})
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
    username = session.get('username') or str(data.get('username', '')).strip()

    with get_db() as conn:
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
    with get_db() as conn:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return jsonify({"error": "Partida não encontrada."}), 404

        white_user = row['white_user']
        black_user = row['black_user']
        status = row['status']
        time_initial = row['time_initial']
        white_time = row['white_time']
        black_time = row['black_time']
        last_move_time = row['last_move_time']
        fen = row['fen']
        turn = row['turn']
        rated = row['rated']
        game_type = row['game_type']

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
                return jsonify({"success": True, "status": "timeout", "winner": winner, "reason": reason})
        else:
            current_b_time = black_time - elapsed
            if current_b_time <= 0:
                winner, reason = check_timeout_fide(board, 'black')
                conn.execute("UPDATE games SET status = 'timeout', winner = ?, termination_reason = ?, black_time = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (winner, reason, game_id))
                if rated and game_type == 'pvp':
                    update_pvp_rating_transaction(conn, white_user, black_user, winner)
                return jsonify({"success": True, "status": "timeout", "winner": winner, "reason": reason})

    return jsonify({"success": False, "message": "O tempo ainda não expirou."})

@game_bp.route('/bot_move', methods=['POST'])
@rate_limit(max_requests=30, window_seconds=60)
def bot_move():
    data = request.get_json(silent=True) or {}
    fen = data.get('fen')
    bot_rating = max(500, min(3000, int(data.get('rating', 500))))
    fast = bool(data.get('fast'))
    if not validate_fen(fen):
        return jsonify({"error": "Posição FEN inválida."}), 400
    try:
        b = chess.Board(fen)
        if b.is_game_over():
            return jsonify({"error": "A partida já terminou."}), 400
        move_uci, think_ms = get_bot_move_fide(b, bot_rating, fast=fast)
        return jsonify({"move": move_uci, "think_time_ms": think_ms})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
