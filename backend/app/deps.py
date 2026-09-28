from fastapi import Request
from sqlalchemy.orm import Session

from .limits import effective_limit, get_rules
from .models import Card, InventoryItem
from .schemas import CardOut


def get_db(request: Request):
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def card_to_out(card: Card, inv: InventoryItem | None, rules: dict) -> CardOut:
    override = inv.limit_override if inv else None
    return CardOut(
        id=card.id,
        name=card.name,
        set_code=card.set_code,
        number=card.number,
        rarity=card.rarity,
        domain=card.domain,
        card_type=card.card_type,
        image_url=f"/images/{card.image_file}",
        count=inv.count if inv else 0,
        foil_count=inv.foil_count if inv else 0,
        in_binder=inv.in_binder if inv else False,
        binder_foil=inv.binder_foil if inv else False,
        limit=effective_limit(card.card_type, card.rarity, rules, override),
        limit_override=override,
    )
