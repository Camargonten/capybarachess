import os
import re
import secrets
import logging
from flask import Flask, jsonify, render_template, send_from_directory, session, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

from core.config import (
    BASE_DIR, APP_ENV, APP_DEBUG, PORT, SECRET_KEY, COOKIE_SECURE,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
)
from core.db import init_db, get_db, freeze_clocks_after_downtime, start_heartbeat_thread
from core.security import apply_security_headers, same_origin_guard
from core.constants import (
    BOT_SEALS, SHOP_ITEMS, PROMO_CODES, CLAN_BADGES, CLASSIC_MODES, MISSION_DEFINITIONS
)
from core.engine import (
    check_fide_end_conditions, check_timeout_fide, get_bot_move_fide,
    categorize_time_control, apply_fide_rating_update, elo_expected
)

from blueprints.auth import auth_bp
from blueprints.game import game_bp
from blueprints.social import social_bp
from blueprints.user import user_bp, ensure_classic_profile


logging.basicConfig(
    level=logging.INFO if not APP_DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("capybara_app")

def google_locale_country_code(profile: dict) -> str:
    locale = profile.get("locale", "")
    match = re.fullmatch(r"[A-Za-z]{2,3}[-_]([A-Za-z]{2})", locale) if isinstance(locale, str) else None
    country_code = match.group(1).upper() if match else ""
    return "" if country_code in {"XA", "XB", "ZZ"} else country_code

PUBLIC_ENDPOINTS = {
    "index", "health", "service_worker", "static", "asset_links", "privacy_policy", "terms_of_use", "delete_account_info",
    "auth.register", "auth.login", "auth.logout", "auth.auth_me", "auth.auth_config",
    "google_login", "google_callback",
    "social.ranking_online",
    "game.game_state", "game.game_create", "game.game_join", "game.game_move",
    "game.game_resign", "game.game_draw_offer", "game.game_takeback", "game.game_claim_timeout",
}

OWNER_FIELDS = {
    ("user.classic_ranking", "GET"): ("username",),
    ("user.classic_result", "POST"): ("username",),
    ("user.classic_matchmake", "POST"): ("username",),
    ("user.list_missions", "GET"): ("username",),
    ("user.claim_mission", "POST"): ("username",),
    ("user.claim_all_missions", "POST"): ("username",),
    ("user.update_avatar", "POST"): ("username",),
    ("user.reset_account", "POST"): ("username",),
    ("user.calibrate", "POST"): ("username",),
    ("user.match_result", "POST"): ("username",),
    ("user.purchase", "POST"): ("username",),
    ("user.redeem_promo", "POST"): ("username",),
    ("user.profile_equip", "POST"): ("username",),
    ("user.profile_settings", "POST"): ("username",),
    ("social.search_users", "GET"): ("username",),
    ("social.send_friend_request", "POST"): ("sender",),
    ("social.respond_friend_request", "POST"): ("recipient",),
    ("social.list_friends", "GET"): ("username",),
}

oauth = OAuth()

def create_app():
    app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates", "index.html"))
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config.update(
        SECRET_KEY=SECRET_KEY,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=COOKIE_SECURE,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024
    )

    oauth.init_app(app)
    google = oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID or None,
        client_secret=GOOGLE_CLIENT_SECRET or None,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    init_db()
    # Persistência: se o servidor ficou desligado, as partidas ativas voltam ao estado em que foram deixadas.
    downtime = freeze_clocks_after_downtime()
    if downtime:
        logging.getLogger("capybara").info("Servidor religado após %.0fs; relógios das partidas ativas congelados.", downtime)
    start_heartbeat_thread()

    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(user_bp)

    @app.before_request
    def enforce_account_security():
        if request.endpoint is None:
            return None
        origin_error = same_origin_guard()
        if origin_error:
            return origin_error
        if request.endpoint in PUBLIC_ENDPOINTS or (request.endpoint and request.endpoint.startswith("static")):
            return None

        username = session.get("username")
        if not username:
            return jsonify({"error": "Entre na sua conta para continuar."}), 401

        owner_tuple = OWNER_FIELDS.get((request.endpoint, request.method), ())
        for field in owner_tuple:
            requested_username = request.args.get(field) if request.method == "GET" else (request.get_json(silent=True) or {}).get(field)
            if requested_username and requested_username != username:
                return jsonify({"error": "Esta sessão não tem permissão para acessar outra conta."}), 403

        if request.endpoint == "social.messages":
            data = request.args if request.method == "GET" else (request.get_json(silent=True) or {})
            owner_field = "user" if request.method == "GET" else "sender"
            if data.get(owner_field) != username:
                return jsonify({"error": "Esta sessão não tem permissão para acessar outra conta."}), 403

        return None

    @app.after_request
    def set_security_headers(response):
        return apply_security_headers(response)

    @app.errorhandler(400)
    def bad_request_error(e):
        return jsonify({"error": "Requisição inválida."}), 400

    @app.errorhandler(401)
    def unauthorized_error(e):
        return jsonify({"error": "Acesso não autorizado."}), 401

    @app.errorhandler(403)
    def forbidden_error(e):
        return jsonify({"error": "Ação proibida para esta sessão."}), 403

    @app.errorhandler(404)
    def not_found_error(e):
        if request.path.startswith(("/api", "/game", "/clubs", "/auth", "/profile")):
            return jsonify({"error": "Recurso não encontrado."}), 404
        return redirect("/")

    @app.errorhandler(429)
    def rate_limit_error(e):
        return jsonify({"error": "Limite de requisições excedido. Aguarde alguns instantes."}), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        logger.error(f"Internal error on {request.path}: {e}", exc_info=True)
        return jsonify({"error": "Erro interno no servidor. Tente novamente mais tarde."}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        logger.error(f"Unhandled exception on {request.path}: {e}", exc_info=True)
        if APP_DEBUG:
            raise e
        return jsonify({"error": "Ocorreu um erro inesperado no processamento."}), 500

    @app.route("/")
    def index():
        from core.bot_identity import classic_bot_country
        from core.constants import CLASSIC_BONUS_BOTS
        bonus_bots = [
            {"number": 701 + index, "name": name, "rating": rating, "country": classic_bot_country(701 + index)}
            for index, (name, rating) in enumerate(CLASSIC_BONUS_BOTS)
        ]
        return render_template("index.html", bonus_bots=bonus_bots)

    @app.route("/health")
    def health():
        return jsonify({"online": True, "authenticated": bool(session.get("username")), "ranked_matches": True})

    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(os.path.join(BASE_DIR, "static"), "sw.js", mimetype="application/javascript")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/.well-known/assetlinks.json")
    def asset_links():
        """Digital Asset Links: liga o site ao app Android (Trusted Web Activity) publicado na Play Store.

        Defina ANDROID_PACKAGE_NAME e ANDROID_SHA256_CERT_FINGERPRINTS (separadas por vírgula; use a
        impressão digital do certificado de ASSINATURA DA PLAY, em Play Console > Integridade do app).
        """
        package = os.environ.get("ANDROID_PACKAGE_NAME", "").strip()
        fingerprints = [f.strip().upper() for f in os.environ.get("ANDROID_SHA256_CERT_FINGERPRINTS", "").split(",") if f.strip()]
        statements = []
        if package and fingerprints:
            statements.append({
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {"namespace": "android_app", "package_name": package, "sha256_cert_fingerprints": fingerprints},
            })
        response = jsonify(statements)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    @app.route("/privacidade")
    def privacy_policy():
        return render_template("legal/privacy.html")

    @app.route("/termos")
    def terms_of_use():
        return render_template("legal/terms.html")

    @app.route("/excluir-conta")
    def delete_account_info():
        return render_template("legal/delete_account.html")

    @app.route("/auth/google")
    def google_login():
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            return jsonify({"error": "Login Google ainda não configurado no servidor."}), 503
        return google.authorize_redirect(url_for("google_callback", _external=True))

    @app.route("/auth/google/callback")
    def google_callback():
        try:
            token = google.authorize_access_token()
            profile = token.get("userinfo") or google.get("userinfo").json()
        except Exception as err:
            logger.warning(f"Google OAuth validation failed: {err}")
            return jsonify({"error": "Não foi possível validar o login do Google."}), 400

        google_sub = profile.get("sub")
        email = profile.get("email", "").strip().lower()
        if not google_sub or not email or profile.get("email_verified") is not True:
            return jsonify({"error": "O Google não confirmou um e-mail válido para esta conta."}), 403
        country_code = google_locale_country_code(profile)

        with get_db() as conn:
            linked = conn.execute("SELECT username FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
            current_username = session.get("username")
            if current_username:
                current_account = conn.execute("SELECT google_sub FROM users WHERE username = ?", (current_username,)).fetchone()
                if not current_account:
                    session.clear()
                    return redirect("/")
                if current_account["google_sub"] and current_account["google_sub"] != google_sub:
                    return redirect("/?google_error=account_already_linked")
                if linked and linked["username"] != current_username:
                    return redirect("/?google_error=google_already_linked")
                username = current_username
                conn.execute("""
                    UPDATE users
                    SET google_sub = ?, google_email = ?,
                        country_code = CASE WHEN country_code = '' THEN ? ELSE country_code END,
                        country_locked = 1
                    WHERE username = ?
                """, (google_sub, email, country_code, username))
            elif linked:
                username = linked["username"]
                conn.execute("""
                    UPDATE users
                    SET country_code = CASE WHEN country_code = '' THEN ? ELSE country_code END,
                        country_locked = 1
                    WHERE username = ?
                """, (country_code, username))
            else:
                base_username = re.sub(r"[^A-Za-z0-9_]", "_", profile.get("name") or email.split("@", 1)[0]).strip("_")[:20] or "Jogador"
                username = base_username
                while True:
                    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                        break
                    username = f"{base_username[:14]}_{secrets.token_hex(2)}"
                from werkzeug.security import generate_password_hash
                password_hash = generate_password_hash(secrets.token_urlsafe(32))

                initial_coins = 100
                initial_is_admin = 0

                conn.execute(
                    "INSERT INTO users (username, password, coins, rating, google_sub, google_email, country_code, country_locked, is_admin) VALUES (?, ?, ?, 1200, ?, ?, ?, ?, ?)",
                    (username, password_hash, initial_coins, google_sub, email, country_code, 1, initial_is_admin)
                )

            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (username,))

        session.clear()
        session["username"] = username
        return redirect("/")

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=APP_DEBUG, host="0.0.0.0", port=PORT)
