# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Onboarding docs for humans live in [`docs/`](docs/README.md) — architecture, API
> reference, auth, and frontend conventions in more depth than this file.

## Project overview

Riftbound Inventory is a self-hosted, **multi-user** card collection tracker for the
Riftbound TCG (League of Legends). Users register an account, record how many copies of
each card they own, build/import decks, browse other collectors' shelves, and swap cards
via text-based trade requests. Stack: Python 3.10+ FastAPI + SQLite backend, TypeScript
React 18 + Vite frontend. Everything runs locally; there is no hosted service.

## Development commands

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000   # dev server
.venv\Scripts\python -m pytest                              # all tests
.venv\Scripts\python -m pytest tests/test_limits.py        # single test file
```

### Frontend

```powershell
cd frontend
npm install
npm run dev      # Vite dev server on :5173
npm run build    # tsc + vite build
npm test         # vitest run (all tests)
```

### Docker (both services together)

```bash
docker compose up --build                      # dev — hot reload, :5173
docker compose --profile prod up --build       # prod — nginx on :8080
```

### Card data ingestion

```powershell
cd backend
.venv\Scripts\python -m app.ingest.fetch_official           # all sets
.venv\Scripts\python -m app.ingest.fetch_official --set UNL # one set
```

## Architecture

### Backend (`backend/app/`)

- **`main.py`** — FastAPI app factory: creates the DB engine, runs additive migrations
  (`PRAGMA table_info` + `ALTER TABLE`), seeds demo data on an empty DB, wires CORS,
  includes every router, and mounts `/images` as static files.
- **`models.py`** — SQLAlchemy 2.0 ORM (`Mapped` / `mapped_column`): `User`, `Card`,
  `InventoryItem`, `Setting`, `CardPrice`, `CardPriceHistory`, `PriceApiUsage`,
  `SavedDeck`, `SavedDeckCard`. Card ids are `SET-NUMBER` slugs (e.g. `OGN-042`),
  validated at ingest against `^[A-Za-z0-9_-]+$`.
- **`auth.py`** — Password hashing (bcrypt over a SHA-256 pre-hash), JWT issuing
  (HS256, python-jose), and the `get_current_user` dependency that every protected
  route depends on.
- **`schemas.py`** — All Pydantic request/response models. Response models are the
  API contract: a field absent here is stripped from the response.
- **`limits.py`** — Rules engine for collection limits, stored **per user** as JSON in
  the `settings` table under the key `"{user_id}:limit_rules"`. Resolution order:
  per-card `limit_override` > rarity cap (if enabled) > card-type default
  (unit/spell/gear=3, legend=1, battlefield=1, rune=12).
- **`trades.py`** — The trade-request text format. The writer (`format_request`) and the
  reader (`parse_request`) live in one module so the two sides can't drift; parsing is
  lenient and reports skipped lines as warnings rather than raising.
- **`routes/`** — One module per domain: `auth.py`, `cards.py`, `inventory.py`,
  `settings.py`, `backup.py` (JSON + Excel), `prices.py`, `community.py` (user directory
  + read-only views of another user's collection), `trades.py` (export/preview/fulfil),
  and `decks/` (a package: `router.py` endpoints, `_common.py` decklist parsers/
  resolvers, `riftrank.py` + `topdeck.py` external deck providers).
- **`pricing/`** — External market-price integration: `client.py` (HTTP), `matcher.py`
  (card → external catalog id), `budget.py` (daily free-tier request quota),
  `service.py` (refresh orchestration + trend math), `refresh_job.py` (batch CLI).
- **`ingest/`** — `fetch_official.py` scrapes Riot's card gallery (the page embeds the
  full card DB as JSON), downloads and re-encodes images with Pillow. `seed.py`
  generates demo cards on an empty DB. `fetch_scrydex.py` is an alternative source.
- **`db.py` / `deps.py`** — Engine/session setup; `get_db` request-scoped session
  dependency and the shared `card_to_out` serializer.
- **`config.py`** — Environment configuration: `RIFTBOUND_DATA_DIR`,
  `RIFTBOUND_CORS_ORIGINS`, `RIFTBOUND_SEED`, `RIFTBOUND_JWT_SECRET`,
  `RIFTBOUND_TOKEN_EXPIRE_DAYS`, `RIFTBOUND_PRICE_API_KEY`, `RIFTBOUND_TOPDECK_KEY`.

Data lives in `backend/data/` — `riftbound.db`, `images/`, and `secret.key` (the
auto-generated JWT signing key). Bind-mounted in Docker so it survives rebuilds.
The whole directory is gitignored — it holds password hashes and the signing key.

API keys are never committed: Compose reads them from a gitignored root `.env`
(template: `.env.example`) via `${VAR:-}` references in `docker-compose.yml`.

### Frontend (`frontend/src/`)

- **`App.tsx`** — Root. Gates on a token: renders `Login` when logged out, otherwise the
  tab shell. The active tab is **hash-routed** (`/#/collection`), so a reload lands back
  on the same screen. Fetches all cards once per login, owns `cards` state, and passes an
  `updateCard` callback down so inventory mutations patch in place without a refetch.
  Also owns `savedDecks` and derives `commitmentMap` (card → deck commitments).
- **`auth.ts`** — Token storage in `localStorage` (`getToken` / `getUsername` /
  `setToken` / `clearToken`) plus the unauthenticated `login` / `register` calls.
- **`api.ts`** — Every HTTP call to `/api/*`. The `request()` wrapper attaches the
  `Authorization: Bearer` header and, on a 401 to a call that presented a token, clears
  the token and invokes the handler registered via `setSessionExpiredHandler` (App's
  logout) — it does **not** reload the document, so view state survives re-authenticating.
- **`types.ts`** — Shared TypeScript types mirroring the backend's Pydantic schemas.
- **`screens/`** — `Login.tsx`, `Dashboard.tsx` (overview/stats), `Collection.tsx` (main
  grid with filter/search; `readOnly` renders someone else's collection, `trade` adds
  per-finish request steppers, `persistKey` namespaces its remembered filters), `Achievements.tsx`, `Settings.tsx`, `DeckBuilder.tsx`,
  `Community.tsx` (user directory → another user's collection + the trade basket).
- **`components/`** — `MultiSelect.tsx`, `TradeImport.tsx` (the owner-side paste →
  review → confirm flow).
- **`lib/`** — Pure logic with unit tests: `collection.ts` (completion/progress math),
  `achievements.ts`, `price.ts`, `trade.ts` (request basket state), `shine.ts` (CSS
  variables for holographic foil effects), `hashRoute.ts` (the `Tab` union + hash
  parse/serialize), `persistentState.ts` (`usePersistedState`, sessionStorage-backed).
- **`styles.css`** — One hand-written stylesheet, retro pixel-art theme, CSS custom
  properties on `:root`. No CSS framework.

### Key data flows

1. `POST /api/auth/token` returns a JWT; the frontend stores it and sends it as a Bearer
   token on every subsequent call. Every route outside `/api/auth/*` requires it.
2. `GET /api/cards` returns all cards joined with **the caller's** inventory counts and
   effective limits — the frontend renders from this single response.
3. `POST /api/inventory/{id}/increment` or `PATCH /api/inventory/{id}` mutates counts and
   returns the updated card, which `updateCard` patches into React state. `Collection.tsx`
   applies the change optimistically and debounces the PATCH by 600 ms. Pending edits are
   **flushed, never dropped** — on unmount, `visibilitychange` and `pagehide` — using
   `fetch(..., { keepalive: true })` so the save survives the page being frozen.
4. `InventoryItem.in_binder` / `binder_foil` track physical binder placement separately
   from playable copies — binder counts as "owned" for missing/complete views but is
   excluded from playset math.
5. Community views are read-only by construction: `GET /api/community/users/{id}/cards`
   resolves the catalog against *another* user's inventory, but every write endpoint
   targets `current_user`, so there is no code path that mutates someone else's rows.
6. Trade requests are stateless — no DB table. The requester's basket is exported as text
   by `POST /api/trades/export`, the owner pastes it into `POST /api/trades/preview`
   (read-only: joins the request against their own counts), and `POST /api/trades/fulfil`
   deducts the confirmed quantities. Fulfil only ever writes to the authenticated user's
   rows and clamps every deduction to what they hold, so a stale preview can't drive a
   count negative.
7. Schema migrations are manual and additive-only: add missing columns in
   `main._migrate()` guarded by `PRAGMA table_info`. Never rewrite or drop a column.

## Conventions

- **Per-user scoping is the invariant.** `InventoryItem` has the composite primary key
  `(user_id, card_id)`; `SavedDeck` and per-user settings key off `user_id`. Any new
  query touching user data must filter by `current_user.id`, and any new write must
  target it — never a user id taken from the request body or path.
- **New endpoint checklist:** add the Pydantic schema in `schemas.py`, add the route in
  the matching `routes/` module with `current_user: User = Depends(get_current_user)`,
  add the typed client function in `frontend/src/api.ts`, mirror the type in `types.ts`,
  and add a pytest in `backend/tests/`.
- **Response models are the contract.** If a field is missing from the `response_model`,
  FastAPI silently strips it and the frontend sees `undefined` — this has already caused
  one live bug (see `docs/09-known-issues.md`).
- Pure, testable logic goes in `frontend/src/lib/` (vitest) or a plain backend module
  (pytest), not inside components or route handlers.
- **View state must survive a reload.** Mobile browsers discard backgrounded tabs and
  re-run the document on return, so anything a user would be annoyed to lose belongs in
  the URL hash (the tab) or in `usePersistedState` (filters, drill-downs) — never in a
  bare `useState`. Modals and half-filled wizards are the deliberate exception. Namespace
  a reused screen's keys so two render modes can't share one bucket (see `Collection`'s
  `persistKey`), and add new persisted slots to `clearPersistedView()`'s namespace so
  logout drops them.
- **No secrets in git.** Keys go in `.env`, never in `docker-compose.yml`, docs, or
  code; `backend/data/` stays ignored. Check `git status` before committing.
- `.card-tile` has `overflow: hidden`, so any row inside it must degrade by wrapping
  (`flex-wrap: wrap`) rather than overflowing.
