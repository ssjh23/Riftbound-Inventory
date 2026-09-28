"""Trade request text format.

A trade request travels between two collectors as plain text: the requester
exports it from the community view, the owner pastes it back into their own
collection. Both the writer and the reader live here so the format can never
drift between the two sides.

    # RIFTBOUND TRADE REQUEST v1
    # From: alice
    # To: bob
    # Date: 2026-07-31

    2x UNL-003 Mosstomper Seedling
    1x UNL-011 Baron Pit [foil]

    # 3 copies requested

Reading is deliberately lenient — a bare list of `2x UNL-003` lines parses
fine, so a request stays usable after someone edits it by hand. The card id is
authoritative; the name that follows it is only there for humans.
"""

import re
from dataclasses import dataclass, field

FORMAT_VERSION = 1
HEADER = f"# RIFTBOUND TRADE REQUEST v{FORMAT_VERSION}"

# "2x UNL-003 Mosstomper Seedling" — the "x" and the trailing name are both
# optional, so "2 UNL-003" is equally valid.
_CARD_RE = re.compile(r"^(\d+)\s*[xX]?\s+([A-Za-z0-9_-]+)\s*(.*)$")
_FOIL_RE = re.compile(r"\[\s*foil\s*\]", re.IGNORECASE)
_META_RE = re.compile(r"^#\s*(from|to)\s*:\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class TradeLine:
    card_id: str
    card_name: str
    foil: bool
    quantity: int


@dataclass
class ParsedRequest:
    lines: list[TradeLine] = field(default_factory=list)
    from_username: str | None = None
    to_username: str | None = None
    warnings: list[str] = field(default_factory=list)


def format_request(
    from_username: str,
    to_username: str,
    date_str: str,
    lines: list[TradeLine],
) -> str:
    """Render a request as the text the requester copies out."""
    body = [
        HEADER,
        f"# From: {from_username}",
        f"# To: {to_username}",
        f"# Date: {date_str}",
        "",
    ]
    for ln in sorted(lines, key=lambda l: (l.card_id, l.foil)):
        name = f" {ln.card_name}" if ln.card_name else ""
        foil = " [foil]" if ln.foil else ""
        body.append(f"{ln.quantity}x {ln.card_id}{name}{foil}")
    total = sum(ln.quantity for ln in lines)
    body += ["", f"# {total} cop{'y' if total == 1 else 'ies'} requested"]
    return "\n".join(body) + "\n"


def parse_request(text: str) -> ParsedRequest:
    """Read a request back. Never raises on malformed input — unreadable lines
    become warnings so the owner can see exactly what was skipped."""
    parsed = ParsedRequest()
    # (card_id, foil) -> index into parsed.lines, so a card listed twice is
    # summed into a single row rather than shown as two.
    seen: dict[tuple[str, bool], int] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            meta = _META_RE.match(line)
            if meta:
                who = meta.group(1).lower()
                if who == "from":
                    parsed.from_username = meta.group(2)
                else:
                    parsed.to_username = meta.group(2)
            continue

        m = _CARD_RE.match(line)
        if not m:
            parsed.warnings.append(f"Skipped unreadable line: {line}")
            continue

        quantity = int(m.group(1))
        if quantity <= 0:
            parsed.warnings.append(f"Skipped zero quantity: {line}")
            continue

        card_id = m.group(2)
        rest = m.group(3) or ""
        foil = bool(_FOIL_RE.search(rest))
        name = _FOIL_RE.sub("", rest).strip()

        key = (card_id, foil)
        if key in seen:
            parsed.lines[seen[key]].quantity += quantity
        else:
            seen[key] = len(parsed.lines)
            parsed.lines.append(
                TradeLine(card_id=card_id, card_name=name, foil=foil, quantity=quantity)
            )

    if not parsed.lines:
        parsed.warnings.append("No card lines found — is this a trade request?")
    return parsed
