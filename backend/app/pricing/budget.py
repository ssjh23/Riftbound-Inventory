"""Daily request-budget tracker for the pricing API's free tier (100/day).

One row per UTC date in `price_api_usage`; `spend()` is the only mutator, and
it's atomic per call (read-then-write inside the caller's existing session/
transaction), so a batch job and an on-demand request racing on the same day
can't jointly overspend by more than one request.
"""

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..config import PRICE_DAILY_BUDGET
from ..models import PriceApiUsage


def _today() -> date:
    return datetime.now(timezone.utc).date()


def remaining(db: Session) -> int:
    row = db.get(PriceApiUsage, _today())
    used = row.request_count if row else 0
    return max(0, PRICE_DAILY_BUDGET - used)


def has_budget(db: Session) -> bool:
    return remaining(db) > 0


def spend(db: Session, n: int = 1) -> None:
    """Record `n` requests spent today. Caller is responsible for commit.
    Flushes immediately so a second `spend()` call later in the same
    (still-uncommitted) transaction sees this row via `db.get()` instead of
    trying to INSERT a second row for the same date and hitting the unique
    constraint — `.get()` only finds pending (un-flushed) objects once
    they've been flushed into the identity map."""
    today = _today()
    row = db.get(PriceApiUsage, today)
    if row is None:
        row = PriceApiUsage(usage_date=today, request_count=0)
        db.add(row)
        db.flush()
    row.request_count += n
