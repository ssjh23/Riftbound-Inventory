from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import get_db
from ..models import Card, InventoryItem, User
from ..schemas import CardOut, CommunityUserOut
from .cards import build_card_list, sort_cards

router = APIRouter(prefix="/api/community", tags=["community"])


@router.get("/users", response_model=list[CommunityUserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every registered user plus a headline of their collection size, so the
    community directory is browsable without loading anyone's cards."""
    # One row per user: how many distinct cards they hold and how many total
    # copies. Binder-only rows count as collected but contribute zero copies.
    stats = {
        user_id: (unique_cards, int(copies or 0))
        for user_id, unique_cards, copies in (
            db.query(
                InventoryItem.user_id,
                func.count(InventoryItem.card_id),
                func.sum(InventoryItem.count + InventoryItem.foil_count),
            )
            .filter(
                or_(
                    InventoryItem.count + InventoryItem.foil_count > 0,
                    InventoryItem.in_binder.is_(True),
                )
            )
            .group_by(InventoryItem.user_id)
            .all()
        )
    }

    users = db.query(User).order_by(User.username).all()
    return [
        CommunityUserOut(
            id=u.id,
            username=u.username,
            unique_cards=stats.get(u.id, (0, 0))[0],
            total_copies=stats.get(u.id, (0, 0))[1],
            is_self=u.id == current_user.id,
        )
        for u in users
    ]


@router.get("/users/{user_id}/cards", response_model=list[CardOut])
def list_user_cards(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only view of another user's collection: the same payload as
    /api/cards, but resolved against `user_id`'s inventory and limit rules.
    There is no write counterpart — the inventory routes always target the
    authenticated user, so viewing can never mutate someone else's counts."""
    owner = db.get(User, user_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    cards = db.query(Card).all()
    sort_cards(cards)
    return build_card_list(db, cards, owner.id)
