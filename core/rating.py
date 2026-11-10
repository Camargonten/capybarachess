# rating-module-v1
"""
Regras de rating do Capybara Chess (online e Bermuda).

Tudo que é número de regra está nas constantes logo abaixo: para mudar uma regra,
mude só aqui.

Fases de um rating:
  1) CALIBRAÇÃO INICIAL (só online): 2 partidas contra os bots oficiais 1 a 5.
     O rating NÃO muda na 1ª partida; ao fim da 2ª ele é definido pela tabela.
  2) SEGUNDA CALIBRAÇÃO: 5 partidas (online ranqueado e cada modo Bermuda).
     Ganhos por partida entre +20 e +100 numa vitória, perdas até -100,
     e o rating nunca cai mais que 100 pontos abaixo do rating base.
  3) FIDE: depois das 5 partidas, ganho/perda proporcional à diferença de
     rating (expectativa FIDE de 400 pontos), K=20 (K=10 a partir de 2400).
"""
import json
import math

MIN_RATING = 100            # nenhum jogador tem menos que isso
CALIB1_GAMES = 2
CALIB2_GAMES = 5
CALIB2_K = 100              # fator da 2ª calibração (limitado pelos valores abaixo)
CALIB2_MIN_WIN = 20         # menor ganho possível numa vitória
CALIB2_MAX_STEP = 100       # maior ganho/perda numa partida
CALIB2_MAX_DROP_FROM_BASE = 100   # queda máxima em relação ao rating base
OFFICIAL_BOT_NUMBERS = {1, 2, 3, 4, 5}

# 1ª calibração: ajuste sobre o rating do bot enfrentado (vale para cada bot, então é
# proporcional ao nível dele). Quanto MAIS pontos nas duas partidas, MENOS se perde em
# relação ao bot:  2 pontos -> 0 | 1,5 -> -50 | 1 -> -150 | 0,5 -> -300 | 0 -> -600.
# Regra de ouro: mais pontos NUNCA rendem menos rating (confira com validate_calibration_table).
# Chave = resultados das 2 partidas em ordem crescente (vitória=1, empate=0.5, derrota=0).
CALIB1_OFFSETS = {
    (1.0, 1.0): 0,       # venceu as duas            -> rating do bot
    (0.5, 1.0): -50,     # venceu e empatou          -> bot -50
    (0.5, 0.5): -150,    # empatou as duas (1 ponto) -> bot -150
    (0.0, 1.0): -150,    # venceu e perdeu (1 ponto) -> bot -150 (igual ao empate duplo)
    (0.0, 0.5): -300,    # perdeu e empatou          -> bot -300
    (0.0, 0.0): -600,    # perdeu as duas            -> bot -600
}


def _round(value: float) -> int:
    """Arredonda para o inteiro mais próximo; metades se afastam do zero."""
    return int(math.floor(abs(value) + 0.5)) * (1 if value >= 0 else -1)


def expected_score(rating: float, opponent_rating: float) -> float:
    diff = max(-400.0, min(400.0, float(opponent_rating) - float(rating)))
    return 1.0 / (1.0 + 10.0 ** (diff / 400.0))


def fide_k(rating: int) -> int:
    return 10 if rating >= 2400 else 20


def calibration1_rating(bot_rating: float, scores) -> int:
    """Rating definido ao fim da 1ª calibração (scores = pontos das 2 partidas)."""
    key = tuple(sorted(float(s) for s in scores))
    bot = _round(bot_rating)
    value = bot + CALIB1_OFFSETS.get(key, CALIB1_OFFSETS[(0.0, 0.0)])
    return max(MIN_RATING, value)


def validate_calibration_table() -> bool:
    """Regra de ouro: um resultado com mais pontos nunca rende menos rating que um com menos pontos."""
    groups = {}
    for (first, second), offset in CALIB1_OFFSETS.items():
        groups.setdefault(first + second, []).append(offset)
    best_below = None
    for points in sorted(groups):
        if best_below is not None and min(groups[points]) < best_below:
            return False
        best_below = max(groups[points]) if best_below is None else max(best_below, max(groups[points]))
    return True


def compute_update(rating: int, base_rating: int, calib2_games: int, opponent_rating: float, score: float) -> dict:
    """Calcula a variação de rating de UMA partida (2ª calibração ou FIDE)."""
    rating = int(rating)
    expected = expected_score(rating, opponent_rating)
    if calib2_games < CALIB2_GAMES:
        base = int(base_rating) if base_rating else rating
        raw = CALIB2_K * (score - expected)
        if score >= 1.0:
            delta = min(CALIB2_MAX_STEP, max(CALIB2_MIN_WIN, _round(raw)))
        elif score <= 0.0:
            delta = max(-CALIB2_MAX_STEP, min(0, _round(raw)))
        else:
            delta = max(-CALIB2_MAX_STEP, min(CALIB2_MAX_STEP, _round(raw)))
        floor = max(MIN_RATING, base - CALIB2_MAX_DROP_FROM_BASE)
        new_rating = max(rating + delta, min(rating, floor))
        return {
            "phase": "calib2", "step": calib2_games + 1, "total": CALIB2_GAMES,
            "delta": new_rating - rating, "new_rating": new_rating,
            "base_rating": base, "calib2_games": calib2_games + 1,
        }
    delta = _round(fide_k(rating) * (score - expected))
    new_rating = max(MIN_RATING, rating + delta)
    return {
        "phase": "fide", "step": 0, "total": 0,
        "delta": new_rating - rating, "new_rating": new_rating,
        "base_rating": int(base_rating or 0), "calib2_games": calib2_games,
    }


def preview_outcomes(rating: int, base_rating: int, calib2_games: int, opponent_rating: float) -> dict:
    """Quanto o rating varia se vencer / empatar / perder esta partida."""
    outcome = {}
    for name, score in (("win", 1.0), ("draw", 0.5), ("loss", 0.0)):
        outcome[name] = compute_update(rating, base_rating, calib2_games, opponent_rating, score)["delta"]
    first = compute_update(rating, base_rating, calib2_games, opponent_rating, 1.0)
    outcome["phase"] = first["phase"]
    outcome["step"] = first["step"]
    outcome["total"] = first["total"]
    return outcome


# ------------------------------------------------------------------ banco de dados
def _player_score(winner: str, player_color: str) -> float:
    if winner == 'draw':
        return 0.5
    return 1.0 if winner == player_color else 0.0


def _is_bot(name) -> bool:
    return bool(name) and str(name).startswith('Bot:')


def record_result(conn, game_id, username, kind, mode, old_rating, new_rating, phase, step, total):
    if not game_id:
        return
    conn.execute(
        """INSERT OR REPLACE INTO game_rating_results
           (game_id, username, kind, mode, old_rating, new_rating, delta, phase, step, total)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (game_id, username, kind, mode or '', int(old_rating), int(new_rating),
         int(new_rating) - int(old_rating), phase, int(step), int(total))
    )


def _already_recorded(conn, game_id, username, kind):
    if not game_id:
        return None
    return conn.execute(
        "SELECT delta, new_rating FROM game_rating_results WHERE game_id = ? AND username = ? AND kind = ?",
        (game_id, username, kind)
    ).fetchone()


def settle_pvp_ratings(conn, game_id, white_user, black_user, winner):
    """Rating online das duas pessoas de uma partida ranqueada entre humanos."""
    if not white_user or not black_user or _is_bot(white_user) or _is_bot(black_user) or not winner:
        return
    rows = {}
    for name in (white_user, black_user):
        rows[name] = conn.execute(
            "SELECT rating, calibrated, calib_base_rating, calib2_games FROM users WHERE username = ?", (name,)
        ).fetchone()
    if not rows[white_user] or not rows[black_user]:
        return
    if not (rows[white_user]['calibrated'] and rows[black_user]['calibrated']):
        return
    ratings = {name: rows[name]['rating'] for name in rows}
    for name, color, opponent in ((white_user, 'white', black_user), (black_user, 'black', white_user)):
        if _already_recorded(conn, game_id, name, 'online'):
            continue
        row = rows[name]
        result = compute_update(row['rating'], row['calib_base_rating'] or 0, row['calib2_games'] or 0,
                                ratings[opponent], _player_score(winner, color))
        conn.execute(
            "UPDATE users SET rating = ?, calib_base_rating = ?, calib2_games = ? WHERE username = ?",
            (result['new_rating'], result['base_rating'], result['calib2_games'], name)
        )
        record_result(conn, game_id, name, 'online', '', row['rating'], result['new_rating'],
                      result['phase'], result['step'], result['total'])


def settle_bot_calibration(conn, game_id, game_type, white_user, black_user, bot_number, bot_rating, winner):
    """1ª calibração: 2 partidas contra os bots oficiais 1 a 5. Retorna (variação, rating)."""
    if game_type != 'bot' or not winner or bot_number not in OFFICIAL_BOT_NUMBERS:
        return 0, None
    bot_is_white = _is_bot(white_user)
    username = black_user if bot_is_white else white_user
    if not username or _is_bot(username):
        return 0, None
    user = conn.execute(
        "SELECT rating, calibrated, calibration_games, calib1_results FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not user:
        return 0, None
    previous = _already_recorded(conn, game_id, username, 'online')
    if previous:
        return previous['delta'], previous['new_rating']
    if user['calibrated'] or (user['calibration_games'] or 0) >= CALIB1_GAMES:
        return 0, user['rating']

    player_color = 'black' if bot_is_white else 'white'
    try:
        results_list = json.loads(user['calib1_results'] or '[]')
    except (TypeError, ValueError):
        results_list = []
    results_list.append({"bot_rating": int(bot_rating or 0), "score": _player_score(winner, player_color)})
    played = len(results_list)
    old_rating = user['rating']

    if played < CALIB1_GAMES:
        conn.execute(
            "UPDATE users SET calibration_games = ?, calib1_results = ? WHERE username = ?",
            (played, json.dumps(results_list), username)
        )
        record_result(conn, game_id, username, 'online', '', old_rating, old_rating, 'calib1', played, CALIB1_GAMES)
        return 0, old_rating

    reference_bot = _round(sum(item["bot_rating"] for item in results_list) / len(results_list))
    new_rating = calibration1_rating(reference_bot, [item["score"] for item in results_list])
    conn.execute(
        """UPDATE users SET rating = ?, calibrated = 1, calibration_games = ?, calib1_results = ?,
                            calib_base_rating = ?, calib2_games = 0 WHERE username = ?""",
        (new_rating, played, json.dumps(results_list), new_rating, username)
    )
    record_result(conn, game_id, username, 'online', '', old_rating, new_rating, 'calib1', played, CALIB1_GAMES)
    return new_rating - old_rating, new_rating


def settle_bermuda_rating(conn, game_id, game_type, classic_mode, classic_bot_number, bot_rating,
                          white_user, black_user, winner, valid_modes):
    """Rating Bermuda (modo offline contra bots) de um modo: Bullet, Blitz ou Rápida."""
    if game_type != 'bot' or classic_mode not in valid_modes or not classic_bot_number or not winner:
        return 0
    bot_is_white = _is_bot(white_user)
    player_user = black_user if bot_is_white else white_user
    player_color = 'black' if bot_is_white else 'white'
    if not player_user or _is_bot(player_user):
        return 0
    profile = conn.execute(
        "SELECT rating, calib_base_rating, calib2_games FROM classic_profiles WHERE username = ? AND mode = ?",
        (player_user, classic_mode)
    ).fetchone()
    if not profile:
        return 0
    previous = _already_recorded(conn, game_id, player_user, 'bermuda')
    if previous:
        return previous['delta']
    result = compute_update(profile['rating'], profile['calib_base_rating'] or 0, profile['calib2_games'] or 0,
                            bot_rating or 0, _player_score(winner, player_color))
    conn.execute(
        """UPDATE classic_profiles SET rating = ?, games_played = games_played + 1,
                  calib_base_rating = ?, calib2_games = ? WHERE username = ? AND mode = ?""",
        (result['new_rating'], result['base_rating'], result['calib2_games'], player_user, classic_mode)
    )
    record_result(conn, game_id, player_user, 'bermuda', classic_mode, profile['rating'], result['new_rating'],
                  result['phase'], result['step'], result['total'])
    _settle_bermuda_bot_rating(conn, player_user, classic_mode, classic_bot_number, profile['rating'],
                               _player_score(winner, player_color))
    return result['delta']


def _settle_bermuda_bot_rating(conn, player_user, classic_mode, bot_number, player_rating_before, player_score):
    """O bot enfrentado também ganha ou perde rating (Elo comum, mesmos K da simulação dos bots)."""
    bot = conn.execute(
        "SELECT rating FROM classic_bots WHERE username = ? AND mode = ? AND bot_number = ?",
        (player_user, classic_mode, bot_number)
    ).fetchone()
    if not bot:
        return
    before = bot['rating']
    k = 8 if before >= 2500 else (14 if before >= 1800 else 28)
    expected = expected_score(before, player_rating_before)
    after = max(200, _round(before + k * ((1.0 - player_score) - expected)))
    conn.execute(
        "UPDATE classic_bots SET rating = ? WHERE username = ? AND mode = ? AND bot_number = ?",
        (after, player_user, classic_mode, bot_number)
    )


def ensure_bermuda_profiles(conn, username, valid_modes):
    """Garante o rating Bermuda (Bullet/Blitz/Rápida) de um jogador, com a mesma semente usada no perfil clássico."""
    user = conn.execute("SELECT rating, calibrated FROM users WHERE username = ?", (username,)).fetchone()
    seed_rating = user['rating'] if user and user['calibrated'] else 1200
    for mode in valid_modes:
        conn.execute("INSERT OR IGNORE INTO classic_profiles (username, mode, rating) VALUES (?, ?, ?)",
                     (username, mode, seed_rating))


def settle_bermuda_pvp_rating(conn, game_id, classic_mode, white_user, black_user, winner, valid_modes):
    """Partida Bermuda entre dois jogadores: o rating Bermuda do ritmo (Bullet/Blitz/Rápida) dos dois é atualizado."""
    if classic_mode not in valid_modes or not winner or not white_user or not black_user:
        return 0
    if _is_bot(white_user) or _is_bot(black_user):
        return 0
    for user in (white_user, black_user):
        ensure_bermuda_profiles(conn, user, valid_modes)
    profiles = {
        user: conn.execute(
            "SELECT rating, calib_base_rating, calib2_games FROM classic_profiles WHERE username = ? AND mode = ?",
            (user, classic_mode)
        ).fetchone()
        for user in (white_user, black_user)
    }
    deltas = {}
    for user, color in ((white_user, 'white'), (black_user, 'black')):
        previous = _already_recorded(conn, game_id, user, 'bermuda')
        if previous:
            deltas[user] = previous['delta']
            continue
        opponent = black_user if user == white_user else white_user
        profile = profiles[user]
        # Os dois são atualizados com o rating que o adversário tinha ANTES da partida.
        result = compute_update(profile['rating'], profile['calib_base_rating'] or 0, profile['calib2_games'] or 0,
                                profiles[opponent]['rating'], _player_score(winner, color))
        conn.execute(
            """UPDATE classic_profiles SET rating = ?, games_played = games_played + 1,
                      calib_base_rating = ?, calib2_games = ? WHERE username = ? AND mode = ?""",
            (result['new_rating'], result['base_rating'], result['calib2_games'], user, classic_mode)
        )
        record_result(conn, game_id, user, 'bermuda', classic_mode, profile['rating'], result['new_rating'],
                      result['phase'], result['step'], result['total'])
        deltas[user] = result['delta']
    return deltas.get(white_user, 0)


def describe_ratings(conn, game_type, classic_mode, bot_number, bot_rating, white_user, black_user, current_user):
    """Ratings que o cabeçalho da partida deve mostrar para quem está jogando."""
    if current_user not in (white_user, black_user):
        return {}
    opponent = black_user if current_user == white_user else white_user
    user = conn.execute(
        "SELECT rating, calibrated, calibration_games, calib_base_rating, calib2_games FROM users WHERE username = ?",
        (current_user,)
    ).fetchone()
    if not user:
        return {}
    if classic_mode:
        profile = conn.execute(
            "SELECT rating, calib_base_rating, calib2_games FROM classic_profiles WHERE username = ? AND mode = ?",
            (current_user, classic_mode)
        ).fetchone()
        opp_rating = bot_rating
        if game_type == 'pvp' and opponent:
            opp_profile = conn.execute(
                "SELECT rating FROM classic_profiles WHERE username = ? AND mode = ?", (opponent, classic_mode)
            ).fetchone()
            opp_rating = opp_profile['rating'] if opp_profile else None
        return {
            "kind": "bermuda", "mode": classic_mode,
            "my_rating": profile['rating'] if profile else user['rating'],
            "opp_rating": opp_rating,
            "calibrating": bool(profile) and (profile['calib2_games'] or 0) < CALIB2_GAMES,
        }
    if game_type == 'bot':
        calibrating = (not user['calibrated']) and bot_number in OFFICIAL_BOT_NUMBERS
        return {
            "kind": "online", "mode": "", "my_rating": user['rating'], "opp_rating": bot_rating,
            "calibrating": calibrating,
            "calibration_step": (user['calibration_games'] or 0) + 1 if calibrating else 0,
        }
    opp_row = conn.execute("SELECT rating FROM users WHERE username = ?", (opponent,)).fetchone() if opponent else None
    return {
        "kind": "online", "mode": "", "my_rating": user['rating'],
        "opp_rating": opp_row['rating'] if opp_row else None,
        "calibrating": bool(user['calibrated']) and (user['calib2_games'] or 0) < CALIB2_GAMES,
    }


def get_rating_summary(conn, game_id, username, prefer_kind=None):
    rows = conn.execute(
        "SELECT kind, mode, old_rating, new_rating, delta, phase, step, total FROM game_rating_results "
        "WHERE game_id = ? AND username = ?", (game_id, username)
    ).fetchall()
    if not rows:
        return None
    chosen = next((r for r in rows if r['kind'] == prefer_kind), rows[0]) if prefer_kind else rows[0]
    return {
        "kind": chosen['kind'], "mode": chosen['mode'], "old_rating": chosen['old_rating'],
        "new_rating": chosen['new_rating'], "delta": chosen['delta'], "phase": chosen['phase'],
        "step": chosen['step'], "total": chosen['total'],
    }
