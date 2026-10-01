import json
import random
import re
from flask import Blueprint, jsonify, request, session
from core.db import get_db
from core.constants import (
    SHOP_ITEMS, PROMO_CODES, BOT_SEALS, CLASSIC_MODES, MISSION_DEFINITIONS,
    CLASSIC_LEGENDS, CLASSIC_OFFICIAL_BOTS, CLASSIC_FIRST_NAMES, CLASSIC_LAST_NAMES, CLASSIC_STYLES
)
from core.security import rate_limit
from core.engine import elo_expected, apply_fide_rating_update
from blueprints.auth import is_user_admin

user_bp = Blueprint('user', __name__)

def classic_bot_rating(bot_number: int) -> int:
    if len(CLASSIC_LEGENDS) < bot_number <= len(CLASSIC_LEGENDS) + len(CLASSIC_OFFICIAL_BOTS):
        return CLASSIC_OFFICIAL_BOTS[bot_number - len(CLASSIC_LEGENDS) - 1][1]
    return round(300 + (700 - bot_number) * 2550 / 699)

def ensure_classic_profile(username: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT OR IGNORE INTO classic_profiles (username, mode) VALUES (?, ?)",
            [(username, mode) for mode in CLASSIC_MODES]
        )
        cursor.executemany(
            "INSERT OR IGNORE INTO missions (username, mission_id) VALUES (?, ?)",
            [(username, m[0]) for m in MISSION_DEFINITIONS]
        )
        row = cursor.execute("SELECT COUNT(*) as cnt FROM classic_bots WHERE username = ? AND mode = 'blitz'", (username,)).fetchone()
        if row and row['cnt'] == 700:
            for mode in CLASSIC_MODES:
                m_cnt = cursor.execute("SELECT COUNT(*) as cnt FROM classic_bots WHERE username = ? AND mode = ?", (username, mode)).fetchone()
                if m_cnt and m_cnt['cnt'] == 700:
                    continue
                cursor.execute("DELETE FROM classic_bots WHERE username = ? AND mode = ?", (username, mode))
                cursor.execute("""
                    INSERT INTO classic_bots (username, bot_number, mode, name_pt, name_en, name_es, name_fr, rating, style)
                    SELECT username, bot_number, ?, name_pt, name_en, name_es, name_fr, rating, style
                    FROM classic_bots WHERE username = ? AND mode = 'blitz'
                """, (mode, username))
            return

        bot_rows = []
        for bot_number in range(1, 701):
            if bot_number <= len(CLASSIC_LEGENDS):
                names = [CLASSIC_LEGENDS[bot_number - 1]] * 4
            elif bot_number <= len(CLASSIC_LEGENDS) + len(CLASSIC_OFFICIAL_BOTS):
                names = [CLASSIC_OFFICIAL_BOTS[bot_number - len(CLASSIC_LEGENDS) - 1][0]] * 4
            else:
                names = []
                index = bot_number - len(CLASSIC_LEGENDS) - len(CLASSIC_OFFICIAL_BOTS) - 1
                for language in ("pt", "en", "es", "fr"):
                    first_name = CLASSIC_FIRST_NAMES[language][index % len(CLASSIC_FIRST_NAMES[language])]
                    last_name = CLASSIC_LAST_NAMES[language][(index // len(CLASSIC_FIRST_NAMES[language])) % len(CLASSIC_LAST_NAMES[language])]
                    names.append(f"{first_name} {last_name}")
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

@user_bp.route('/profile/settings', methods=['POST'])
def profile_settings():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username:
        return jsonify({"error": "Não autenticado."}), 401

    colorblind = 1 if data.get('colorblind_mode') else 0
    skip_anim = 1 if data.get('skip_animation') else 0
    bgm = int(data.get('bgm_choice', 1))

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

@user_bp.route('/profile/equip', methods=['POST'])
def profile_equip():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    item_id = str(data.get('item', '')).strip()

    if not username:
        return jsonify({"error": "Usuário inválido."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT inventory, active_frame, active_banner FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        inventory_items = set(json.loads(user['inventory'] or '[]'))
        current_frame = user['active_frame'] or ''
        current_banner = user['active_banner'] or ''

        if not item_id:
            conn.execute("UPDATE users SET active_frame = '', active_banner = '' WHERE username = ?", (username,))
            return jsonify({"success": True, "active_frame": '', "active_banner": ''})

        if item_id not in inventory_items:
            return jsonify({"error": "Você ainda não possui este item."}), 400

        if item_id.startswith('frame_'):
            current_frame = item_id
            conn.execute("UPDATE users SET active_frame = ? WHERE username = ?", (current_frame, username))
        elif item_id.startswith('banner_'):
            current_banner = item_id
            conn.execute("UPDATE users SET active_banner = ? WHERE username = ?", (current_banner, username))

    return jsonify({"success": True, "active_frame": current_frame, "active_banner": current_banner})

@user_bp.route('/account/reset', methods=['POST'])
def reset_account():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    if not username or data.get('confirmation') != 'RESET_ACCOUNT':
        return jsonify({"error": "Confirmação de reinício inválida."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        conn.execute("UPDATE users SET coins = 100, rating = 1200, promo_count = 0, inventory = '[]', calibrated = 0, calibration_games = 0, avatar = '', active_frame = '', active_banner = '' WHERE username = ?", (username,))
        conn.execute("DELETE FROM achievements WHERE username = ?", (username,))
        conn.execute("DELETE FROM promo_redemptions WHERE username = ?", (username,))
        conn.execute("DELETE FROM friend_requests WHERE sender = ? OR recipient = ?", (username, username))
        conn.execute("DELETE FROM messages WHERE sender = ? OR recipient = ?", (username, username))

    return jsonify({"success": True, "message": "Conta reiniciada com sucesso."})

@user_bp.route('/calibrate', methods=['POST'])
def calibrate():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    bot_rating = int(data.get('bot_rating', 1000))
    result = str(data.get('result', ''))

    if not username or result not in {'win', 'draw', 'loss'}:
        return jsonify({"error": "Calibração inválida."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT rating, calibrated, calibration_games FROM users WHERE username = ?", (username,)) .fetchone()
        if not user:
            return jsonify({"error": "Conta não encontrada."}), 404

        cal_games = user['calibration_games'] or 0
        if cal_games >= 2:
            return jsonify({"error": "Sua calibração inicial já foi concluída (2 partidas)."}), 400

        score = {'win': 1.0, 'draw': 0.5, 'loss': 0.0}[result]
        fide_delta, new_rating = apply_fide_rating_update(conn.cursor(), username, bot_rating, score)
        u_now = conn.execute("SELECT calibrated, calibration_games FROM users WHERE username = ?", (username,)).fetchone()

    return jsonify({
        "success": True,
        "rating": new_rating,
        "change": fide_delta,
        "calibration_games": u_now['calibration_games'],
        "calibration_allowed": u_now['calibration_games'] < 2,
        "calibrated": bool(u_now['calibrated'])
    })

@user_bp.route('/match_result', methods=['POST'])
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
def purchase():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    item = str(data.get('item', '')).strip()
    price = SHOP_ITEMS.get(item)

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
    code = str(data.get('code', '')).strip()
    username = session.get('username') or str(data.get('username', '')).strip()

    if not username or not code:
        return jsonify({"error": "Dados inválidos."}), 400

    promo_config = PROMO_CODES.get(code)
    if not promo_config:
        return jsonify({"error": "Código promocional inválido ou expirado."}), 400

    if promo_config.get('admin_only') and not is_user_admin(username):
        return jsonify({"error": f"O código '{code}' é restrito ao Administrador do sistema."}), 403

    with get_db() as conn:
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
            owned_items = set(json.loads(user['inventory'] or '[]')) | set(SHOP_ITEMS.keys())
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

@user_bp.route('/missions', methods=['GET'])
def list_missions():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({"missions": []})

    ensure_classic_profile(username)
    with get_db() as conn:
        rows = conn.execute("SELECT mission_id, progress, completed, claimed FROM missions WHERE username = ?", (username,)).fetchall()
        row_dict = {r['mission_id']: r for r in rows}

    return jsonify({"missions": [{
        "id": m[0], "title": m[1], "target": m[2], "reward": m[3],
        "progress": row_dict.get(m[0], {}).get('progress', 0) if row_dict.get(m[0]) else 0,
        "completed": row_dict.get(m[0], {}).get('completed', 0) if row_dict.get(m[0]) else 0,
        "claimed": row_dict.get(m[0], {}).get('claimed', 0) if row_dict.get(m[0]) else 0
    } for m in MISSION_DEFINITIONS]})

@user_bp.route('/missions/claim', methods=['POST'])
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
        row = conn.execute(
            "SELECT progress, completed, claimed FROM missions WHERE username = ? AND mission_id = ?",
            (username, mission_id)
        ).fetchone()
        if not row or row['completed'] == 0 or row['claimed'] == 1:
            return jsonify({"error": "Missão ainda não disponível para resgate."}), 400

        u_row = conn.execute("SELECT coins FROM users WHERE username = ?", (username,)).fetchone()
        coins = u_row['coins']
        conn.execute("UPDATE missions SET claimed = 1 WHERE username = ? AND mission_id = ?", (username, mission_id))
        conn.execute("UPDATE users SET coins = ? WHERE username = ?", (coins + mission[3], username))

    return jsonify({"success": True, "coins": coins + mission[3], "reward": mission[3]})

@user_bp.route('/classic/ranking', methods=['GET'])
def classic_ranking():
    username = request.args.get('username', '').strip()
    language = request.args.get('language', 'pt')
    mode = request.args.get('mode', 'blitz')
    if mode not in CLASSIC_MODES:
        mode = 'blitz'
    if not username:
        return jsonify({"error": "Ranking inválido."}), 400

    ensure_classic_profile(username)
    simulate_classic_bots(username, mode)

    with get_db() as conn:
        p_row = conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
        player_rating = p_row['rating'] if p_row else 1200
        col_name = f"name_{language}" if language in ('pt', 'en', 'es', 'fr') else "name_pt"
        bot_rows = conn.execute(
            f"SELECT bot_number, {col_name} as bname, rating, style FROM classic_bots WHERE username = ? AND mode = ? ORDER BY rating DESC, bot_number ASC",
            (username, mode)
        ).fetchall()
        bots = [{"rank": idx, "number": r['bot_number'], "name": r['bname'], "rating": r['rating'], "style": r['style']} for idx, r in enumerate(bot_rows, 1)]
        player_rank = 1 + sum(b["rating"] > player_rating for b in bots)

    return jsonify({"mode": mode, "player": {"name": username, "rating": player_rating, "rank": player_rank}, "bots": bots})

@user_bp.route('/classic/result', methods=['POST'])
def classic_result():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    bot_number = data.get('bot_number')
    result = data.get('result')
    mode = data.get('mode', 'blitz')
    if mode not in CLASSIC_MODES:
        mode = 'blitz'
    if not username or not isinstance(bot_number, int) or not 1 <= bot_number <= 700 or result not in {'win', 'draw', 'loss'}:
        return jsonify({"error": "Resultado clássico inválido."}), 400

    ensure_classic_profile(username)
    with get_db() as conn:
        p_row = conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
        player_rating = p_row['rating'] if p_row else 1200
        bot_row = conn.execute("SELECT rating FROM classic_bots WHERE username = ? AND mode = ? AND bot_number = ?", (username, mode, bot_number)).fetchone()
        if not bot_row:
            return jsonify({"error": "Bot não encontrado."}), 404

        bot_rating = bot_row['rating']
        score = {'win': 1.0, 'draw': 0.5, 'loss': 0.0}[result]

        diff = max(-400, min(400, bot_rating - player_rating))
        expected = 1.0 / (1.0 + 10.0 ** (diff / 400.0))
        new_mode_rating = max(100, round(player_rating + 20 * (score - expected)))
        conn.execute("UPDATE classic_profiles SET rating = ? WHERE username = ? AND mode = ?", (new_mode_rating, username, mode))

        fide_delta, _ = apply_fide_rating_update(conn.cursor(), username, bot_rating, score)

        coins_map = {'bullet': {'win': 5, 'draw': 2, 'loss': 0}, 'blitz': {'win': 10, 'draw': 3, 'loss': 0}, 'rapid': {'win': 20, 'draw': 5, 'loss': 0}}
        coins_won = coins_map.get(mode, coins_map['blitz']).get(result, 0)
        if coins_won > 0:
            conn.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (coins_won, username))

        u_row = conn.execute("SELECT coins, rating, calibration_games, calibrated FROM users WHERE username = ?", (username,)).fetchone()

    return jsonify({
        "success": True,
        "mode": mode,
        "rating": new_mode_rating,
        "global_rating": u_row['rating'],
        "coins": u_row['coins'],
        "earned_coins": coins_won,
        "change": fide_delta,
        "calibration_games": u_row['calibration_games'] or 0,
        "calibrated": bool(u_row['calibrated'])
    })

@user_bp.route('/classic/matchmake', methods=['POST'])
def classic_matchmake():
    data = request.get_json(silent=True) or {}
    username = session.get('username') or str(data.get('username', '')).strip()
    language = request.args.get('language') or data.get('language', 'pt')
    mode = data.get('mode', 'blitz')
    if mode not in CLASSIC_MODES:
        mode = 'blitz'
    if not username:
        return jsonify({"error": "Emparelhamento inválido."}), 400

    min_offset = int(data.get('min_offset', -100))
    max_offset = int(data.get('max_offset', 200))
    min_offset = max(-300, min(200, min_offset))
    max_offset = max(min_offset, min(400, max_offset))

    ensure_classic_profile(username)
    with get_db() as conn:
        p_row = conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (username, mode)).fetchone()
        player_rating = p_row['rating'] if p_row else 1200
        col_name = f"name_{language}" if language in ('pt', 'en', 'es', 'fr') else "name_pt"

        candidates = conn.execute(f"""
            SELECT bot_number, {col_name} as bname, rating, style
            FROM classic_bots
            WHERE username = ? AND mode = ? AND rating BETWEEN ? AND ?
        """, (username, mode, player_rating + min_offset, player_rating + max_offset)).fetchall()

        if not candidates:
            candidates = conn.execute(f"""
                SELECT bot_number, {col_name} as bname, rating, style
                FROM classic_bots
                WHERE username = ? AND mode = ?
                ORDER BY ABS(rating - ?) LIMIT 10
            """, (username, mode, player_rating)).fetchall()

    if not candidates:
        return jsonify({"error": "Nenhum adversário disponível nesta faixa."}), 404

    bot = random.choice(candidates)
    return jsonify({"success": True, "bot": {"number": bot['bot_number'], "name": bot['bname'], "rating": bot['rating'], "style": bot['style']}})

@user_bp.route('/classic/rematch', methods=['POST'])
def classic_rematch():
    accepted = random.random() < 0.6
    return jsonify({"accepted": accepted})
