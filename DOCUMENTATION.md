# 📜 Documentação Oficial da Arquitetura & Segurança - Capybara Chess

## 1. Visão Geral do Sistema & Clean Architecture
O **Capybara Chess** é uma plataforma de xadrez full-stack de alto desempenho construída em Python (Flask) e Vanilla JS/CSS moderno, com suporte nativo a partidas online (PvP) e offline contra bots simulados pelo **Stockfish**.

O backend foi projetado segundo os princípios de **Clean Architecture** e **Separação de Responsabilidades (SoC)**, estruturado em camadas desacopladas:
```
capybara-chess/
├── core/
│   ├── config.py         # Configurações de ambiente, caminhos e segredos (.env)
│   ├── db.py             # Abstração de banco de dados, conexão com WAL mode e PRAGMA de alta concorrência
│   ├── security.py       # RateLimiter thread-safe, sanitização de inputs e Security Headers (OWASP)
│   ├── engine.py         # Motor Stockfish isolado com thread locks, regras FIDE e tempo de reflexão
│   └── constants.py      # Constantes de domínio (itens da loja, cupons, selos de bot, brasões)
├── blueprints/
│   ├── auth.py           # Autenticação, registro, login, OAuth Google e perfil
│   ├── game.py           # Gestão autoritativa de partidas, lances FIDE, relógio e timeouts
│   ├── social.py         # Ranking online, pesquisa, amigos, chat e sistema de clubes
│   ├── user.py           # Cosméticos, inventário, cupons promocionais, missões e calibração
│   └── analysis.py       # Análise tática com avaliação de centipawns e classificação de lances
├── static/
│   ├── pieces/           # 12 peças SVG locais oficiais (independência de CDNs e prevenção de tela preta)
│   ├── sw.js             # Service Worker otimizado com política Network-First para navegação
│   └── manifest.webmanifest
├── templates/
│   └── index.html/index.html # Frontend responsivo estilo Chess.com com Click-to-Move e Drag-and-Drop
├── xadrez.py             # Application Factory (create_app) compatível com Gunicorn e WSGI
├── DOCUMENTATION.md      # Esta documentação técnica
├── .env                  # Segredos locais protegidos (ignorado no git)
├── .env.example          # Modelo seguro de variáveis para produção
└── .gitignore            # Blindagem de arquivos locais e caches
```

---

## 2. Hardening de Cibersegurança & OWASP Top 10

### 2.1. Proteção contra Injeção (SQLi, XSS, Path Traversal)
- **Consultas Parametrizadas:** Valores de entrada devem ser enviados por parâmetros SQL (`?`); identificadores dinâmicos, como colunas de idioma, devem vir de listas permitidas. Isso reduz o risco de SQL injection, mas não substitui revisão contínua nem representa uma certificação de segurança.
- **Sanitização de Inputs:**
  - Nomes de usuário: validação via expressão regular `^[A-Za-z0-9_ -]+$` entre 3 e 25 caracteres.
  - Notação UCI: regex `^[a-h][1-8][a-h][1-8][qrbn]?$` com validação estrita no `python-chess`.
  - Posições FEN: validadas com instanciação no motor antes de qualquer operação.
  - Mensagens e textos: escape de HTML (`escapeHtml`) no frontend e truncamento de tamanho no backend.
- **Prevenção de Path Traversal:** Arquivos estáticos servidos via caminhos canônicos e absolutos.

### 2.2. Autenticação, Gestão de Sessões & Passwords
- **Armazenamento de Senhas:** Hashing com `scrypt` ou `pbkdf2:sha256` com salts aleatórios seguros via Werkzeug.
- **Cadastro e privilégios:** Novas contas recebem 100 moedas e não são promovidas a administradoras por serem as primeiras. A senha local exige de 7 a 128 caracteres e pelo menos um símbolo; a interface mostra um aviso amigável da capivara quando a senha ainda não cumpre esses critérios. O código promocional `adm` pode desbloquear o catálogo da loja para uma única conta; ele não concede privilégios administrativos.
- **Segurança de Cookies de Sessão:**
  - `SESSION_COOKIE_HTTPONLY = True` (proteção contra roubo de sessão via XSS).
  - `SESSION_COOKIE_SAMESITE = 'Lax'` (proteção contra ataques CSRF).
  - `SESSION_COOKIE_SECURE = True` em ambiente de produção HTTPS.
- **Validação de Posse de Conta:** O middleware `before_request` verifica rigorosamente a correspondência entre o usuário da sessão e o recurso requisitado em todos os endpoints autenticados.
- **Identidade online e bandeira do perfil:** partidas PvP, fila ranqueada, desafios diretos/de clube e revanche exigem uma conta Google vinculada; a validação é repetida no backend. A bandeira é preenchida automaticamente uma única vez a partir da região (`locale`, por exemplo `pt-BR`) informada pelo Google — isso indica a região da preferência de idioma, não geolocalização ou nacionalidade. Como esse campo pode não trazer região de país, nesses casos o perfil fica sem bandeira; o usuário não pode escolher nem editar esse valor. Uma migração única remove bandeiras escolhidas manualmente anteriormente para que possam ser recalculadas pela conta Google.

### 2.3. Proteção contra Negação de Serviço (Rate Limiting)
Implementado em `core/security.py` via `InMemoryRateLimiter` thread-safe com janela deslizante (Sliding Window):
- `/login`: máximo de 10 requisições por minuto por IP.
- `/register`: máximo de 5 requisições por minuto por IP.
- `/game/<id>/move`: máximo de 60 requisições por minuto (1 lance/s).
- `/analyze_position` & `/bot_move`: máximo de 30 requisições por minuto por IP.
- `/redeem_promo`: máximo de 6 tentativas por minuto por IP.
- Resposta padronizada HTTP `429 Too Many Requests`.

### 2.4. Cabeçalhos HTTP de Segurança & Truncamento de Erros
- **Security Headers Aplicados em Todas as Respostas:**
  - `Content-Security-Policy`: whitelist estrita para recursos necessários.
  - `X-Frame-Options: DENY` (anti-clickjacking).
  - `X-Content-Type-Options: nosniff` (anti-MIME-sniffing).
  - `Referrer-Policy: strict-origin-when-cross-origin`.
  - `Permissions-Policy: geolocation=(), camera=(), microphone=()`.
- **Truncamento de Erros:** Erros 400, 401, 403, 404, 429 e 500 possuem manipuladores centralizados com respostas JSON limpas. NUNCA expõem stack traces ou informações de depuração em produção.

---

## 3. Arquitetura Atual e Caminho de Escala
- **Modo WAL (Write-Ahead Logging) no SQLite:**
  - `PRAGMA journal_mode = WAL;` permite leitores concorrentes, mas o SQLite mantém um único escritor por arquivo; gravações podem aguardar.
  - `PRAGMA busy_timeout = 5000;` aguarda locks transitórios, não elimina contenção.
- **Migração de banco:** `core/db.py` centraliza conexões e migrações, mas o projeto usa SQL e recursos específicos do SQLite. PostgreSQL exigirá adaptar dialecto, transações, migrações e estratégia de concorrência; não basta trocar a string de conexão.
- **Escala horizontal:** O serviço atual deve manter um worker quando compartilhar um arquivo SQLite. O rate limiter também mantém estado em memória do processo. Para múltiplos workers/instâncias, será necessário migrar para banco compartilhado e rate limiting distribuído e validar filas, sessões e locks sob carga.
- **Isolamento de Processamento do Stockfish:** Chamadas à engine isoladas por mutex (`_engine_lock`) e bounds de busca, evitando que análises pesadas congelem as threads de requisições HTTP do servidor.

---

## 4. Funcionalidades do Jogo & Regras FIDE
- **Movimentação do Tabuleiro:**
  - **Drag-and-Drop:** Arrastar e soltar peças no tabuleiro.
  - **Click-to-Move:** Clicar na peça de origem (destacando-a com borda e preenchimento âmbar) e clicar na casa de destino para mover.
- **Regras FIDE Oficiais:**
  - Afogamento (Stalemate) -> Empate.
  - Insuficiência de material -> Empate.
  - Regra dos 50 e 75 lances -> Empate compulsório FIDE.
  - Repetição tríplice e quíntupla -> Empate compulsório FIDE.
  - Regra FIDE 6.9 de Relógio -> Derrota por tempo, exceto se o oponente não possuir material suficiente para dar mate legal (empate automático).
  - Promoção de Peão -> Modal FIDE com escolha de Dama, Torre, Bispo ou Cavalo.
- **Calibração de Rating FIDE:**
  - 2 partidas iniciais de calibração com volatilidade $K=40$.
  - Ativação imediata no ranking online após a 2ª partida.
  - Fator FIDE pós-calibração: $K=20$ (ou $K=10$ para rating $\ge 2400$).
- **Modos de Jogo Oficiais:**
  - Bullet, Blitz e Rapid (online e offline).
  - Modo Clássico exclusivo para desafios customizados de longa duração.
- **Economia Escalonada de Camacoins:**
  - Offline: Bullet (+5 🪙), Blitz (+10 🪙), Rapid (+20 🪙).
  - Online: Bullet (+15 🪙), Blitz (+30 🪙), Rapid (+50 🪙).

---

## 5. Áudio, Interface & Sistema de Clubes
- **Web Audio API Nativa:** Sons sintetizados leves para lances, capturas, fanfarras de vitória/derrota e efeito metálico da espada de xeque-mate.
- **4 Trilhas de BGM:** Capivara Serena, Café & Xadrez, Batalha Medieval e Sintetizador 8-Bit, com silenciamento automático durante partidas.
- **Acessibilidade:** Modo para daltônicos (alto contraste), pular animações de fim de jogo e suporte a 7 idiomas (pt, en, es, fr, ru, de, hi).
- **Clubes de Xadrez:** Fundação com 600 Camacoins, 10 brasões de clã, privacidade por senha/aprovação, chat exclusivo e desafios internos diretos.
- **Canal de Atendimento Oficial:** `camaleocamargo@gmail.com`.

## Regra do primeiro lance e do botão Abortar

- O botão **Abortar** some assim que o jogador faz um lance; o servidor também recusa `POST /game/<id>/abort` (409) se o solicitante já moveu.
- Se o jogador da vez não fizer o **primeiro lance em 20 segundos** (`FIRST_MOVE_LIMIT_SECONDS` em `blueprints/game.py`), a partida é abortada automaticamente (`status='aborted'`, sem alteração de rating e sem consumir os 7 abortos/24h). A checagem ocorre em `/game/<id>/state` e `/game/<id>/move`.
- `/state` devolve `first_move_seconds_left` e `player_has_moved`; o cliente mostra o mini cronômetro (`#first-move-timer`).

## Pareamento online (fila ranqueada)

- `POST /matchmaking/ranked/join` entra na fila e tenta parear na hora. `GET /matchmaking/ranked/status` (consultado a cada 2 s pelo cliente) renova a presença e **refaz a busca** via `rematch_waiting_player` em `blueprints/game.py`; assim dois jogadores que já esperam se encontram. O claim é atômico (`UPDATE ... WHERE status='waiting'` precisa afetar 2 linhas).
- "Sem limite" para cima (`max_offset >= 9999`) pareia com o primeiro da fila; o mínimo continua definido pelo jogador.
- O cliente trata `waiting` e `queued` como "ainda procurando".

## Força dos bots (`core/engine.py`)

- Rating >= 1320: `UCI_LimitStrength` com `UCI_Elo` igual ao rating do bot (máx. 3190).
- Rating < 1320: sem `UCI_Elo` (o Stockfish não aceita). Usa `blunder_chance()` (65% em 300 → 5% em 1320 de lance aleatório) e, no restante, busca rasa (depth 2, MultiPV 4) escolhendo candidatos piores com probabilidade crescente para ratings menores. Teste local: bot 500 perdeu 0/6 contra 800 e 0/6 contra 1100.
- Os valores são aproximados e podem ser ajustados nas tabelas de `blunder_chance`/`best_weight`.
- Tempo de "pensar": o bot espera pelo menos `BOT_MIN_THINK_SECONDS` (4 s) antes de cada lance. Só joga sem essa espera quando o próprio relógio está em `BOT_INSTANT_BELOW_SECONDS` (10 s) ou menos. O tempo gasto é descontado do relógio do bot.

## Bots lendas

- `core/bot_identity.py`: nome e país (bandeira) de cada bot, derivados do número (lendas 1–30, oficiais, comuns 42–700 com nomes de 21 países e bots brasileiros 701+). Para mudar um nome ou país, edite as tabelas desse arquivo. As bandeiras são SVGs em `static/flags/<código>.svg`.
- A migração `classic_bot_identities_v1` (`core/db.py`) renomeia os bots comuns já gravados; rating, estilo e número não mudam. `/classic/ranking`, `/classic/matchmake`, `/game/create` e `/game/<id>/state` devolvem `country`/`opponent_country`.
- Bots extras (`CLASSIC_BONUS_BOTS`, números 701+): aparecem na aba **Bots Oficiais** como "Desafio" (opções geradas em `xadrez.py:index` → `bonus_bots`). Os avatares são `static/avatars/<slug>.svg`, ligados em `BONUS_BOT_AVATARS` no `index.html` (mesma ordem de `CLASSIC_BONUS_BOTS`). Podem ser desafiados, mas não contam para calibração (`/game/create` bloqueia durante a calibração e `settle_bot_calibration` só aceita bots oficiais 1–5) e não dão selo (`bot_seal` vazio).

- `CLASSIC_LEGENDS` (`core/constants.py`) usa nomes de paródia; `OLD_CLASSIC_LEGENDS` guarda os antigos só para a migração `legends_parody_names_v1` (`core/db.py`), que renomeia bots já gravados.

## Traduções

- Frases em `pagePhrases` (en/es/fr) e `additionalPagePhrases` (ru/de/hi) em `templates/index.html/index.html`. Toda chave nova deve existir nas 6 línguas; em caso de dúvida, rode a checagem de chaves faltantes no console do navegador.
- Mensagens de erro do backend (JSON `error`) ainda são em português.

## Lances: clique, arrastar, premove e confirmar lance (`templates/index.html/index.html`)

- Entrada única: `handleSquareTap` (toque/clique) e `onDrop` (arrastar) chamam `requestPlayerMove` na sua vez, ou `queuePremove` fora da vez.
- Premove: até 2 lances agendados (casas em vermelho). `executePremove` roda quando a vez volta (resposta do bot ou polling PvP) e valida a legalidade; botão direito no tabuleiro cancela. Não pede confirmação.
- Confirmar lance (Acessibilidade): `stageMoveForConfirmation` mostra a barra `#move-confirm-bar` com o SAN e marca origem/destino em verde; só `resolveConfirmMove(true)` envia ao servidor.
- `#board` usa `touch-action: none` para o arrasto no celular não rolar a página.
- Captura por toque: `onDragStart` recusa peças do adversário **sem limpar a seleção** (o `touchstart` vem antes do `click`; limpar antes fazia o toque na peça adversária nunca capturar).
- Arrasto: `onDrop` devolve `undefined` quando o lance foi enviado (a peça fica onde foi solta) e `'snapback'` nos demais casos; `onSnapEnd` reconcilia roque/en passant com `game.fen()`. `sendGameMoveToServer(uci, { viaDrag })` não chama `board.position` ao arrastar, para não animar duas vezes.

## Ritmos e relógio

- `TIME_CONTROLS` (`core/constants.py`) é a **única** lista de ritmos aceitos; `/game/create`, a fila rankeada, desafios diretos, desafios de clube e `/game/restore` leem dela. Ritmo fora da lista devolve 400 (antes a fila e os desafios trocavam por 3+2 em silêncio). Ao liberar um ritmo novo: acrescente em `TIME_CONTROLS` e o botão/opção em `index.html` (`.time-btn`, `#select-time` e `#time-menu`).
- "Ritmo aleatório" no seletor de Bots Oficiais sorteia no cliente um ritmo concreto do `<select>`.
- Cliente: `setClocks` sincroniza com o servidor e `advanceClocks` desconta o tempo real decorrido (`performance.now()`), a cada 100 ms; não depende mais de o `setInterval` disparar certinho. Ao jogar, o incremento entra **na hora** no relógio do jogador (o servidor confirma na resposta). Reivindicação de tempo esgotado (`checkTimeoutServer`) é limitada a uma por 1,5 s.
- Servidor: `MOVE_LAG_GRACE_SECONDS` (0,5 s, `blueprints/game.py`) é uma tolerância de rede: só dá bandeira quando o tempo estourou por mais que isso (`clock_expired`), em `/move`, `/state` e `/claim_timeout`. O tempo é descontado normalmente (nunca negativo) e o incremento soma depois.

## Áudio (`// --- SISTEMA DE ÁUDIO` em `index.html`)

- Web Audio sintetizado (sem arquivos): barramentos `sfxBus` e `musicBus`.
- Efeitos: `sfxMove`, `sfxCapture`, `sfxCheck`, `sfxPromotion`, `sfxClick`, `sfxNotify`, `sfxCoin`, `playGiftOpenSound` etc. `playMoveSoundForSan(san)` escolhe o efeito pelo lance (captura `x`, xeque `+`, mate `#`, roque, promoção).
- Clique: um listener global toca `sfxClick` em botões/abas; os menus (`playMenuSound`) não duplicam.
- Música: 4 trilhas em `MUSIC_TRACKS` (lo-fi, jazz em 3/4, marcha medieval, 8-bit), agendadas por compasso. Começa desligada e só toca se o jogador ativar; pausa durante partidas. "Testar trilha" toca uma prévia de ~14 s.

## Presentes

- A animação de abertura (`playGiftReveal`): caixa chacoalha, tampa voa, brilho e o item sobe, com som e confete.

## Cabeçalhos de segurança

- `apply_security_headers` (`core/security.py`) envia CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, COOP, `Server: Capybara` e HSTS (somente sob HTTPS).

## Checklist de segurança (revisão interna, não é certificação)

| # | Vetor | Situação no código |
|---|-------|--------------------|
| 1 | `.env` exposto | `.env` fora do Git; `/.env` e `/capybara.db` não são servidos (testado). `SECRET_KEY` obrigatória em produção. |
| 2–3 | Validação front e back | Regras de senha/nick no front **e** em `/register` (`core/security.py`: `validate_username`, `parse_bounded_integer`, `validate_uci_move`, `validate_fen`). O back é quem vale. |
| 4 | SQL injection | Valores sempre por `?`; f-strings só com constantes/listas permitidas (colunas de idioma). |
| 5 | Autenticação fraca | Senha de 7 a 128 caracteres com 1 símbolo; hash `scrypt/pbkdf2`; comparação de senhas antigas com `hmac.compare_digest`; hash falso para nick inexistente (sem diferença de tempo). |
| 6 | IDOR | Sessão obrigatória (`enforce_account_security` em `xadrez.py`); campos de dono (`OWNER_FIELDS`) devem bater com a sessão; rotas de partida checam participação (testado: outro usuário recebe 403). |
| 7 | Senhas no banco | Só hash. |
| 8 | Força bruta | `/login`: 10 req/min por IP **e** `LoginThrottle` (5 falhas por IP+nick e 20 por nick em 15 min → 429). Em memória; use Redis se houver vários servidores. |
| 9 | Bloquear durante envio | Cadastro/login e envio de presente travam o botão até a resposta (`authBusy`, `giftSending`). |
| 10 | CSRF | `same_origin_guard` (Origin e `Sec-Fetch-Site`) + cookie `SameSite=Lax`. |
| 11 | Upload sem validação | Não há rota de upload de arquivo; o avatar é data-URI `png/jpeg/webp` validado, e o corpo é limitado a 2 MB. |
| 12 | Informação em respostas | Erros genéricos em produção; `Server: Capybara`; sem stack trace. |
| 13 | Dependências | `requirements.txt` com versões fixadas; `pip-audit` sem vulnerabilidades conhecidas (Authlib 1.9.1). Reexecute `pip-audit -r requirements.txt` periodicamente. |
| 14 | Tokens/sessões | Sessão assinada pelo Flask, `session.clear()` no login; o login não aceita token em URL. |
| 15 | Rate limit | `rate_limit` por IP e rota. `ProxyFix` já está configurado para 1 proxy (`xadrez.py`); ajuste `x_for` se houver mais camadas. |
| 16 | Arquivos sensíveis | `.gitignore` cobre `.env`, `*.db`, backups. |
| 17 | SSRF | O servidor não faz requisições a URLs enviadas por usuários; só o OAuth do Google (Authlib). |
| 18 | Cookies | `HttpOnly`, `SameSite=Lax`, `Secure` via `COOKIE_SECURE` (ligue em HTTPS). |
| 19 | CORS e outros | Sem CORS aberto; CSP restrita; HSTS sob HTTPS. A CSP ainda permite `unsafe-inline` por causa do HTML com scripts embutidos. |

Limites conhecidos: o limitador e o bloqueio de login são em memória (zerados ao reiniciar); mensagens de erro do backend estão em português; revisão jurídica (LGPD, termos de uso) deve ser feita por profissional.

## Persistência, Play Store e testes

- **Dados que sobrevivem a reinícios:** configure `DATABASE_URL` (PostgreSQL). Passo a passo em `DEPLOY.md`; arquitetura em `ARCHITECTURE.md`. Partidas voltam ao ponto em que foram deixadas (`/game/active`, relógios congelados durante a pausa do servidor, cópia no `localStorage` para bots).
- **Play Store:** veja `PLAYSTORE.md` (PWA/TWA, ícones, assetlinks, páginas legais, exclusão de conta).
- **Exclusão de conta:** `POST /account/delete` (Configurações → Suporte). Apaga dados pessoais e anonimiza partidas; o código `adm` continua marcado como usado.
- **Erros do servidor traduzidos:** `window.alert` passa pelo `localizeStaticPhrase`; novas mensagens de erro devem ganhar tradução em `featurePhrases` (6 idiomas).
- **Testes:** `python3 tests/smoke_api.py`, `tests/test_persistence.py`, `tests/test_google_login.py`, `tests/test_store_readiness.py`, `tests/test_time_controls.py` (banco vazio; SQLite por padrão, PostgreSQL com `DATABASE_URL`).
