"""Collection-limit rules engine.

Defaults are derived from Riftbound's deck-construction rules
(https://playriftbound.com/en-us/news/rules-and-releases/deckbuilding-primer/):
a deck may run at most 3 copies of a card, exactly 1 Legend, 3 distinct
Battlefields (1 copy each), and a 12-card rune deck. Owning that many copies
means you can build any deck that uses the card, which is the natural
"collection complete" target.

Resolution order (most specific wins):
  per-card override > rarity cap (if enabled) > card-type default
"""

import json

from sqlalchemy.orm import Session

from .models import Setting

SETTINGS_KEY = "limit_rules"

DEFAULT_RULES = {
    "type_limits": {
        "unit": 3,
        "spell": 3,
        "gear": 3,
        "legend": 1,
        "battlefield": 1,
        "rune": 12,
    },
    # When enabled, caps cards of a rarity regardless of type — useful if you
    # collect high rarities for display (1 copy) rather than play (a playset).
    "rarity_caps_enabled": False,
    "rarity_caps": {"epic": 1},
    # When enabled, showcase-rarity cards (alternate art / collector variants)
    # are capped at 1 — you only need one copy for display purposes.
    "showcase_cap_enabled": False,
    "fallback_limit": 3,
}


def _key(user_id: int) -> str:
    return f"{user_id}:{SETTINGS_KEY}"


def get_rules(db: Session, user_id: int) -> dict:
    row = db.get(Setting, _key(user_id))
    if row is None:
        return json.loads(json.dumps(DEFAULT_RULES))  # deep copy
    stored = json.loads(row.value)
    merged = json.loads(json.dumps(DEFAULT_RULES))
    merged.update({k: stored[k] for k in stored if k in merged})
    return merged


def save_rules(db: Session, user_id: int, rules: dict) -> dict:
    current = get_rules(db, user_id)
    current.update({k: rules[k] for k in rules if k in current})
    key = _key(user_id)
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=json.dumps(current))
        db.add(row)
    else:
        row.value = json.dumps(current)
    db.commit()
    return current


def effective_limit(
    card_type: str,
    rarity: str,
    rules: dict,
    override: int | None = None,
) -> int:
    if override is not None:
        return override
    limit = rules["type_limits"].get(
        card_type.lower(), rules["fallback_limit"]
    )
    if rules.get("rarity_caps_enabled"):
        cap = rules["rarity_caps"].get(rarity.lower())
        if cap is not None:
            limit = min(limit, cap)
    if rules.get("showcase_cap_enabled") and rarity.lower() == "showcase":
        limit = min(limit, 1)
    return limit
