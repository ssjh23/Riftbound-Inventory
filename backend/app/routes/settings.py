import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import get_db
from ..limits import get_rules, save_rules
from ..models import Setting, User
from ..schemas import DeckOptionsOut, LimitRules

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DECK_OPT_KEY = "deck_options"
_DECK_OPT_DEFAULTS: dict = {"count_all_variants": True}


@router.get("/limits", response_model=LimitRules)
def read_limits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_rules(db, current_user.id)


@router.put("/limits", response_model=LimitRules)
def write_limits(
    body: LimitRules,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return save_rules(db, current_user.id, body.model_dump())


@router.get("/deck-options", response_model=DeckOptionsOut)
def read_deck_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = f"{current_user.id}:{_DECK_OPT_KEY}"
    row = db.get(Setting, key)
    if row is None:
        return _DECK_OPT_DEFAULTS.copy()
    stored = json.loads(row.value)
    merged = _DECK_OPT_DEFAULTS.copy()
    merged.update({k: stored[k] for k in stored if k in merged})
    return merged


@router.put("/deck-options", response_model=DeckOptionsOut)
def write_deck_options(
    body: DeckOptionsOut,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = f"{current_user.id}:{_DECK_OPT_KEY}"
    data = body.model_dump()
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=json.dumps(data))
        db.add(row)
    else:
        row.value = json.dumps(data)
    db.commit()
    return data
