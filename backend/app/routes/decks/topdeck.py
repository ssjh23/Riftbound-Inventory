"""TopDeck.gg deck provider."""
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ._common import _parse_deckobj, _parse_decklist_text, _resolve_names, legend_image_url

_URL = "https://topdeck.gg/api/v2/tournaments"


def _fetch_raw(api_key: str) -> list[dict]:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            _URL,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={
                "game": "Riftbound",
                "format": "Constructed",
                "last": 90,
                "columns": ["name", "decklist", "wins", "losses"],
            },
        )
        resp.raise_for_status()
        return resp.json()


def fetch(db: Session, api_key: str) -> list[dict]:
    tournaments = _fetch_raw(api_key)
    decks: list[dict] = []

    for t in tournaments:
        tid = t.get("TID", "")
        tournament_name = t.get("tournamentName", "Unknown Tournament")
        start_ts = t.get("startDate")
        date_str = (
            datetime.fromtimestamp(start_ts, tz=timezone.utc).date().isoformat()
            if start_ts
            else ""
        )

        for standing in t.get("standings", []):
            if not standing.get("decklist") and not standing.get("deckObj"):
                continue

            player_name = standing.get("name", "Unknown")
            player_id = standing.get("id", "")
            leader = standing.get("leader", "")
            placement = standing.get("standing", 0)
            wins = standing.get("wins", 0)
            losses = standing.get("losses", 0)

            if standing.get("deckObj"):
                resolved = _parse_deckobj(standing["deckObj"])
                if not leader:
                    legend_section = standing["deckObj"].get("Legend", {})
                    leader = next(iter(legend_section.keys()), "") if legend_section else ""
            else:
                raw = _parse_decklist_text(standing.get("decklist", ""))
                resolved = _resolve_names(db, raw)

            sets = sorted({
                c["card_id"].split("-")[0]
                for c in resolved
                if c["card_id"]
            })

            decks.append({
                "id": f"td-{tid}-{player_id}",
                "name": f"{player_name}'s {leader} deck" if leader else f"{player_name}'s deck",
                "legend": leader,
                "legend_image_url": legend_image_url(db, resolved),
                "player": player_name,
                "placement": placement,
                "wins": wins,
                "losses": losses,
                "tournament": tournament_name,
                "source": "TopDeck.gg",
                "source_url": "https://topdeck.gg/riftbound",
                "date": date_str,
                "sets": sets,
                "cards": resolved,
            })

    return decks
