from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import PRICE_DAILY_BUDGET, PRICE_STALE_HOURS, price_api_key
from ..deps import get_db
from ..models import Card, CardPrice, CardPriceHistory, User
from ..pricing import budget
from ..pricing.service import is_stale, pct_change, try_refresh_if_stale
from ..schemas import PriceHistoryOut, PriceHistoryPoint, PriceOut, PriceStatusOut

router = APIRouter(prefix="/api/prices", tags=["prices"])


def _price_out(db: Session, card: Card, price: CardPrice | None) -> PriceOut:
    if not price_api_key():
        return PriceOut(card_id=card.id, configured=False, stale=True)
    history = (
        db.query(CardPriceHistory)
        .filter(CardPriceHistory.card_id == card.id)
        .all()
    )
    return PriceOut(
        card_id=card.id,
        configured=True,
        market_price=price.market_price if price else None,
        low_price=price.low_price if price else None,
        foil_market_price=price.foil_market_price if price else None,
        foil_low_price=price.foil_low_price if price else None,
        currency=price.currency if price else "USD",
        updated_at=price.updated_at.isoformat() if price else None,
        stale=is_stale(price),
        pct_change_7d=pct_change(history, 7, price.market_price if price else None),
        pct_change_30d=pct_change(history, 30, price.market_price if price else None),
    )


@router.get("/status", response_model=PriceStatusOut)
def price_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return PriceStatusOut(
        configured=bool(price_api_key()),
        requests_used_today=PRICE_DAILY_BUDGET - budget.remaining(db),
        daily_budget=PRICE_DAILY_BUDGET,
        stale_hours=PRICE_STALE_HOURS,
    )


@router.get("/summary", response_model=list[PriceOut])
def price_summary(
    ids: str = Query(..., description="comma-separated card ids"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Batched current prices for cards actually on screen. Never triggers a
    live refresh — always serves whatever is cached, so rendering a page of
    tiles is fast and free regardless of the pricing API's budget."""
    card_ids = [i.strip() for i in ids.split(",") if i.strip()][:200]
    out = []
    for card_id in card_ids:
        card = db.get(Card, card_id)
        if card is None:
            continue
        price = db.get(CardPrice, card_id)
        out.append(_price_out(db, card, price))
    return out


@router.get("/{card_id}", response_model=PriceOut)
def get_price(
    card_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(404, f"unknown card {card_id}")
    price = try_refresh_if_stale(db, card)
    return _price_out(db, card, price)


@router.get("/{card_id}/history", response_model=PriceHistoryOut)
def get_price_history(
    card_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(404, f"unknown card {card_id}")
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    rows = (
        db.query(CardPriceHistory)
        .filter(CardPriceHistory.card_id == card_id, CardPriceHistory.snapshot_date >= cutoff)
        .order_by(CardPriceHistory.snapshot_date)
        .all()
    )
    return PriceHistoryOut(
        card_id=card_id,
        points=[
            PriceHistoryPoint(
                date=r.snapshot_date,
                market_price=r.market_price,
                foil_market_price=r.foil_market_price,
            )
            for r in rows
        ],
    )
