# Capybara Chess architecture

## Application layout

- `app.py` is the development and WSGI entry point. `xadrez.py` owns the Flask
  application factory, shared request middleware, OAuth setup, and legacy
  compatibility for existing deployments.
- `blueprints/` contains feature-level HTTP routes: authentication, chess
  games and matchmaking, social interactions, user profiles/economy, and
  analysis. Keep request parsing and response formatting at this boundary.
- `core/` contains shared configuration, database access (SQLite/PostgreSQL) and schema migrations,
  constants/catalogues, security helpers, rating rules, and Stockfish
  orchestration. Put rules used by multiple routes here rather than copying
  them into templates or route handlers.
- `templates/index.html/index.html` is the single-page client. Its JavaScript
  calls the Flask JSON endpoints; `static/` contains styles, images, sounds,
  service-worker assets, and chess piece artwork.
- `deployment/`, `Dockerfile`, `Procfile`, and `.github/workflows/` describe
  hosting and delivery. Keep secrets in the host environment, never in these
  files.

## Request and data flow

1. `app.py` imports the Flask application created by `xadrez.py`.
2. The application registers feature blueprints and applies session,
   ownership, error-response, and security-header middleware.
3. Route handlers validate input and authorization, then use `core.db.get_db`
   for a transaction. SQLite schema changes are additive and idempotent in
   `core/db.py:init_db`.
4. The client updates its state from JSON responses and polls game state for
   live matches. Stockfish work is isolated in `core/engine.py`.

## Data persistence (SQLite locally, PostgreSQL in production)

- `core/db.py` exposes `get_db()` and `init_db()`. Without `DATABASE_URL` it
  uses a local SQLite file (WAL). With `DATABASE_URL=postgresql://...` it uses
  PostgreSQL through a connection pool (`core/db_postgres.py`).
- The routes keep writing SQLite-dialect SQL. `core/db_postgres.py` translates
  it on the fly (placeholders, `datetime('now', ...)`, `INSERT OR IGNORE/REPLACE`,
  `BEGIN IMMEDIATE` -> advisory lock, autoincrement ids, ...) and returns rows
  that behave like `sqlite3.Row`. When you add SQL that is SQLite-only, add a
  rule in `translate_sql`; then run the three suites below against both engines.
- Free hosting wipes local files, so production must set `DATABASE_URL` (see
  `DEPLOY.md`). `tools/migrate_sqlite_to_postgres.py` copies an existing SQLite
  database (ids and sequences preserved).
- Nothing important lives only in RAM: games, ratings, queue and presence are
  tables. The in-memory rate limiter / login throttle intentionally reset on
  restart. A heartbeat (`server_state`) lets `freeze_clocks_after_downtime`
  give active games the time the server was off, so they resume exactly where
  the last player left them. The client resumes via `GET /game/active` and keeps
  a `localStorage` copy of bot games; `POST /game/restore` recreates a bot game
  (validated, flagged `restored`, no rating/coin/mission/seal effects) if the
  server lost its data.
- Tests (run against an empty throwaway database, SQLite or PostgreSQL):
  `tests/smoke_api.py` (API sweep), `tests/test_persistence.py`,
  `tests/test_google_login.py` (OAuth callback logic with a mocked Google),
  `tests/test_store_readiness.py` (legal pages, assetlinks, account deletion),
  `tests/test_time_controls.py` (ranked/challenge time controls, clock increment and network grace).

Back up the database before deployments or manual maintenance. Never edit
production rows directly without a backup and a migration plan.

## Maintaining features

- Add a route to the blueprint that owns the feature. Require the authenticated
  session for account mutations; derive the actor from the session rather than
  trusting a username supplied by the browser.
- Validate identifiers, lengths, enum values, and ownership on the server.
  Bind SQL values with parameters; never interpolate user input into SQL.
- Keep multi-row balance, inventory, match, or rating changes inside one
  transaction. Add an index alongside a new table when queries filter or sort
  on its owner and status.
- Add persistent schema through `init_db` using `CREATE TABLE IF NOT EXISTS`
  or a guarded `ALTER TABLE`. Preserve existing rows and make startup
  repeatable.
- Online PvP, ranked matchmaking, direct/club challenges, and rematches require
  `users.google_sub` to be linked. The profile flag is derived from the verified
  Google `locale` region when present (a locale preference, not verified
  residence); it is immutable through user-facing routes and remains blank
  when Google provides no country-region subtag. A one-time migration clears
  the former manually selected flags before Google can populate them.
- Keep browser-visible labels in the locale dictionaries in the main
  template. Escape user-controlled strings before inserting them into HTML.
- Keep Stockfish invocation and resource limits in `core/engine.py`; do not
  run an engine process directly from a template or route without the shared
  limits.

## Current scaling and security boundaries

The feature boundaries are intended to make later replacement or extraction
possible, but this deployment is **not** presently sized or certified for
millions of users. SQLite is a single-node database, the rate limiter is
process-local, and live-game updates use polling. Before multi-instance scale,
move persistent data to a managed transactional database, put rate-limit and
presence state in shared storage, and introduce a shared realtime transport
and background job queue. Preserve the existing route/service boundaries and
test migrations and rating transactions during each step.

Bot ratings below Stockfish's supported `UCI_Elo` minimum use Stockfish's
`Skill Level` plus controlled random legal moves. That is a strength
approximation, not an empirically certified Elo rating. Before presenting
those numbers as exact, run a reproducible engine tournament with fixed
time controls, enough games, color swaps, and confidence intervals.

Security controls must be verified for the deployed configuration. Production
requires a stable secret key, HTTPS and secure cookies, a persistent database
path, controlled proxy headers, reviewed upload handling, and backups. The
in-memory limiter is not a distributed abuse defense. Do not treat security
headers or frontend validation as substitutes for authorization and backend
validation.

## Primeiro lance (auto-abort)

Helpers `first_move_seconds_left` e `auto_abort_idle_game` em `blueprints/game.py`; UI em `startFirstMoveGuard()` no `index.html`. Veja `DOCUMENTATION.md`.
