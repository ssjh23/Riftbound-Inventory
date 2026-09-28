"""Scheduled price top-up — spends today's remaining pricing-API budget
refreshing the stalest cards (owned cards first). Run manually or on a
schedule (cron / Windows Task Scheduler / the host's own scheduler):

    python -m app.pricing.refresh_job [--limit N]

Does nothing (prints a message, exits 0) if RIFTBOUND_PRICE_API_KEY isn't
set — safe to schedule unconditionally even before pricing is configured.
"""

import argparse
import sys

from .client import PriceApiNotConfigured, PriceClient
from .service import refresh_stale_batch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=90, help="max cards to refresh this run"
    )
    args = parser.parse_args()

    from ..config import data_dir
    from ..db import Base, make_engine, make_session_factory

    engine = make_engine(data_dir() / "riftbound.db")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        try:
            with PriceClient() as client:
                result = refresh_stale_batch(session, client, args.limit)
        except PriceApiNotConfigured:
            print("RIFTBOUND_PRICE_API_KEY is not set — nothing to do.")
            return 0
    print(
        f"refreshed {result['refreshed']} cards "
        f"({result['matched']} priced, {result['skipped']} unmatched)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
