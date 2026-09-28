[← Docs index](README.md)

# 9. Known issues

Confirmed defects, each reproduced against the current code. They make good first
tickets: small, self-contained, and each one teaches a convention that matters here.

---

## #1 — Excel download fails with 401

**Severity:** medium — a user-visible feature is completely broken.
**Where:** `frontend/src/api.ts:144`

`exportExcel()` uses a bare `fetch` instead of the authenticated `request()` wrapper, so
no `Authorization` header is sent. `GET /api/backup/excel` requires auth, so the download
always fails.

```ts
export async function exportExcel(): Promise<{ blob: Blob; filename: string }> {
  const resp = await fetch("/api/backup/excel");          // ← no auth header
  if (!resp.ok) throw new Error(`GET /api/backup/excel failed: ${resp.status}`);
  ...
}
```

It can't simply call `request()`, because that helper parses JSON and this endpoint
returns a binary stream — which is presumably why it was written this way. The fix is to
attach the header manually (and ideally handle 401 the same way `request()` does — see
`setSessionExpiredHandler`):

```ts
import { getToken } from "./auth";

const token = getToken();
const resp = await fetch("/api/backup/excel", {
  headers: token ? { Authorization: `Bearer ${token}` } : {},
});
```

**Reproduce:**

```python
def test_excel_export_requires_auth(client):
    client.headers.pop("Authorization", None)
    assert client.get("/api/backup/excel").status_code == 401   # passes → the UI 401s too
```

Confirmed: returns **401**. `importExcel()` on the line below is fine — it goes through
`request()` (FormData bodies pass through untouched).

**Lesson:** every authenticated call goes through `request()`. When a response isn't JSON
and you must hand-roll the fetch, you own attaching auth and handling 401.

---

## #2 — The "Showcase cap" setting never persists

**Severity:** medium — a settings toggle silently does nothing.
**Where:** `backend/app/schemas.py:107` (`LimitRules`)

`limits.DEFAULT_RULES` defines `showcase_cap_enabled`, `effective_limit()` honours it, and
`Settings.tsx:138` renders a checkbox for it. But the `LimitRules` Pydantic model doesn't
declare the field, so FastAPI strips it in **both** directions:

- `PUT` — `body.model_dump()` never contains it, so `save_rules()` never stores it.
- `GET` — even if it were stored, the `response_model` would remove it before serializing.

The checkbox therefore always renders unchecked and the cap never applies.

```python
class LimitRules(BaseModel):
    type_limits: dict[str, int]
    rarity_caps_enabled: bool
    rarity_caps: dict[str, int]
    # showcase_cap_enabled: bool = False   ← missing
    fallback_limit: int = Field(ge=0)
```

**Reproduce:**

```python
def test_showcase_cap_round_trips(client):
    rules = client.get("/api/settings/limits").json()
    rules["showcase_cap_enabled"] = True
    client.put("/api/settings/limits", json=rules)
    assert client.get("/api/settings/limits").json().get("showcase_cap_enabled") is True
```

Confirmed: the `GET` response contains only `fallback_limit`, `rarity_caps`,
`rarity_caps_enabled`, `type_limits` — the field is absent at every step.

**Fix:** add `showcase_cap_enabled: bool = False` to `LimitRules`. Note the default
matters: existing clients that `PUT` without the field must not have it flipped on.

**Lesson:** the response model *is* the API contract. A field that exists in the ORM, the
rules dict, and the UI still doesn't exist as far as the API is concerned unless it's
declared in the schema. When adding anything user-visible, trace it through all five
layers: `DEFAULT_RULES` → `schemas.py` → route → `types.ts` → component.

---

## #3 — Two pre-existing test failures

**Severity:** low — noise that trains people to ignore red suites.

| Test | Symptom |
|---|---|
| `backend/tests/test_ingest_official.py::test_map_card_normalizes_gallery_fields` | Expects id `UNL-047-219`; the mapper yields `UNL-047` |
| `frontend/src/lib/price.test.ts` | `formatPctChange(0)` expects `"+0.0%"`; the implementation adds the `+` only when `pct > 0`, so it returns `"0.0%"` |

Both are assertion-vs-implementation disagreements, not crashes. Someone needs to decide
which side is right — the id scheme changed at some point, and `+0.0%` for a zero change is
arguably wrong anyway (a flat price isn't an increase).

Until they're resolved, a run showing **exactly these two** means you broke nothing.

---

## Non-issues worth knowing about

These look like bugs and aren't. Don't "fix" them:

**`GET /api/cards` has filter params the UI never sends.** Deliberate — see
[system design](02-system-design.md#client-side-filtering-server-side-filter-params).

**`/api/prices/status` and `/summary` are declared before `/{card_id}`.** Required. FastAPI
matches routes in declaration order; reordering them would make the path parameter swallow
both literals.

**`Community.tsx` returns a `<div>`, not a `<main>`.** It renders `Collection`, which
already returns a `<main>`; nesting them is invalid HTML.

**Every URL has a `#/` in it.** Deliberate — hash routing is what makes a reload (and a
phone's tab discard, which is the same event) land back on the screen you were on. It
needs no dependency and no server config. See
[frontend § hash routing](06-frontend.md#hash-routing-not-a-router-library).

**Filters reset in a new browser tab but not on reload.** Correct: view state lives in
`sessionStorage`, which is scoped to one tab on purpose. Only the token (`localStorage`)
is meant to follow you into a new tab.

**`Collection.tsx` fires a `PATCH` when you switch away from the tab.** That's the flush
of a debounced count edit, not a stray write. Without it, backgrounding the phone inside
the 600 ms debounce window silently discarded the click.

**`.count-label` has no `min-width: 0`.** Deliberate — it's what makes the row wrap instead
of truncating "NORMAL" to "NORM…" inside the clipping `.card-tile`. See
[frontend § CSS conventions](06-frontend.md#64-css-conventions-you-must-know).

**Deck routes return plain dicts instead of Pydantic models.** Inconsistent with the rest
of the codebase, but working. Worth converting if you're already changing those routes;
not worth a dedicated PR.

**`docker-compose.yml` references `${RIFTBOUND_TOPDECK_KEY:-}` but no value.** Correct:
API keys live in a gitignored `.env` next to it (copy `.env.example`). Never paste a key
back into the compose file — it is committed.

**Registering the first user runs an `UPDATE inventory SET user_id = ...`.** Intentional —
it adopts rows created before multi-user support existed.

---

[← Docs index](README.md)
