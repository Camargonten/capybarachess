"""Backend PostgreSQL para o Capybara Chess (usado quando DATABASE_URL está definida).

O código do app foi escrito com SQL no dialeto do SQLite. Em vez de reescrever ~330 consultas, esta camada
traduz o SQL na hora (com cache) e entrega objetos com a mesma interface que o app já usa:

    conn.execute(sql, params) / conn.cursor() / cursor.execute / executemany / fetchone / fetchall
    row['coluna'], row[0], row.keys(), cursor.lastrowid, cursor.rowcount

Traduções (ver `translate_sql`):
    ?                         -> %s
    datetime('now', '-N unit') / CURRENT_TIMESTAMP -> texto 'YYYY-MM-DD HH24:MI:SS' em UTC (as colunas de data
                                 continuam TEXT, igual ao SQLite, então nenhum código precisa mudar)
    INSERT OR IGNORE          -> INSERT ... ON CONFLICT DO NOTHING
    INSERT OR REPLACE         -> INSERT ... ON CONFLICT (chave) DO UPDATE (chaves em UPSERT_KEYS)
    BEGIN IMMEDIATE           -> pg_advisory_xact_lock (mesma exclusão mútua que o lock de escrita do SQLite)
    INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY (lastrowid via RETURNING id)
    PRAGMA table_info / sqlite_master -> information_schema
    COLLATE NOCASE, MIN(a, b), REAL, julianday(...) -> equivalentes do PostgreSQL

Se um dia adicionar SQL com função exclusiva do SQLite, acrescente a regra em `translate_sql`.
"""
import logging
import re
import time
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

import psycopg2
import psycopg2.extensions
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger("capybara_db")

# Datas continuam sendo TEXT 'YYYY-MM-DD HH:MM:SS' (UTC), como no SQLite.
TS_FORMAT = "'YYYY-MM-DD HH24:MI:SS'"
TS_NOW = f"to_char(timezone('utc', now()), {TS_FORMAT})"
# Chave global usada no lugar do "BEGIN IMMEDIATE" do SQLite (trava até o fim da transação).
ADVISORY_LOCK_KEY = 724001
# Chaves primárias das tabelas usadas com INSERT OR REPLACE.
UPSERT_KEYS = {
    'classic_bots': ('username', 'mode', 'bot_number'),
    'game_rating_results': ('game_id', 'username', 'kind'),
}
# Tabelas com id autoincremental; o conjunto também é preenchido ao traduzir os CREATE TABLE.
SERIAL_TABLES = {
    'users', 'direct_challenges', 'messages', 'clubs', 'club_messages',
    'club_challenges', 'rematch_requests', 'gift_requests',
}

# O SQLite grava True como 1; o PostgreSQL recusaria boolean em coluna INTEGER.
psycopg2.extensions.register_adapter(bool, lambda value: psycopg2.extensions.AsIs('1' if value else '0'))

_QUOTED = re.compile(r"('(?:[^']|'')*')")
_DATETIME_OFFSET = re.compile(
    r"datetime\(\s*'now'\s*,\s*'([+-]?)(\d+)\s+(second|minute|hour|day)s?'\s*\)", re.IGNORECASE)
_DATETIME_NOW = re.compile(r"datetime\(\s*'now'\s*\)", re.IGNORECASE)
_JULIANDAY_MINUTES = re.compile(
    r"\(\s*julianday\('now'\)\s*-\s*julianday\((\w+)\)\s*\)\s*\*\s*1440", re.IGNORECASE)
_COLLATE_NOCASE = re.compile(r"([\w.]+)\s*=\s*\?\s+COLLATE\s+NOCASE", re.IGNORECASE)
_SCALAR_MIN = re.compile(r"\bMIN\(\s*(\w+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_TABLE_INFO = re.compile(r"^\s*PRAGMA\s+table_info\(\s*(\w+)\s*\)\s*;?\s*$", re.IGNORECASE)
_SQLITE_MASTER = re.compile(
    r"^\s*SELECT\s+1\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'\s+AND\s+name\s*=\s*'(\w+)'\s*;?\s*$",
    re.IGNORECASE)
_INSERT_TABLE = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(
    r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]*)\)(.*)$", re.IGNORECASE | re.DOTALL)
_CREATE_TABLE = re.compile(r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE)


class Translated:
    __slots__ = ('sql', 'params_override', 'returning')

    def __init__(self, sql, params_override=None, returning=False):
        self.sql = sql
        self.params_override = params_override
        self.returning = returning


def _outside_quotes(sql, transform):
    parts = _QUOTED.split(sql)
    return ''.join(part if index % 2 else transform(part) for index, part in enumerate(parts))


@lru_cache(maxsize=2048)
def translate_sql(sql: str) -> Translated:
    text = sql.strip()

    table_info = _TABLE_INFO.match(text)
    if table_info:
        return Translated(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
            params_override=(table_info.group(1).lower(),))
    if re.match(r"^\s*PRAGMA\b", text, re.IGNORECASE):
        return Translated("SELECT 1 WHERE FALSE")
    if re.match(r"^\s*BEGIN(\s+IMMEDIATE)?\s*;?\s*$", text, re.IGNORECASE):
        return Translated("SELECT pg_advisory_xact_lock(%d)" % ADVISORY_LOCK_KEY)
    master = _SQLITE_MASTER.match(text)
    if master:
        return Translated(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = %s",
            params_override=(master.group(1).lower(),))

    text = _DATETIME_OFFSET.sub(
        lambda m: "to_char(timezone('utc', now()) %s interval '%s %s', %s)" % (
            '+' if m.group(1) == '+' else '-', m.group(2), m.group(3), TS_FORMAT), text)
    text = _DATETIME_NOW.sub(TS_NOW, text)
    text = _JULIANDAY_MINUTES.sub(
        lambda m: "(EXTRACT(EPOCH FROM (timezone('utc', now()) - %s::timestamp)) / 86400.0) * 1440" % m.group(1), text)
    text = re.sub(r"\bCURRENT_TIMESTAMP\b", TS_NOW, text, flags=re.IGNORECASE)
    text = _COLLATE_NOCASE.sub(lambda m: "LOWER(%s) = LOWER(?)" % m.group(1), text)
    text = _SCALAR_MIN.sub(lambda m: "LEAST(%s, %s)" % (m.group(1), m.group(2)), text)
    text = text.rstrip().rstrip(';')

    create = _CREATE_TABLE.match(text)
    if create:
        if re.search(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", text, re.IGNORECASE):
            SERIAL_TABLES.add(create.group(1).lower())
        text = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "SERIAL PRIMARY KEY", text, flags=re.IGNORECASE)
        text = re.sub(r"\bREAL\b", "DOUBLE PRECISION", text, flags=re.IGNORECASE)
        text = re.sub(r"\bBLOB\b", "BYTEA", text, flags=re.IGNORECASE)

    replace = _INSERT_OR_REPLACE.match(text)
    if replace:
        table, columns, rest = replace.group(1).lower(), [c.strip() for c in replace.group(2).split(',')], replace.group(3)
        keys = UPSERT_KEYS.get(table)
        if not keys:
            raise ValueError(f"INSERT OR REPLACE em '{table}' sem chave em UPSERT_KEYS (core/db_postgres.py)")
        updates = ', '.join(f"{c} = EXCLUDED.{c}" for c in columns if c not in keys)
        text = (f"INSERT INTO {table} ({', '.join(columns)}){rest} "
                f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {updates}")
    elif re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", text, re.IGNORECASE):
        text = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", text, flags=re.IGNORECASE) + " ON CONFLICT DO NOTHING"

    returning = False
    insert = _INSERT_TABLE.match(text)
    if insert and insert.group(1).lower() in SERIAL_TABLES and 'RETURNING' not in text.upper():
        text += " RETURNING id"
        returning = True

    text = _outside_quotes(text, lambda part: part.replace('%', '%%').replace('?', '%s'))
    # '%' dentro de literais também precisa ser escapado por causa da interpolação do psycopg2.
    text = _QUOTED.sub(lambda m: m.group(1).replace('%%', '%').replace('%', '%%'), text)
    return Translated(text, returning=returning)


class PGCursor:
    """Cursor com a interface do sqlite3 (execute devolve o próprio cursor)."""

    def __init__(self, raw):
        self._raw = raw
        self.lastrowid = None

    def execute(self, sql, params=()):
        translated = translate_sql(sql)
        values = translated.params_override if translated.params_override is not None else tuple(params or ())
        self._raw.execute(translated.sql, values)
        if translated.returning:
            row = self._raw.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def executemany(self, sql, seq_of_params):
        translated = translate_sql(sql)
        psycopg2.extras.execute_batch(self._raw, translated.sql, [tuple(p) for p in seq_of_params], page_size=500)
        return self

    def fetchone(self):
        return self._raw.fetchone() if self._raw.description else None

    def fetchall(self):
        return self._raw.fetchall() if self._raw.description else []

    def fetchmany(self, size=None):
        return self._raw.fetchmany(size) if size else self._raw.fetchmany()

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def description(self):
        return self._raw.description

    def close(self):
        self._raw.close()


class PGConnection:
    """Conexão do pool com a interface do sqlite3.Connection que o app usa."""

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool

    def cursor(self):
        return PGCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq_of_params):
        return self.cursor().executemany(sql, seq_of_params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._pool.release(self._raw)


class PostgresPool:
    """Pool de conexões (evita abrir TLS a cada requisição) com reconexão de conexões ociosas derrubadas."""

    IDLE_CHECK_SECONDS = 20

    def __init__(self, dsn: str, max_connections: int = 10):
        self._dsn = normalize_dsn(dsn)
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            1, max_connections, self._dsn, cursor_factory=psycopg2.extras.DictCursor,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3, connect_timeout=15)
        self._last_used = {}

    def acquire(self) -> PGConnection:
        for _ in range(3):
            raw = self._pool.getconn()
            idle_for = time.time() - self._last_used.get(id(raw), 0)
            if raw.closed or (idle_for > self.IDLE_CHECK_SECONDS and not self._alive(raw)):
                self._pool.putconn(raw, close=True)
                continue
            return PGConnection(raw, self)
        raw = self._pool.getconn()
        return PGConnection(raw, self)

    @staticmethod
    def _alive(raw) -> bool:
        try:
            with raw.cursor() as cursor:
                cursor.execute("SELECT 1")
            raw.rollback()
            return True
        except Exception:
            return False

    def release(self, raw):
        self._last_used[id(raw)] = time.time()
        try:
            if not raw.closed and raw.status != psycopg2.extensions.STATUS_READY:
                raw.rollback()
        except Exception:
            pass
        self._pool.putconn(raw, close=bool(raw.closed))


def normalize_dsn(url: str) -> str:
    """Aceita postgres:// ou postgresql://; exige TLS em hosts remotos (Neon, Supabase, Render)."""
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    host = (parts.hostname or '').lower()
    is_local = host in ('', 'localhost', '127.0.0.1', '::1') or 'host' in query
    if 'sslmode' not in query and not is_local:
        url += ('&' if parts.query else '?') + 'sslmode=require'
    return url
