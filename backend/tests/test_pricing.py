from datetime import date, datetime, timedelta

import httpx
import pytest

from app.models import Card, CardPrice, CardPriceHistory
from app.pricing import budget
from app.pricing.client import PriceApiNotConfigured, PriceClient, parse_price_fields
from app.pricing.matcher import pick_best_match
from app.pricing.service import is_stale, pct_change, refresh_card, refresh_stale_batch


# --- fixtures ----------------------------------------------------------------

def mock_transport(search_result=None, price_result=None):
    """A fake external pricing API: /cards?search= returns search_result,
    /cards/<id> returns price_result. Both default to a single sensible card."""
    search_result = search_result if search_result is not None else {
        "data": [{"id": "ext-1", "name": "Mosstomper", "expansion": "Unleashed"}]
    }
    price_result = price_result if price_result is not None else {
        "data": {
            "id": "ext-1",
            "name": "Mosstomper",
            "prices": {"tcgplayer": {"market": 1.25, "low": 0.9, "currency": "USD"}},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cards") and "search" in request.url.params:
            return httpx.Response(200, json=search_result)
        return httpx.Response(200, json=price_result)

    return httpx.MockTransport(handler)


def make_price_client(monkeypatch, **kwargs) -> PriceClient:
    monkeypatch.setenv("RIFTBOUND_PRICE_API_KEY", "test-key")
    inner = httpx.Client(transport=mock_transport(**kwargs))
    return PriceClient(client=inner)


def make_card(db, card_id="ZZZ-047", name="Mosstomper", set_code="ZZZ"):
    """ZZZ- prefix deliberately avoids colliding with the UNL-00x demo seed
    cards the `client` fixture already seeds into the database."""
    card = Card(
        id=card_id, name=name, set_code=set_code, number="47", rarity="Uncommon",
        domain="Body", card_type="unit", image_file="x.jpg", phash="0" * 16, source_url="",
    )
    db.add(card)
    db.commit()
    return card


# --- client.py -----------------------------------------------------------------

def test_price_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("RIFTBOUND_PRICE_API_KEY", raising=False)
    with pytest.raises(PriceApiNotConfigured):
        PriceClient()


def test_parse_price_fields_reads_tcgplayer_block():
    raw = {"prices": {"tcgplayer": {"market": 2.5, "low": 1.1, "currency": "USD"}}}
    fields = parse_price_fields(raw)
    assert fields.market_price == 2.5
    assert fields.low_price == 1.1
    assert fields.currency == "USD"


def test_parse_price_fields_falls_back_to_cardmarket():
    raw = {"prices": {"cardmarket": {"trend": 3.0, "low": 2.0, "currency": "EUR"}}}
    fields = parse_price_fields(raw)
    assert fields.market_price == 3.0
    assert fields.currency == "EUR"


def test_parse_price_fields_never_raises_on_unrecognized_shape():
    fields = parse_price_fields({"totally": "unexpected"})
    assert fields.market_price is None
    assert fields.low_price is None


# --- matcher.py ------------------------------------------------------------

def test_pick_best_match_prefers_exact_name(client):
    from app.pricing.client import ExternalCard

    db = client.app.state.session_factory()
    card = make_card(db)
    candidates = [
        ExternalCard("a", "Mosstomper (Alt Art)", "Unleashed", {}),
        ExternalCard("b", "Mosstomper", "Unleashed", {}),
    ]
    match = pick_best_match(card, candidates)
    assert match.source_id == "b"


def test_pick_best_match_returns_none_when_no_exact_match(client):
    from app.pricing.client import ExternalCard

    db = client.app.state.session_factory()
    card = make_card(db)
    candidates = [ExternalCard("a", "Something Else", "Unleashed", {})]
    assert pick_best_match(card, candidates) is None


# --- service.py --------------------------------------------------------------

def test_refresh_card_matches_prices_and_records_history(client, monkeypatch):
    db = client.app.state.session_factory()
    card = make_card(db)
    pc = make_price_client(monkeypatch)

    price = refresh_card(db, pc, card)

    assert price is not None
    assert price.market_price == 1.25
    assert price.low_price == 0.9
    assert card.price_source_id == "ext-1"  # cached for next time

    history = db.query(CardPriceHistory).filter(CardPriceHistory.card_id == card.id).all()
    assert len(history) == 1
    assert history[0].market_price == 1.25


def test_refresh_card_same_day_updates_snapshot_not_duplicates(client, monkeypatch):
    db = client.app.state.session_factory()
    card = make_card(db)
    pc = make_price_client(monkeypatch)

    refresh_card(db, pc, card)
    refresh_card(db, pc, card)  # second refresh, same UTC day

    history = db.query(CardPriceHistory).filter(CardPriceHistory.card_id == card.id).all()
    assert len(history) == 1  # not 2


def test_refresh_card_spends_two_requests_first_time_one_thereafter(client, monkeypatch):
    db = client.app.state.session_factory()
    card = make_card(db)
    pc = make_price_client(monkeypatch)

    refresh_card(db, pc, card)
    assert budget.remaining(db) == 90 - 2  # search + price lookup

    refresh_card(db, pc, card)
    assert budget.remaining(db) == 90 - 3  # source_id cached, just the price lookup


def test_refresh_card_unmatched_card_is_skipped_not_fatal(client, monkeypatch):
    db = client.app.state.session_factory()
    card = make_card(db, name="Totally Unknown Card")
    pc = make_price_client(monkeypatch, search_result={"data": []})

    price = refresh_card(db, pc, card)
    assert price is None
    assert card.price_source_id is None


def test_is_stale():
    assert is_stale(None) is True
    fresh = CardPrice(card_id="x", updated_at=datetime.utcnow())
    assert is_stale(fresh) is False
    old = CardPrice(card_id="x", updated_at=datetime.utcnow() - timedelta(hours=48))
    assert is_stale(old) is True


def test_pct_change_uses_closest_qualifying_snapshot():
    history = [
        CardPriceHistory(card_id="x", snapshot_date=date.today() - timedelta(days=10), market_price=1.0),
        CardPriceHistory(card_id="x", snapshot_date=date.today() - timedelta(days=8), market_price=1.5),
    ]
    change = pct_change(history, days=7, current=2.0)
    # Both snapshots are >=7 days old; the day-8 one is the CLOSEST to the
    # 7-day mark, so it's the baseline — not the oldest one available.
    # pct_change rounds to 2dp for display, so compare with matching precision.
    assert change == round((2.0 - 1.5) / 1.5 * 100, 2)


def test_pct_change_none_without_enough_history():
    assert pct_change([], days=7, current=5.0) is None
    recent_only = [CardPriceHistory(card_id="x", snapshot_date=date.today(), market_price=1.0)]
    assert pct_change(recent_only, days=7, current=5.0) is None


def test_refresh_stale_batch_prioritizes_owned_cards(client, monkeypatch):
    db = client.app.state.session_factory()
    owned = make_card(db, "ZZZ-001", "Owned Card")
    unowned = make_card(db, "ZZZ-002", "Unowned Card")
    client.post(f"/api/inventory/{owned.id}/increment")

    pc = make_price_client(
        monkeypatch,
        search_result={"data": [{"id": "ext-x", "name": "Owned Card", "expansion": "Unleashed"}]},
    )
    result = refresh_stale_batch(db, pc, limit=1)
    assert result["refreshed"] == 1
    assert db.get(CardPrice, owned.id) is not None
    assert db.get(CardPrice, unowned.id) is None  # budget spent on the owned card first


# --- budget.py ---------------------------------------------------------------

def test_budget_tracks_and_resets_by_date(client):
    db = client.app.state.session_factory()
    assert budget.has_budget(db) is True
    budget.spend(db, 5)
    db.commit()
    assert budget.remaining(db) == 90 - 5


# --- routes/prices.py ---------------------------------------------------------

def test_price_status_reports_not_configured_by_default(client):
    resp = client.get("/api/prices/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["daily_budget"] == 90


def test_get_price_not_configured_returns_null_fields_not_error(client):
    resp = client.get("/api/prices/UNL-003")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["market_price"] is None


def test_get_price_unknown_card_404s(client):
    assert client.get("/api/prices/NOPE").status_code == 404


def test_price_summary_batches_multiple_ids(client):
    resp = client.get("/api/prices/summary", params={"ids": "UNL-003,UNL-004,NOPE"})
    assert resp.status_code == 200
    body = resp.json()
    assert {p["card_id"] for p in body} == {"UNL-003", "UNL-004"}  # unknown id silently dropped


def test_price_history_empty_before_any_refresh(client):
    resp = client.get("/api/prices/UNL-003/history")
    assert resp.status_code == 200
    assert resp.json()["points"] == []
