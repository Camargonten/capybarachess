import sqlite3
from contextlib import contextmanager
from core.config import DATABASE_PATH

def get_db_connection():
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

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
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
                is_admin INTEGER DEFAULT 0,
                active_frame TEXT DEFAULT '',
                active_banner TEXT DEFAULT ''
            )
        ''')
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row['name'] for row in cursor.fetchall()}
        
        columns_to_add = {
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
            'is_admin': "INTEGER DEFAULT 0",
            'active_frame': "TEXT DEFAULT ''",
            'active_banner': "TEXT DEFAULT ''"
        }
        for col, col_def in columns_to_add.items():
            if col not in existing_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                if col == 'last_login':
                    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE last_login IS NULL")

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
                rated INTEGER DEFAULT 0,
                draw_offered_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classic_profiles (
                username TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'blitz',
                rating INTEGER NOT NULL DEFAULT 1200,
                last_simulation TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (username, mode)
            )
        ''')
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
