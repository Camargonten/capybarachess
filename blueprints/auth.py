import os
import re
import secrets
from flask import Blueprint, jsonify, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from core.db import get_db
from core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ADMIN_USERS
from core.security import rate_limit, validate_username

auth_bp = Blueprint('auth', __name__)

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
                 SELECT id, username, display_name, bio, coins, rating, inventory, calibrated, avatar, google_email, is_admin,
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
            "bio": user['bio'] or '',
            "coins": user['coins'],
            "rating": user['rating'],
            "inventory": user['inventory'] or '[]',
            "achievements": achievements,
            "calibration_allowed": cal_games < 2,
            "calibration_games": cal_games,
            "calibrated": bool(user['calibrated']),
            "avatar": user['avatar'] or '',
            "google_linked": bool(user['google_email']),
            "google_email": user['google_email'] or '',
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
        return jsonify({"error": "Nome de usuário deve ter entre 3 e 25 caracteres alfanuméricos."}), 400
    if len(password) < 7:
        return jsonify({"error": "A senha deve ter pelo menos 7 caracteres."}), 400
        
    pwd_hash = generate_password_hash(password)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            user_count = cursor.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']
            is_first_user = (user_count == 0)
            initial_coins = 8000 if is_first_user else 100
            initial_is_admin = 1 if is_first_user else 0

            cursor.execute(
                "INSERT INTO users (username, password, coins, rating, is_admin) VALUES (?, ?, ?, 1200, ?)",
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
    except Exception:
        return jsonify({"error": "Nome de usuário já está em uso."}), 400

@auth_bp.route('/login', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    
    if not username or not password:
        return jsonify({"error": "Nick ou senha incorretos."}), 401

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, password, coins, rating, inventory, calibrated, avatar FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not user:
            return jsonify({"error": "Nick ou senha incorretos."}), 401

        stored_password = user['password']
        valid_password = check_password_hash(stored_password, password) if stored_password.startswith(('pbkdf2:', 'scrypt:')) else stored_password == password
        if not valid_password:
            return jsonify({"error": "Nick ou senha incorretos."}), 401

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
