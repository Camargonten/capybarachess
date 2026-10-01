import os
import secrets
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
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', str(APP_ENV == 'production')).lower() == 'true'

STOCKFISH_PATH = os.environ.get('STOCKFISH_PATH', '/usr/games/stockfish')
if not os.path.exists(STOCKFISH_PATH):
    STOCKFISH_PATH = "stockfish"

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()

ADMIN_USERS = [u.strip().lower() for u in os.environ.get('ADMIN_USERS', '').split(',') if u.strip()]

