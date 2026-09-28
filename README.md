# Riftbound Inventory

Track your [Riftbound](https://playriftbound.com/) (League of Legends TCG)
collection: browse every card, record how many copies you own, set per-card
collection limits, and see what's still missing. Cards are entered manually
from the browsable card list. Multiple people can each keep an account on the
same instance, browse each other's collections, and trade cards.

```
backend/    Python 3.10+ · FastAPI · SQLite
frontend/   TypeScript · React · Vite
docs/       Engineering onboarding — start at docs/README.md
```

**Developers:** [`docs/`](docs/README.md) has the full onboarding guide —
architecture, API reference, authentication, frontend conventions, and known
issues. For a one-page picture of the system, open
[`docs/architecture.html`](docs/architecture.html) in a browser (interactive,
self-contained).

## Quick start

### Docker (macOS or Windows)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
# Development — hot reload, Vite on :5173
docker compose up --build

# Production-style — nginx on :8080, API proxied same-origin
docker compose --profile prod up --build
```

| Mode | URL |
|---|---|
| Development | http://localhost:5173 |
| Production profile | http://localhost:8080 |

Optional integrations (TopDeck.gg community decks, market prices) need API
keys. Copy `.env.example` to `.env` and fill in any you have — Compose reads it
automatically. `.env` is gitignored; never put keys in `docker-compose.yml`.

SQLite and card images persist in `backend/data/` on the host (bind-mounted into the
backend container). To ingest real card data inside Docker:

```bash
docker compose exec backend python -m app.ingest.fetch_official
```

### Local (without Docker)

```powershell
# Backend (terminal 1)
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# Frontend (terminal 2)
cd frontend
npm install
npm run dev        # open http://localhost:5173
```

### Loading real card data — free, no API key

```powershell
cd backend
.venv\Scripts\python -m app.ingest.fetch_official           # all sets (~950 cards)
.venv\Scripts\python -m app.ingest.fetch_official --set UNL # one set only
# then restart the backend so it loads the new cards
```

This pulls the complete card database (every card's name, set, collector
number, rarity, domain, type, and full-size image, across all sets) from
**Riot's official card gallery** at
[playriftbound.com/en-us/card-gallery](https://playriftbound.com/en-us/card-gallery/).
Why this source:

- It's Riot's own published data — first-party, always current, and their
  [robots.txt](https://playriftbound.com/robots.txt) is `Allow: /` for all
  agents, i.e. crawling is explicitly permitted. Marketplace/pricing sites
  (TCGPlayer etc.) forbid scraping in their terms of service, so they are
  deliberately *not* used.
- It's one single page request for all metadata (the gallery embeds its full
  card database as JSON), plus one image download per card.
- The fetcher identifies itself with a descriptive User-Agent, waits 250 ms
  between image downloads (`--delay` to change), caches images locally, and
  skips already-ingested cards on re-runs — a new set release is just another
  run.

On an empty database the backend seeds a small generated demo set so the app
works before any ingest; the first real ingest removes it automatically
(`--keep-seed` to retain). The Scrydex fetcher (`fetch_scrydex.py`, requires
an API key) remains as an alternative source.

### Recording your collection

Everything is entered manually from the **Collection** tab. Search or filter
(by set, type, rarity, owned/missing) to find a card, then use **+ / −** to set
how many copies you own; click the `count / limit` label to set a per-card
limit override. Cards you don't own are greyed out, so the grid doubles as a
"what's still missing" view. Counts persist immediately in SQLite.

Viewing on a phone works too: `npm run dev` serves on the LAN, so open
`http://<your-pc-ip>:5173` (find the IP with `ipconfig`). If the phone can't
reach it, allow the port through Windows Firewall:
`New-NetFirewallRule -DisplayName "Riftbound dev" -Direction Inbound
-LocalPort 5173 -Protocol TCP -Action Allow` (run as admin).

Locking your phone or switching apps won't lose your place. Mobile browsers
discard backgrounded tabs to free memory and reload the page when you come
back, so the app keeps the current screen in the URL (`/#/collection`) and your
filters and drill-downs in `sessionStorage`. The back button moves between tabs
rather than leaving the app, and a `+` click still saves even if the phone
sleeps in the moment right after you tap it.

## Design decisions and why

**FastAPI + SQLite.** The collection is local, small, and relational
(users ↔ counts ↔ cards ↔ rules), with a handful of accounts at most. SQLite is
a zero-admin single file — ideal for an appliance-style app
([SQLite: appropriate uses](https://sqlite.org/whentouse.html)).
FastAPI gives request validation via Pydantic on every endpoint for free
([FastAPI docs](https://fastapi.tiangolo.com/)).

**Collection limits derive from Riftbound's deck rules**
([official deckbuilding primer](https://playriftbound.com/en-us/news/rules-and-releases/deckbuilding-primer/)):
max 3 copies per card in a deck, exactly 1 Legend, 3 distinct Battlefields
(1 copy each), 12-card rune deck. Owning those counts means you can build any
deck using the card — the natural "complete" target. Resolution order:
per-card override → optional rarity cap (e.g. keep 1 Epic for display) →
type default. Copies beyond the limit are flagged as trade fodder.

**Vite proxy instead of exposing the API cross-origin.** The dev server
proxies `/api` and `/images` to the backend so the browser sees one origin
([Vite server.proxy](https://vitejs.dev/config/server-options.html#server-proxy)).
CORS on the backend is additionally locked to the frontend origin only.

## Security posture

- **External images** (card art): HTTPS only, explicit host allowlist
  (Riot's `cmsassets.rgpub.io`/`assetcdn.rgpub.io`/`cdn.rgpub.io`,
  playriftbound.com, Scrydex CDN), Content-Type and
  10 MB size checks, and every image is **re-encoded with Pillow** before
  storage — the stored JPEG contains pixels only, stripping metadata or any
  smuggled payload. SVG is never accepted (it can carry scripts). File names
  come from validated card ids (`^[A-Za-z0-9_-]+$`), never from URLs.
  (Per the [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).)
- **Path traversal**: images are served by Starlette `StaticFiles`, which
  resolves strictly inside the mounted directory.
- **CORS** restricted to the frontend origin — arbitrary websites cannot make
  your browser mutate your collection
  ([MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)).
- **SQL injection**: all queries go through SQLAlchemy ORM parameter binding;
  no string-built SQL anywhere.
- The server binds to localhost by default; expose it to your LAN only on a
  network you trust.
- **Secrets stay out of git**: API keys live in a gitignored `.env`, and
  `backend/data/` (the database with password hashes, card images, and the
  JWT signing key `secret.key`) is gitignored and never committed.

## Testing

```powershell
cd backend;  .venv\Scripts\python -m pytest      # backend tests
cd frontend; npm test                             # vitest unit tests
```

Backend tests cover auth, per-user scoping, card-ingest parsing and
image-download safety checks, count clamping, limit resolution, settings
persistence, trades, decks, pricing, and export/import round-trips. Frontend
tests cover the pure logic in `src/lib/` (collection progress, achievements,
prices, the trade basket, hash routing, persisted view state).

## Data & API

Every route except `/api/auth/*` requires a `Bearer` token and is scoped to the
signed-in user. The highlights:

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/register` · `POST /api/auth/token` | Create an account / log in (JWT) |
| `GET /api/cards` | All cards + your counts + effective limits |
| `POST /api/inventory/{id}/increment` | Adjust count (never below 0) |
| `PATCH /api/inventory/{id}` | Set count / limit override |
| `GET/PUT /api/settings/limits` | Limit rules engine |
| `GET /api/backup/export` · `POST /api/backup/import` | JSON backup (Excel too) |
| `/api/decks/*` | Saved decks, decklist import, community decks |
| `/api/community/*` | User directory + read-only views of others' collections |
| `/api/trades/export` · `preview` · `fulfil` | Text-based trade requests |
| `/api/prices/*` | Market prices (key-gated) |

The full reference is [`docs/05-api-reference.md`](docs/05-api-reference.md);
live interactive docs are at <http://localhost:8000/docs>.

Everything persists in `backend/data/riftbound.db` (SQLite) with card images
in `backend/data/images/`.
