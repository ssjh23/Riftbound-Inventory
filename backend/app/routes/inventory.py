from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import card_to_out, get_db
from ..limits import get_rules
from ..models import Card, InventoryItem, User
from ..schemas import CardOut, InventoryPatch

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _get_or_create(db: Session, card_id: str, user_id: int) -> InventoryItem:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(404, f"unknown card {card_id}")
    inv = db.get(InventoryItem, (user_id, card_id))
    if inv is None:
        inv = InventoryItem(
            user_id=user_id, card_id=card_id,
            count=0, foil_count=0, in_binder=False, binder_foil=False,
        )
        db.add(inv)
    return inv


@router.post("/{card_id}/increment", response_model=CardOut)
def increment(
    card_id: str,
    delta: int = Query(default=1, ge=-99, le=99),
    foil: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = _get_or_create(db, card_id, current_user.id)
    if foil:
        inv.foil_count = max(0, inv.foil_count + delta)
    else:
        inv.count = max(0, inv.count + delta)
    db.commit()
    card = db.get(Card, card_id)
    return card_to_out(card, inv, get_rules(db, current_user.id))


@router.patch("/{card_id}", response_model=CardOut)
def patch(
    card_id: str,
    body: InventoryPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = _get_or_create(db, card_id, current_user.id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("count") is not None:
        inv.count = fields["count"]
    if fields.get("foil_count") is not None:
        inv.foil_count = fields["foil_count"]
    if fields.get("in_binder") is not None:
        inv.in_binder = fields["in_binder"]
        if not inv.in_binder:  # leaving the binder clears its foil marker
            inv.binder_foil = False
    if fields.get("binder_foil") is not None:
        inv.binder_foil = fields["binder_foil"]
        if inv.binder_foil:  # a foil binder card must be in the binder
            inv.in_binder = True
    if "limit_override" in fields:  # explicit null clears the override
        inv.limit_override = fields["limit_override"]
    db.commit()
    card = db.get(Card, card_id)
    return card_to_out(card, inv, get_rules(db, current_user.id))
