"""RiftRank.com deck provider — no API key required."""
import concurrent.futures

import httpx
from sqlalchemy.orm import Session

_BASE = "https://riftrank.com/api"
_TAKE = 50  # most recent tournament decks to fetch details for
_MAX_WORKERS = 10

_ZONE_TO_SECTION = {
    "main": "Mainboard",
    "rune": "Runes",
    "sideboard": "Sideboard",
    "battlefield": "Battlefields",
}


def _fetch_detail(deck_id: str) -> dict | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{_BASE}/decks/{deck_id}")
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception:
        return None


def _normalize(raw: dict) -> dict | None:
    deck = raw.get("deck", raw)
    if not deck or not isinstance(deck, dict):
        return None

    deck_id = deck.get("id", "")
    name = deck.get("name", "")
    legend_card = deck.get("legendCard") or {}
    legend_name = legend_card.get("name", "")
    # Image comes straight from the official Riot CDN — no local DB lookup needed.
    legend_img = legend_card.get("imageUrl")

    parts = name.split(" · ", 1)
    player = parts[0].strip() if len(parts) == 2 else "Unknown"
    tournament = parts[1].strip() if len(parts) == 2 else name

    created_at = deck.get("createdAt", "")
    date_str = created_at[:10] if created_at else ""

    cards: list[dict] = []

    legend_id = deck.get("legendId")
    if legend_id and legend_name:
        cards.append({
            "card_id": legend_id,
            "card_name": legend_name,
            "quantity": 1,
            "section": "Legend",
        })

    for c in deck.get("cards", []):
        zone = c.get("zone", "main")
        section = _ZONE_TO_SECTION.get(zone, "Mainboard")
        card_obj = c.get("card") or {}
        cards.append({
            "card_id": c.get("cardId") or card_obj.get("id"),
            "card_name": card_obj.get("name", c.get("cardId", "")),
            "quantity": c.get("quantity", 1),
            "section": section,
        })

    sets = sorted({
        c["card_id"].split("-")[0]
        for c in cards
        if c.get("card_id")
    })

    return {
        "id": f"rr-{deck_id}",
        "name": name,
        "legend": legend_name,
        "legend_image_url": legend_img,
        "player": player,
        "placement": 0,
        "wins": 0,
        "losses": 0,
        "tournament": tournament,
        "source": "RiftRank",
        "source_url": f"https://riftrank.com/decks/{deck_id}",
        "date": date_str,
        "sets": sets,
        "cards": cards,
    }


def fetch(db: Session) -> list[dict]:  # noqa: ARG001 — db unused, kept for uniform provider signature
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{_BASE}/decks", params={"tags": "official-tournament"})
            if resp.status_code != 200:
                return []
            summaries = resp.json().get("decks", [])
    except Exception:
        return []

    if not summaries:
        return []

    summaries.sort(
        key=lambda d: d.get("updatedAt") or d.get("createdAt") or "",
        reverse=True,
    )
    top_ids = [d["id"] for d in summaries[:_TAKE]]

    details: list[dict | None] = [None] * len(top_ids)
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_to_idx = {pool.submit(_fetch_detail, did): i for i, did in enumerate(top_ids)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                details[idx] = future.result()
            except Exception:
                pass

    result = []
    for raw in details:
        if raw:
            normalized = _normalize(raw)
            if normalized:
                result.append(normalized)
    return result
