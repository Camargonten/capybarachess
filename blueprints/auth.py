import hmac
import os
import secrets
import sqlite3
from flask import Blueprint, jsonify, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from core.db import IntegrityError, get_db
from core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ADMIN_USERS
from core.security import login_throttle, rate_limit, validate_username

auth_bp = Blueprint('auth', __name__)
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(16))

def is_user_admin(username: str) -> bool:
    if not username:
        return False
    if username.lower() in ADMIN_USERS:
        return True
    with get_db() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE username = ?", (username,)).fetchone()
        return bool(row and row['is_admin'] == 1)

def build_auth_payload(username: str):
    with get_db() as conn:
        user = conn.execute("""
                 SELECT id, username, display_name, display_name_changes, bio, coins, rating, inventory, calibrated, avatar, google_sub, google_email, country_code, country_locked, is_admin,
                     active_frame, active_banner, active_piece_skin, calibration_games, colorblind_mode, skip_animation, bgm_choice
            FROM users WHERE username = ?
        """, (username,)).fetchone()
        if not user:
            return None
        
        achievements_rows = conn.execute(
            "SELECT seal FROM achievements WHERE username = ? ORDER BY earned_at", (username,)
        ).fetchall()
        achievements = [r['seal'] for r in achievements_rows]
        
        cal_games = user['calibration_games'] or 0
        return {
            "success": True,
            "user_id": user['id'],
            "username": username,
            "display_name": user['display_name'] or username,
            "display_name_changes": user['display_name_changes'] or 0,
            "bio": user['bio'] or '',
            "coins": user['coins'],
            "rating": user['rating'],
            "inventory": user['inventory'] or '[]',
            "achievements": achievements,
            "calibration_allowed": cal_games < 2,
            "calibration_games": cal_games,
            "calibrated": bool(user['calibrated']),
            "avatar": user['avatar'] or '',
            "google_linked": bool(user['google_sub']),
            "google_email": user['google_email'] or '',
            "country_code": user['country_code'] or '',
            "country_locked": bool(user['country_locked']),
            "is_admin": bool(user['is_admin'] or is_user_admin(username)),
            "active_frame": user['active_frame'] or '',
            "active_banner": user['active_banner'] or '',
            "active_piece_skin": user['active_piece_skin'] or '',
            "colorblind_mode": bool(user['colorblind_mode']),
            "skip_animation": bool(user['skip_animation']),
            "bgm_choice": user['bgm_choice'] or 1
        }

@auth_bp.route('/register', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60)
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    
    if not validate_username(username):
        return jsonify({"error": "O nome de usuário deve ter de 3 a 25 caracteres (letras, números, espaço, _ - ou .)."}), 400
    if (
        len(password) < 7
        or len(password) > 128
        or not any(not character.isalnum() and not character.isspace() for character in password)
    ):
        return jsonify({
            "error": "A senha deve ter de 7 a 128 caracteres e incluir pelo menos um símbolo."
        }), 400
        
    pwd_hash = generate_password_hash(password)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            initial_coins = 100
            initial_is_admin = 0

            cursor.execute(
                "INSERT INTO users (username, password, coins, rating, is_admin, country_code, country_locked) VALUES (?, ?, ?, 1200, ?, '', 0)",
                (username, pwd_hash, initial_coins, initial_is_admin)
            )
            user_id = cursor.lastrowid
        session.clear()
        session['username'] = username
        return jsonify({
            "success": True,
            "user_id": user_id,
            "coins": initial_coins,
            "rating": 1200,
            "username": username,
            "is_admin": bool(initial_is_admin)
        })
    except IntegrityError:
        return jsonify({"error": "Nome de usuário já está em uso."}), 409

@auth_bp.route('/login', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    
    if not username or not password:
        return jsonify({"error": "Nick ou senha incorretos."}), 401

    client_ip = request.remote_addr or 'unknown'
    if login_throttle.is_blocked(client_ip, username):
        return jsonify({"error": "Muitas tentativas de login. Aguarde alguns minutos e tente de novo."}), 429

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, password, coins, rating, inventory, calibrated, avatar FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            # Hash de mentira: o tempo de resposta não revela se o nick existe.
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            login_throttle.record_failure(client_ip, username)
            return jsonify({"error": "Nick ou senha incorretos."}), 401

        stored_password = user['password']
        valid_password = check_password_hash(stored_password, password) if stored_password.startswith(('pbkdf2:', 'scrypt:')) else hmac.compare_digest(stored_password.encode(), password.encode())
        if not valid_password:
            login_throttle.record_failure(client_ip, username)
            return jsonify({"error": "Nick ou senha incorretos."}), 401
        login_throttle.reset(client_ip, username)

        if not stored_password.startswith(('pbkdf2:', 'scrypt:')):
            conn.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(password), user['id']))
        conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))

    session.clear()
    session['username'] = username
    payload = build_auth_payload(username)
    return jsonify(payload)

@auth_bp.route('/auth/me', methods=['GET'])
def auth_me():
    username = session.get('username')
    payload = build_auth_payload(username) if username else None
    if not payload:
        session.clear()
        return jsonify({"authenticated": False}), 401
    return jsonify(payload)

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@auth_bp.route('/auth/config', methods=['GET'])
def auth_config():
    configured = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    return jsonify({"google_enabled": configured})
