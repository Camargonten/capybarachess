import json
import random
import re
import secrets
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash
from core.db import get_db
from core.constants import (
    SHOP_ITEMS, PROMO_CODES, BOT_SEALS, CLASSIC_MODES, MISSION_DEFINITIONS,
    MISSION_ITEMS, MISSION_ITEM_BY_MISSION,
    CLASSIC_LEGENDS, CLASSIC_OFFICIAL_BOTS, CLASSIC_BONUS_BOTS, CLASSIC_FIRST_NAMES,
    CLASSIC_LAST_NAMES, CLASSIC_STYLES
)
from core.bot_identity import classic_bot_country, classic_bot_identity
from core.security import rate_limit, parse_bounded_integer
from core.engine import elo_expected, apply_fide_rating_update
from blueprints.auth import is_user_admin

user_bp = Blueprint('user', __name__)

LANGUAGE_COLUMN_WHITELIST = {
    'pt': 'name_pt', 'en': 'name_en', 'es': 'name_es', 'fr': 'name_fr',
}
def user_is_calibrated(conn, username: str) -> bool:
    row = conn.execute("SELECT calibrated FROM users WHERE username = ?", (username,)).fetchone()
    return bool(row and row['calibrated'])

def classic_bot_rating(bot_number: int) -> int:
    if len(CLASSIC_LEGENDS) < bot_number <= len(CLASSIC_LEGENDS) + len(CLASSIC_OFFICIAL_BOTS):
        return CLASSIC_OFFICIAL_BOTS[bot_number - len(CLASSIC_LEGENDS) - 1][1]
    if 700 < bot_number <= 700 + len(CLASSIC_BONUS_BOTS):
        return CLASSIC_BONUS_BOTS[bot_number - 701][1]
    return round(300 + (700 - bot_number) * 2550 / 699)

def ensure_classic_profile(username: str):
    with get_db() as conn:
        cursor = conn.cursor()
        user = cursor.execute("SELECT rating, calibrated FROM users WHERE username = ?", (username,)).fetchone()
        seed_rating = user['rating'] if user and user['calibrated'] else 1200
        cursor.executemany(
            "INSERT OR IGNORE INTO classic_profiles (username, mode, rating) VALUES (?, ?, ?)",
            [(username, mode, seed_rating) for mode in CLASSIC_MODES]
        )
        if user and user['calibrated']:
            cursor.execute(
                "UPDATE classic_profiles SET rating = ? WHERE username = ? AND games_played = 0",
                (user['rating'], username)
            )
        cursor.executemany(
            "INSERT OR IGNORE INTO missions (username, mission_id) VALUES (?, ?)",
            [(username, m[0]) for m in MISSION_DEFINITIONS]
        )
        row = cursor.execute("SELECT COUNT(*) as cnt FROM classic_bots WHERE username = ? AND mode = 'blitz'", (username,)).fetchone()
        if row and row['cnt'] >= 700:
            for mode in CLASSIC_MODES:
                if mode == 'blitz':
                    continue
                cursor.execute("""
                    INSERT OR IGNORE INTO classic_bots (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
                    SELECT username, bot_number, ?, name_pt, name_en, name_es, name_fr, rating, style
                    FROM classic_bots WHERE username = ? AND mode = 'blitz'
                """, (mode, username))
            bonus_rows = [
                (username, 700 + index, mode, name, name, name, name, rating, CLASSIC_STYLES[(index - 1) % len(CLASSIC_STYLES)])
                for index, (name, rating) in enumerate(CLASSIC_BONUS_BOTS, 1)
                for mode in CLASSIC_MODES
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO classic_bots
                    (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, bonus_rows)
            return

        bot_rows = []
        for bot_number in range(1, 701):
            if bot_number <= len(CLASSIC_LEGENDS):
                names = [CLASSIC_LEGENDS[bot_number - 1]] * 4
            elif bot_number <= len(CLASSIC_LEGENDS) + len(CLASSIC_OFFICIAL_BOTS):
                names = [CLASSIC_OFFICIAL_BOTS[bot_number - len(CLASSIC_LEGENDS) - 1][0]] * 4
            else:
                names = [classic_bot_identity(bot_number)[0]] * 4
            bot_rows.append((username, bot_number, 'blitz', *names, classic_bot_rating(bot_number), CLASSIC_STYLES[(bot_number - 1) % len(CLASSIC_STYLES)]))

        cursor.executemany("""
            INSERT OR REPLACE INTO classic_bots (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, bot_rows)

        for mode in CLASSIC_MODES:
            if mode == 'blitz':
                continue
            cursor.execute("""
                INSERT INTO classic_bots (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
                SELECT username, bot_number, ?, name_pt, name_en, name_es, name_fr, rating, style
                FROM classic_bots WHERE username = ? AND mode = 'blitz'
            """, (mode, username))
        bonus_rows = [
            (username, 700 + index, mode, name, name, name, name, rating, CLASSIC_STYLES[(index - 1) % len(CLASSIC_STYLES)])
            for index, (name, rating) in enumerate(CLASSIC_BONUS_BOTS, 1)
            for mode in CLASSIC_MODES
        ]
        cursor.executemany("""
            INSERT OR IGNORE INTO classic_bots
                (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, bonus_rows)

def simulate_classic_bots(username: str, mode: str = 'blitz'):
    with get_db() as conn:
        cursor = conn.cursor()
        profile = cursor.execute(
            "SELECT CAST((julianday('now') - julianday(last_simulation)) * 1440 AS INTEGER) as elapsed FROM classic_profiles WHERE username = ? AND mode = ?",
            (username, mode)
        ).fetchone()
        if not profile:
            return
        elapsed_minutes = profile['elapsed'] or 0
        rounds = min(10, elapsed_minutes // 10)
        if not rounds:
            return

        bot_rows = cursor.execute("SELECT bot_number, rating FROM classic_bots WHERE username = ? AND mode = ?", (username, mode)).fetchall()
        ratings = {r['bot_number']: r['rating'] for r in bot_rows}

        for _ in range(rounds * 25):
            first_num = random.choice(list(ratings))
            first_r = ratings[first_num]
            opponents = [num for num, r in ratings.items() if abs(r - first_r) <= 250 and num != first_num]
            if not opponents:
                continue
            second_num = random.choice(opponents)
            second_r = ratings[second_num]

            expected_1 = elo_expected(first_r, second_r)
            score_1 = 1.0 if random.random() < expected_1 else 0.0

            k1 = 8 if first_r >= 2500 else (14 if first_r >= 1800 else 28)
            k2 = 8 if second_r >= 2500 else (14 if second_r >= 1800 else 28)

            ratings[first_num] = max(200, round(first_r + k1 * (score_1 - expected_1)))
            ratings[second_num] = max(200, round(second_r + k2 * ((1.0 - score_1) - (1.0 - expected_1))))

        cursor.executemany(
            "UPDATE classic_bots SET rating = ? WHERE username = ? AND mode = ? AND bot_number = ?",
            [(r, username, mode, num) for num, r in ratings.items()]
        )
        cursor.execute("UPDATE classic_profiles SET last_simulation = CURRENT_TIMESTAMP WHERE username = ? AND mode = ?", (username, mode))

@user_bp.route('/profile/avatar', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def update_avatar():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    avatar = str(data.get('avatar', ''))
    valid_image = bool(re.match(r'^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$', avatar))

    if not username or not valid_image or len(avatar) > 1_500_000:
        return jsonify({"error": "Imagem inválida ou muito grande (máximo 1MB em base64)."}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET avatar = ? WHERE username = ?", (avatar, username))
        if cursor.rowcount != 1:
            return jsonify({"error": "Conta não encontrada."}), 404

    return jsonify({"success": True, "avatar": avatar})

@user_bp.route('/profile/name', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def update_profile_name():
    username = session.get('username')
    data = request.get_json(silent=True) or {}
    display_name = str(data.get('display_name', '')).strip()
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    if not display_name or len(display_name) > 30 or any(ord(char) < 32 for char in display_name):
        return jsonify({"error": "O nome de perfil deve ter entre 1 e 30 caracteres."}), 400

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT display_name, display_name_changes, coins FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        current_name = user['display_name'] or username
        changes = user['display_name_changes'] or 0
        if display_name == current_name:
            return jsonify({
                "success": True,
                "display_name": current_name,
                "display_name_changes": changes,
                "coins": user['coins'],
                "charged": 0
            })

        charged = 0 if changes == 0 else 100
        if user['coins'] < charged:
            return jsonify({"error": "São necessárias 100 moedas para alterar o nome novamente."}), 400

        conn.execute(
            "UPDATE users SET display_name = ?, display_name_changes = ?, coins = coins - ? WHERE username = ?",
            (display_name, changes + 1, charged, username)
        )
        remaining_coins = user['coins'] - charged
    return jsonify({
        "success": True,
        "display_name": display_name,
        "display_name_changes": changes + 1,
        "coins": remaining_coins,
        "charged": charged
    })

@user_bp.route('/profile/bio', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def update_profile_bio():
    username = session.get('username')
    data = request.get_json(silent=True) or {}
    bio = str(data.get('bio', '')).strip()
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    if len(bio) > 30 or any(ord(char) < 32 for char in bio):
        return jsonify({"error": "A bio deve ter no máximo 30 caracteres."}), 400

    with get_db() as conn:
        cursor = conn.execute("UPDATE users SET bio = ? WHERE username = ?", (bio, username))
        if cursor.rowcount != 1:
            return jsonify({"error": "Conta não encontrada."}), 404
    return jsonify({"success": True, "bio": bio})

@user_bp.route('/profile/settings', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=60)
def profile_settings():
    data = request.get_json(silent=True) or {}
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401

    colorblind = 1 if data.get('colorblind_mode') else 0
    skip_anim = 1 if data.get('skip_animation') else 0
    bgm = parse_bounded_integer(data.get('bgm_choice', 1), 1, 4)
    if bgm is None:
        return jsonify({"error": "Opção de música inválida."}), 400

    with get_db() as conn:
        conn.execute("""
            UPDATE users SET colorblind_mode = ?, skip_animation = ?, bgm_choice = ?
            WHERE username = ?
        """, (colorblind, skip_anim, bgm, username))

    return jsonify({
        "success": True,
        "colorblind_mode": bool(colorblind),
        "skip_animation": bool(skip_anim),
        "bgm_choice": bgm
    })

@user_bp.route('/profile/country', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60)
def set_profile_country():
    username = session.get('username')
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    return jsonify({
        "error": "A bandeira é definida automaticamente pela região da conta Google e não pode ser alterada."
    }), 403

@user_bp.route('/profile/equip', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=60)
def profile_equip():
    data = request.get_json(silent=True) or {}
    username = session.get('username')
    item_id = str(data.get('item', '')).strip()

    if not username:
        return jsonify({"error": "Usuário inválido."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT inventory, active_frame, active_banner, active_piece_skin FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        inventory_items = set(json.loads(user['inventory'] or '[]'))
        current_frame = user['active_frame'] or ''
        current_banner = user['active_banner'] or ''
        current_piece_skin = user['active_piece_skin'] or ''

        if not item_id:
            conn.execute("UPDATE users SET active_frame = '', active_banner = '', active_piece_skin = '' WHERE username = ?", (username,))
            return jsonify({"success": True, "active_frame": '', "active_banner": '', "active_piece_skin": ''})

        if item_id not in inventory_items:
            return jsonify({"error": "Você ainda não possui este item."}), 400

        if item_id.startswith('frame_'):
            current_frame = item_id
            conn.execute("UPDATE users SET active_frame = ? WHERE username = ?", (current_frame, username))
        elif item_id.startswith('banner_'):
            current_banner = item_id
            conn.execute("UPDATE users SET active_banner = ? WHERE username = ?", (current_banner, username))
        elif item_id.startswith('skin_'):
            current_piece_skin = item_id
            conn.execute("UPDATE users SET active_piece_skin = ? WHERE username = ?", (current_piece_skin, username))

    return jsonify({"success": True, "active_frame": current_frame, "active_banner": current_banner, "active_piece_skin": current_piece_skin})

@user_bp.route('/account/reset', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=300)
def reset_account():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username or data.get('confirmation') != 'RESET_ACCOUNT':
        return jsonify({"error": "Confirmação de reinício inválida."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        conn.execute("UPDATE users SET coins = 100, rating = 1200, promo_count = 0, display_name_changes = 0, inventory = '[]', calibrated = 0, calibration_games = 0, avatar = '', bio = '', active_frame = '', active_banner = '', active_piece_skin = '' WHERE username = ?", (username,))
        conn.execute("DELETE FROM achievements WHERE username = ?", (username,))
        conn.execute("UPDATE users SET calib1_results = '[]', calib_base_rating = 0, calib2_games = 0 WHERE username = ?", (username,))
        conn.execute("UPDATE classic_profiles SET games_played = 0, calib_base_rating = 0, calib2_games = 0 WHERE username = ?", (username,))
        conn.execute("DELETE FROM game_rating_results WHERE username = ?", (username,))
        conn.execute("DELETE FROM promo_redemptions WHERE username = ? AND code != 'adm'", (username,))
        conn.execute("DELETE FROM friend_requests WHERE sender = ? OR recipient = ?", (username, username))
        conn.execute("DELETE FROM messages WHERE sender = ? OR recipient = ?", (username, username))

    return jsonify({"success": True, "message": "Conta reiniciada com sucesso."})

@user_bp.route('/account/delete', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60)
def delete_account():
    """Exclui a conta e os dados pessoais (exigência da Play Store e direito da LGPD, art. 18)."""
    data = request.get_json(silent=True) or {}
    username = session.get('username')
    if not username or data.get('confirmation') != username:
        return jsonify({"error": "Digite o seu nome de usuário para confirmar a exclusão."}), 400

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT password, google_sub FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            session.clear()
            return jsonify({"error": "Conta não encontrada."}), 404
        # Contas só com senha precisam provar a senha; contas vinculadas ao Google já provaram a identidade no login.
        if not user['google_sub']:
            password = str(data.get('password', ''))
            stored = user['password'] or ''
            valid = check_password_hash(stored, password) if stored.startswith(('pbkdf2:', 'scrypt:')) else False
            if not valid:
                return jsonify({"error": "Senha incorreta."}), 403

        conn.execute(
            "UPDATE clubs SET member_count = member_count - 1 "
            "WHERE leader != ? AND id IN (SELECT club_id FROM club_members WHERE username = ?)", (username, username))
        for table, column in (
            ('achievements', 'username'), ('user_presence', 'username'), ('ranked_queue', 'username'),
            ('club_members', 'username'), ('game_aborts', 'username'), ('classic_profiles', 'username'),
            ('classic_bots', 'username'), ('game_rating_results', 'username'), ('missions', 'username'),
            ('club_messages', 'sender'), ('club_challenges', 'creator'),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (username,))
        for table, first, second in (
            ('friend_requests', 'sender', 'recipient'), ('direct_challenges', 'sender', 'recipient'),
            ('messages', 'sender', 'recipient'), ('gift_requests', 'sender', 'recipient'),
            ('rematch_requests', 'requester', 'opponent'),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {first} = ? OR {second} = ?", (username, username))
        led_clubs = [row['id'] for row in conn.execute("SELECT id FROM clubs WHERE leader = ?", (username,)).fetchall()]
        for club_id in led_clubs:
            for table in ('club_members', 'club_messages', 'club_challenges'):
                conn.execute(f"DELETE FROM {table} WHERE club_id = ?", (club_id,))
            conn.execute("DELETE FROM clubs WHERE id = ?", (club_id,))
        conn.execute(
            "UPDATE games SET status = 'aborted', winner = 'aborted', termination_reason = 'Conta excluída.' "
            "WHERE status IN ('active', 'waiting') AND (white_user = ? OR black_user = ? OR creator_user = ?)",
            (username, username, username))
        for column in ('white_user', 'black_user', 'creator_user'):
            conn.execute(f"UPDATE games SET {column} = 'Conta excluída' WHERE {column} = ?", (username,))
        # O código promocional de uso único continua "usado", agora sem identificar ninguém.
        conn.execute("UPDATE promo_redemptions SET username = ? WHERE username = ?", (f"excluida-{secrets.token_hex(6)}", username))
        conn.execute("DELETE FROM users WHERE username = ?", (username,))

    session.clear()
    return jsonify({"success": True})

@user_bp.route('/calibrate', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def calibrate():
    return jsonify({"error": "O rating é calibrado automaticamente ao concluir duas partidas contra os bots oficiais iniciais."}), 410

@user_bp.route('/match_result', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=60)
def match_result():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    seal = str(data.get('seal', '')).strip()

    if not username or data.get('won') is not True or seal not in BOT_SEALS:
        return jsonify({"error": "Resultado inválido."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO achievements (username, seal) VALUES (?, ?)", (username, seal))
        earned_now = cursor.rowcount == 1
        achievements_rows = conn.execute("SELECT seal FROM achievements WHERE username = ? ORDER BY earned_at", (username,)).fetchall()
        achievements = [r['seal'] for r in achievements_rows]

    return jsonify({
        "success": True,
        "earned_now": earned_now,
        "seal": seal,
        "bot": BOT_SEALS[seal],
        "achievements": achievements
    })

@user_bp.route('/purchase', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def purchase():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    item = str(data.get('item', '')).strip()
    price = SHOP_ITEMS.get(item)

    if item in MISSION_ITEMS:
        return jsonify({"error": "Este item é exclusivo de missão: complete a missão para desbloquear."}), 403
    if price is None:
        return jsonify({"error": "Item inválido."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT coins, inventory FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        coins = user['coins']
        inventory = set(json.loads(user['inventory'] or '[]'))

        if item in inventory:
            return jsonify({"error": "Você já possui este item."}), 400
        if coins < price:
            return jsonify({"error": "Camarcoins insuficientes."}), 400

        inventory.add(item)
        remaining_coins = coins - price
        conn.execute(
            "UPDATE users SET coins = ?, inventory = ? WHERE username = ?",
            (remaining_coins, json.dumps(sorted(inventory)), username)
        )

    return jsonify({"success": True, "coins": remaining_coins, "inventory": sorted(inventory)})

@user_bp.route('/redeem_promo', methods=['POST'])
@rate_limit(max_requests=6, window_seconds=60)
def redeem_promo():
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', '')).strip().lower()
    username = session.get('username') or str(data.get('username', '')).strip()

    if not username or not code:
        return jsonify({"error": "Dados inválidos."}), 400

    promo_config = PROMO_CODES.get(code)
    if not promo_config:
        return jsonify({"error": "Código promocional inválido ou expirado."}), 400

    if promo_config.get('admin_only') and not is_user_admin(username):
        return jsonify({"error": f"O código '{code}' é restrito ao Administrador do sistema."}), 403

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT id, coins, inventory FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        used = conn.execute("SELECT 1 FROM promo_redemptions WHERE code = ? AND username = ?", (code, username)).fetchone()
        if used:
            return jsonify({"error": "Este código já foi usado nesta conta."}), 400

        max_global = promo_config.get('max_global_uses')
        if max_global is not None:
            g_count = conn.execute("SELECT COUNT(DISTINCT username) as cnt FROM promo_redemptions WHERE code = ?", (code,)).fetchone()
            if g_count and g_count['cnt'] >= max_global:
                return jsonify({"error": f"Limite global de {max_global} utilizadores atingido para este código."}), 400

        conn.execute("INSERT INTO promo_redemptions (code, username) VALUES (?, ?)", (code, username))
        response_data = {"success": True}

        if promo_config['type'] == 'unlock_all':
            owned_items = set(json.loads(user['inventory'] or '[]')) | set(SHOP_ITEMS.keys()) | set(MISSION_ITEMS.keys())
            conn.execute("UPDATE users SET inventory = ? WHERE username = ?", (json.dumps(sorted(owned_items)), username))
            response_data['inventory'] = sorted(owned_items)
            response_data['message'] = "Todos os itens da loja foram liberados com sucesso!"
        elif promo_config['type'] == 'coins':
            amount = promo_config['amount']
            new_coins = user['coins'] + amount
            conn.execute("UPDATE users SET coins = ?, promo_count = promo_count + 1 WHERE username = ?", (new_coins, username))
            response_data['coins'] = new_coins
            response_data['message'] = f"+{amount} Camarcoins adicionadas com sucesso à sua conta!"

    return jsonify(response_data)

def _mission_item_info(mission_id):
    """Item cosmético exclusivo ligado a uma missão (ou None)."""
    item = MISSION_ITEM_BY_MISSION.get(mission_id)
    if not item:
        return None
    name, _mission, rarity = MISSION_ITEMS[item]
    return {"id": item, "name": name, "rarity": rarity}


def _grant_mission_items(conn, username, mission_ids):
    """Entrega ao inventário os itens exclusivos das missões resgatadas. Devolve (novos, inventário)."""
    row = conn.execute("SELECT inventory FROM users WHERE username = ?", (username,)).fetchone()
    inventory = set(json.loads((row['inventory'] if row else '[]') or '[]'))
    granted = []
    for mission_id in mission_ids:
        info = _mission_item_info(mission_id)
        if info and info['id'] not in inventory:
            inventory.add(info['id'])
            granted.append(info)
    if granted:
        conn.execute("UPDATE users SET inventory = ? WHERE username = ?", (json.dumps(sorted(inventory)), username))
    return granted, sorted(inventory)


@user_bp.route('/missions', methods=['GET'])
def list_missions():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({"missions": []})

    ensure_classic_profile(username)
    with get_db() as conn:
        rows = conn.execute("SELECT mission_id, progress, completed, claimed FROM missions WHERE username = ?", (username,)).fetchall()
        row_dict = {r['mission_id']: dict(r) for r in rows}

    return jsonify({"missions": [{
        "id": mission[0], "title": mission[1], "target": mission[2],
        "reward": mission[3], "difficulty": mission[4],
        "progress": row_dict.get(mission[0], {}).get('progress', 0),
        "completed": row_dict.get(mission[0], {}).get('completed', 0),
        "claimed": row_dict.get(mission[0], {}).get('claimed', 0),
        "item": _mission_item_info(mission[0])
    } for mission in MISSION_DEFINITIONS]})

@user_bp.route('/missions/claim', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def claim_mission():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    mission_id = data.get('mission_id')

    if not username or not isinstance(mission_id, int):
        return jsonify({"error": "Missão inválida."}), 400

    mission = next((m for m in MISSION_DEFINITIONS if m[0] == mission_id), None)
    if not mission:
        return jsonify({"error": "Missão não encontrada."}), 404

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT progress, completed, claimed FROM missions WHERE username = ? AND mission_id = ?",
            (username, mission_id)
        ).fetchone()
        if not row or row['completed'] == 0 or row['claimed'] == 1:
            return jsonify({"error": "Missão ainda não disponível para resgate."}), 400

        u_row = conn.execute("SELECT coins FROM users WHERE username = ?", (username,)).fetchone()
        if not u_row:
            return jsonify({"error": "Conta não encontrada."}), 404
        coins = u_row['coins']
        cursor = conn.execute(
            "UPDATE missions SET claimed = 1 WHERE username = ? AND mission_id = ? AND completed = 1 AND claimed = 0",
            (username, mission_id)
        )
        if cursor.rowcount != 1:
            return jsonify({"error": "Esta recompensa já foi resgatada."}), 409
        conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (mission[3], username))
        granted, inventory_now = _grant_mission_items(conn, username, [mission_id])

    return jsonify({"success": True, "coins": coins + mission[3], "reward": mission[3], "items": granted, "inventory": inventory_now})

@user_bp.route('/missions/claim_all', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def claim_all_missions():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        return jsonify({"error": "Conta inválida."}), 400

    rewards = {mission[0]: mission[3] for mission in MISSION_DEFINITIONS}

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        u_row = conn.execute("SELECT coins FROM users WHERE username = ?", (username,)).fetchone()
        if not u_row:
            return jsonify({"error": "Conta não encontrada."}), 404

        rows = conn.execute(
            "SELECT mission_id FROM missions WHERE username = ? AND completed = 1 AND claimed = 0",
            (username,)
        ).fetchall()

        total = 0
        count = 0
        claimed_ids = []
        for row in rows:
            mission_id = row['mission_id']
            if mission_id not in rewards:
                continue
            cursor = conn.execute(
                "UPDATE missions SET claimed = 1 WHERE username = ? AND mission_id = ? AND completed = 1 AND claimed = 0",
                (username, mission_id)
            )
            if cursor.rowcount == 1:
                total += rewards[mission_id]
                count += 1
                claimed_ids.append(mission_id)

        if count == 0:
            return jsonify({"error": "Nenhuma recompensa disponível para coletar."}), 400

        conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (total, username))
        coins = u_row['coins'] + total
        granted_all, inventory_now = _grant_mission_items(conn, username, claimed_ids)

    return jsonify({"success": True, "coins": coins, "reward": total, "count": count, "items": granted_all, "inventory": inventory_now})

@user_bp.route('/classic/ranking', methods=['GET'])
def classic_ranking():
    username = request.args.get('username', '').strip()
    language = request.args.get('language', 'pt')
    mode = request.args.get('mode', 'blitz')
    if mode not in CLASSIC_MODES:
        mode = 'blitz'
    if not username:
        return jsonify({"error": "Ranking inválido."}), 400

    with get_db() as conn:
        if not user_is_calibrated(conn, username):
            return jsonify({"error": "Conclua duas partidas de calibração antes de acessar o modo clássico."}), 403

    ensure_classic_profile(username)
    simulate_classic_bots(username, mode)

    with get_db() as conn:
        p_row = conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
        player_rating = p_row['rating'] if p_row else 1200
        col_name = LANGUAGE_COLUMN_WHITELIST.get(language, "name_pt")
        bot_rows = conn.execute(
            f"SELECT bot_number, {col_name} as bname, rating, style FROM classic_bots WHERE username = ? AND mode = ? ORDER BY rating DESC, bot_number ASC",
            (username, mode)
        ).fetchall()
        bots = [{"rank": idx, "number": r['bot_number'], "name": r['bname'], "rating": r['rating'], "style": r['style'], "country": classic_bot_country(r['bot_number'])} for idx, r in enumerate(bot_rows, 1)]
        player_rank = 1 + sum(b["rating"] > player_rating for b in bots)

    return jsonify({"mode": mode, "player": {"name": username, "rating": player_rating, "rank": player_rank}, "bots": bots})

@user_bp.route('/classic/result', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def classic_result():
    return jsonify({"error": "O resultado clássico é processado automaticamente ao encerrar a partida."}), 410

@user_bp.route('/classic/matchmake', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def classic_matchmake():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    language = request.args.get('language') or data.get('language', 'pt')
    mode = data.get('mode', 'blitz')
    if mode not in CLASSIC_MODES:
        mode = 'blitz'
    if not username:
        return jsonify({"error": "Emparelhamento inválido."}), 400

    with get_db() as conn:
        if not user_is_calibrated(conn, username):
            return jsonify({"error": "Conclua duas partidas de calibração antes de buscar bots clássicos."}), 403

    min_offset = parse_bounded_integer(data.get('min_offset', -100), -300, 200)
    max_offset = parse_bounded_integer(data.get('max_offset', 200), -300, 100000)
    if min_offset is None or max_offset is None or max_offset < min_offset:
        return jsonify({"error": "Faixa de rating inválida."}), 400

    ensure_classic_profile(username)
    with get_db() as conn:
        p_row = conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
        player_rating = p_row['rating'] if p_row else 1200
        col_name = LANGUAGE_COLUMN_WHITELIST.get(language, "name_pt")
        minimum_rating = max(0, player_rating + min_offset)
        maximum_rating = (
            2147483647 if max_offset >= 9999 else max(0, player_rating + max_offset)
        )

        query = f"""
            SELECT bot_number, {col_name} as bname, rating, style
            FROM classic_bots
            WHERE username = ? AND mode = ? AND rating BETWEEN ? AND ?
        """
        params = (username, mode, minimum_rating, maximum_rating)
        if max_offset >= 9999:
            query += " ORDER BY ABS(rating - ?), bot_number LIMIT 1"
            params += (player_rating,)
        candidates = conn.execute(query, params).fetchall()

    if not candidates:
        return jsonify({"error": "Nenhum adversário disponível nesta faixa."}), 404

    bot = candidates[0] if max_offset >= 9999 else random.choice(candidates)
    return jsonify({"success": True, "mode": mode, "player_rating": player_rating, "bot": {"number": bot['bot_number'], "name": bot['bname'], "rating": bot['rating'], "style": bot['style'], "country": classic_bot_country(bot['bot_number'])}})

@user_bp.route('/classic/rematch', methods=['POST'])
@rate_limit(max_requests=15, window_seconds=60)
def classic_rematch():
    accepted = random.random() < 0.6
    return jsonify({"accepted": accepted})
