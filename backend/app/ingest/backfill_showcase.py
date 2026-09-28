"""Re-derive the Showcase rarity for cards already in the database.

Riot's card gallery used to publish alt-art and overnumbered prints with rarity
id "showcase"; from Vendetta (VEN) on it reports the print's underlying rarity
instead, so those cards landed in the DB as plain Rare/Epic and the Showcase
category came out empty for the set. `fetch_official.is_showcase()` now derives
the category from the public code, but the ingest is insert-only, so rows that
already exist need this one-off backfill.

Run:  python -m app.ingest.backfill_showcase [--set VEN] [--dry-run]
"""

import argparse
import sys

from sqlalchemy.orm import Session

from ..models import Card
from .fetch_official import fetch_gallery_data, iter_card_dicts, map_card


def backfill(
    db: Session, set_filter: str | None = None, dry_run: bool = False, log=print
) -> int:
    """Set rarity="Showcase" on every stored card the gallery now derives as one."""
    wanted = {
        meta["id"]
        for raw in iter_card_dicts(fetch_gallery_data())
        if (meta := map_card(raw)) is not None and meta["rarity"] == "Showcase"
    }
    query = db.query(Card).filter(Card.id.in_(wanted), Card.rarity != "Showcase")
    if set_filter:
        query = query.filter(Card.set_code == set_filter.upper())
    stale = query.all()
    for card in stale:
        log(f"  {card.id}  {card.name}: {card.rarity} -> Showcase")
        if not dry_run:
            card.rarity = "Showcase"
    if not dry_run:
        db.commit()
    return len(stale)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_filter", help="only this set code, e.g. VEN")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    from ..config import data_dir
    from ..db import Base, make_engine, make_session_factory

    engine = make_engine(data_dir() / "riftbound.db")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        n = backfill(session, set_filter=args.set_filter, dry_run=args.dry_run)
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {n} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
