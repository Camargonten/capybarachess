"""Testes de publicação: páginas legais, assetlinks, manifest e exclusão de conta.

    DATABASE_PATH=/tmp/store.db python3 tests/test_store_readiness.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['ANDROID_PACKAGE_NAME'] = 'br.com.capybarachess.app'
os.environ['ANDROID_SHA256_CERT_FINGERPRINTS'] = 'aa:bb:cc'

import xadrez  # noqa: E402
from core.db import get_db  # noqa: E402

app = xadrez.app
errors = []


def check(condition, label):
    print(('ok   ' if condition else 'FALHA'), label)
    if not condition:
        errors.append(label)


anon = app.test_client()
for path in ('/privacidade', '/termos', '/excluir-conta'):
    response = anon.get(path)
    check(response.status_code == 200 and b'Capybara' in response.data, f'{path} abre sem login')
links = anon.get('/.well-known/assetlinks.json').get_json()
check(links and links[0]['target']['package_name'] == 'br.com.capybarachess.app'
      and links[0]['target']['sha256_cert_fingerprints'] == ['AA:BB:CC'], 'assetlinks.json usa o pacote e o certificado configurados')
manifest = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static/manifest.webmanifest')))
sizes = {(icon['sizes'], icon['purpose']) for icon in manifest['icons']}
check(('512x512', 'any') in sizes and ('512x512', 'maskable') in sizes and ('192x192', 'any') in sizes, 'manifest com ícones PNG 192/512 e maskable')
check(anon.get('/static/icons/icon-512.png').status_code == 200, 'ícone 512 é servido')

# exclusão de conta
a, b = app.test_client(), app.test_client()
a.post('/register', json={'username': 'del_ana', 'password': 'Teste#1234'})
b.post('/register', json={'username': 'del_bob', 'password': 'Teste#1234'})
with get_db() as conn:
    conn.execute("UPDATE users SET calibrated = 1 WHERE username IN ('del_ana', 'del_bob')")
a.post('/redeem_promo', json={'code': 'adm'})
a.post('/friends/request', json={'recipient': 'del_bob'})
b.post('/friends/respond', json={'sender': 'del_ana', 'accept': True})
club = a.post('/clubs/create', json={'name': 'Clube Del', 'description': 'x', 'badge_id': 1, 'privacy': 'public'}).get_json()
game = a.post('/game/create', json={'mode': 'bot', 'color': 'white', 'time_control': '180,2', 'bot_number': 1, 'bot_rating': 500}).get_json()

check(a.post('/account/delete', json={'confirmation': 'errado', 'password': 'Teste#1234'}).status_code == 400, 'exige digitar o nome de usuário')
check(a.post('/account/delete', json={'confirmation': 'del_ana', 'password': 'senha errada#1'}).status_code == 403, 'exige a senha correta')
check(b.post('/account/delete', json={'confirmation': 'del_ana', 'password': 'Teste#1234'}).status_code == 400, 'não exclui conta de outra pessoa')
response = a.post('/account/delete', json={'confirmation': 'del_ana', 'password': 'Teste#1234'})
check(response.status_code == 200, 'exclusão aceita com nome e senha')

with get_db() as conn:
    count = lambda sql, *p: conn.execute(sql, p).fetchone()[0]
    check(count("SELECT COUNT(*) FROM users WHERE username = 'del_ana'") == 0, 'usuário removido')
    check(count("SELECT COUNT(*) FROM friend_requests WHERE sender = 'del_ana' OR recipient = 'del_ana'") == 0, 'amizades removidas')
    check(count("SELECT COUNT(*) FROM classic_bots WHERE username = 'del_ana'") == 0, 'bots Bermuda do usuário removidos')
    check(count("SELECT COUNT(*) FROM clubs WHERE leader = 'del_ana'") == 0, 'clube liderado removido')
    check(count("SELECT COUNT(*) FROM games WHERE white_user = 'del_ana' OR creator_user = 'del_ana'") == 0, 'nome some das partidas')
    check(count("SELECT COUNT(*) FROM games WHERE creator_user = 'Conta excluída'") >= 1, 'partidas ficam anonimizadas')
    check(count("SELECT COUNT(*) FROM promo_redemptions WHERE code = 'adm'") == 1, 'código adm continua marcado como usado (uso único)')
    check(count("SELECT COUNT(*) FROM promo_redemptions WHERE username = 'del_ana'") == 0, 'resgate do código não identifica mais a conta')
check(app.test_client().post('/login', json={'username': 'del_ana', 'password': 'Teste#1234'}).status_code == 401, 'login da conta excluída falha')
check(a.get('/auth/me').get_json().get('authenticated') is not True, 'sessão encerrada após excluir')

print()
sys.exit(1 if errors else 0)
