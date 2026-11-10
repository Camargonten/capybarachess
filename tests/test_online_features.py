"""Recursos online entre jogadores: empate com aceitar/recusar, partida por link (Amistosa, Bermuda ou
Rankeada), fila que expira sozinha, faixa de Elo com infinito para baixo, chat da partida e histórico com replay/PGN no perfil.

Usa partidas PvP (sem Stockfish). Rode contra um banco VAZIO/descartável:

    DATABASE_PATH=/tmp/online.db python3 tests/test_online_features.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xadrez  # noqa: E402
from core.constants import CLASSIC_MODES  # noqa: E402
from core.db import get_db  # noqa: E402
from core.rating import ensure_bermuda_profiles  # noqa: E402
from core.security import limiter  # noqa: E402

app = xadrez.app
errors = []
PASSWORD = 'Teste#1234'


def check(condition, label):
    print(('ok   ' if condition else 'FALHA'), label)
    if not condition:
        errors.append(label)


def register(name, rating):
    client = app.test_client()
    client.post('/register', json={'username': name, 'password': PASSWORD})
    with get_db() as conn:
        conn.execute("UPDATE users SET google_sub = ?, google_email = ?, calibrated = 1, rating = ? WHERE username = ?",
                     (f"sub-{name}", f"{name}@example.com", rating, name))
    return client


alice, bob = register('of_alice', 1500), register('of_bob', 1000)


def link_game(creator, joiner, **options):
    """Cria uma partida por link e o convidado entra; devolve (id, resposta da criação)."""
    limiter._requests.clear()
    created = creator.post('/game/create', json={'mode': 'pvp', 'color': 'white', 'time_control': '180,2', **options}).get_json()
    if not created.get('success'):
        return None, created
    joiner.post(f"/game/{created['game_id']}/join", json={})
    return created['game_id'], created


def classic_rating(name, mode='blitz'):
    with get_db() as conn:
        ensure_bermuda_profiles(conn, name, CLASSIC_MODES)
        return conn.execute("SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (name, mode)).fetchone()['rating']


def official_rating(name):
    with get_db() as conn:
        return conn.execute("SELECT rating FROM users WHERE username = ?", (name,)).fetchone()['rating']


# 1) empate: propor, recusar, propor de novo e aceitar
game_id, _ = link_game(alice, bob, rated=False)
check(game_id is not None, 'partida por link criada e aceita')
alice.post(f'/game/{game_id}/draw_offer', json={'action': 'offer'})
state = bob.get(f'/game/{game_id}/state').get_json()
check(state.get('draw_offered_by') == 'of_alice', 'adversário vê quem propôs o empate no estado da partida')
bob.post(f'/game/{game_id}/draw_offer', json={'action': 'decline'})
state = alice.get(f'/game/{game_id}/state').get_json()
check(state.get('draw_offered_by') is None and state.get('status') == 'active', 'recusar limpa a proposta e a partida segue')
alice.post(f'/game/{game_id}/draw_offer', json={'action': 'offer'})
data = bob.post(f'/game/{game_id}/draw_offer', json={'action': 'accept'}).get_json()
check(data.get('status') == 'draw_agreed', 'aceitar a proposta encerra em empate sem o outro apertar de novo')
state = alice.get(f'/game/{game_id}/state').get_json()
check(state.get('status') == 'draw_agreed' and state.get('winner') == 'draw', 'quem propôs vê o empate no estado')

# 2) partida por link Amistosa não mexe em nenhum rating
before_c, before_o = classic_rating('of_alice'), official_rating('of_alice')
game_id, created = link_game(alice, bob, rated=False)
check(created.get('rating_kind') == 'friendly', 'link amistoso identificado como amistoso')
bob.post(f'/game/{game_id}/resign', json={})
check(classic_rating('of_alice') == before_c and official_rating('of_alice') == before_o, 'amistosa não altera rating Bermuda nem oficial')

# 3) partida por link Bermuda atualiza o rating Bermuda dos dois (e não o oficial)
game_id, created = link_game(alice, bob, rated=False, bermuda=True)
check(created.get('rating_kind') == 'bermuda', 'link Bermuda identificado')
state = alice.get(f'/game/{game_id}/state').get_json()
check(state.get('classic_mode') == 'blitz' and not state.get('rated'), 'estado mostra partida Bermuda do ritmo (blitz) e não rankeada')
a0, b0, o0 = classic_rating('of_alice'), classic_rating('of_bob'), official_rating('of_alice')
bob.post(f'/game/{game_id}/resign', json={})
a1, b1 = classic_rating('of_alice'), classic_rating('of_bob')
check(a1 > a0 and b1 < b0, f'vencedor sobe e perdedor desce no rating Bermuda ({a0}->{a1}, {b0}->{b1})')
check(official_rating('of_alice') == o0, 'rating oficial não muda em partida Bermuda')
state = alice.get(f'/game/{game_id}/state').get_json()
check((state.get('display_ratings') or {}).get('kind') == 'bermuda', 'cabeçalho mostra rating Bermuda dos dois')

# 4) partida por link Rankeada atualiza o rating oficial
o_a0, o_b0 = official_rating('of_alice'), official_rating('of_bob')
game_id, created = link_game(alice, bob, rated=True)
check(created.get('rating_kind') == 'ranked', 'link rankeado identificado')
bob.post(f'/game/{game_id}/resign', json={})
check(official_rating('of_alice') > o_a0 and official_rating('of_bob') < o_b0, 'rankeada por link atualiza o rating oficial')

# 5) Bermuda exige ritmo de Bullet/Blitz/Rápida
limiter._requests.clear()
bad = alice.post('/game/create', json={'mode': 'pvp', 'color': 'white', 'time_control': '60,0', 'rated': False, 'bermuda': 'sim'})
check(bad.status_code == 400, 'campo Bermuda inválido é recusado')

# 6) fila rankeada: sem consultar o status, a pessoa sai sozinha
limiter._requests.clear()
with get_db() as conn:
    conn.execute("DELETE FROM ranked_queue")
bob.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -100, 'max_offset': 100000})
with get_db() as conn:
    conn.execute("UPDATE ranked_queue SET heartbeat_at = datetime('now', '-60 seconds') WHERE username = 'of_bob'")
data = alice.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -9999, 'max_offset': 200}).get_json()
check(data.get('status') == 'queued', 'quem parou de consultar a fila não é pareado')
with get_db() as conn:
    gone = conn.execute("SELECT COUNT(*) AS n FROM ranked_queue WHERE username = 'of_bob'").fetchone()['n']
check(gone == 0, 'entrada antiga da fila foi removida automaticamente')
alice.post('/matchmaking/ranked/leave', json={})

# 7) infinito para baixo: alice (1500) busca de qualquer rating abaixo até +200 e acha bob (1000) na fila
limiter._requests.clear()
bob.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -100, 'max_offset': 100000})
data = alice.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -9999, 'max_offset': 200}).get_json()
check(data.get('status') == 'matched', 'infinito para baixo encontra adversário muito abaixo do Elo')
if data.get('game_id'):
    alice.post(f"/game/{data['game_id']}/resign", json={})
limiter._requests.clear()
bob.post('/matchmaking/ranked/leave', json={})
bob.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -100, 'max_offset': 100000})
data = alice.post('/matchmaking/ranked/join', json={'time_control': '180,2', 'min_offset': -300, 'max_offset': 200}).get_json()
check(data.get('status') == 'queued', 'faixa normal (-300 a +200) não pega adversário 500 pontos abaixo')
alice.post('/matchmaking/ranked/leave', json={})
bob.post('/matchmaking/ranked/leave', json={})

# 8) chat da partida: só os dois jogadores conversam
carol = register('of_carol', 1200)
game_id, _ = link_game(alice, bob, rated=False)
limiter._requests.clear()
check(alice.post(f'/game/{game_id}/chat', json={'message': 'Boa sorte!'}).status_code == 200, 'jogador envia mensagem no chat')
check(bob.post(f'/game/{game_id}/chat', json={'message': 'Valeu \x00\x07 e boa!'}).status_code == 200, 'adversário responde no chat')
messages = alice.get(f'/game/{game_id}/chat').get_json()['messages']
check([m['sender'] for m in messages] == ['of_alice', 'of_bob'] and messages[1]['message'] == 'Valeu e boa!',
      'os dois veem as mensagens em ordem, sem caracteres de controle')
last_id = messages[0]['id']
check([m['message'] for m in bob.get(f'/game/{game_id}/chat?after={last_id}').get_json()['messages']] == ['Valeu e boa!'],
      'consulta com "after" devolve só as mensagens novas')
check(carol.get(f'/game/{game_id}/chat').status_code == 403, 'quem não joga não lê o chat')
check(carol.post(f'/game/{game_id}/chat', json={'message': 'oi'}).status_code == 403, 'quem não joga não escreve no chat')
check(alice.post(f'/game/{game_id}/chat', json={'message': 'x' * 201}).status_code == 400, 'mensagem acima de 200 caracteres é recusada')
check(alice.post(f'/game/{game_id}/chat', json={'message': '   '}).status_code == 400, 'mensagem vazia é recusada')
check(app.test_client().get(f'/game/{game_id}/chat').status_code == 401, 'sem login não há chat')
bob.post(f'/game/{game_id}/resign', json={})
check(alice.post(f'/game/{game_id}/chat', json={'message': 'gg'}).status_code == 200, 'chat continua depois do fim da partida (gg)')

# 9) histórico no perfil e replay com PGN
limiter._requests.clear()
game_id, _ = link_game(alice, bob, rated=False, bermuda=True)
check(alice.get(f'/game/{game_id}/replay').status_code == 409, 'partida em andamento ainda não tem replay')
alice.post(f'/game/{game_id}/move', json={'move': 'e2e4'})
bob.post(f'/game/{game_id}/move', json={'move': 'e7e5'})
bob.post(f'/game/{game_id}/resign', json={})
profile = alice.get('/players/of_alice').get_json()
entry = next((item for item in profile['history'] if item.get('game_id') == game_id), None)
check(entry is not None and entry['result'] == 'win' and entry['kind'] == 'bermuda' and entry['opponent'] == 'of_bob',
      'perfil lista a partida com adversário, resultado e tipo (Bermuda)')
replay = carol.get(f'/game/{game_id}/replay').get_json()
check(replay.get('moves') == ['e4', 'e5'] and len(replay.get('fens', [])) == 3, 'replay devolve lances (SAN) e uma posição por lance')
check('[Result "1-0"]' in replay.get('pgn', '') and '1. e4 e5' in replay.get('pgn', '') and '[White "of_alice"]' in replay.get('pgn', ''),
      'PGN completo com cabeçalhos e lances')
check(app.test_client().get(f'/game/{game_id}/replay').status_code == 401, 'replay exige login')
with get_db() as conn:
    conn.execute("INSERT INTO games (id, white_user, black_user, creator_user, game_type, status, winner, history) "
                 "VALUES ('bot-replay-1', 'of_alice', 'Bot: Teste', 'of_alice', 'bot', 'resigned', 'white', '[]')")
    conn.execute("INSERT INTO games (id, white_user, black_user, creator_user, game_type, status, history) "
                 "VALUES ('abort-1', 'of_alice', 'of_bob', 'of_alice', 'pvp', 'aborted', '[]')")
check(carol.get('/game/bot-replay-1/replay').status_code == 403, 'replay de partida contra bot é só dos jogadores')
check(alice.get('/game/bot-replay-1/replay').status_code == 200, 'o dono vê o replay da partida contra bot')
profile = alice.get('/players/of_alice').get_json()
aborted = next((item for item in profile['history'] if item.get('game_id') == 'abort-1'), None)
check(aborted is not None and aborted['result'] == 'aborted', 'partida abortada aparece como Abortada (não como derrota)')
check(profile['stats']['losses'] == profile['stats']['played'] - profile['stats']['wins'] - profile['stats']['draws'] and
      profile['stats']['played'] == len([i for i in profile['history'] if i['result'] != 'aborted']),
      'estatísticas ignoram partidas abortadas')

print()
sys.exit(1 if errors else 0)
