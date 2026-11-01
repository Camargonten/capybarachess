#!/usr/bin/env python3
"""Copia os dados de um banco SQLite do Capybara Chess para o PostgreSQL (Neon, Supabase, Render...).

    DATABASE_URL='postgresql://usuario:senha@host/banco' python3 tools/migrate_sqlite_to_postgres.py [capybara.db]

- Cria o esquema no PostgreSQL se ainda não existir (mesmo código do app).
- Copia todas as tabelas preservando ids; pode ser rodado de novo (linhas já existentes são ignoradas).
- Ajusta as sequências dos ids autoincrementais.
- NÃO altera o arquivo SQLite (aberto somente para leitura).
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not os.environ.get('DATABASE_URL'):
    sys.exit("Defina DATABASE_URL (postgresql://...) antes de rodar.")

from core.config import BASE_DIR  # noqa: E402
from core.db import get_db, init_db  # noqa: E402
import psycopg2.extras  # noqa: E402

BATCH = 1000


def main():
    source_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(BASE_DIR, 'capybara.db')
    if not os.path.exists(source_path):
        sys.exit(f"Arquivo SQLite não encontrado: {source_path}")

    print("1/4 Criando o esquema no PostgreSQL...")
    init_db()
    with get_db() as conn:
        # Deixa as migrações pendentes para rodarem DEPOIS da cópia, sobre os dados copiados.
        conn.execute("DELETE FROM schema_migrations")

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    tables = [row['name'] for row in source.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    print("2/4 Copiando dados...")
    with get_db() as conn:
        raw = conn._raw
        pg_tables = {row['table_name'] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()").fetchall()}
        cursor = raw.cursor()
        for table in tables:
            if table not in pg_tables or table == 'server_state':
                print(f"   - {table}: ignorada (não existe no PostgreSQL)")
                continue
            pg_columns = {row['column_name'] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?",
                (table,)).fetchall()}
            columns = [row['name'] for row in source.execute(f'PRAGMA table_info("{table}")') if row['name'] in pg_columns]
            total = source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if not columns or not total:
                print(f"   - {table}: 0 linhas")
                continue
            insert = f'INSERT INTO {table} ({", ".join(columns)}) VALUES %s ON CONFLICT DO NOTHING'
            copied = 0
            rows_cursor = source.execute(f'SELECT {", ".join(columns)} FROM "{table}"')
            while True:
                batch = rows_cursor.fetchmany(BATCH)
                if not batch:
                    break
                psycopg2.extras.execute_values(cursor, insert, [tuple(row) for row in batch], page_size=BATCH)
                copied += len(batch)
            print(f"   - {table}: {copied}/{total} linhas")

    print("3/4 Ajustando sequências de ids...")
    with get_db() as conn:
        for table in ('users', 'direct_challenges', 'messages', 'clubs', 'club_messages',
                      'club_challenges', 'rematch_requests', 'gift_requests'):
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")

    print("4/4 Aplicando migrações pendentes sobre os dados copiados...")
    init_db()
    print("Pronto. Defina DATABASE_URL no servidor e reinicie o app.")


if __name__ == '__main__':
    main()
