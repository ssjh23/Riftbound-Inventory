"""Shared helpers used by multiple deck providers."""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Card, InventoryItem

# Suffixes that may appear in local DB names but not in decklist text.
_VARIANT_SUFFIX_RE = re.compile(r"\s*-\s*starter$", re.IGNORECASE)

# ── riftbound.gg format helpers ───────────────────────────────────────────────
# Matches: "3 Card Name (Optional Promo Desc) (SET-ID)"
# The card ID is always the LAST parenthesised group and follows SET-NUMBER[letters]
# or SET-NUMBER-SUFFIX patterns.  Non-greedy (.+?) with $ anchor lets the regex
# engine backtrack until the rightmost valid card-ID group is found.
_RIFTBOUND_GG_LINE_RE = re.compile(
    r"^(\d+)\s+(.+?)\s+\(([A-Za-z]{2,6}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\)\s*$"
)
# Matches trailing alpha suffix on SET-NUMBER card IDs: OGN-007a, VEN-021A → OGN-007 / VEN-021
_TRAILING_ALPHA_RE = re.compile(r"^([A-Za-z]{2,6}-\d+)[A-Za-z]+$")

_PILTOVER_SECTION_MAP: dict[str, str] = {
    "champion": "Mainboard",  # playable champion unit, not the legend identity
    "commanders": "Legend",
    "legend": "Legend",
    "legends": "Legend",
    "maindeck": "Mainboard",
    "main deck": "Mainboard",
    "main": "Mainboard",
    "battlefields": "Battlefields",
    "battlefield": "Battlefields",
    "runes": "Runes",
    "rune pool": "Runes",
    "sideboard": "Sideboard",
    "side": "Sideboard",
}


def _parse_piltover_text(text: str) -> list[dict]:
    """Parse Piltover Archive / generic 'N Card Name\\nSection:' export format.

    Leading card lines (before any section header) are treated as Legend.
    Section headers are word(s) followed by a lone colon on the line, e.g.
    'MainDeck:' or 'Champion:'.
    """
    cards: list[dict] = []
    section = "Legend"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Section header: letters/spaces/apostrophes ending with ':' (nothing after)
        m = re.match(r"^([A-Za-z][A-Za-z '\t]*):\s*$", line)
        if m:
            key = m.group(1).strip().lower()
            section = _PILTOVER_SECTION_MAP.get(key, m.group(1).strip())
            continue
        # Card line: optional quantity then card name
        m = re.match(r"^(\d+)x?\s+(.+)$", line)
        if m:
            cards.append({
                "quantity": int(m.group(1)),
                "card_name": m.group(2).strip(),
                "section": section,
            })
    return cards


def _parse_decklist_text(text: str) -> list[dict]:
    cards = []
    section = "Mainboard"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[~=]{2,}(.+?)[~=]{2,}$", line)
        if m:
            section = m.group(1).strip()
            continue
        if re.match(r"^#+\s", line):
            section = re.sub(r"^#+\s*", "", line).strip()
            continue
        m = re.match(r"^(\d+)x?\s+(.+?)(?:\s+\(\w+\))?$", line)
        if m:
            cards.append({"quantity": int(m.group(1)), "card_name": m.group(2).strip(), "section": section})
            continue
        m = re.match(r"^(.+?)\s+x(\d+)$", line)
        if m:
            cards.append({"quantity": int(m.group(2)), "card_name": m.group(1).strip(), "section": section})
    return cards


def _parse_deckobj(obj: dict) -> list[dict]:
    # Real TopDeck.gg structure: {section: {card_name: {"id": "SET-NNN", "count": N}}}
    # A "metadata" key with {"game": ..., "format": ...} must be skipped.
    cards = []
    for section, entries in obj.items():
        if section == "metadata":
            continue
        if not isinstance(entries, dict):
            continue
        for name, card_data in entries.items():
            if not isinstance(card_data, dict):
                continue
            cards.append({
                "quantity": int(card_data.get("count", 1)),
                "card_name": name,
                "card_id": card_data.get("id"),
                "section": section,
            })
    return cards


def _resolve_names(db: Session, raw_cards: list[dict]) -> list[dict]:
    if not raw_cards:
        return []
    names_lower = [e["card_name"].lower() for e in raw_cards]

    # When multiple DB cards share a name (alt arts, promos), prefer the
    # printing the user actually owns. ORDER BY owned count DESC then take
    # the first hit per name via setdefault.
    owned_expr = (
        func.coalesce(InventoryItem.count, 0)
        + func.coalesce(InventoryItem.foil_count, 0)
    )

    def _first_per_name(stmt) -> dict[str, str]:
        name_to_id: dict[str, str] = {}
        for r in db.execute(stmt).fetchall():
            name_to_id.setdefault(r.name.lower(), r.id)
        return name_to_id

    # Pass 1 — exact match OR "- Starter" suffix stripped.
    stripped_col = func.replace(func.lower(Card.name), " - starter", "")
    stmt1 = (
        select(Card.id, Card.name)
        .outerjoin(InventoryItem, Card.id == InventoryItem.card_id)
        .where(func.lower(Card.name).in_(names_lower) | stripped_col.in_(names_lower))
        .order_by(owned_expr.desc())
    )
    name_to_id = _first_per_name(stmt1)

    # Also register stripped "- Starter" keys so "Wuju Bladesman" finds the above.
    for name, cid in list(name_to_id.items()):
        stripped = _VARIANT_SUFFIX_RE.sub("", name)
        if stripped != name:
            name_to_id.setdefault(stripped, cid)

    # Pass 2 — subtitle-only for "ChampionName, LegendTitle" that didn't resolve.
    # Legend cards are stored without their champion prefix in the DB.
    unresolved = {
        name: name.split(", ", 1)[1]
        for name in names_lower
        if name not in name_to_id and ", " in name
    }
    if unresolved:
        subtitles = list(unresolved.values())
        stmt2 = (
            select(Card.id, Card.name)
            .outerjoin(InventoryItem, Card.id == InventoryItem.card_id)
            .where(func.lower(Card.name).in_(subtitles))
            .order_by(owned_expr.desc())
        )
        subtitle_to_id = _first_per_name(stmt2)
        for full_name, subtitle in unresolved.items():
            if subtitle in subtitle_to_id:
                name_to_id[full_name] = subtitle_to_id[subtitle]

    return [
        {
            "card_id": name_to_id.get(e["card_name"].lower()),
            "card_name": e["card_name"],
            "quantity": e["quantity"],
            "section": e["section"],
        }
        for e in raw_cards
    ]


def legend_image_url(db: Session, resolved: list[dict]) -> str | None:
    """Look up legend card image from the local DB by card_id."""
    legend_entry = next(
        (c for c in resolved if c.get("section", "").lower() in ("legend", "commanders", "legends")),
        None,
    )
    card_id = legend_entry.get("card_id") if legend_entry else None
    if not card_id:
        return None
    image_file = db.execute(select(Card.image_file).where(Card.id == card_id)).scalar_one_or_none()
    return f"/images/{image_file}" if image_file else None


# ── riftbound.gg decklist parser ──────────────────────────────────────────────

def _card_type_to_section(card_type: str) -> str:
    t = card_type.lower()
    if t == "legend":
        return "Legend"
    if t == "rune":
        return "Runes"
    if t == "battlefield":
        return "Battlefields"
    return "Mainboard"


def _riftbound_gg_id_candidates(raw_id: str) -> list[str]:
    """Return candidate DB card IDs to try for a riftbound.gg raw ID, in priority order.

    Handles three patterns:
      • OGN-007a / VEN-021A  → strip trailing alpha:  OGN-007 / VEN-021
      • SFD-059-P / OGN-058-P → strip -LETTER suffix: SFD-059 / OGN-058
      • VEN-189               → no stripping needed
    Case-insensitive matches are tried for each candidate.
    """
    seen: set[str] = set()
    results: list[str] = []

    def _add(s: str) -> None:
        for v in (s, s.upper()):
            if v not in seen:
                seen.add(v)
                results.append(v)

    _add(raw_id)

    # Strip trailing alpha variant: OGN-007a → OGN-007
    m = _TRAILING_ALPHA_RE.match(raw_id)
    if m:
        _add(m.group(1))

    # Strip -LETTER(S) promo suffix on 3-part IDs: SFD-059-P → SFD-059
    parts = raw_id.split("-")
    if len(parts) == 3 and parts[2].isalpha() and len(parts[2]) <= 3:
        _add(f"{parts[0]}-{parts[1]}")

    return results


def _parse_riftbound_gg(text: str) -> list[dict]:
    """Parse a riftbound.gg flat decklist.

    Each line: {qty} {card name} [{promo desc}] ({SET-ID})
    The card ID is always the LAST parenthesised token on the line.
    Promo descriptors like "(Judge Promo)" are stripped from the name.
    Returns a list of dicts with keys: quantity, card_name, raw_card_id.
    """
    cards: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _RIFTBOUND_GG_LINE_RE.match(line)
        if not m:
            continue
        qty = int(m.group(1))
        raw_name = m.group(2).strip()
        # Remove any trailing "(Promo Desc)" group left in the name portion
        clean_name = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name).strip() or raw_name
        raw_card_id = m.group(3)
        cards.append({"quantity": qty, "card_name": clean_name, "raw_card_id": raw_card_id})
    return cards


def _resolve_riftbound_gg(db: Session, raw_cards: list[dict]) -> list[dict]:
    """Resolve riftbound.gg parsed items to DB cards using the embedded card IDs.

    Resolution order per card:
      1. Candidate IDs derived from the embedded raw_card_id (exact → stripped variants)
      2. Name-based fallback via _resolve_names for any still-unmatched cards.
    Section is assigned from the card's type in the DB (legend/rune/battlefield → named
    sections; everything else → Mainboard).
    """
    if not raw_cards:
        return []

    all_upper: set[str] = set()
    for c in raw_cards:
        for cand in _riftbound_gg_id_candidates(c["raw_card_id"]):
            all_upper.add(cand.upper())

    rows = db.execute(
        select(Card.id, Card.card_type).where(func.upper(Card.id).in_(all_upper))
    ).fetchall()

    upper_map: dict[str, tuple[str, str]] = {
        row.id.upper(): (row.id, row.card_type) for row in rows
    }

    resolved: list[dict] = []
    name_fallback: list[dict] = []

    for c in raw_cards:
        matched_id: str | None = None
        matched_type: str = ""
        for cand in _riftbound_gg_id_candidates(c["raw_card_id"]):
            hit = upper_map.get(cand.upper())
            if hit:
                matched_id, matched_type = hit
                break

        if matched_id:
            resolved.append({
                "card_id": matched_id,
                "card_name": c["card_name"],
                "quantity": c["quantity"],
                "section": _card_type_to_section(matched_type),
            })
        else:
            name_fallback.append({
                "card_name": c["card_name"],
                "quantity": c["quantity"],
                "section": "Mainboard",
            })

    if name_fallback:
        resolved.extend(_resolve_names(db, name_fallback))

    return resolved
