FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    DATABASE_PATH=/tmp/capybara.db \
    STOCKFISH_PATH=/usr/local/bin/stockfish

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && ln -sf /usr/games/stockfish /usr/bin/stockfish \
    && chmod 755 /usr/games/stockfish \
    && chmod +x /usr/bin/stockfish \
    && ln -sf /usr/games/stockfish /usr/local/bin/stockfish \
    && chmod +x /usr/local/bin/stockfish \
    && test -x /usr/local/bin/stockfish \
    && test -x /usr/bin/stockfish \
    && printf 'uci\nquit\n' | /usr/local/bin/stockfish | grep -q '^uciok$' \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY xadrez.py ./
COPY core ./core
COPY blueprints ./blueprints
COPY templates ./templates
COPY static ./static

USER nobody
EXPOSE 10000

CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-10000} xadrez:app"]