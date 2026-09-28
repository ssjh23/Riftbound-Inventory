"""Free, keyless card ingest from Riot's official Riftbound card gallery.

The gallery at https://playriftbound.com/en-us/card-gallery/ embeds the full
card database (every set) as JSON inside the page's __NEXT_DATA__ script tag,
with card images hosted on Riot's public CDN. Their robots.txt is
`User-agent: * / Allow: /`, i.e. crawling is explicitly permitted, and this
is Riot's own published data — the safest possible free source (unlike
marketplace/pricing sites, whose terms of service generally forbid scraping).

Politeness rules applied here:
  * one single page request for all metadata (no crawling),
  * a descriptive User-Agent identifying this tool,
  * a delay between image downloads (default 250 ms),
  * images fetched once and cached locally — re-runs skip existing cards.

Run:  python -m app.ingest.fetch_official [--set UNL] [--limit N] [--keep-seed]
"""

import argparse
import json
import re
import sys
import time
from typing import Iterator

import httpx
from sqlalchemy.orm import Session

from ..models import Card
from .pipeline import (
    CARD_ID_RE,
    IngestError,
    USER_AGENT,
    download_image,
    store_card_image,
)

GALLERY_URL = "https://playriftbound.com/en-us/card-gallery/"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def fetch_gallery_data(client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or httpx.Client(
        timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    try:
        resp = client.get(GALLERY_URL)
        resp.raise_for_status()
    finally:
        if own:
            client.close()
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        raise IngestError("gallery page had no __NEXT_DATA__ payload (layout changed?)")
    return json.loads(m.group(1))


def iter_card_dicts(node) -> Iterator[dict]:
    """Recursively find card objects anywhere in the page data. A card is any
    dict carrying publicCode + name + cardImage — keyed on content, not on
    JSON paths, so gallery layout reshuffles don't break us."""
    if isinstance(node, dict):
        if {"publicCode", "name", "cardImage"} <= node.keys():
            yield node
        else:
            for v in node.values():
                yield from iter_card_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_card_dicts(v)


def _first_id(field: dict | None, key: str) -> str:
    """Pull `label` ids out of the gallery's {label, value/values/type} wrappers."""
    if not isinstance(field, dict):
        return ""
    inner = field.get("value") or field.get("values") or field.get(key) or field.get("type")
    if isinstance(inner, dict):
        return str(inner.get("id", ""))
    if isinstance(inner, list) and inner:
        return "/".join(str(x.get("id", "")) for x in inner if isinstance(x, dict))
    return ""


# Alt-art / overnumbered prints carry a variant marker in their public code:
# a letter suffix ("OGN-066a/298"), a star ("OGN-304*/298"), a collector number
# past the set's base-set size ("VEN-167/166" — an "overnumber"), or a separate
# special-alt subset ("VEN-SP3/006"). Riot's gallery used to expose these with
# rarity id "showcase", but from Vendetta on it reports the underlying rarity
# instead, so we derive the Showcase category from the public code and only fall
# back to the rarity field. Validated to reproduce OGN/UNL/SFD/OGS exactly.
SPECIAL_ALT_RE = re.compile(r"SP\d+", re.I)
VARIANT_NUM_RE = re.compile(r"(\d+)([A-Za-z]|\*)?")


def is_showcase(public_code: str, rarity_id: str) -> bool:
    """True if this public code denotes a Showcase (alt-art / overnumbered) print."""
    if rarity_id.lower() == "showcase":
        return True
    code, _, denominator = public_code.partition("/")
    if not denominator:
        return False  # tokens and runes ("UNL-T01") have no set-size denominator
    number = code.split("-", 1)[1] if "-" in code else code
    if SPECIAL_ALT_RE.fullmatch(number):
        return True
    m = VARIANT_NUM_RE.fullmatch(number)
    if m is None:
        return False
    if m.group(2):
        return True  # "066a" / "304*"
    return denominator.isdigit() and int(m.group(1)) > int(denominator)


def map_card(raw: dict) -> dict | None:
    """Normalize one gallery card object to our Card fields (image not yet
    downloaded). Returns None if required fields are missing."""
    public_code = str(raw.get("publicCode", ""))  # e.g. "UNL-047/219"
    name = str(raw.get("name", ""))
    image = raw.get("cardImage") or {}
    image_url = image.get("url", "")
    if not public_code or not name or not image_url:
        return None
    public_code_clean = re.sub(r"/\d+$", "", public_code)  # "UNL-183/219" → "UNL-183"
    card_id = re.sub(r"[^A-Za-z0-9_-]", "-", public_code_clean)[:64]
    if not CARD_ID_RE.match(card_id):
        return None
    set_code = str((raw.get("set") or {}).get("value", {}).get("id", "")) or public_code.split("-")[0]
    rarity_id = _first_id(raw.get("rarity"), "value")
    rarity = "Showcase" if is_showcase(public_code, rarity_id) else (
        rarity_id.capitalize() or "Unknown"
    )
    return {
        "id": card_id,
        "name": name,
        "set_code": set_code,
        "number": str(raw.get("collectorNumber", "")),
        "rarity": rarity,
        "domain": "/".join(
            p.capitalize() for p in _first_id(raw.get("domain"), "values").split("/") if p
        )
        or "Colorless",
        "card_type": (_first_id(raw.get("cardType"), "type").split("/") or ["unit"])[0].lower()
        or "unit",
        "image_url": image_url,
        "source_url": image_url,
    }


def remove_seed_cards(db: Session) -> int:
    seeds = db.query(Card).filter(Card.source_url == "generated://seed").all()
    for card in seeds:
        db.delete(card)  # inventory rows cascade
    db.commit()
    return len(seeds)


def ingest(
    db: Session,
    set_filter: str | None = None,
    limit: int | None = None,
    delay_s: float = 0.25,
    keep_seed: bool = False,
    log=print,
) -> int:
    data = fetch_gallery_data()
    metas: dict[str, dict] = {}
    for raw in iter_card_dicts(data):
        meta = map_card(raw)
        if meta is None:
            continue
        if set_filter and meta["set_code"].upper() != set_filter.upper():
            continue
        metas.setdefault(meta["id"], meta)  # dedupe repeated embeds

    if not keep_seed and metas:
        removed = remove_seed_cards(db)
        if removed:
            log(f"removed {removed} demo seed cards")

    todo = [m for m in metas.values() if db.get(Card, m["id"]) is None]
    if limit is not None:
        todo = todo[:limit]
    log(f"gallery has {len(metas)} cards; {len(todo)} new to ingest")

    created = 0
    with httpx.Client(
        timeout=30, follow_redirects=False, headers={"User-Agent": USER_AGENT}
    ) as img_client:
        for i, meta in enumerate(todo):
            try:
                img = download_image(meta["image_url"], client=img_client)
            except IngestError as exc:
                log(f"  skip {meta['id']}: {exc}")
                continue
            image_file, phash = store_card_image(meta["id"], img)
            db.add(
                Card(
                    id=meta["id"],
                    name=meta["name"],
                    set_code=meta["set_code"],
                    number=meta["number"],
                    rarity=meta["rarity"],
                    domain=meta["domain"],
                    card_type=meta["card_type"],
                    image_file=image_file,
                    phash=phash,
                    source_url=meta["source_url"],
                )
            )
            created += 1
            if created % 25 == 0:
                db.commit()
                log(f"  {created}/{len(todo)} ingested…")
            if i < len(todo) - 1:
                time.sleep(delay_s)  # politeness delay between image fetches
    db.commit()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_filter", help="only this set code, e.g. UNL")
    parser.add_argument("--limit", type=int, help="max new cards to ingest")
    parser.add_argument("--delay", type=float, default=0.25, help="seconds between image downloads")
    parser.add_argument("--keep-seed", action="store_true", help="keep the demo seed cards")
    args = parser.parse_args()

    from ..config import data_dir
    from ..db import Base, make_engine, make_session_factory

    engine = make_engine(data_dir() / "riftbound.db")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        try:
            n = ingest(
                session,
                set_filter=args.set_filter,
                limit=args.limit,
                delay_s=args.delay,
                keep_seed=args.keep_seed,
            )
        except (IngestError, httpx.HTTPError) as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 1
    print(f"ingested {n} cards — restart the backend to load the new cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
