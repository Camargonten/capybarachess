FROM python:3.14-slim-bookworm

ENV PATH="/usr/games:${PATH}"

# MALLOC_ARENA_MAX=2 evita que a memória das threads do gunicorn fique inchando com o tempo.
ENV PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    DATABASE_PATH=/tmp/capybara.db \
    STOCKFISH_PATH=/usr/local/bin/stockfish

WORKDIR /app

RUN apt-get update \
    && apt-get install -y stockfish \
    && ln -sf /usr/games/stockfish /usr/bin/stockfish \
    && ln -sf /usr/games/stockfish /usr/local/bin/stockfish \
    && rm -rf /var/lib/apt/lists/*

RUN chmod +x /usr/games/stockfish || true
RUN chmod +x /usr/bin/stockfish || true

RUN test -x /usr/games/stockfish \
    && test -x /usr/local/bin/stockfish \
    && test -x /usr/bin/stockfish \
    && printf 'uci\nquit\n' | /usr/local/bin/stockfish | grep -q '^uciok$'

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py xadrez.py ./
COPY core ./core
COPY blueprints ./blueprints
COPY templates ./templates
COPY static ./static

USER nobody
EXPOSE 10000

CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 4 --timeout 120 --max-requests 1500 --max-requests-jitter 150 --worker-tmp-dir /dev/shm --bind 0.0.0.0:${PORT:-10000} app:app"]