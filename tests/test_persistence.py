"""Testes de persistência: retomada de partida, restauração pelo navegador e congelamento de relógios.

    DATABASE_PATH=/tmp/persist.db python3 tests/test_persistence.py
    DATABASE_URL=postgresql://... python3 tests/test_persistence.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
from core.db import HEARTBEAT_KEY, freeze_clocks_after_downtime, get_db  # noqa: E402

app = xadrez.app
errors = []


def check(condition, label):
    print(('ok   ' if condition else 'FALHA'), label)
    if not condition:
        errors.append(label)


client = app.test_client()
client.post('/register', json={'username': 'persist_qa', 'password': 'Teste#1234'})
with get_db() as conn:
    conn.execute("UPDATE users SET calibrated = 1, rating = 1500 WHERE username = 'persist_qa'")

check(client.get('/game/active').get_json()['game_id'] is None, 'sem partida ativa no começo')

created = client.post('/game/create', json={'mode': 'bot', 'color': 'white', 'time_control': '600,0',
                                            'bot_number': 1, 'bot_rating': 500}).get_json()
gid = created['game_id']
check(client.get('/game/active').get_json()['game_id'] == gid, '/game/active devolve a partida em andamento')
state = client.get(f'/game/{gid}/state').get_json()
check(state['player_color'] == 'white' and state['status'] == 'active', 'estado da partida retomável')

# congelamento de relógios depois de downtime
with get_db() as conn:
    conn.execute("UPDATE games SET last_move_time = ? WHERE id = ?", (time.time() - 3600, gid))
    conn.execute("INSERT INTO server_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (HEARTBEAT_KEY, repr(time.time() - 3600)))
frozen = freeze_clocks_after_downtime()
with get_db() as conn:
    last_move = conn.execute("SELECT last_move_time FROM games WHERE id = ?", (gid,)).fetchone()['last_move_time']
check(3590 < frozen < 3700, f'downtime de ~1h detectado ({frozen:.0f}s)')
check(abs(time.time() - last_move) < 30, 'relógio da partida voltou ao instante em que foi deixada')

# restauração a partir do localStorage
client.post(f'/game/{gid}/resign', json={})
restore_payload = {'history': ['e2e4', 'e7e5', 'g1f3'], 'bot_number': 2, 'color': 'white', 'time_control': '180,2',
                   'white_time': 150.5, 'black_time': 160.0}
bad = client.post('/game/restore', json={**restore_payload, 'history': ['e2e5']})
check(bad.status_code == 400, 'restauração recusa lances ilegais')
bad = client.post('/game/restore', json={**restore_payload, 'bot_number': 40})
check(bad.status_code == 400, 'restauração recusa bot fora da lista')
restored = client.post('/game/restore', json=restore_payload)
check(restored.status_code == 200, 'restauração aceita partida válida')
new_id = restored.get_json().get('game_id')
if new_id:
    restored_state = client.get(f'/game/{new_id}/state').get_json()
    check(len(restored_state['history']) >= 3 and restored_state['status'] == 'active', 'partida restaurada continua ativa')
    check(restored_state['bot_rating'] == 1000, 'rating do bot vem do servidor, não do navegador')
    before = client.get('/auth/me').get_json()
    client.post(f'/game/{new_id}/resign', json={})
    after = client.get('/auth/me').get_json()
    check(before['rating'] == after['rating'] and before['coins'] == after['coins'], 'partida restaurada não altera rating nem moedas')
    check(client.post('/game/restore', json=restore_payload).status_code == 200, 'restaura de novo após encerrar')

print()
sys.exit(1 if errors else 0)
