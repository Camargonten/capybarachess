import os
import sqlite3
import threading
from contextlib import contextmanager
from core.config import DATABASE_PATH, DATABASE_URL, USING_POSTGRES

# Exceções de violação de unicidade, em qualquer um dos dois bancos.
if USING_POSTGRES:
    import psycopg2
    IntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError)
else:
    IntegrityError = (sqlite3.IntegrityError,)

_pg_pool = None
_pg_pool_lock = threading.Lock()


def _postgres_pool():
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                from core.db_postgres import PostgresPool
                _pg_pool = PostgresPool(DATABASE_URL, max_connections=int(os.environ.get('DB_POOL_SIZE', 10)))
    return _pg_pool


def get_db_connection():
    if USING_POSTGRES:
        return _postgres_pool().acquire()
    database_directory = os.path.dirname(DATABASE_PATH) or '.'
    os.makedirs(database_directory, exist_ok=True)
    if not os.access(database_directory, os.W_OK):
        raise PermissionError(f"O diretório do banco SQLite não permite escrita: {database_directory}")
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def cleanup_ephemeral_sessions(conn, current_username: str | None = None) -> None:
    # Heartbeats make abandoned queue entries cheap to identify without a scheduler.
    conn.execute("""
        DELETE FROM ranked_queue
        WHERE status = 'waiting' AND NOT EXISTS (
            SELECT 1 FROM user_presence p
            WHERE p.username = ranked_queue.username
              AND p.last_seen_at >= datetime('now', '-45 seconds')
        )
    """)
    conn.execute("""
        DELETE FROM ranked_queue
        WHERE status = 'matched' AND NOT EXISTS (
            SELECT 1 FROM games g
            WHERE g.id = ranked_queue.game_id AND g.status = 'active'
        )
    """)
    if current_username:
        conn.execute(
            "DELETE FROM user_presence WHERE last_seen_at < datetime('now', '-7 days') AND username != ?",
            (current_username,)
        )
    else:
        conn.execute("DELETE FROM user_presence WHERE last_seen_at < datetime('now', '-7 days')")

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        if USING_POSTGRES:
            # Vários workers podem iniciar juntos: só um cria/migra o esquema por vez.
            cursor.execute("SELECT pg_advisory_xact_lock(724002)")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT DEFAULT '',
                display_name_changes INTEGER DEFAULT 0,
                bio TEXT DEFAULT '',
                password TEXT NOT NULL,
                coins INTEGER DEFAULT 100,
                rating INTEGER DEFAULT 1200,
                promo_count INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '[]',
                last_login TEXT DEFAULT CURRENT_TIMESTAMP,
                calibrated INTEGER DEFAULT 0,
                calibration_games INTEGER DEFAULT 0,
                colorblind_mode INTEGER DEFAULT 0,
                skip_animation INTEGER DEFAULT 0,
                bgm_choice INTEGER DEFAULT 1,
                avatar TEXT DEFAULT '',
                google_sub TEXT UNIQUE,
                google_email TEXT,
                country_code TEXT NOT NULL DEFAULT '',
                country_locked INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                active_frame TEXT DEFAULT '',
                active_banner TEXT DEFAULT '',
                active_piece_skin TEXT DEFAULT ''
            )
        ''')
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row['name'] for row in cursor.fetchall()}
        
        columns_to_add = {
            'display_name': "TEXT DEFAULT ''",
            'display_name_changes': "INTEGER DEFAULT 0",
            'bio': "TEXT DEFAULT ''",
            'inventory': "TEXT DEFAULT '[]'",
            'last_login': "TEXT",
            'calibrated': "INTEGER DEFAULT 0",
            'calibration_games': "INTEGER DEFAULT 0",
            'colorblind_mode': "INTEGER DEFAULT 0",
            'skip_animation': "INTEGER DEFAULT 0",
            'bgm_choice': "INTEGER DEFAULT 1",
            'avatar': "TEXT DEFAULT ''",
            'google_sub': "TEXT",
            'google_email': "TEXT",
            'country_code': "TEXT NOT NULL DEFAULT ''",
            'country_locked': "INTEGER NOT NULL DEFAULT 0",
            'is_admin': "INTEGER DEFAULT 0",
            'active_frame': "TEXT DEFAULT ''",
            'active_banner': "TEXT DEFAULT ''",
            'active_piece_skin': "TEXT DEFAULT ''"
        }
        for col, col_def in columns_to_add.items():
            if col not in existing_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                if col == 'last_login':
                    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE last_login IS NULL")
        cursor.execute("UPDATE users SET display_name = username WHERE display_name IS NULL OR display_name = ''")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        country_migration = cursor.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            ("google_region_profile_flag_v1",)
        ).fetchone()
        if not country_migration:
            cursor.execute("UPDATE users SET country_code = '', country_locked = 0")
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                ("google_region_profile_flag_v1",)
            )

        has_bots_table = cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='classic_bots'").fetchone()
        if has_bots_table and not cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", ("legends_parody_names_v1",)).fetchone():
            from core.constants import CLASSIC_LEGENDS, OLD_CLASSIC_LEGENDS
            for old, new in zip(OLD_CLASSIC_LEGENDS, CLASSIC_LEGENDS):
                cursor.execute(
                    "UPDATE classic_bots SET name_pt=?, name_en=?, name_es=?, name_fr=? WHERE name_pt=?",
                    (new, new, new, new, old))
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("legends_parody_names_v1",))

        if has_bots_table and not cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", ("classic_bot_identities_v1",)).fetchone():
            # Bots comuns (42-700) ganham nome multicultural; rating, estilo e número não mudam.
            from core.bot_identity import classic_bot_identity, CLASSIC_COMMON_FIRST_NUMBER, CLASSIC_COMMON_LAST_NUMBER
            identities = [(name, name, name, name, number)
                          for number in range(CLASSIC_COMMON_FIRST_NUMBER, CLASSIC_COMMON_LAST_NUMBER + 1)
                          for name in [classic_bot_identity(number)[0]]]
            cursor.executemany(
                "UPDATE classic_bots SET name_pt=?, name_en=?, name_es=?, name_fr=? WHERE bot_number=?", identities)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("classic_bot_identities_v1",))

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique ON users (google_sub)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_redemptions (
                code TEXT NOT NULL,
                username TEXT NOT NULL,
                redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, username)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                username TEXT NOT NULL,
                seal TEXT NOT NULL,
                earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (username, seal)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS friend_requests (
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (sender, recipient)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_presence (
                username TEXT PRIMARY KEY,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS user_presence_last_seen_idx ON user_presence (last_seen_at)")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS direct_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                time_control TEXT NOT NULL DEFAULT '180,2',
                status TEXT NOT NULL DEFAULT 'pending',
                game_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                responded_at TEXT
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS direct_challenges_recipient_status_idx ON direct_challenges (recipient, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS direct_challenges_sender_status_idx ON direct_challenges (sender, status)")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ranked_queue (
                username TEXT PRIMARY KEY,
                rating INTEGER NOT NULL,
                min_rating INTEGER NOT NULL DEFAULT 0,
                max_rating INTEGER NOT NULL DEFAULT 2147483647,
                time_control TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting',
                game_id TEXT,
                queued_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("PRAGMA table_info(ranked_queue)")
        ranked_queue_columns = {row['name'] for row in cursor.fetchall()}
        for column, definition in {
            'min_rating': "INTEGER NOT NULL DEFAULT 0",
            'max_rating': "INTEGER NOT NULL DEFAULT 2147483647",
        }.items():
            if column not in ranked_queue_columns:
                cursor.execute(f"ALTER TABLE ranked_queue ADD COLUMN {column} {definition}")
        cursor.execute("CREATE INDEX IF NOT EXISTS ranked_queue_status_time_idx ON ranked_queue (status, time_control, queued_at)")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                content TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clubs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                leader TEXT NOT NULL,
                badge_id INTEGER DEFAULT 1,
                privacy TEXT DEFAULT 'public',
                password_hash TEXT,
                min_rating INTEGER DEFAULT 0,
                member_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS club_members (
                club_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (club_id, username)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS club_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS club_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club_id INTEGER NOT NULL,
                creator TEXT NOT NULL,
                time_control TEXT NOT NULL DEFAULT '180,2',
                mode TEXT NOT NULL DEFAULT 'blitz',
                status TEXT NOT NULL DEFAULT 'open',
                game_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                white_user TEXT,
                black_user TEXT,
                creator_user TEXT NOT NULL,
                creator_color TEXT NOT NULL DEFAULT 'random',
                game_type TEXT NOT NULL DEFAULT 'bot',
                time_initial INTEGER NOT NULL DEFAULT 180,
                time_increment INTEGER NOT NULL DEFAULT 2,
                white_time REAL NOT NULL DEFAULT 180,
                black_time REAL NOT NULL DEFAULT 180,
                last_move_time REAL,
                fen TEXT NOT NULL DEFAULT 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                history TEXT DEFAULT '[]',
                turn TEXT NOT NULL DEFAULT 'w',
                status TEXT NOT NULL DEFAULT 'waiting',
                winner TEXT,
                termination_reason TEXT,
                bot_number INTEGER DEFAULT 0,
                bot_rating INTEGER DEFAULT 500,
                bot_seal TEXT DEFAULT '',
                classic_mode TEXT DEFAULT '',
                classic_bot_number INTEGER DEFAULT 0,
                rated INTEGER DEFAULT 0,
                draw_offered_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("PRAGMA table_info(games)")
        game_columns = {row['name'] for row in cursor.fetchall()}
        for column, definition in {
            'classic_mode': "TEXT DEFAULT ''",
            'classic_bot_number': "INTEGER DEFAULT 0",
            'takeback_requested_by': "TEXT",
            'restored': "INTEGER DEFAULT 0"
        }.items():
            if column not in game_columns:
                cursor.execute(f"ALTER TABLE games ADD COLUMN {column} {definition}")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_aborts (
                game_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                aborted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_game_aborts_user_time
            ON game_aborts(username, aborted_at)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rematch_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                requester TEXT NOT NULL,
                opponent TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                new_game_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                responded_at TEXT,
                UNIQUE(game_id, requester)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rematch_inbox
            ON rematch_requests(opponent, status, created_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rematch_expiry
            ON rematch_requests(status, created_at)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gift_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                item_id TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                item_price INTEGER NOT NULL,
                fee INTEGER NOT NULL DEFAULT 50,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                responded_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_gift_inbox
            ON gift_requests(recipient, status, created_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_gift_expiry
            ON gift_requests(status, created_at)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classic_profiles (
                username TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'blitz',
                rating INTEGER NOT NULL DEFAULT 1200,
                games_played INTEGER NOT NULL DEFAULT 0,
                last_simulation TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (username, mode)
            )
        ''')
        cursor.execute("PRAGMA table_info(classic_profiles)")
        classic_profile_columns = {row['name'] for row in cursor.fetchall()}
        if 'games_played' not in classic_profile_columns:
            cursor.execute("ALTER TABLE classic_profiles ADD COLUMN games_played INTEGER NOT NULL DEFAULT 0")
        # --- Sistema de rating (calibrações) ---
        cursor.execute("PRAGMA table_info(users)")
        rating_user_columns = {row['name'] for row in cursor.fetchall()}
        for column, definition in {
            'calib1_results': "TEXT DEFAULT '[]'",
            'calib_base_rating': "INTEGER DEFAULT 0",
            'calib2_games': "INTEGER DEFAULT 0"
        }.items():
            if column not in rating_user_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        cursor.execute("PRAGMA table_info(classic_profiles)")
        rating_profile_columns = {row['name'] for row in cursor.fetchall()}
        for column, definition in {
            'calib_base_rating': "INTEGER DEFAULT 0",
            'calib2_games': "INTEGER DEFAULT 0"
        }.items():
            if column not in rating_profile_columns:
                cursor.execute(f"ALTER TABLE classic_profiles ADD COLUMN {column} {definition}")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_rating_results (
                game_id TEXT NOT NULL,
                username TEXT NOT NULL,
                kind TEXT NOT NULL,
                mode TEXT DEFAULT '',
                old_rating INTEGER NOT NULL,
                new_rating INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                phase TEXT NOT NULL,
                step INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (game_id, username, kind)
            )
        ''')
        # Contas que já terminaram a calibração antes deste sistema não refazem a 2ª calibração.
        cursor.execute("UPDATE users SET calib_base_rating = rating, calib2_games = 5 WHERE calibrated = 1 AND calib_base_rating = 0 AND calib2_games = 0")
        cursor.execute("UPDATE classic_profiles SET calib2_games = MIN(games_played, 5) WHERE games_played > 0 AND calib2_games = 0 AND calib_base_rating = 0")
        # Calibração inicial que estava no meio, sem o resultado das partidas guardado: recomeça.
        cursor.execute("UPDATE users SET calibration_games = 0 WHERE calibrated = 0 AND calibration_games > 0 AND (calib1_results IS NULL OR calib1_results = '[]')")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classic_bots (
                username TEXT NOT NULL,
                bot_number INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'blitz',
                name_pt TEXT NOT NULL,
                name_en TEXT NOT NULL,
                name_es TEXT NOT NULL,
                name_fr TEXT NOT NULL,
                rating INTEGER NOT NULL,
                style TEXT NOT NULL,
                PRIMARY KEY (username, mode, bot_number)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS missions (
                username TEXT NOT NULL,
                mission_id INTEGER NOT NULL,
                progress INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0,
                PRIMARY KEY (username, mission_id)
            )
        ''')


HEARTBEAT_KEY = 'last_heartbeat'
# Abaixo disso consideramos que foi só uma reinicialização rápida e não congelamos os relógios.
MIN_DOWNTIME_TO_FREEZE_SECONDS = 20.0


def record_heartbeat() -> None:
    """Marca "o servidor estava vivo agora". Chamado periodicamente e no desligamento."""
    import time
    with get_db() as conn:
        conn.execute(
            "INSERT INTO server_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (HEARTBEAT_KEY, repr(time.time())))


def freeze_clocks_after_downtime() -> float:
    """Ao iniciar, devolve às partidas ativas o tempo em que o servidor ficou desligado.

    Os relógios contam desde `last_move_time`; empurrar esse instante para frente pelo tempo de
    inatividade faz a partida voltar exatamente ao estado em que o último jogador a deixou.
    Retorna os segundos de inatividade aplicados (0 se não houve).
    """
    import time
    with get_db() as conn:
        row = conn.execute("SELECT value FROM server_state WHERE key = ?", (HEARTBEAT_KEY,)).fetchone()
        if not row:
            return 0.0
        try:
            downtime = time.time() - float(row['value'])
        except (TypeError, ValueError):
            return 0.0
        if downtime < MIN_DOWNTIME_TO_FREEZE_SECONDS:
            return 0.0
        conn.execute(
            "UPDATE games SET last_move_time = last_move_time + ? WHERE status = 'active' AND last_move_time IS NOT NULL",
            (downtime,))
        return downtime


def start_heartbeat_thread(interval_seconds: float = 15.0) -> None:
    """Thread leve que grava o heartbeat; também grava um último ao encerrar o processo."""
    import atexit
    import logging
    import threading
    import time

    logger = logging.getLogger("capybara_db")

    def safe_beat():
        try:
            record_heartbeat()
        except Exception:
            logger.exception("Falha ao gravar o heartbeat do servidor.")

    def loop():
        while True:
            time.sleep(interval_seconds)
            safe_beat()

    safe_beat()
    threading.Thread(target=loop, name="capybara-heartbeat", daemon=True).start()
    atexit.register(safe_beat)
