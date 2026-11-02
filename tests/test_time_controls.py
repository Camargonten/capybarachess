"""Ritmos de jogo e relógio: lista única (TIME_CONTROLS), incremento e tolerância de rede.

Usa partidas PvP (sem Stockfish). Rode contra um banco VAZIO/descartável:

    DATABASE_PATH=/tmp/timectl.db python3 tests/test_time_controls.py
    DATABASE_URL=postgresql://... python3 tests/test_time_controls.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
from blueprints.game import MOVE_LAG_GRACE_SECONDS  # noqa: E402
from core.constants import TIME_CONTROLS  # noqa: E402
from core.db import get_db  # noqa: E402
from core.security import limiter  # noqa: E402

app = xadrez.app
errors = []
PASSWORD = 'Teste#1234'


def check(condition, label):
    print(('ok   ' if condition else 'FALHA'), label)
    if not condition:
        errors.append(label)


def register(name):
    client = app.test_client()
    client.post('/register', json={'username': name, 'password': PASSWORD})
    with get_db() as conn:
        conn.execute("UPDATE users SET google_sub = ?, google_email = ?, calibrated = 1, rating = 1500 WHERE username = ?",
                     (f"sub-{name}", f"{name}@example.com", name))
    return client


alice, bob = register('tc_alice'), register('tc_bob')
JOIN = {'min_offset': -300, 'max_offset': 100000}


def new_game(control):
    """Pareia alice e bob no ritmo pedido; devolve (id, cliente das brancas, cliente das pretas)."""
    limiter._requests.clear()
    alice.post('/matchmaking/ranked/join', json={'time_control': control, **JOIN})
    bob.post('/matchmaking/ranked/join', json={'time_control': control, **JOIN})
    alice.get('/matchmaking/ranked/status')
    game_id = bob.get('/matchmaking/ranked/status').get_json().get('game_id')
    if not game_id:
        return None, None, None
    state = alice.get(f'/game/{game_id}/state').get_json()
    white = alice if state['white_user'] == 'tc_alice' else bob
    return game_id, white, (bob if white is alice else alice)


def finish(game_id, client):
    if game_id:
        client.post(f'/game/{game_id}/resign', json={})


def set_clock(game_id, white_time, elapsed):
    with get_db() as conn:
        conn.execute("UPDATE games SET white_time = ?, last_move_time = ? WHERE id = ?",
                     (white_time, time.time() - elapsed, game_id))


# 1) todo ritmo da lista vira exatamente aquela partida na fila rankeada (10+5 não pode virar 3+2)
for control, (initial, increment) in TIME_CONTROLS.items():
    game_id, white, black = new_game(control)
    if not game_id:
        check(False, f'fila rankeada pareou {control}')
        continue
    state = white.get(f'/game/{game_id}/state').get_json()
    check((state['time_initial'], state['time_increment']) == (initial, increment),
          f'fila rankeada {control} -> {state["time_initial"]}+{state["time_increment"]}')
    finish(game_id, white)

# 2) ritmo fora da lista é recusado, não trocado em silêncio
limiter._requests.clear()
check(alice.post('/matchmaking/ranked/join', json={'time_control': '7,7', **JOIN}).status_code == 400, 'fila recusa ritmo inválido')
check(alice.post('/challenges/direct', json={'recipient': 'tc_bob', 'time_control': '7,7'}).status_code == 400, 'desafio direto recusa ritmo inválido')
alice.post('/matchmaking/ranked/leave', json={})
limiter._requests.clear()
check(alice.post('/challenges/direct', json={'recipient': 'tc_bob', 'time_control': '300,0'}).status_code == 200, 'desafio direto aceita 5+0')
with get_db() as conn:
    row = conn.execute("SELECT time_control FROM direct_challenges WHERE sender = 'tc_alice' ORDER BY id DESC LIMIT 1").fetchone()
check(row is not None and row['time_control'] == '300,0', 'desafio direto guarda 5+0 (antes virava 3+2)')

# 3) incremento soma depois de descontar o tempo gasto
game_id, white, black = new_game('60,1')
set_clock(game_id, 30.0, 3.0)
data = white.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('success') and abs(data['white_time'] - 28.0) < 0.5, f'30 s - 3 s + 1 s = ~28 s (veio {data.get("white_time")})')
finish(game_id, white)

# 4) estouro DENTRO da tolerância de rede: lance vale, tempo vai a zero e o incremento entra
game_id, white, black = new_game('60,1')
set_clock(game_id, 1.0, 1.0 + MOVE_LAG_GRACE_SECONDS * 0.5)
data = white.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('success') and abs(data['white_time'] - 1.0) < 0.5, f'estouro dentro da tolerância não dá bandeira (veio {data})')
finish(game_id, white)

# 5) estouro ALÉM da tolerância: bandeira
game_id, white, black = new_game('60,1')
set_clock(game_id, 1.0, 1.0 + MOVE_LAG_GRACE_SECONDS + 1.0)
data = white.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('status') == 'timeout' and data.get('game_over'), 'estouro além da tolerância dá bandeira no lance')

# 6) claim_timeout respeita a mesma tolerância
game_id, white, black = new_game('60,1')
set_clock(game_id, 1.0, 1.0 + MOVE_LAG_GRACE_SECONDS * 0.5)
data = black.post(f'/game/{game_id}/claim_timeout', json={}).get_json()
check(data.get('success') is False, 'claim_timeout não derruba dentro da tolerância')
set_clock(game_id, 1.0, 1.0 + MOVE_LAG_GRACE_SECONDS + 1.0)
data = black.post(f'/game/{game_id}/claim_timeout', json={}).get_json()
check(data.get('status') == 'timeout', 'claim_timeout derruba além da tolerância')

# 7) /state mostra 0,0 (sem bandeira) dentro da tolerância
game_id, white, black = new_game('60,1')
set_clock(game_id, 1.0, 1.0 + MOVE_LAG_GRACE_SECONDS * 0.5)
state = white.get(f'/game/{game_id}/state').get_json()
check(state.get('status') == 'active' and state.get('white_time') == 0.0, 'state dentro da tolerância: ativo com 0,0')
finish(game_id, white)

print()
sys.exit(1 if errors else 0)
