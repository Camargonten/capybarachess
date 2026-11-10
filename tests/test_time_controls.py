"""Ritmos de jogo e relógio: lista única (TIME_CONTROLS), incremento, tolerância de rede, bandeira do bot
e rating dos bots do modo Bermuda.

Usa partidas PvP e um motor simulado no lugar do Stockfish. Rode contra um banco VAZIO/descartável:

    DATABASE_PATH=/tmp/timectl.db python3 tests/test_time_controls.py
    DATABASE_URL=postgresql://... python3 tests/test_time_controls.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
import blueprints.game as game_module  # noqa: E402
from blueprints.game import MOVE_LAG_GRACE_SECONDS  # noqa: E402
from blueprints.user import ensure_classic_profile  # noqa: E402
from core.constants import CLASSIC_MODES  # noqa: E402
from core.engine import BOT_INSTANT_BELOW_SECONDS  # noqa: E402
from core.rating import settle_bermuda_rating  # noqa: E402
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

# 8) bots: modo automático (lance imediato) só abaixo de 20 s
check(BOT_INSTANT_BELOW_SECONDS == 20.0, 'bot joga no automático com 20 s ou menos no relógio')

# 9) bots perdem por tempo (motor simulado: lance legal após `fake_think` segundos)
fake_think = [0.0]


def fake_bot_move(board, rating, remaining_time=None):
    time.sleep(fake_think[0])
    return next(iter(board.legal_moves)).uci(), 1


game_module.get_bot_move_fide = fake_bot_move


def new_bot_game(control='60,0'):
    limiter._requests.clear()
    created = alice.post('/game/create', json={'mode': 'bot', 'color': 'white', 'time_control': control,
                                               'bot_number': 1, 'bot_rating': 500, 'rated': False}).get_json()
    return created.get('game_id') or created.get('id')


def set_bot_clock(game_id, black_time):
    with get_db() as conn:
        conn.execute("UPDATE games SET black_time = ?, last_move_time = ? WHERE id = ?", (black_time, time.time(), game_id))


game_id = new_bot_game()
data = alice.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('status') == 'active' and data.get('bot_move'), 'bot com tempo responde normalmente')

set_bot_clock(game_id, 0.0)
data = alice.post(f'/game/{game_id}/move', json={'move': 'd2d4'}).get_json()
check(data.get('status') == 'timeout' and data.get('winner') == 'white' and not data.get('bot_move'),
      'bot com relógio zerado perde por tempo sem jogar')
check(data.get('black_time') == 0.0, 'relógio do bot fica em 0,0 após a derrota')

game_id = new_bot_game()
fake_think[0] = 0.5
set_bot_clock(game_id, 0.2)
data = alice.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('status') == 'timeout' and data.get('winner') == 'white' and not data.get('bot_move'),
      'bot que demora mais que o tempo restante perde por tempo')

game_id = new_bot_game()
set_bot_clock(game_id, 5.0)
data = alice.post(f'/game/{game_id}/move', json={'move': 'e2e4'}).get_json()
check(data.get('status') == 'active' and 4.0 <= data.get('black_time', 0) <= 5.0, 'bot com folga segue jogando e paga o tempo gasto')
fake_think[0] = 0.0
finish(game_id, alice)

# 10) rating dos bots do modo Bermuda sobe/desce depois da partida (uma única vez por partida)
ensure_classic_profile('tc_alice')
with get_db() as conn:
    bot = conn.execute("SELECT bot_number, rating FROM classic_bots WHERE username = 'tc_alice' AND mode = 'blitz' ORDER BY bot_number LIMIT 1").fetchone()
    start = bot['rating']
    settle_bermuda_rating(conn, 'bermuda-teste-1', 'bot', 'blitz', bot['bot_number'], start, 'tc_alice', 'Bot: Teste', 'white', CLASSIC_MODES)
    after_loss = conn.execute("SELECT rating FROM classic_bots WHERE username = 'tc_alice' AND mode = 'blitz' AND bot_number = ?", (bot['bot_number'],)).fetchone()['rating']
    settle_bermuda_rating(conn, 'bermuda-teste-1', 'bot', 'blitz', bot['bot_number'], start, 'tc_alice', 'Bot: Teste', 'white', CLASSIC_MODES)
    repeated = conn.execute("SELECT rating FROM classic_bots WHERE username = 'tc_alice' AND mode = 'blitz' AND bot_number = ?", (bot['bot_number'],)).fetchone()['rating']
    settle_bermuda_rating(conn, 'bermuda-teste-2', 'bot', 'blitz', bot['bot_number'], after_loss, 'tc_alice', 'Bot: Teste', 'black', CLASSIC_MODES)
    after_win = conn.execute("SELECT rating FROM classic_bots WHERE username = 'tc_alice' AND mode = 'blitz' AND bot_number = ?", (bot['bot_number'],)).fetchone()['rating']
check(after_loss < start, f'bot perde rating ao ser derrotado ({start} -> {after_loss})')
check(repeated == after_loss, 'a mesma partida não conta duas vezes para o bot')
check(after_win > after_loss, f'bot ganha rating ao vencer ({after_loss} -> {after_win})')

print()
sys.exit(1 if errors else 0)
