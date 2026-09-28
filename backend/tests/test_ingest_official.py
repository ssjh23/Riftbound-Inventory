import pytest

from app.ingest.fetch_official import iter_card_dicts, map_card
from app.ingest.pipeline import IngestError, download_image

# A trimmed-down replica of the gallery's __NEXT_DATA__ card shape.
GALLERY_CARD = {
    "id": "unl-047-219",
    "collectorNumber": 47,
    "name": "Mosstomper",
    "publicCode": "UNL-047/219",
    "set": {"label": "Card Set", "value": {"id": "UNL", "label": "Unleashed"}},
    "cardType": {"label": "Card Type", "type": [{"id": "unit", "label": "Unit"}]},
    "rarity": {"label": "Rarity", "value": {"id": "uncommon", "label": "Uncommon"}},
    "domain": {"label": "Domain", "values": [{"id": "calm", "label": "Calm"}]},
    "cardImage": {
        "type": "image",
        "url": "https://cmsassets.rgpub.io/sanity/images/x/abc-744x1039.png?accountingTag=RB",
    },
}


def test_iter_card_dicts_finds_cards_at_any_depth():
    page = {
        "props": {
            "pageProps": {
                "blades": [
                    {"stuff": 1},
                    {"cards": [GALLERY_CARD, {"not": "a card"}]},
                    {"nested": {"deeper": [{"again": [GALLERY_CARD]}]}},
                ]
            }
        }
    }
    found = list(iter_card_dicts(page))
    assert len(found) == 2
    assert all(c["name"] == "Mosstomper" for c in found)


def test_map_card_normalizes_gallery_fields():
    meta = map_card(GALLERY_CARD)
    assert meta == {
        "id": "UNL-047-219",  # publicCode slash slugged to a filesystem-safe id
        "name": "Mosstomper",
        "set_code": "UNL",
        "number": "47",
        "rarity": "Uncommon",
        "domain": "Calm",
        "card_type": "unit",
        "image_url": GALLERY_CARD["cardImage"]["url"],
        "source_url": GALLERY_CARD["cardImage"]["url"],
    }


def test_map_card_multi_domain_and_missing_fields():
    card = dict(GALLERY_CARD)
    card["domain"] = {"values": [{"id": "fury"}, {"id": "chaos"}]}
    assert map_card(card)["domain"] == "Fury/Chaos"

    incomplete = dict(GALLERY_CARD)
    incomplete.pop("cardImage")
    assert map_card({**incomplete, "cardImage": {}}) is None
    assert map_card({"name": "x"}) is None


def test_download_rejects_http_and_unlisted_hosts():
    with pytest.raises(IngestError, match="non-HTTPS"):
        download_image("http://cmsassets.rgpub.io/x.png")
    with pytest.raises(IngestError, match="allowlist"):
        download_image("https://evil.example.com/x.png")


def test_ingest_removes_seed_cards(client):
    # `client` fixture seeds the demo set; removing seeds must empty the table.
    from app.ingest.fetch_official import remove_seed_cards

    factory = client.app.state.session_factory
    with factory() as db:
        client.post("/api/inventory/UNL-003/increment")  # inventory row too
        removed = remove_seed_cards(db)
        assert removed == 16
    assert client.get("/api/cards").json() == []


def _coded(public_code, rarity_id, number):
    """A gallery card with a given public code / rarity — the two showcase inputs."""
    return {
        **GALLERY_CARD,
        "publicCode": public_code,
        "collectorNumber": number,
        "rarity": {"value": {"id": rarity_id}},
    }


@pytest.mark.parametrize(
    "public_code,rarity_id",
    [
        ("OGN-066a/298", "showcase"),  # legacy: source still says showcase
        ("VEN-021a/166", "epic"),  # alt art, letter suffix
        ("VEN-189*/166", "rare"),  # signed legend overnumber, star suffix
        ("VEN-167/166", "rare"),  # rival overnumber, past the base-set size
        ("VEN-SP3/006", "epic"),  # Crystal Rose special-alt subset
    ],
)
def test_map_card_derives_showcase_for_variant_prints(public_code, rarity_id):
    assert map_card(_coded(public_code, rarity_id, 167))["rarity"] == "Showcase"


@pytest.mark.parametrize(
    "public_code,rarity_id,expected",
    [
        ("VEN-024/166", "common", "Common"),  # plain base-set card
        ("VEN-166/166", "uncommon", "Uncommon"),  # last base number is not "over"
        ("VEN-R01", "common", "Common"),  # runes have no denominator
        ("UNL-T01", "common", "Common"),  # nor do tokens
    ],
)
def test_map_card_leaves_base_prints_alone(public_code, rarity_id, expected):
    assert map_card(_coded(public_code, rarity_id, 24))["rarity"] == expected
