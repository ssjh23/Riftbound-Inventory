"""Orchestrates price refreshing: matching, budget spending, upserting the
current price, and appending today's history snapshot.

Two call patterns:
  * on-demand — `refresh_card` for a single card when its cached price is
    stale and someone is actively looking at it (routes/prices.py).
  * scheduled top-up — `refresh_stale_batch`, run manually or via a cron
    job (see README), spends the remaining daily budget on the cards that
    most need it: owned cards first, then whichever have gone longest
    without a refresh.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import PRICE_STALE_HOURS
from ..models import Card, CardPrice, CardPriceHistory, InventoryItem
from . import budget
from .client import PriceApiNotConfigured, PriceClient
from .matcher import resolve_source_id

logger = logging.getLogger(__name__)


def is_stale(price: CardPrice | None) -> bool:
    if price is None:
        return True
    age = datetime.utcnow() - price.updated_at
    return age > timedelta(hours=PRICE_STALE_HOURS)


def refresh_card(db: Session, client: PriceClient, card: Card) -> CardPrice | None:
    """Fetch and store the current price for one card. Spends 1 request to
    match (only the first time a card is ever priced) plus 1 to fetch the
    price. Returns None if the card can't be matched to the external catalog
    — that's a normal, non-fatal outcome, not an error."""
    had_source_id = bool(card.price_source_id)
    source_id = resolve_source_id(db, client, card)
    requests_spent = 0 if had_source_id else 1  # the search call, whether or not it matched
    if source_id is None:
        if requests_spent:
            budget.spend(db, requests_spent)
        db.commit()
        return None

    fields = client.get_card_price(source_id)
    requests_spent += 1
    budget.spend(db, requests_spent)

    price = db.get(CardPrice, card.id)
    if price is None:
        price = CardPrice(card_id=card.id)
        db.add(price)
    price.market_price = fields.market_price
    price.low_price = fields.low_price
    price.foil_market_price = fields.foil_market_price
    price.foil_low_price = fields.foil_low_price
    price.currency = fields.currency
    price.updated_at = datetime.utcnow()

    today = datetime.now(timezone.utc).date()
    existing_snapshot = (
        db.query(CardPriceHistory)
        .filter(CardPriceHistory.card_id == card.id, CardPriceHistory.snapshot_date == today)
        .first()
    )
    if existing_snapshot is None:
        db.add(
            CardPriceHistory(
                card_id=card.id,
                snapshot_date=today,
                market_price=fields.market_price,
                foil_market_price=fields.foil_market_price,
            )
        )
    else:
        # Re-refreshed same day (e.g. on-demand after a batch run) — keep the
        # snapshot current rather than appending a duplicate for the day.
        existing_snapshot.market_price = fields.market_price
        existing_snapshot.foil_market_price = fields.foil_market_price

    db.commit()
    return price


def refresh_stale_batch(db: Session, client: PriceClient, limit: int) -> dict:
    """Refresh up to `limit` cards, prioritizing owned cards, then the
    longest-stale. Stops early if the daily budget runs out. Returns a
    summary dict for logging/CLI output."""
    owned_ids = {
        row.card_id
        for row in db.query(InventoryItem.card_id).filter(
            (InventoryItem.count > 0)
            | (InventoryItem.foil_count > 0)
            | (InventoryItem.in_binder.is_(True))
        )
    }

    candidates = db.query(Card).all()

    def sort_key(c: Card):
        price = db.get(CardPrice, c.id)
        last_updated = price.updated_at if price else datetime.min
        return (c.id not in owned_ids, last_updated)  # owned first, then oldest

    candidates.sort(key=sort_key)

    refreshed, matched, skipped = 0, 0, 0
    for card in candidates:
        if refreshed >= limit or not budget.has_budget(db):
            break
        price = refresh_card(db, client, card)
        refreshed += 1
        if price is not None:
            matched += 1
        else:
            skipped += 1
    return {"refreshed": refreshed, "matched": matched, "skipped": skipped}


def try_refresh_if_stale(db: Session, card: Card) -> CardPrice | None:
    """Best-effort on-demand refresh used by the API routes: no-ops quietly
    if pricing isn't configured or the budget is exhausted, so a price
    lookup never breaks the surrounding request."""
    price = db.get(CardPrice, card.id)
    if not is_stale(price):
        return price
    if not budget.has_budget(db):
        return price
    try:
        with PriceClient() as client:
            return refresh_card(db, client, card) or price
    except PriceApiNotConfigured:
        return price
    except Exception:
        logger.exception("on-demand price refresh failed for %s", card.id)
        return price


def pct_change(history: list[CardPriceHistory], days: int, current: float | None) -> float | None:
    """% change from the closest snapshot at least `days` old to `current`.
    None if there isn't enough history or no current price."""
    if current is None or not history:
        return None
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    older = [h for h in history if h.snapshot_date <= cutoff and h.market_price is not None]
    if not older:
        return None
    baseline = max(older, key=lambda h: h.snapshot_date).market_price
    if not baseline:
        return None
    return round((current - baseline) / baseline * 100, 2)
