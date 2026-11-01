"""Professional WSGI entry point; xadrez.py remains as a compatibility module."""

from core.config import APP_DEBUG, PORT
from xadrez import app


if __name__ == "__main__":
    app.run(debug=APP_DEBUG, host="127.0.0.1", port=PORT)
