import re
import time
import logging
from threading import Lock
from functools import wraps
from flask import request, jsonify
import chess

logger = logging.getLogger("capybara_security")

class InMemoryRateLimiter:
    """
    Sliding window rate limiter thread-safe em memória.
    Sem dependências externas pesadas (Redis/memcached), ultra-leve e escalável.
    """
    def __init__(self):
        self._requests = {}
        self._lock = Lock()

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            # Limpeza periódica de entradas antigas se a tabela ficar muito grande
            if len(self._requests) > 10000:
                expired_threshold = now - 3600
                self._requests = {
                    k: [t for t in timestamps if t > expired_threshold]
                    for k, timestamps in self._requests.items()
                    if any(t > expired_threshold for t in timestamps)
                }

            timestamps = self._requests.get(key, [])
            cutoff = now - window_seconds
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= max_requests:
                self._requests[key] = timestamps
                return False
            timestamps.append(now)
            self._requests[key] = timestamps
            return True

limiter = InMemoryRateLimiter()

def rate_limit(max_requests: int, window_seconds: int = 60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
            key = f"{ip}:{request.endpoint}"
            if not limiter.is_allowed(key, max_requests, window_seconds):
                logger.warning(f"Rate limit exceeded for {key}")
                return jsonify({
                    "error": "Muitas requisições em curto intervalo. Aguarde alguns instantes."
                }), 429
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def apply_security_headers(response):
    """
    Aplica os Security Headers recomendados pela OWASP e NIST.
    """
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://code.jquery.com https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
    return response

def validate_username(username: str) -> bool:
    if not isinstance(username, str) or len(username) < 3 or len(username) > 25:
        return False
    return re.fullmatch(r'[A-Za-z0-9_ -]+', username) is not None

def parse_bounded_integer(value, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r'-?[0-9]+', value):
        parsed = int(value)
    else:
        return None
    return parsed if minimum <= parsed <= maximum else None

def validate_uci_move(move_str: str) -> bool:
    if not isinstance(move_str, str) or len(move_str) not in (4, 5):
        return False
    return re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', move_str.lower()) is not None

def validate_fen(fen_str: str) -> bool:
    if not isinstance(fen_str, str) or not fen_str or len(fen_str) > 120:
        return False
    if re.fullmatch(r'[A-Za-z0-9/ -]+', fen_str) is None or len(fen_str.split(' ')) != 6:
        return False
    try:
        return chess.Board(fen_str).is_valid()
    except Exception:
        return False
