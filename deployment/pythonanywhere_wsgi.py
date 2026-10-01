import os
import sys

project_root = os.environ.get('CAPYBARA_PROJECT_ROOT', '/home/yourusername/capybara-chess')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('APP_ENV', 'production')
os.environ.setdefault('COOKIE_SECURE', 'true')
from xadrez import app as application
