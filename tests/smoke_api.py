"""Teste de fumaça da API: percorre as rotas principais e falha se alguma responder 5xx.

Roda contra o banco configurado no ambiente (SQLite por padrão; PostgreSQL com DATABASE_URL):

    DATABASE_PATH=/tmp/smoke.db python3 tests/smoke_api.py
    DATABASE_URL=postgresql://usuario@host/banco python3 tests/smoke_api.py

Use um banco VAZIO/descartável: o teste cria contas "smoke_*".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
from core.db import get_db  # noqa: E402

app = xadrez.app
failures = []
PASSWORD = 'Teste#1234'


def call(client, method, path, label=None, expect=None, **kwargs):
    response = getattr(client, method)(path, **kwargs)
    body = response.get_json(silent=True)
    status = response.status_code
    name = label or f"{method.upper()} {path}"
    bad = status >= 500 or (expect is not None and status not in (expect if isinstance(expect, tuple) else (expect,)))
    print(f"{'FALHA' if bad else 'ok   '} {status} {name}" + (f" -> {body.get('error')}" if bad and isinstance(body, dict) else ''))
    if bad:
        failures.append(name)
    return body or {}


def register(name):
    client = app.test_client()
    call(client, 'post', '/register', f'registrar {name}', 200, json={'username': name, 'password': PASSWORD})
    return client


def link_google(name):
    with get_db() as conn:
        conn.execute("UPDATE users SET google_sub = ?, google_email = ?, calibrated = 1, rating = 1500 WHERE username = ?",
                     (f"sub-{name}", f"{name}@example.com", name))


alice, bob = register('smoke_alice'), register('smoke_bob')
link_google('smoke_alice')
link_google('smoke_bob')

call(alice, 'post', '/login', 'login errado', 401, json={'username': 'smoke_alice', 'password': 'errada#1'})
call(alice, 'post', '/login', 'login', 200, json={'username': 'smoke_alice', 'password': PASSWORD})
call(alice, 'get', '/auth/me', expect=200)
call(alice, 'get', '/health', expect=200)
call(alice, 'get', '/auth/config', expect=200)
call(alice, 'post', '/presence/ping', expect=(200, 204), json={})
call(bob, 'post', '/presence/ping', expect=(200, 204), json={})

# perfil e loja
call(alice, 'post', '/profile/settings', expect=200, json={'bgm_choice': 2, 'confirm_moves': True, 'colorblind_mode': False})
call(alice, 'post', '/profile/bio', json={'bio': 'ola mundo'})
call(alice, 'post', '/profile/name', json={'display_name': 'Alice Smoke'})
call(alice, 'post', '/redeem_promo', json={'code': 'adm'})
call(alice, 'post', '/purchase', json={'item': 'frame_oak'})
call(alice, 'post', '/profile/equip', json={'item': 'frame_oak'})
call(alice, 'get', '/missions', expect=200)
call(alice, 'post', '/missions/claim', json={'mission_id': 1})
call(alice, 'post', '/missions/claim_all', json={})
call(alice, 'get', '/notifications', expect=200)
call(alice, 'get', '/ranking/online', expect=200)
call(alice, 'get', '/users/search?q=smoke', expect=200)
call(alice, 'get', '/players/smoke_bob', expect=200)

# Bermuda e bots
call(alice, 'get', '/classic/ranking?username=smoke_alice&language=pt&mode=blitz', expect=200)
mm = call(alice, 'post', '/classic/matchmake', expect=200, json={'mode': 'blitz', 'min_offset': -100, 'max_offset': 200})
bot = mm.get('bot', {})
game = call(alice, 'post', '/game/create', 'partida Bermuda', 200, json={
    'mode': 'bot', 'color': 'white', 'time_control': '600,0', 'bot_number': bot.get('number', 100),
    'bot_rating': bot.get('rating', 800), 'classic_mode': 'blitz', 'language': 'pt'})
gid = game.get('game_id')
if gid:
    call(alice, 'get', f'/game/{gid}/state', expect=200)
    call(alice, 'post', f'/game/{gid}/move', 'lance e2e4', 200, json={'move': 'e2e4'})
    call(alice, 'post', f'/game/{gid}/draw_offer', json={'action': 'offer'})
    call(alice, 'post', f'/game/{gid}/resign', 'desistir', (200, 400), json={})  # o bot pode aceitar o empate antes (aleatório)
    call(alice, 'post', '/classic/rematch', json={'mode': 'blitz'})
official = call(alice, 'post', '/game/create', 'partida bot oficial', 200, json={
    'mode': 'bot', 'color': 'black', 'time_control': '180,2', 'bot_number': 702, 'bot_rating': 2500})
if official.get('game_id'):
    call(alice, 'post', f"/game/{official['game_id']}/abort", json={})
call(alice, 'post', '/bot_move', json={'fen': 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'bot_rating': 800})
call(alice, 'post', '/analyze_position', json={'fen': 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'})

# amigos, mensagens, presentes
call(alice, 'post', '/friends/request', expect=200, json={'recipient': 'smoke_bob'})
call(bob, 'post', '/friends/respond', expect=200, json={'sender': 'smoke_alice', 'accept': True})
call(alice, 'get', '/friends', expect=200)
call(alice, 'get', '/friends/active_games', expect=200)
call(alice, 'post', '/messages', json={'recipient': 'smoke_bob', 'content': 'oi'})
call(bob, 'get', '/messages?with=smoke_alice')
with get_db() as conn:
    conn.execute("UPDATE users SET coins = 5000 WHERE username = 'smoke_alice'")
call(alice, 'post', '/gifts', expect=200, json={'recipient': 'smoke_bob', 'item_id': 'frame_bronze', 'message': 'presente!'})
call(bob, 'get', '/notifications', expect=200)
with get_db() as conn:
    gift_row = conn.execute("SELECT id FROM gift_requests ORDER BY id DESC LIMIT 1").fetchone()
if gift_row:
    call(bob, 'post', '/gifts/respond', expect=200, json={'gift_id': gift_row['id'], 'accept': True})

# clubes
club = call(alice, 'post', '/clubs/create', expect=200, json={'name': 'Clube Smoke', 'description': 'teste', 'badge_id': 2, 'privacy': 'public'})
club_id = club.get('club_id') or club.get('id')
call(alice, 'get', '/clubs/list', expect=200)
if club_id:
    call(bob, 'post', '/clubs/join', json={'club_id': club_id})
    call(bob, 'post', f'/clubs/{club_id}/message', json={'content': 'ola clube'})
    call(alice, 'get', f'/clubs/{club_id}', expect=200)
    call(alice, 'post', f'/clubs/{club_id}/challenge', json={'time_control': '180,2'})
    call(bob, 'post', f'/clubs/{club_id}/leave', json={})

# online (PvP): fila ranqueada, revanche, desafio direto
call(alice, 'post', '/matchmaking/ranked/join', expect=200, json={'time_control': '180,2', 'min_offset': -300, 'max_offset': 100000})
call(bob, 'post', '/matchmaking/ranked/join', expect=200, json={'time_control': '180,2', 'min_offset': -300, 'max_offset': 100000})
call(alice, 'get', '/matchmaking/ranked/status', expect=200)
status = call(bob, 'get', '/matchmaking/ranked/status', expect=200)
pvp_id = status.get('game_id')
if pvp_id:
    state = call(alice, 'get', f'/game/{pvp_id}/state', expect=200)
    mover = alice if state.get('white_user') == 'smoke_alice' else bob
    other = bob if mover is alice else alice
    call(mover, 'post', f'/game/{pvp_id}/move', 'pvp lance', 200, json={'move': 'e2e4'})
    call(other, 'post', f'/game/{pvp_id}/move', 'pvp lance preto', 200, json={'move': 'e7e5'})
    call(mover, 'post', f'/game/{pvp_id}/takeback', json={'action': 'request'})
    call(other, 'post', f'/game/{pvp_id}/resign', 'pvp desistir', 200, json={})
    call(alice, 'post', f'/game/{pvp_id}/rematch', json={})
    call(bob, 'get', '/notifications', expect=200)
call(alice, 'post', '/challenges/direct', json={'recipient': 'smoke_bob', 'time_control': '180,2'})
call(bob, 'get', '/challenges/direct', expect=200)
call(alice, 'post', '/matchmaking/ranked/leave', expect=200, json={})
call(alice, 'get', '/ranking/online', expect=200)
call(bob, 'post', '/logout', expect=200, json={})

print()
if failures:
    print(f"{len(failures)} chamada(s) com falha:", failures)
    sys.exit(1)
print("Tudo certo: nenhuma rota respondeu 5xx.")
