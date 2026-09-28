[← Docs index](README.md)

# 5. API reference

Base URL: `/api`. In the browser this is same-origin (proxied); direct backend access is
`http://localhost:8000`.

> **Live, always-accurate docs:** <http://localhost:8000/docs> (Swagger UI) and
> <http://localhost:8000/redoc>. FastAPI generates both from the route signatures and
> Pydantic models, so they cannot drift. This page adds the *why* and the gotchas that
> generated docs can't express.

---

## Conventions

**Authentication.** Every endpoint requires `Authorization: Bearer <jwt>` **except**
`POST /api/auth/register` and `POST /api/auth/token`. Missing or invalid → `401` with
`WWW-Authenticate: Bearer`.

**Scoping.** Unless stated otherwise, an endpoint reads and writes *only the
authenticated user's* data. The single exception is
`GET /api/community/users/{user_id}/cards`, which is read-only.

**Mutations return the updated resource.** Inventory and trade writes return `CardOut`
objects so the frontend can patch React state in place instead of refetching. Keep this
convention for new endpoints.

**Errors.** FastAPI's standard `{"detail": "..."}` body. `422` for schema validation
failures (Pydantic, automatic). Ad-hoc `HTTPException`s use the codes listed per endpoint.

---

## 5.1 Auth — `routes/auth.py`

### `POST /api/auth/register` 🔓

```jsonc
// request
{ "username": "alice", "password": "secret1" }   // username 1–64 chars, password ≥ 6
// 201
{ "id": 1, "username": "alice" }
```

`409` if the username is taken. The **first** user ever registered also adopts any
`inventory` rows with `user_id IS NULL` — a migration path from the pre-multi-user
version. The frontend auto-logs-in after a successful register.

### `POST /api/auth/token` 🔓

```jsonc
// request
{ "username": "alice", "password": "secret1" }
// 200
{ "access_token": "eyJ…", "token_type": "bearer", "username": "alice" }
```

`401` for both wrong password and unknown user — the response doesn't reveal which.

> Despite `OAuth2PasswordBearer(tokenUrl=…)` pointing here, this endpoint takes **JSON**,
> not OAuth2's `application/x-www-form-urlencoded`. Swagger UI's "Authorize" button posts
> form data and will fail; get a token from `/docs`'s `POST /api/auth/token` "Try it out"
> instead, then paste it into Authorize as `Bearer <token>`.

---

## 5.2 Cards — `routes/cards.py`

### `GET /api/cards`

The workhorse. Returns **every** card joined with the caller's counts and effective
limits. No pagination — see [system design](02-system-design.md#one-bulk-endpoint-instead-of-pagination).

| Query param | Type | Behaviour |
|---|---|---|
| `search` | string | Case-insensitive substring on name **or** id |
| `set_code` | string | Exact match |
| `domain` | string | Case-insensitive substring |
| `rarity` | string | Exact match |
| `card_type` | string | Exact match |
| `owned` | bool | `true` = has any copy or is in the binder; `false` = the inverse |

```jsonc
// 200 — CardOut[]
[{
  "id": "OGN-042", "name": "Blazing Scorcher",
  "set_code": "OGN", "number": "42", "rarity": "Common",
  "domain": "Fury", "card_type": "unit",
  "image_url": "/images/OGN-042.jpg",
  "count": 2, "foil_count": 1,
  "in_binder": false, "binder_foil": false,
  "limit": 3, "limit_override": null
}]
```

**Ordering** (via `sort_cards`): by `set_code`, then non-tokens before tokens, then
collector number **numerically**. Tokens have their `number` rewritten to `T01`-style
labels for display.

`limit` is the *resolved* limit — override, then rarity cap, then type default. See
[the limits engine](07-feature-deep-dives.md#collection-limits).

Two helpers in this module are reused by the community routes; keep them shared:

```python
sort_cards(cards)                     # in-place canonical ordering
build_card_list(db, cards, user_id)   # join against ONE user's inventory + rules
```

---

## 5.3 Inventory — `routes/inventory.py`

Both endpoints create the `InventoryItem` row on demand and return the updated `CardOut`.
`404` if the card id isn't in the catalog.

### `POST /api/inventory/{card_id}/increment`

| Query param | Default | Notes |
|---|---|---|
| `delta` | `1` | `-99 … 99`. Result is clamped at 0 — never negative |
| `foil` | `false` | Which tally to adjust |

### `PATCH /api/inventory/{card_id}`

```jsonc
{
  "count": 3,             // optional, ≥ 0
  "foil_count": 1,        // optional, ≥ 0
  "in_binder": true,      // optional
  "binder_foil": true,    // optional
  "limit_override": 4     // optional; explicit null clears the override
}
```

Uses `exclude_unset`, so omitted fields are untouched — this is a true partial update.
Two invariants are enforced server-side:

- setting `binder_foil: true` forces `in_binder: true`
- setting `in_binder: false` clears `binder_foil`

The frontend relies on this: it sends one field and trusts the response for both.

---

## 5.4 Community — `routes/community.py`

### `GET /api/community/users`

```jsonc
[{ "id": 2, "username": "bob", "unique_cards": 140, "total_copies": 312, "is_self": false }]
```

One row per registered user, ordered by username, with a headline of their collection
size so the directory is browsable without loading anyone's cards. `unique_cards` counts
binder-only rows (which contribute 0 to `total_copies`). `is_self` lets the UI badge your
own row.

### `GET /api/community/users/{user_id}/cards`

Identical shape and ordering to `GET /api/cards`, but resolved against `user_id`'s
inventory *and their limit rules*. `404` if the user doesn't exist.

**This is the only endpoint that accepts a user id from the request.** It is safe because
there is no write counterpart — every mutating route in the codebase targets
`current_user`. If you add a write endpoint that takes a user id, you are breaking the
model; don't.

---

## 5.5 Trades — `routes/trades.py`

Stateless: no table, no trade record. The exported text *is* the transport. Full walkthrough
in [feature deep dives](07-feature-deep-dives.md#trade-requests).

### `POST /api/trades/export`

```jsonc
// request
{ "to_username": "bob",
  "items": [ { "card_id": "UNL-003", "foil": false, "quantity": 2 } ] }   // quantity ≥ 1
// 200
{ "text": "# RIFTBOUND TRADE REQUEST v1\n# From: alice\n…" }
```

`400` on an empty basket. Card names are filled from the catalog server-side, so the
recipient sees real names even if the sender's client had none. `From:` is the
authenticated user — it can't be spoofed by the request body.

### `POST /api/trades/preview` — read-only

```jsonc
// request
{ "text": "…pasted request…" }
// 200
{
  "from_username": "alice", "to_username": "bob",
  "lines": [{
    "card_id": "UNL-003", "card_name": "Mosstomper",
    "image_url": "/images/UNL-003.jpg", "foil": false,
    "requested": 2, "current_count": 3, "resulting_count": 1,
    "known": true, "sufficient": true
  }],
  "warnings": ["Skipped unreadable line: …"]
}
```

Parses the text and joins it against **the caller's own** counts. Writes nothing —
`tests/test_trades.py` asserts this explicitly.

- `known: false` — the card id isn't in the catalog (also appended to `warnings`)
- `sufficient: false` — the owner holds fewer copies than requested
- `resulting_count` is floored at 0
- A `To:` naming someone other than the caller adds a warning but does not block

Parsing is deliberately lenient: unreadable lines become warnings, never exceptions, so a
hand-edited request stays usable.

### `POST /api/trades/fulfil` — the only write

```jsonc
// request
{ "items": [ { "card_id": "UNL-003", "foil": false, "quantity": 1 } ] }
// 200
{ "applied": 1, "cards": [ /* CardOut[] — updated, for in-place patching */ ] }
```

`404` on an unknown card id. **Safety properties, both covered by tests:**

1. Only ever writes to `current_user`'s rows.
2. Each deduction is `min(requested, held)` — a stale or forged request cannot drive a
   count negative.

`applied` is what was *actually* deducted, which may be less than requested. Rows the
caller doesn't hold at all are skipped silently.

---

## 5.6 Settings — `routes/settings.py`

### `GET` / `PUT /api/settings/limits`

```jsonc
{
  "type_limits": { "unit": 3, "spell": 3, "gear": 3,
                   "legend": 1, "battlefield": 1, "rune": 12 },
  "rarity_caps_enabled": false,
  "rarity_caps": { "epic": 1 },
  "fallback_limit": 3
}
```

Stored per user as JSON under the settings key `"{user_id}:limit_rules"`. `GET` merges
the stored blob over `DEFAULT_RULES`, so keys added in a later version appear
automatically. `PUT` merges the body over the current rules and returns the result.

> ⚠️ The `LimitRules` schema is **missing `showcase_cap_enabled`**, which
> `limits.DEFAULT_RULES` defines and the Settings UI renders a toggle for. FastAPI strips
> it from both directions, so the toggle silently never persists. See
> [known issue #2](09-known-issues.md).

### `GET` / `PUT /api/settings/deck-options`

```jsonc
{ "count_all_variants": true }
```

Same key-value pattern, under `"{user_id}:deck_options"`.

---

## 5.7 Backup — `routes/backup.py`

### `GET /api/backup/export` → `POST /api/backup/import` (JSON)

```jsonc
{
  "version": 1,
  "rules": { /* LimitRules */ },
  "inventory": [ { "card_id": "OGN-042", "count": 2, "foil_count": 1,
                   "in_binder": false, "binder_foil": false, "limit_override": null } ]
}
```

Export includes only rows that carry information (any count, in binder, or an override) —
it is not one row per catalog card. Import **replaces** the values on matching rows;
unknown card ids are counted as `skipped`, not errors, so a backup taken with more sets
ingested still restores cleanly. Returns `{"applied": n, "skipped": m}`.

### `GET` / `POST /api/backup/excel` (.xlsx)

The download is both a **physical backup** (prefilled with your counts) and an **ingest
template** (edit in Excel, upload the same file). Sheet `Collection`, row 1 frozen header:

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Card ID | Set | Number | Name | Rarity | Count | Foil count | In binder | Binder foil | Limit override |

A–E are reference columns (greyed); F–J are the editable ones. Column A identifies each
row. Upload validation: `.xlsx` extension (`415`), 10 MB cap (`413`), parseable workbook
(`422`). Cell coercion is forgiving — `_to_bool` accepts native booleans,
`TRUE`/`YES`/`Y`/`1`, and numbers; `_to_int` clamps negatives to 0. Deleted rows are left
alone, not zeroed.

> ⚠️ `exportExcel()` in `frontend/src/api.ts` bypasses the authenticated `request()`
> wrapper, so the download currently fails with 401. See
> [known issue #1](09-known-issues.md).

---

## 5.8 Prices — `routes/prices.py`

All price endpoints return `configured: false` with null fields when
`RIFTBOUND_PRICE_API_KEY` is unset. Nothing errors.

**Route order matters:** `/status` and `/summary` are declared *before* `/{card_id}`,
otherwise the path parameter would swallow them. Keep new literal paths above the
parameterised one.

| Endpoint | Spends API budget? | Notes |
|---|---|---|
| `GET /api/prices/status` | no | `{configured, requests_used_today, daily_budget, stale_hours}` |
| `GET /api/prices/summary?ids=a,b,c` | **no** | Batched cached prices, max 200 ids; unknown ids omitted |
| `GET /api/prices/{card_id}` | **yes, if stale** | Best-effort on-demand refresh |
| `GET /api/prices/{card_id}/history?days=30` | no | `days` 1–365; daily snapshots |

`PriceOut` carries `market_price`, `low_price`, `foil_market_price`, `foil_low_price`,
`currency`, `updated_at`, `stale`, and `pct_change_7d` / `pct_change_30d` computed from
local history.

**The grid uses `/summary` precisely because it never spends budget.** Only opening a
single card can trigger a refresh. Don't change that.

---

## 5.9 Decks — `routes/decks/`

| Endpoint | Purpose |
|---|---|
| `GET /api/decks/community` | Merged decks from RiftRank + TopDeck.gg. 6-hour in-process cache; provider failures are logged and skipped, never fatal |
| `POST /api/decks/import` | Parse a decklist and resolve names → card ids. **Does not persist** |
| `GET /api/decks/saved` | The caller's saved decks, newest first |
| `POST /api/decks/saved` | Parse and persist. Body `{text, format}` where format is `"piltover"` (default) or `"riftbound_gg"` |
| `PATCH /api/decks/saved/{id}/meta` | Set/clear `source_url` |
| `PATCH /api/decks/saved/{id}/commit` | Set `committed_quantity` for one card |
| `POST /api/decks/saved/{id}/commit-all` | `{commit: bool}` — commit or release every card |
| `DELETE /api/decks/saved/{id}` | Delete (cascades to `saved_deck_cards`) |

Every `/saved/*` route filters on `SavedDeck.user_id == current_user.id` and returns
`404` — not `403` — for someone else's deck, so the API doesn't confirm that an id exists.

**Committing** reserves physical copies for a deck. `App.tsx` builds a `commitmentMap`
(card id → `[{deckName, qty}]`) from all saved decks and passes it to `Collection`, so a
tile can show "2 committed to Yasuo".

These routes return hand-built dicts rather than Pydantic response models — the odd one
out in this codebase. New deck endpoints should prefer a schema.

---

## 5.10 Images

`GET /images/{filename}` — mounted via Starlette `StaticFiles` in `main.py`, which
resolves strictly inside `data/images/` (no path traversal). Unauthenticated: image URLs
in `CardOut` are card art, not user data.

---

Next: [Frontend guide →](06-frontend.md)
