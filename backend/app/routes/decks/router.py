import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...config import topdeck_api_key
from ...deps import get_db
from ...models import SavedDeck, SavedDeckCard, User
from . import _common, riftrank, topdeck

router = APIRouter(prefix="/api/decks", tags=["decks"])


class _ImportBody(BaseModel):
    text: str
    format: str = "piltover"  # "piltover" | "riftbound_gg"


class _MetaBody(BaseModel):
    source_url: str | None = None


class _CommitBody(BaseModel):
    card_id: str
    quantity: int


class _CommitAllBody(BaseModel):
    commit: bool  # True = commit all, False = uncommit all


_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 6 * 3600


def _parse_and_resolve(db: Session, text: str, fmt: str) -> list[dict]:
    """Route text to the right parser + resolver based on the source format."""
    if fmt == "riftbound_gg":
        raw = _common._parse_riftbound_gg(text)
        return _common._resolve_riftbound_gg(db, raw)
    raw = _common._parse_piltover_text(text)
    return _common._resolve_names(db, raw)


def _deck_to_dict(deck: SavedDeck) -> dict:
    sets = sorted({c.card_id.split("-")[0] for c in deck.cards if c.card_id})
    return {
        "id": str(deck.id),
        "name": deck.name,
        "legend": deck.legend,
        "legend_image_url": deck.legend_image_url,
        "player": "",
        "placement": 0,
        "wins": 0,
        "losses": 0,
        "tournament": "Imported Deck",
        "source": deck.source,
        "source_url": deck.source_url,
        "date": deck.created_at.strftime("%Y-%m-%d"),
        "sets": sets,
        "cards": [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "quantity": c.quantity,
                "section": c.section,
                "committed_quantity": c.committed_quantity,
            }
            for c in deck.cards
        ],
    }


@router.get("/community")
def get_community_decks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["data"]

    rr_decks: list[dict] = []
    try:
        rr_decks = riftrank.fetch(db)
    except Exception as exc:
        print(f"[decks] RiftRank error: {exc}")

    td_decks: list[dict] = []
    api_key = topdeck_api_key()
    if api_key:
        try:
            td_decks = topdeck.fetch(db, api_key)
        except Exception as exc:
            print(f"[decks] TopDeck.gg error: {exc}")

    cdn_images: dict[str, str] = {}
    for d in rr_decks:
        img = d.get("legend_image_url")
        if img:
            for c in d.get("cards", []):
                if c.get("section") == "Legend" and c.get("card_id"):
                    cdn_images[c["card_id"]] = img

    for d in td_decks:
        if not d.get("legend_image_url"):
            for c in d.get("cards", []):
                if c.get("section") == "Legend" and c.get("card_id"):
                    d["legend_image_url"] = cdn_images.get(c["card_id"])
                    break

    decks: list[dict] = td_decks + rr_decks

    seen: set[str] = set()
    unique: list[dict] = []
    for d in decks:
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)

    unique.sort(key=lambda d: d.get("date") or "", reverse=True)
    unique = unique[:100]

    result: dict = {"configured": True, "decks": unique}
    _cache["data"] = result
    _cache["ts"] = now
    return result


@router.post("/import")
def import_deck(
    body: _ImportBody,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    resolved = _parse_and_resolve(db, body.text, body.format)

    legend_slot = next((c for c in resolved if c["section"] == "Legend"), None)
    legend_name = legend_slot["card_name"] if legend_slot else "Imported Deck"

    sets = sorted({
        c["card_id"].split("-")[0]
        for c in resolved
        if c.get("card_id")
    })

    deck_id = "import-" + hashlib.md5(body.text.encode()).hexdigest()[:8]

    return {
        "id": deck_id,
        "name": legend_name,
        "legend": legend_name,
        "legend_image_url": _common.legend_image_url(db, resolved),
        "player": "",
        "placement": 0,
        "wins": 0,
        "losses": 0,
        "tournament": "Imported Deck",
        "source": "Piltover Archive",
        "source_url": None,
        "date": "",
        "sets": sets,
        "cards": resolved,
    }


@router.get("/saved")
def list_saved_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    decks = (
        db.query(SavedDeck)
        .filter(SavedDeck.user_id == current_user.id)
        .order_by(SavedDeck.created_at.desc())
        .all()
    )
    return [_deck_to_dict(d) for d in decks]


@router.post("/saved")
def save_deck(
    body: _ImportBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _parse_and_resolve(db, body.text, body.format)

    legend_slot = next((c for c in resolved if c["section"] == "Legend"), None)
    legend_name = legend_slot["card_name"] if legend_slot else "Imported Deck"

    deck = SavedDeck(
        user_id=current_user.id,
        name=legend_name,
        legend=legend_name,
        legend_image_url=_common.legend_image_url(db, resolved),
        source="Piltover Archive",
    )
    db.add(deck)
    db.flush()

    for c in resolved:
        db.add(SavedDeckCard(
            deck_id=deck.id,
            card_id=c.get("card_id"),
            card_name=c["card_name"],
            quantity=c["quantity"],
            section=c["section"],
        ))

    db.commit()
    db.refresh(deck)
    return _deck_to_dict(deck)


@router.patch("/saved/{deck_id}/meta")
def update_deck_meta(
    deck_id: int,
    body: _MetaBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = (
        db.query(SavedDeck)
        .filter(SavedDeck.id == deck_id, SavedDeck.user_id == current_user.id)
        .first()
    )
    if deck is None:
        raise HTTPException(404, "deck not found")
    url = (body.source_url or "").strip()
    deck.source_url = url if url else None
    db.commit()
    db.refresh(deck)
    return _deck_to_dict(deck)


@router.post("/saved/{deck_id}/commit-all")
def commit_all_cards(
    deck_id: int,
    body: _CommitAllBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = (
        db.query(SavedDeck)
        .filter(SavedDeck.id == deck_id, SavedDeck.user_id == current_user.id)
        .first()
    )
    if deck is None:
        raise HTTPException(404, "deck not found")
    for card_row in deck.cards:
        if card_row.card_id:
            card_row.committed_quantity = card_row.quantity if body.commit else 0
    db.commit()
    db.refresh(deck)
    return _deck_to_dict(deck)


@router.patch("/saved/{deck_id}/commit")
def commit_card(
    deck_id: int,
    body: _CommitBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = (
        db.query(SavedDeck)
        .filter(SavedDeck.id == deck_id, SavedDeck.user_id == current_user.id)
        .first()
    )
    if deck is None:
        raise HTTPException(404, "deck not found")
    card_rows = (
        db.query(SavedDeckCard)
        .filter(SavedDeckCard.deck_id == deck_id, SavedDeckCard.card_id == body.card_id)
        .all()
    )
    if not card_rows:
        raise HTTPException(404, "card not in deck")
    for row in card_rows:
        row.committed_quantity = 0
    if body.quantity > 0:
        card_rows[0].committed_quantity = body.quantity
    db.commit()
    db.refresh(deck)
    return _deck_to_dict(deck)


@router.delete("/saved/{deck_id}")
def delete_saved_deck(
    deck_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = (
        db.query(SavedDeck)
        .filter(SavedDeck.id == deck_id, SavedDeck.user_id == current_user.id)
        .first()
    )
    if deck is None:
        raise HTTPException(404, "deck not found")
    db.delete(deck)
    db.commit()
    return {"ok": True}
