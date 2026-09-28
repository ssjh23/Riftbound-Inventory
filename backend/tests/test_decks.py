"""Unit tests for deck parsing helpers in routes/decks.py."""

import pytest
from app.routes.decks._common import _parse_deckobj, _parse_decklist_text

# ---------------------------------------------------------------------------
# Real-world deckObj as returned by TopDeck.gg (confirmed from live API call)
# ---------------------------------------------------------------------------
REAL_DECKOBJ = {
    "Legend": {
        "Rengar, Pridestalker": {"id": "UNL-183", "count": 1},
    },
    "Champion": {
        "Rengar, Trophy Hunter": {"id": "UNL-120", "count": 1},
    },
    "Runes": {
        "Body Rune": {"id": "OGN-126", "count": 8},
        "Fury Rune": {"id": "OGN-007", "count": 4},
    },
    "Battlefields": {
        "Emperor's Dais": {"id": "SFD-207", "count": 1},
        "Seat of Power": {"id": "SFD-217", "count": 1},
        "The Arena's Greatest": {"id": "OGN-290", "count": 1},
    },
    "Mainboard": {
        "Challenge": {"id": "OGN-128", "count": 2},
        "Determined Sentry": {"id": "UNL-111", "count": 3},
        "Grim Apothecary": {"id": "UNL-021", "count": 3},
    },
    "Sideboard": {
        "Akshan, Mischievous": {"id": "SFD-109", "count": 2},
        "Challenge": {"id": "OGN-128", "count": 1},
    },
    "metadata": {
        "game": "Riftbound",
        "format": "Constructed",
    },
}


class TestParseDeckobj:
    def test_extracts_card_id_from_nested_dict(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        legend = next(c for c in cards if c["section"] == "Legend")
        assert legend["card_id"] == "UNL-183"
        assert legend["quantity"] == 1
        assert legend["card_name"] == "Rengar, Pridestalker"

    def test_extracts_quantity_from_count_field(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        rune = next(c for c in cards if c["card_name"] == "Body Rune")
        assert rune["quantity"] == 8

    def test_skips_metadata_section(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        sections = {c["section"] for c in cards}
        assert "metadata" not in sections

    def test_all_non_metadata_sections_present(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        sections = {c["section"] for c in cards}
        assert sections == {"Legend", "Champion", "Runes", "Battlefields", "Mainboard", "Sideboard"}

    def test_total_card_count(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        # Legend(1) + Champion(1) + Runes(2) + Battlefields(3) + Mainboard(3) + Sideboard(2) = 12
        assert len(cards) == 12

    def test_all_have_card_id(self):
        cards = _parse_deckobj(REAL_DECKOBJ)
        assert all(c["card_id"] is not None for c in cards)

    def test_empty_deckobj(self):
        assert _parse_deckobj({}) == []

    def test_skips_non_dict_section_values(self):
        obj = {
            "Mainboard": {"Fireball": {"id": "OGN-001", "count": 3}},
            "metadata": {"game": "Riftbound"},
            "bad_section": "not a dict",
        }
        cards = _parse_deckobj(obj)
        assert len(cards) == 1
        assert cards[0]["card_name"] == "Fireball"

    def test_missing_id_becomes_none(self):
        obj = {"Mainboard": {"No ID Card": {"count": 2}}}
        cards = _parse_deckobj(obj)
        assert cards[0]["card_id"] is None
        assert cards[0]["quantity"] == 2


class TestParseDecklistText:
    REAL_TEXT = (
        "~~Legend~~\n1 Rengar, Pridestalker\n\n"
        "~~Champion~~\n1 Rengar, Trophy Hunter\n\n"
        "~~Runes~~\n8 Body Rune\n4 Fury Rune\n\n"
        "~~Battlefields~~\n1 Emperor's Dais\n\n"
        "~~Mainboard~~\n2 Challenge\n3 Determined Sentry\n\n"
        "~~Sideboard~~\n2 Akshan, Mischievous\n"
    )

    def test_parses_legend_section(self):
        cards = _parse_decklist_text(self.REAL_TEXT)
        legend = next(c for c in cards if c["section"] == "Legend")
        assert legend["card_name"] == "Rengar, Pridestalker"
        assert legend["quantity"] == 1

    def test_parses_rune_quantities(self):
        cards = _parse_decklist_text(self.REAL_TEXT)
        body = next(c for c in cards if c["card_name"] == "Body Rune")
        assert body["quantity"] == 8

    def test_parses_tilde_section_headers(self):
        cards = _parse_decklist_text(self.REAL_TEXT)
        sections = {c["section"] for c in cards}
        assert "Runes" in sections
        assert "Mainboard" in sections
        assert "Sideboard" in sections

    def test_card_name_with_comma(self):
        cards = _parse_decklist_text(self.REAL_TEXT)
        rengar = next(c for c in cards if "Rengar, Trophy" in c["card_name"])
        assert rengar["card_name"] == "Rengar, Trophy Hunter"

    def test_ignores_blank_lines(self):
        cards = _parse_decklist_text(self.REAL_TEXT)
        # No empty card_name entries
        assert all(c["card_name"] for c in cards)

    def test_x_suffix_format(self):
        text = "~~Mainboard~~\nChallenge x2\n"
        cards = _parse_decklist_text(text)
        assert cards[0]["quantity"] == 2
        assert cards[0]["card_name"] == "Challenge"

    def test_default_section_is_mainboard(self):
        text = "3 Some Card\n"
        cards = _parse_decklist_text(text)
        assert cards[0]["section"] == "Mainboard"

    def test_empty_string(self):
        assert _parse_decklist_text("") == []

    def test_hash_section_header(self):
        text = "# Runes\n4 Body Rune\n"
        cards = _parse_decklist_text(text)
        assert cards[0]["section"] == "Runes"
