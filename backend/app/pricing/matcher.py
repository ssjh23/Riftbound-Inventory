"""Match our Card rows to the external price source's catalog.

The external API has its own ids with no relation to ours, so cards are
matched by name via their search endpoint and the match is cached on
`Card.price_source_id` so we never re-search for a card twice. This is
inherently best-effort (see client.py's schema caveat) — ambiguous or
no-result matches are simply skipped (logged), not treated as errors, so one
bad match never blocks refreshing the rest of the catalog.
"""

import logging

from sqlalchemy.orm import Session

from ..models import Card
from .client import ExternalCard, PriceClient

logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def pick_best_match(card: Card, candidates: list[ExternalCard]) -> ExternalCard | None:
    """Prefer an exact normalized-name match; if several tie, prefer one
    whose expansion string mentions our set code (best-effort substring
    check — we don't have a verified set-code-to-expansion-name mapping)."""
    target = _normalize(card.name)
    exact = [c for c in candidates if _normalize(c.name) == target]
    if not exact:
        return None
    if len(exact) == 1:
        return exact[0]
    for c in exact:
        if c.expansion and card.set_code.lower() in c.expansion.lower():
            return c
    return exact[0]  # ambiguous — best guess, logged by the caller


def resolve_source_id(db: Session, client: PriceClient, card: Card) -> str | None:
    """Return the card's external id, searching and caching it if needed.
    Returns None (and leaves price_source_id unset) if no confident match is
    found — the card is simply skipped this round, not treated as fatal."""
    if card.price_source_id:
        return card.price_source_id

    candidates = client.search_cards(card.name)
    match = pick_best_match(card, candidates)
    if match is None:
        logger.info("no price-source match for %s (%s)", card.id, card.name)
        return None

    card.price_source_id = match.source_id
    db.add(card)
    return match.source_id
