"""HTTP client for the external Riftbound price source.

Source: riftbound-api.com (branded TCGGO), reached via its RapidAPI listing
("Riftbound Prices API"). Free tier: 100 requests/day, current market + low
prices aggregated from Cardmarket and TCGPlayer — no historical endpoint on
the free tier, which is why CardPriceHistory exists (we build our own trend
by snapshotting current price over time).

IMPORTANT — schema caveat: this integration was built without an API key
(account creation is something this assistant does not do on the user's
behalf — see README). The endpoint paths and field names below come from the
provider's public marketing/description pages, NOT a verified live response,
because their formal docs pages returned 403 to automated fetches during
research. `parse_price_fields()` is written defensively — it tries several
plausible key spellings and degrades to `None` fields (never raises) if none
match, so a schema mismatch shows as "no price data" in the UI rather than a
crash. The first raw response received is captured to
`data/price_debug_last_response.json` (see `_capture_debug`) specifically so
a one-time adjustment against a real response is fast once a key is added.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import data_dir, price_api_host, price_api_key

logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://{host}/api/v1"
REQUEST_TIMEOUT = 15.0


class PriceApiNotConfigured(Exception):
    """Raised when no API key is set; callers should treat pricing as
    unavailable rather than surface this as an error."""


@dataclass
class ExternalCard:
    source_id: str
    name: str
    expansion: str | None
    raw: dict


@dataclass
class PriceFields:
    market_price: float | None
    low_price: float | None
    foil_market_price: float | None
    foil_low_price: float | None
    currency: str


def _capture_debug(payload: dict, label: str) -> None:
    """Write the raw response to disk once, for schema verification. Never
    raises — this is a debugging aid, not a critical path."""
    try:
        path = data_dir() / f"price_debug_{label}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("failed to write price debug capture")


def _first_number(*candidates: object) -> float | None:
    for c in candidates:
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            return float(c)
        if isinstance(c, str):
            try:
                return float(c.replace("$", "").replace(",", "").strip())
            except ValueError:
                continue
    return None


def parse_price_fields(raw: dict) -> PriceFields:
    """Defensively extract price fields from a card payload. Tries
    tcgplayer's block first (USD, matches this app's other USD-only
    assumptions), falls back to cardmarket. See module docstring — the exact
    key names are unverified against a live response."""
    prices = raw.get("prices") or {}
    tcg = prices.get("tcgplayer") or {}
    cm = prices.get("cardmarket") or {}

    market = _first_number(
        tcg.get("market"), tcg.get("marketPrice"), tcg.get("market_price"),
        tcg.get("mid"), cm.get("market"), cm.get("trend"), cm.get("avg"),
    )
    low = _first_number(
        tcg.get("low"), tcg.get("lowPrice"), tcg.get("low_price"),
        cm.get("low"),
    )
    foil_block = (
        tcg.get("foil") or cm.get("foil")
        or prices.get("foil") or {}
    )
    foil_market = _first_number(
        foil_block.get("market") if isinstance(foil_block, dict) else None,
        foil_block.get("marketPrice") if isinstance(foil_block, dict) else None,
    )
    foil_low = _first_number(
        foil_block.get("low") if isinstance(foil_block, dict) else None,
    )
    currency = str(tcg.get("currency") or cm.get("currency") or "USD")

    return PriceFields(
        market_price=market,
        low_price=low,
        foil_market_price=foil_market,
        foil_low_price=foil_low,
        currency=currency,
    )


class PriceClient:
    def __init__(self, client: httpx.Client | None = None):
        key = price_api_key()
        if not key:
            raise PriceApiNotConfigured("RIFTBOUND_PRICE_API_KEY is not set")
        host = price_api_host()
        self._base = BASE_URL_TEMPLATE.format(host=host)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": host},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PriceClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def search_cards(self, query: str) -> list[ExternalCard]:
        resp = self._client.get(f"{self._base}/cards", params={"search": query})
        resp.raise_for_status()
        payload = resp.json()
        _capture_debug(payload, "search")
        items = payload.get("data") if isinstance(payload, dict) else payload
        out = []
        for raw in items or []:
            sid = str(raw.get("id") or raw.get("card_id") or "")
            if not sid:
                continue
            out.append(
                ExternalCard(
                    source_id=sid,
                    name=str(raw.get("name", "")),
                    expansion=(raw.get("expansion") or raw.get("set") or {}).get("name")
                    if isinstance(raw.get("expansion") or raw.get("set"), dict)
                    else raw.get("expansion"),
                    raw=raw,
                )
            )
        return out

    def get_card_price(self, source_id: str) -> PriceFields:
        resp = self._client.get(f"{self._base}/cards/{source_id}")
        resp.raise_for_status()
        payload = resp.json()
        _capture_debug(payload, "card")
        raw = payload.get("data", payload) if isinstance(payload, dict) else payload
        return parse_price_fields(raw)
