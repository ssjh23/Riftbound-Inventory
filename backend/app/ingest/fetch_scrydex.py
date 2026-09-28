"""Ingest real Riftbound card data from the Scrydex API.

Requires an API key (https://scrydex.com/docs/riftbound/cards). Set
SCRYDEX_API_KEY and SCRYDEX_TEAM_ID, then run:

    python -m app.ingest.fetch_scrydex

Riot's Developer Portal (https://developer.riotgames.com/docs/riftbound) is
the fully-official alternative source; swap fetch_cards() accordingly.

All images pass through pipeline.download_image, which enforces HTTPS, a host
allowlist, content-type and size checks, and a Pillow re-encode (see
pipeline.py for the reasoning).
"""

import os
import re
import sys

import httpx
from sqlalchemy.orm import Session

from ..models import Card
from .pipeline import IngestError, download_image, store_card_image

API_BASE = "https://api.scrydex.com/v1/riftbound"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", value)[:64]


def fetch_cards(client: httpx.Client) -> list[dict]:
    cards: list[dict] = []
    page = 1
    while True:
        resp = client.get(f"{API_BASE}/cards", params={"page": page, "pageSize": 250})
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("data", [])
        if not batch:
            break
        cards.extend(batch)
        page += 1
    return cards


def ingest(db: Session) -> int:
    api_key = os.environ.get("SCRYDEX_API_KEY")
    team_id = os.environ.get("SCRYDEX_TEAM_ID", "")
    if not api_key:
        raise IngestError("SCRYDEX_API_KEY is not set")

    headers = {"X-Api-Key": api_key}
    if team_id:
        headers["X-Team-ID"] = team_id
    created = 0
    with httpx.Client(timeout=30, headers=headers) as client:
        for raw in fetch_cards(client):
            card_id = _slug(f"{raw.get('expansion', {}).get('code', 'UNK')}-{raw.get('number', raw.get('id', ''))}")
            if db.get(Card, card_id) is not None:
                continue
            images = raw.get("images") or {}
            image_url = images.get("large") or images.get("medium") or images.get("small")
            if not image_url:
                continue
            img = download_image(image_url, client=None)  # separate unauthenticated fetch
            image_file, phash = store_card_image(card_id, img)
            db.add(
                Card(
                    id=card_id,
                    name=raw.get("name", card_id),
                    set_code=raw.get("expansion", {}).get("code", "UNK"),
                    number=str(raw.get("number", "")),
                    rarity=str(raw.get("rarity", "Unknown")),
                    domain="/".join(raw.get("domains", [])) or "Unknown",
                    card_type=str(raw.get("type", "unit")).lower(),
                    image_file=image_file,
                    phash=phash,
                    source_url=image_url,
                )
            )
            created += 1
        db.commit()
    return created


if __name__ == "__main__":
    from ..config import data_dir
    from ..db import Base, make_engine, make_session_factory

    engine = make_engine(data_dir() / "riftbound.db")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        try:
            n = ingest(session)
        except IngestError as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            sys.exit(1)
    print(f"ingested {n} cards")
