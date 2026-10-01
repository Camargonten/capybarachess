import os
import secrets
import shutil
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

APP_ENV = os.environ.get('APP_ENV', 'development').lower()
APP_DEBUG = os.environ.get('APP_DEBUG', 'false').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))

SECRET_KEY = os.environ.get('SECRET_KEY')
if APP_ENV == 'production' and not SECRET_KEY:
    raise RuntimeError('FATAL: SECRET_KEY precisa ser configurada no ambiente de produção.')
SECRET_KEY = SECRET_KEY or secrets.token_hex(32)

DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'capybara.db'))
if APP_ENV == 'production':
    configured_database_path = os.environ.get('DATABASE_PATH')
    if not configured_database_path or not os.path.isabs(configured_database_path):
        raise RuntimeError('DATABASE_PATH deve apontar para um caminho absoluto.')
    database_directory = os.path.dirname(configured_database_path)
    if not os.path.isdir(database_directory) or not os.access(database_directory, os.W_OK):
        raise RuntimeError('O diretório configurado em DATABASE_PATH não existe ou não permite escrita.')
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', str(APP_ENV == 'production')).lower() == 'true'

def resolve_stockfish_path(configured_path: str | None = None) -> str | None:
    candidates = [configured_path] if configured_path else [
        '/usr/games/stockfish', '/usr/bin/stockfish', shutil.which('stockfish')
    ]
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if os.path.sep not in candidate else os.path.abspath(candidate)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        if os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            return resolved
    return None

STOCKFISH_PATH = resolve_stockfish_path(os.environ.get('STOCKFISH_PATH'))
if APP_ENV == 'production' and not STOCKFISH_PATH:
    raise RuntimeError('Stockfish não foi encontrado como arquivo executável; configure STOCKFISH_PATH no ambiente de produção.')

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()

ADMIN_USERS = [u.strip().lower() for u in os.environ.get('ADMIN_USERS', '').split(',') if u.strip()]

