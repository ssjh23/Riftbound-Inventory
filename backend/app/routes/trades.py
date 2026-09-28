from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import card_to_out, get_db
from ..limits import get_rules
from ..models import Card, InventoryItem, User
from ..schemas import (
    CardOut,
    TradeExportOut,
    TradeExportRequest,
    TradeFulfilOut,
    TradeFulfilRequest,
    TradeParseRequest,
    TradePreviewLine,
    TradePreviewOut,
)
from ..trades import TradeLine, format_request, parse_request

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("/export", response_model=TradeExportOut)
def export_request(
    body: TradeExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Render the requester's basket as shareable text. Card names are filled
    in from the catalog here so the recipient sees real names even if the
    sender's client had none."""
    if not body.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No cards selected")

    lines = []
    for item in body.items:
        card = db.get(Card, item.card_id)
        lines.append(
            TradeLine(
                card_id=item.card_id,
                card_name=card.name if card else "",
                foil=item.foil,
                quantity=item.quantity,
            )
        )
    text = format_request(
        from_username=current_user.username,
        to_username=body.to_username,
        date_str=date.today().isoformat(),
        lines=lines,
    )
    return TradeExportOut(text=text)


@router.post("/preview", response_model=TradePreviewOut)
def preview_request(
    body: TradeParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse a pasted request and show it against the owner's own shelves:
    what was asked for, what they hold now, and what they'd be left with."""
    parsed = parse_request(body.text)
    warnings = list(parsed.warnings)

    if parsed.to_username and parsed.to_username.lower() != current_user.username.lower():
        warnings.append(
            f"This request was addressed to \"{parsed.to_username}\", not you."
        )

    lines: list[TradePreviewLine] = []
    for ln in parsed.lines:
        card = db.get(Card, ln.card_id)
        inv = db.get(InventoryItem, (current_user.id, ln.card_id))
        current = 0
        if inv is not None:
            current = inv.foil_count if ln.foil else inv.count
        if card is None:
            warnings.append(f"Unknown card id \"{ln.card_id}\" — skipped.")
        lines.append(
            TradePreviewLine(
                card_id=ln.card_id,
                card_name=card.name if card else (ln.card_name or ln.card_id),
                image_url=f"/images/{card.image_file}" if card else None,
                foil=ln.foil,
                requested=ln.quantity,
                current_count=current,
                resulting_count=max(0, current - ln.quantity),
                known=card is not None,
                sufficient=card is not None and current >= ln.quantity,
            )
        )

    return TradePreviewOut(
        from_username=parsed.from_username,
        to_username=parsed.to_username,
        lines=lines,
        warnings=warnings,
    )


@router.post("/fulfil", response_model=TradeFulfilOut)
def fulfil_request(
    body: TradeFulfilRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hand the cards over: deduct the confirmed quantities from the caller's
    own inventory. Only ever touches the authenticated user's rows, and each
    deduction is clamped to what they actually hold, so a stale preview can
    never drive a count negative."""
    applied = 0
    touched: dict[str, InventoryItem] = {}

    for item in body.items:
        card = db.get(Card, item.card_id)
        if card is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown card {item.card_id}")
        inv = db.get(InventoryItem, (current_user.id, item.card_id))
        if inv is None:
            continue  # nothing held, nothing to give
        if item.foil:
            take = min(item.quantity, inv.foil_count)
            inv.foil_count -= take
        else:
            take = min(item.quantity, inv.count)
            inv.count -= take
        applied += take
        touched[item.card_id] = inv

    db.commit()

    rules = get_rules(db, current_user.id)
    cards: list[CardOut] = [
        card_to_out(db.get(Card, card_id), inv, rules) for card_id, inv in touched.items()
    ]
    return TradeFulfilOut(applied=applied, cards=cards)
