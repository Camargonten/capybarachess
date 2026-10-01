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
- **Consultas Parametrizadas Obrigatórias:** 100% das interações com a base de dados em `core/db.py` e nos blueprints utilizam bind parameters (`?`), eliminando qualquer possibilidade de SQL Injection.
- **Sanitização de Inputs:**
  - Nomes de usuário: validação via expressão regular `^[A-Za-z0-9_ -]+$` entre 3 e 25 caracteres.
  - Notação UCI: regex `^[a-h][1-8][a-h][1-8][qrbn]?$` com validação estrita no `python-chess`.
  - Posições FEN: validadas com instanciação no motor antes de qualquer operação.
  - Mensagens e textos: escape de HTML (`escapeHtml`) no frontend e truncamento de tamanho no backend.
- **Prevenção de Path Traversal:** Arquivos estáticos servidos via caminhos canônicos e absolutos.

### 2.2. Autenticação, Gestão de Sessões & Passwords
- **Armazenamento de Senhas:** Hashing com `scrypt` ou `pbkdf2:sha256` com salts aleatórios seguros via Werkzeug.
- **Regra do Primeiro Administrador (Bootstrap Admin):** A primeira conta registrada no sistema (seja via formulário tradicional ou OAuth Google) é automaticamente promovida a Administrador (`is_admin = True`) com saldo especial de 8.000 moedas. A partir da segunda conta em diante, os novos utilizadores entram com permissões padrão (`is_admin = False`) e o saldo regular de 100 moedas.
- **Segurança de Cookies de Sessão:**
  - `SESSION_COOKIE_HTTPONLY = True` (proteção contra roubo de sessão via XSS).
  - `SESSION_COOKIE_SAMESITE = 'Lax'` (proteção contra ataques CSRF).
  - `SESSION_COOKIE_SECURE = True` em ambiente de produção HTTPS.
- **Validação de Posse de Conta:** O middleware `before_request` verifica rigorosamente a correspondência entre o usuário da sessão e o recurso requisitado em todos os endpoints autenticados.

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

## 3. Arquitetura Escalável & Preparação para Alta Concorrência (+1M Usuários)
- **Modo WAL (Write-Ahead Logging) no SQLite:**
  - `PRAGMA journal_mode = WAL;` permite operações simultâneas de leitura e escrita sem bloqueio de tabela.
  - `PRAGMA busy_timeout = 5000;` evita erros transitórios de lock.
- **Pronto para PostgreSQL:** Toda a camada de banco de dados está isolada em `core/db.py`, permitindo a transição para PostgreSQL ou pools gerenciados apenas alterando a string de conexão.
- **Backend Stateless:** Sem sessões dependentes de memória volátil da thread, permitindo múltiplos workers Gunicorn em paralelo.
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
