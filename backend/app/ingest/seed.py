"""Generate a deterministic demo card set so the app is fully usable (and
testable) before real card data is ingested.

The demo cards are modeled on the Unleashed set (UNL, Riftbound set 3):
real card and champion names where confirmed publicly (Master Yi, Kha'Zix,
Baron Nashor, Mosstomper, Inferna, Baron Pit, ...); domains/rarities/numbers
are placeholders until real data is ingested. Each card gets procedurally
generated 'art' (seeded per card id, so the same card always renders
identical pixels) — this gives every card a distinct pHash, exactly like
real card art would. Replace with fetch_scrydex.py output once you have an
API key; the rest of the app is source-agnostic.
"""

import random

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from ..models import Card
from .pipeline import store_card_image

W, H = 480, 670

DOMAIN_COLORS = {
    "Fury": (170, 40, 40),
    "Calm": (40, 120, 150),
    "Mind": (110, 60, 160),
    "Body": (60, 130, 60),
    "Order": (180, 150, 60),
    "Chaos": (150, 60, 130),
    "Colorless": (120, 120, 120),
}

SEED_CARDS = [
    # (id, name, number, rarity, domain, card_type)
    ("UNL-001", "Master Yi, Unstoppable", "001", "Legend", "Calm/Body", "legend"),
    ("UNL-002", "Kha'Zix, Voidreaver", "002", "Legend", "Chaos/Body", "legend"),
    ("UNL-003", "Mosstomper", "003", "Uncommon", "Body", "unit"),
    ("UNL-004", "Inferna", "004", "Rare", "Fury", "unit"),
    ("UNL-005", "Vi", "005", "Rare", "Fury", "unit"),
    ("UNL-006", "Pyke", "006", "Rare", "Chaos", "unit"),
    ("UNL-007", "LeBlanc", "007", "Epic", "Mind", "unit"),
    ("UNL-008", "Rengar", "008", "Rare", "Body", "unit"),
    ("UNL-009", "Ivern, Green Father", "009", "Rare", "Body", "unit"),
    ("UNL-010", "Baron Nashor", "010", "Ultimate", "Colorless", "unit"),
    ("UNL-011", "Baron Pit", "011", "Epic", "Colorless", "battlefield"),
    ("UNL-012", "Alpha Strike", "012", "Rare", "Calm", "spell"),
    ("UNL-013", "Void Assault", "013", "Uncommon", "Chaos", "spell"),
    ("UNL-014", "Wuju Blade", "014", "Uncommon", "Calm", "gear"),
    ("UNL-015", "Body Rune", "015", "Common", "Body", "rune"),
    ("UNL-016", "Fury Rune", "016", "Common", "Fury", "rune"),
]


def render_card(card_id: str, name: str, domain: str, card_type: str) -> Image.Image:
    rng = random.Random(card_id)
    base = DOMAIN_COLORS.get(domain.split("/")[0], (90, 90, 90))
    img = Image.new("RGB", (W, H), tuple(c // 3 for c in base))
    draw = ImageDraw.Draw(img)

    # Frame + name bar + type bar, like a real card layout.
    draw.rectangle([12, 12, W - 12, H - 12], outline=(230, 220, 190), width=6)
    draw.rectangle([24, 24, W - 24, 78], fill=(25, 25, 30))
    draw.text((36, 42), name, fill=(240, 235, 220))
    draw.rectangle([24, H - 78, W - 24, H - 24], fill=(25, 25, 30))
    draw.text((36, H - 62), f"{card_type.upper()}  ·  {domain}", fill=(200, 195, 180))

    # Procedural 'art': random shapes seeded by card id -> unique, stable pHash.
    for _ in range(28):
        x0, y0 = rng.randint(30, W - 120), rng.randint(90, H - 200)
        x1, y1 = x0 + rng.randint(30, 110), y0 + rng.randint(30, 110)
        color = tuple(min(255, c + rng.randint(-60, 100)) for c in base)
        if rng.random() < 0.5:
            draw.ellipse([x0, y0, x1, y1], fill=color)
        else:
            draw.rectangle([x0, y0, x1, y1], fill=color)
    return img


def seed_database(db: Session) -> int:
    created = 0
    for card_id, name, number, rarity, domain, card_type in SEED_CARDS:
        if db.get(Card, card_id) is not None:
            continue
        img = render_card(card_id, name, domain, card_type)
        image_file, phash = store_card_image(card_id, img)
        db.add(
            Card(
                id=card_id,
                name=name,
                set_code="UNL",
                number=number,
                rarity=rarity,
                domain=domain,
                card_type=card_type,
                image_file=image_file,
                phash=phash,
                source_url="generated://seed",
            )
        )
        created += 1
    db.commit()
    return created
