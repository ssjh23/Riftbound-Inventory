import re

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import card_to_out, get_db
from ..limits import get_rules
from ..models import Card, InventoryItem, User
from ..schemas import CardOut

router = APIRouter(prefix="/api/cards", tags=["cards"])


TOKEN_RE = re.compile(r"-T(\d+)$", re.IGNORECASE)


def _number_key(number: str) -> tuple[int, str]:
    """Sort collector numbers numerically ("2" before "10" before "100"),
    since `number` is stored as a string. Non-numeric numbers fall back to the
    raw string after all numbered cards."""
    m = re.match(r"\d+", number or "")
    return (int(m.group()) if m else 10**9, number or "")


def _token_number(card_id: str) -> str | None:
    """Return a token's "T0X" label from its id (e.g. UNL-T01 -> "T01"), or
    None if the card is not a token. Tokens carry a `-T<n>` public code in the
    official gallery; our ids preserve it."""
    m = TOKEN_RE.search(card_id)
    return f"T{m.group(1).zfill(2)}" if m else None


def sort_cards(cards: list[Card]) -> None:
    """Sort in place: non-tokens first (numeric order), then tokens at the
    back of each set."""
    cards.sort(
        key=lambda c: (c.set_code, _token_number(c.id) is not None, _number_key(c.number))
    )


def build_card_list(db: Session, cards: list[Card], user_id: int) -> list[CardOut]:
    """Join cards with one user's inventory counts and their effective limits.
    Shared by the owner's own collection and the read-only community views, so
    another user's collection renders through exactly the same shape."""
    inv_map: dict[str, InventoryItem] = {
        i.card_id: i
        for i in db.query(InventoryItem).filter(InventoryItem.user_id == user_id).all()
    }
    rules = get_rules(db, user_id)
    out = []
    for c in cards:
        co = card_to_out(c, inv_map.get(c.id), rules)
        token = _token_number(c.id)
        if token is not None:
            co.number = token  # display "T01" instead of the raw number
        out.append(co)
    return out


@router.get("", response_model=list[CardOut])
def list_cards(
    search: str | None = None,
    set_code: str | None = None,
    domain: str | None = None,
    rarity: str | None = None,
    card_type: str | None = None,
    owned: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Card)
    if search:
        q = q.filter(or_(Card.name.ilike(f"%{search}%"), Card.id.ilike(f"%{search}%")))
    if set_code:
        q = q.filter(Card.set_code == set_code)
    if domain:
        q = q.filter(Card.domain.ilike(f"%{domain}%"))
    if rarity:
        q = q.filter(Card.rarity == rarity)
    if card_type:
        q = q.filter(Card.card_type == card_type)
    cards = q.all()
    sort_cards(cards)
    out = build_card_list(db, cards, current_user.id)
    if owned is True:  # owned = any copy (foil or non-foil) or marked in binder
        out = [c for c in out if c.count + c.foil_count > 0 or c.in_binder]
    elif owned is False:
        out = [c for c in out if c.count + c.foil_count == 0 and not c.in_binder]
    return out
