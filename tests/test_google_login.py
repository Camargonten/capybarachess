"""Teste do login com Google sem acessar o Google: simula o retorno do OAuth (callback) e confere as regras.

    DATABASE_PATH=/tmp/google.db python3 tests/test_google_login.py

Não prova que as credenciais do Google Cloud estão corretas (isso só se testa clicando em
"Continuar com Google" com GOOGLE_CLIENT_ID/SECRET reais), mas garante a lógica do servidor.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
from core.db import get_db  # noqa: E402

app = xadrez.app
google = xadrez.oauth.google
errors = []


def check(condition, label):
    print(('ok   ' if condition else 'FALHA'), label)
    if not condition:
        errors.append(label)


def fake_token(profile):
    google.authorize_access_token = lambda: {"userinfo": profile}


def row(sql, params=()):
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()


# 1) primeiro login Google cria conta nova, com bandeira vinda do idioma da conta Google
fake_token({"sub": "g-111", "email": "ana@example.com", "email_verified": True, "name": "Ana Souza", "locale": "pt-BR"})
client = app.test_client()
response = client.get('/auth/google/callback')
check(response.status_code == 302 and response.headers['Location'].endswith('/'), 'callback redireciona para o jogo')
user = row("SELECT username, country_code, country_locked, google_email FROM users WHERE google_sub = ?", ('g-111',))
check(user is not None and user['google_email'] == 'ana@example.com', 'conta criada com o e-mail do Google')
check(user is not None and user['country_code'] == 'BR' and user['country_locked'] == 1, 'bandeira BR fixada a partir do Google')
me = client.get('/auth/me').get_json()
check(me.get('username') == (user['username'] if user else None), 'sessão aberta depois do login Google')

# 2) mesmo Google de novo não duplica a conta
other = app.test_client()
other.get('/auth/google/callback')
check(row("SELECT COUNT(*) AS n FROM users WHERE google_sub = ?", ('g-111',))['n'] == 1, 'segundo login Google reaproveita a conta')

# 3) e-mail não verificado é recusado
fake_token({"sub": "g-222", "email": "x@example.com", "email_verified": False})
check(app.test_client().get('/auth/google/callback').status_code == 403, 'e-mail não verificado é recusado')

# 4) conta de senha vincula o Google (mantém nick) e a bandeira fica fixa
legacy = app.test_client()
legacy.post('/register', json={'username': 'conta senha', 'password': 'Teste#1234'})
fake_token({"sub": "g-333", "email": "senha@example.com", "email_verified": True, "name": "Senha", "locale": "en-US"})
legacy.get('/auth/google/callback')
linked = row("SELECT google_sub, country_code, country_locked FROM users WHERE username = ?", ('conta senha',))
check(linked['google_sub'] == 'g-333' and linked['country_code'] == 'US' and linked['country_locked'] == 1, 'conta com senha vinculou o Google e fixou a bandeira')

# 5) o mesmo Google não pode ser vinculado a outra conta
second = app.test_client()
second.post('/register', json={'username': 'outra conta', 'password': 'Teste#1234'})
response = second.get('/auth/google/callback')
check('google_already_linked' in response.headers.get('Location', ''), 'Google já vinculado não é reutilizado em outra conta')

# 6) falha do OAuth devolve erro e não abre sessão
def broken():
    raise RuntimeError('token inválido')
google.authorize_access_token = broken
check(app.test_client().get('/auth/google/callback').status_code == 400, 'falha na validação do Google devolve 400')

print()
sys.exit(1 if errors else 0)
