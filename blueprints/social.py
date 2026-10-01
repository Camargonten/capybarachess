import random
import secrets
import time
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from core.db import get_db
from core.constants import CLAN_BADGES
from core.security import rate_limit

social_bp = Blueprint('social', __name__)

def are_friends(conn, first_user: str, second_user: str) -> bool:
    row = conn.execute("""
        SELECT 1 FROM friend_requests
        WHERE status = 'accepted' AND (
            (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
        )
    """, (first_user, second_user, second_user, first_user)).fetchone()
    return row is not None

@social_bp.route('/ranking/online', methods=['GET'])
def ranking_online():
    current_user = session.get('username') or request.args.get('username', '').strip()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT username, display_name, rating, coins, avatar, active_frame, active_banner, calibrated
            FROM users
            WHERE rating IS NOT NULL
            ORDER BY rating DESC, coins DESC, id ASC
            LIMIT 100
        """).fetchall()

        ranking = []
        user_rank = None
        for idx, row in enumerate(rows, 1):
            uname = row['username']
            seal_row = conn.execute(
                "SELECT seal FROM achievements WHERE username = ? ORDER BY earned_at DESC LIMIT 1", (uname,)
            ).fetchone()
            seal = seal_row['seal'] if seal_row else None

            ranking.append({
                "rank": idx,
                "username": uname,
                "display_name": row['display_name'] or uname,
                "rating": row['rating'],
                "coins": row['coins'],
                "avatar": row['avatar'] or '',
                "active_frame": row['active_frame'] or '',
                "active_banner": row['active_banner'] or '',
                "seal": seal,
                "calibrated": bool(row['calibrated'])
            })
            if current_user and uname == current_user:
                user_rank = idx

    return jsonify({
        "success": True,
        "ranking": ranking,
        "current_user_rank": user_rank,
        "total_players": len(ranking)
    })

@social_bp.route('/users/search', methods=['GET'])
def search_users():
    username = request.args.get('username', '').strip()
    query = request.args.get('query', '').strip()
    if not username or not query or len(query) < 2:
        return jsonify({"users": []})
    
    with get_db() as conn:
        rows = conn.execute("""
            SELECT username, rating FROM users
            WHERE username != ? AND username LIKE ?
            ORDER BY rating DESC, username ASC LIMIT 10
        """, (username, f"%{query}%")).fetchall()
        users = [{"username": r['username'], "rating": r['rating']} for r in rows]

    return jsonify({"users": users})

@social_bp.route('/players/<username>', methods=['GET'])
def player_profile(username):
    viewer = session.get('username') or request.args.get('viewer', '').strip()
    with get_db() as conn:
        player = conn.execute(
            "SELECT username, display_name, bio, rating, avatar FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not player:
            return jsonify({"error": "Jogador não encontrado."}), 404

        friend_status = 'none'
        if viewer == username:
            friend_status = 'self'
        elif viewer:
            if are_friends(conn, viewer, username):
                friend_status = 'friends'
            else:
                sent = conn.execute(
                    "SELECT 1 FROM friend_requests WHERE sender = ? AND recipient = ? AND status = 'pending'",
                    (viewer, username)
                ).fetchone()
                received = conn.execute(
                    "SELECT 1 FROM friend_requests WHERE sender = ? AND recipient = ? AND status = 'pending'",
                    (username, viewer)
                ).fetchone()
                friend_status = 'sent' if sent else 'received' if received else 'none'

        games = conn.execute("""
            SELECT white_user, black_user, status, winner, termination_reason, created_at
            FROM games
            WHERE (white_user = ? OR black_user = ?) AND status NOT IN ('waiting', 'active')
            ORDER BY created_at DESC LIMIT 25
        """, (username, username)).fetchall()

    history = []
    for game in games:
        player_side = 'white' if game['white_user'] == username else 'black'
        opponent = game['black_user'] if player_side == 'white' else game['white_user']
        if game['winner'] == 'draw':
            result = 'draw'
        else:
            result = 'win' if game['winner'] == player_side else 'loss'
        history.append({
            "opponent": opponent or 'Desconhecido',
            "result": result,
            "status": game['status'],
            "termination_reason": game['termination_reason'] or '',
            "played_at": game['created_at'] or ''
        })

    return jsonify({
        "success": True,
        "username": player['username'],
        "display_name": player['display_name'] or player['username'],
        "bio": player['bio'] or '',
        "rating": player['rating'],
        "avatar": player['avatar'] or '',
        "friend_status": friend_status,
        "history": history
    })

@social_bp.route('/notifications', methods=['GET'])
def notifications():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401

    with get_db() as conn:
        rows = conn.execute("""
            SELECT fr.sender, u.display_name, fr.created_at
            FROM friend_requests fr JOIN users u ON u.username = fr.sender
            WHERE fr.recipient = ? AND fr.status = 'pending'
            ORDER BY fr.created_at DESC
        """, (username,)).fetchall()

    return jsonify({"notifications": [
        {"sender": row['sender'], "display_name": row['display_name'] or row['sender'], "created_at": row['created_at']}
        for row in rows
    ]})

@social_bp.route('/friends/request', methods=['POST'])
def send_friend_request():
    data = request.get_json(silent=True) or {}
    sender = session.get('username')
    recipient = str(data.get('recipient', '')).strip()

    if not sender:
        return jsonify({"error": "Não autenticado."}), 401
    if not recipient or sender == recipient:
        return jsonify({"error": "Pedido de amizade inválido."}), 400

    with get_db() as conn:
        source = conn.execute("SELECT 1 FROM users WHERE username = ?", (sender,)).fetchone()
        target = conn.execute("SELECT 1 FROM users WHERE username = ?", (recipient,)).fetchone()
        if not source:
            return jsonify({"error": "Conta remetente não encontrada."}), 404
        if not target:
            return jsonify({"error": "Usuário não encontrado."}), 404
        if are_friends(conn, sender, recipient):
            return jsonify({"error": "Este usuário já é seu amigo."}), 400

        reverse = conn.execute(
            "SELECT 1 FROM friend_requests WHERE sender = ? AND recipient = ? AND status = 'pending'",
            (recipient, sender)
        ).fetchone()
        if reverse:
            conn.execute(
                "UPDATE friend_requests SET status = 'accepted' WHERE sender = ? AND recipient = ?",
                (recipient, sender)
            )
            return jsonify({"success": True, "accepted": True, "message": "Pedido recíproco aceito; vocês agora são amigos."})

        existing = conn.execute(
            "SELECT 1 FROM friend_requests WHERE sender = ? AND recipient = ? AND status = 'pending'",
            (sender, recipient)
        ).fetchone()
        if existing:
            return jsonify({"error": "Pedido já enviado."}), 400

        conn.execute(
            "INSERT INTO friend_requests (sender, recipient, status) VALUES (?, ?, 'pending')",
            (sender, recipient)
        )

    return jsonify({"success": True, "message": "Pedido de amizade enviado!"})

@social_bp.route('/friends/respond', methods=['POST'])
def respond_friend_request():
    data = request.get_json(silent=True) or {}
    recipient = session.get('username')
    sender = str(data.get('sender', '')).strip()
    accept = data.get('accept') is True
    if not recipient:
        return jsonify({"error": "Não autenticado."}), 401

    with get_db() as conn:
        req = conn.execute(
            "SELECT 1 FROM friend_requests WHERE sender = ? AND recipient = ? AND status = 'pending'",
            (sender, recipient)
        ).fetchone()
        if not req:
            return jsonify({"error": "Pedido não encontrado."}), 404

        if accept:
            conn.execute("UPDATE friend_requests SET status = 'accepted' WHERE sender = ? AND recipient = ?", (sender, recipient))
        else:
            conn.execute("DELETE FROM friend_requests WHERE sender = ? AND recipient = ?", (sender, recipient))

    return jsonify({"success": True})

@social_bp.route('/friends', methods=['GET'])
def list_friends():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    with get_db() as conn:
        f_rows = conn.execute("""
            SELECT CASE WHEN sender = ? THEN recipient ELSE sender END as friend
            FROM friend_requests
            WHERE status = 'accepted' AND (sender = ? OR recipient = ?)
        """, (username, username, username)).fetchall()
        friends = [r['friend'] for r in f_rows]

        inc_rows = conn.execute(
            "SELECT sender FROM friend_requests WHERE recipient = ? AND status = 'pending'", (username,)
        ).fetchall()
        incoming = [r['sender'] for r in inc_rows]

    return jsonify({"friends": friends, "incoming": incoming})

@social_bp.route('/messages', methods=['GET', 'POST'])
def messages():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        sender = session.get('username')
        recipient = str(data.get('recipient', '')).strip()
        content = str(data.get('content', '')).strip()[:500]

        if not sender:
            return jsonify({"error": "Não autenticado."}), 401
        if not recipient or not content:
            return jsonify({"error": "Mensagem inválida."}), 400

        with get_db() as conn:
            if not are_friends(conn, sender, recipient):
                return jsonify({"error": "Você só pode conversar com amigos confirmados."}), 403
            conn.execute(
                "INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?)",
                (sender, recipient, content)
            )
        return jsonify({"success": True})

    user = session.get('username')
    friend = request.args.get('friend', '').strip()
    if not user:
        return jsonify({"error": "Não autenticado."}), 401
    with get_db() as conn:
        if not are_friends(conn, user, friend):
            return jsonify({"error": "Você só pode conversar com amigos confirmados."}), 403
        rows = conn.execute("""
            SELECT sender, content, sent_at FROM messages
            WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
            ORDER BY id DESC LIMIT 50
        """, (user, friend, friend, user)).fetchall()
        messages_list = [{"sender": r['sender'], "content": r['content'], "sent_at": r['sent_at']} for r in reversed(rows)]

    return jsonify({"messages": messages_list})

# --- SISTEMA DE CLUBES ---
@social_bp.route('/clubs/list', methods=['GET'])
def clubs_list():
    username = session.get('username') or request.args.get('username', '').strip()
    query = request.args.get('q', '').strip().lower()

    with get_db() as conn:
        if query:
            rows = conn.execute("""
                SELECT id, name, description, leader, badge_id, privacy, min_rating, member_count, created_at
                FROM clubs WHERE LOWER(name) LIKE ? ORDER BY member_count DESC, id ASC LIMIT 50
            """, (f"%{query}%",)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, name, description, leader, badge_id, privacy, min_rating, member_count, created_at
                FROM clubs ORDER BY member_count DESC, id ASC LIMIT 50
            """).fetchall()

        user_club_ids = set()
        if username:
            u_clubs = conn.execute("SELECT club_id FROM club_members WHERE username = ?", (username,)).fetchall()
            user_club_ids = {r['club_id'] for r in u_clubs}

    clubs = []
    for r in rows:
        cid = r['id']
        badge_id = r['badge_id']
        badge_info = CLAN_BADGES.get(badge_id, CLAN_BADGES[1])
        clubs.append({
            "id": cid,
            "name": r['name'],
            "description": r['description'] or '',
            "leader": r['leader'],
            "badge_id": badge_id,
            "badge_name": badge_info["name"],
            "badge_icon": badge_info["icon"],
            "privacy": r['privacy'],
            "has_password": r['privacy'] == 'private_password',
            "min_rating": r['min_rating'],
            "member_count": r['member_count'],
            "is_member": cid in user_club_ids,
            "is_leader": r['leader'] == username
        })
    return jsonify({"success": True, "clubs": clubs})

@social_bp.route('/clubs/create', methods=['POST'])
def clubs_create():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        return jsonify({"error": "Faça login para criar um clube."}), 401

    name = str(data.get('name', '')).strip()
    description = str(data.get('description', '')).strip()[:200]
    badge_id = max(1, min(10, int(data.get('badge_id', 1))))
    privacy = data.get('privacy', 'public')
    if privacy not in ('public', 'private_password', 'private_approval'):
        privacy = 'public'
    password = str(data.get('password', '')).strip()
    min_rating = max(0, min(3000, int(data.get('min_rating', 0))))

    if not name or len(name) < 3 or len(name) > 30:
        return jsonify({"error": "Nome do clube deve ter entre 3 e 30 caracteres."}), 400

    password_hash = generate_password_hash(password) if privacy == 'private_password' and password else None

    with get_db() as conn:
        u_row = conn.execute("SELECT coins FROM users WHERE username = ?", (username,)).fetchone()
        if not u_row:
            return jsonify({"error": "Conta não encontrada."}), 404

        coins = u_row['coins']
        if coins < 600:
            return jsonify({"error": "Saldo insuficiente: criar um clube custa 600 Camacoins."}), 400

        try:
            conn.execute("UPDATE users SET coins = coins - 600 WHERE username = ?", (username,))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO clubs (name, description, leader, badge_id, privacy, password_hash, min_rating, member_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (name, description, username, badge_id, privacy, password_hash, min_rating))
            club_id = cursor.lastrowid
            conn.execute("""
                INSERT INTO club_members (club_id, username, role) VALUES (?, ?, 'leader')
            """, (club_id, username))
        except Exception:
            return jsonify({"error": "Já existe um clube com esse nome."}), 400

    return jsonify({"success": True, "club_id": club_id, "coins_remaining": coins - 600, "message": "Clube fundado com sucesso!"})

@social_bp.route('/clubs/join', methods=['POST'])
def clubs_join():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    club_id = data.get('club_id')
    password = str(data.get('password', '')).strip()

    if not username or not club_id:
        return jsonify({"error": "Dados inválidos."}), 400

    with get_db() as conn:
        u_row = conn.execute("SELECT rating FROM users WHERE username = ?", (username,)).fetchone()
        if not u_row:
            return jsonify({"error": "Usuário não encontrado."}), 404
        user_rating = u_row['rating']

        c_row = conn.execute("SELECT * FROM clubs WHERE id = ?", (club_id,)).fetchone()
        if not c_row:
            return jsonify({"error": "Clube não encontrado."}), 404

        min_r = c_row['min_rating']
        if user_rating < min_r:
            return jsonify({"error": f"Rating mínimo de {min_r} necessário (seu rating: {user_rating})."}), 403

        if c_row['privacy'] == 'private_password':
            pwd_hash = c_row['password_hash']
            if not pwd_hash or not check_password_hash(pwd_hash, password):
                return jsonify({"error": "Senha do clube incorreta."}), 403

        existing = conn.execute("SELECT 1 FROM club_members WHERE club_id = ? AND username = ?", (club_id, username)).fetchone()
        if existing:
            return jsonify({"error": "Você já é membro deste clube."}), 400

        conn.execute("INSERT INTO club_members (club_id, username, role) VALUES (?, ?, 'member')", (club_id, username))
        conn.execute("UPDATE clubs SET member_count = member_count + 1 WHERE id = ?", (club_id,))

    return jsonify({"success": True, "message": f"Você entrou no clube {c_row['name']}!"})

@social_bp.route('/clubs/<int:club_id>', methods=['GET'])
def clubs_detail(club_id):
    username = session.get('username') or request.args.get('username', '').strip()
    with get_db() as conn:
        c_row = conn.execute("SELECT * FROM clubs WHERE id = ?", (club_id,)).fetchone()
        if not c_row:
            return jsonify({"error": "Clube não encontrado."}), 404

        badge_id = c_row['badge_id']
        badge_info = CLAN_BADGES.get(badge_id, CLAN_BADGES[1])

        m_rows = conn.execute("""
            SELECT cm.username, cm.role, u.rating, u.avatar, u.active_frame
            FROM club_members cm
            JOIN users u ON cm.username = u.username
            WHERE cm.club_id = ?
            ORDER BY CASE WHEN cm.role = 'leader' THEN 0 ELSE 1 END, u.rating DESC
        """, (club_id,)).fetchall()
        member_list = [{
            "username": r['username'], "role": r['role'], "rating": r['rating'],
            "avatar": r['avatar'] or '', "active_frame": r['active_frame'] or ''
        } for r in m_rows]

        msg_rows = conn.execute("""
            SELECT sender, content, sent_at FROM club_messages
            WHERE club_id = ? ORDER BY id DESC LIMIT 40
        """, (club_id,)).fetchall()
        messages = [{"sender": r['sender'], "content": r['content'], "sent_at": r['sent_at']} for r in reversed(msg_rows)]

        ch_rows = conn.execute("""
            SELECT id, creator, time_control, mode, status, game_id, created_at
            FROM club_challenges
            WHERE club_id = ? AND status = 'open'
            ORDER BY id DESC LIMIT 10
        """, (club_id,)).fetchall()
        challenges = [{
            "id": r['id'], "creator": r['creator'], "time_control": r['time_control'],
            "mode": r['mode'], "status": r['status'], "game_id": r['game_id'], "created_at": r['created_at']
        } for r in ch_rows]

    is_member = any(m["username"] == username for m in member_list)
    return jsonify({
        "success": True,
        "club": {
            "id": c_row['id'], "name": c_row['name'], "description": c_row['description'], "leader": c_row['leader'],
            "badge_id": badge_id, "badge_name": badge_info["name"], "badge_icon": badge_info["icon"],
            "privacy": c_row['privacy'], "min_rating": c_row['min_rating'], "member_count": c_row['member_count'],
            "is_member": is_member, "is_leader": c_row['leader'] == username
        },
        "members": member_list,
        "messages": messages,
        "challenges": challenges
    })

@social_bp.route('/clubs/<int:club_id>/message', methods=['POST'])
def clubs_message(club_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    content = str(data.get('content', '')).strip()[:400]
    if not username or not content:
        return jsonify({"error": "Mensagem inválida."}), 400

    with get_db() as conn:
        member = conn.execute("SELECT 1 FROM club_members WHERE club_id = ? AND username = ?", (club_id, username)).fetchone()
        if not member:
            return jsonify({"error": "Você precisa ser membro do clube para enviar mensagens."}), 403
        conn.execute("INSERT INTO club_messages (club_id, sender, content) VALUES (?, ?, ?)", (club_id, username, content))

    return jsonify({"success": True})

@social_bp.route('/clubs/<int:club_id>/challenge', methods=['POST'])
def clubs_challenge(club_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    time_control = str(data.get('time_control', '180,2'))
    mode = str(data.get('mode', 'blitz'))

    if not username:
        return jsonify({"error": "Não autenticado."}), 401

    with get_db() as conn:
        member = conn.execute("SELECT 1 FROM club_members WHERE club_id = ? AND username = ?", (club_id, username)).fetchone()
        if not member:
            return jsonify({"error": "Você precisa ser membro do clube para criar desafios."}), 403

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO club_challenges (club_id, creator, time_control, mode, status)
            VALUES (?, ?, ?, ?, 'open')
        """, (club_id, username, time_control, mode))
        cid = cursor.lastrowid

    return jsonify({"success": True, "challenge_id": cid})

@social_bp.route('/clubs/<int:club_id>/accept_challenge', methods=['POST'])
def clubs_accept_challenge(club_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    challenge_id = data.get('challenge_id')

    if not username or not challenge_id:
        return jsonify({"error": "Dados inválidos."}), 400

    with get_db() as conn:
        member = conn.execute("SELECT 1 FROM club_members WHERE club_id = ? AND username = ?", (club_id, username)).fetchone()
        if not member:
            return jsonify({"error": "Você precisa ser membro do clube para aceitar desafios."}), 403

        ch = conn.execute(
            "SELECT creator, time_control, status, game_id FROM club_challenges WHERE id = ? AND club_id = ?",
            (challenge_id, club_id)
        ).fetchone()
        if not ch:
            return jsonify({"error": "Desafio não encontrado."}), 404

        creator = ch['creator']
        time_control = ch['time_control']
        status = ch['status']
        existing_gid = ch['game_id']

        if status == 'accepted' and existing_gid:
            return jsonify({"success": True, "game_id": existing_gid})
        if status != 'open':
            return jsonify({"error": "Desafio já aceito ou cancelado."}), 400
        if creator == username:
            return jsonify({"error": "Você não pode aceitar seu próprio desafio."}), 400

        t_parts = time_control.split(',')
        time_initial = int(t_parts[0])
        time_increment = int(t_parts[1]) if len(t_parts) > 1 else 0
        game_id = secrets.token_urlsafe(8)

        white_user = creator if random.random() < 0.5 else username
        black_user = username if white_user == creator else creator

        conn.execute('''
            INSERT INTO games (id, white_user, black_user, creator_user, creator_color, game_type,
                              time_initial, time_increment, white_time, black_time, last_move_time,
                              fen, history, turn, status, rated)
            VALUES (?, ?, ?, ?, 'random', 'pvp', ?, ?, ?, ?, ?, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', '[]', 'w', 'active', 1)
        ''', (game_id, white_user, black_user, creator, time_initial, time_increment,
              float(time_initial), float(time_initial), time.time()))

        conn.execute("UPDATE club_challenges SET status = 'accepted', game_id = ? WHERE id = ?", (game_id, challenge_id))

    return jsonify({"success": True, "game_id": game_id, "white_user": white_user, "black_user": black_user})

@social_bp.route('/clubs/<int:club_id>/leave', methods=['POST'])
def clubs_leave(club_id):
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        return jsonify({"error": "Não autenticado."}), 401

    with get_db() as conn:
        c_row = conn.execute("SELECT leader FROM clubs WHERE id = ?", (club_id,)).fetchone()
        if not c_row:
            return jsonify({"error": "Clube não encontrado."}), 404
        leader = c_row['leader']
        if leader == username:
            next_leader = conn.execute(
                "SELECT username FROM club_members WHERE club_id = ? AND username != ? LIMIT 1",
                (club_id, username)
            ).fetchone()
            if next_leader:
                conn.execute("UPDATE clubs SET leader = ? WHERE id = ?", (next_leader['username'], club_id))
                conn.execute("UPDATE club_members SET role = 'leader' WHERE club_id = ? AND username = ?", (club_id, next_leader['username']))
                conn.execute("DELETE FROM club_members WHERE club_id = ? AND username = ?", (club_id, username))
                conn.execute("UPDATE clubs SET member_count = member_count - 1 WHERE id = ?", (club_id,))
            else:
                conn.execute("DELETE FROM club_messages WHERE club_id = ?", (club_id,))
                conn.execute("DELETE FROM club_challenges WHERE club_id = ?", (club_id,))
                conn.execute("DELETE FROM club_members WHERE club_id = ?", (club_id,))
                conn.execute("DELETE FROM clubs WHERE id = ?", (club_id,))
        else:
            conn.execute("DELETE FROM club_members WHERE club_id = ? AND username = ?", (club_id, username))
            conn.execute("UPDATE clubs SET member_count = member_count - 1 WHERE id = ?", (club_id,))

    return jsonify({"success": True, "message": "Você saiu do clube."})
