"""One-time migration: rename SET-NNN-TTT card IDs to SET-NNN.

fetch_official.py stored IDs like UNL-183-219 (publicCode="UNL-183/219" with
the slash replaced by a dash). TopDeck.gg and RiftRank use the short form
UNL-183, so ownership matching in the Deck Builder was broken for all users
who had ingested real card data.

This script renames every affected card ID in-place across all DB tables that
reference it, preserving all inventory counts, prices, and price history.

SQLite FK enforcement is off in this engine (db.py does not emit
PRAGMA foreign_keys=ON), so the PK update and FK column updates can run in
any order within the same transaction without constraint violations.

Image files on disk (e.g. UNL-183-219.jpg) are NOT renamed — card.image_file
continues to point to the existing file and the /images/ route keeps working.

Run once after updating fetch_official.py:
    cd backend
    .venv\\Scripts\\python -m app.ingest.migrate_card_ids
"""

import sys

from sqlalchemy import text

from ..config import data_dir
from ..db import make_engine, make_session_factory

_FK_TABLES = [
    ("inventory", "card_id"),
    ("card_prices", "card_id"),
    ("card_price_history", "card_id"),
]


def _short(card_id: str) -> str:
    """Strip trailing all-digit set-total segment if present.

    "UNL-183-219" -> "UNL-183"
    "OGN-128-186" -> "OGN-128"
    "UNL-001"     -> "UNL-001"  (seed cards: unchanged)
    """
    parts = card_id.split("-")
    if len(parts) > 2 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return card_id


def migrate() -> int:
    engine = make_engine(data_dir() / "riftbound.db")
    with make_session_factory(engine)() as session:
        conn = session.connection()

        old_ids = [r[0] for r in conn.execute(text("SELECT id FROM cards")).fetchall()]

        renamed = 0
        skipped = 0
        for old_id in old_ids:
            new_id = _short(old_id)
            if new_id == old_id:
                continue  # already in correct format

            if conn.execute(text("SELECT 1 FROM cards WHERE id=:id"), {"id": new_id}).fetchone():
                print(f"  SKIP {old_id} → {new_id}  (target ID already exists)")
                skipped += 1
                continue

            # Update FK columns first (order doesn't matter; FK enforcement is off)
            for table, col in _FK_TABLES:
                conn.execute(
                    text(f"UPDATE {table} SET {col}=:n WHERE {col}=:o"),
                    {"n": new_id, "o": old_id},
                )

            # Rename the PK itself (SQLite allows UPDATE on primary key columns)
            conn.execute(
                text("UPDATE cards SET id=:n WHERE id=:o"),
                {"n": new_id, "o": old_id},
            )

            print(f"  {old_id} → {new_id}")
            renamed += 1

        session.commit()

    if skipped:
        print(f"Skipped {skipped} conflict(s).")
    print(f"Done — renamed {renamed} card ID(s).")
    return renamed


if __name__ == "__main__":
    migrate()
    sys.exit(0)
