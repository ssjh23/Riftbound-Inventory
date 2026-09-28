from app.trades import TradeLine, format_request, parse_request


def _register(client, username, password="testpass1"):
    client.post("/api/auth/register", json={"username": username, "password": password})
    token = client.post(
        "/api/auth/token", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── format ────────────────────────────────────────────────


def test_request_round_trips_through_text():
    lines = [
        TradeLine("UNL-003", "Mosstomper Seedling", False, 2),
        TradeLine("UNL-011", "Baron Pit", True, 1),
    ]
    text = format_request("alice", "bob", "2026-07-31", lines)
    parsed = parse_request(text)

    assert parsed.from_username == "alice"
    assert parsed.to_username == "bob"
    assert parsed.warnings == []
    assert [(l.card_id, l.card_name, l.foil, l.quantity) for l in parsed.lines] == [
        ("UNL-003", "Mosstomper Seedling", False, 2),
        ("UNL-011", "Baron Pit", True, 1),
    ]


def test_format_is_human_readable():
    text = format_request("alice", "bob", "2026-07-31", [TradeLine("UNL-003", "Mosstomper", False, 2)])
    assert "# RIFTBOUND TRADE REQUEST v1" in text
    assert "# From: alice" in text
    assert "2x UNL-003 Mosstomper" in text
    assert "# 2 copies requested" in text


def test_parse_accepts_a_bare_hand_written_list():
    parsed = parse_request("2x UNL-003\n1 UNL-011 Baron Pit [FOIL]\n")
    assert [(l.card_id, l.foil, l.quantity) for l in parsed.lines] == [
        ("UNL-003", False, 2),
        ("UNL-011", True, 1),
    ]


def test_parse_sums_duplicates_and_keeps_finishes_apart():
    parsed = parse_request("2x UNL-003\n1x UNL-003\n1x UNL-003 [foil]")
    assert [(l.foil, l.quantity) for l in parsed.lines] == [(False, 3), (True, 1)]


def test_parse_warns_on_junk_instead_of_raising():
    parsed = parse_request("# RIFTBOUND TRADE REQUEST v1\nnot a card line\n2x UNL-003")
    assert len(parsed.lines) == 1
    assert any("Skipped unreadable line" in w for w in parsed.warnings)


def test_parse_warns_when_nothing_found():
    assert parse_request("hello there").lines == []
    assert any("No card lines found" in w for w in parse_request("").warnings)


# ── export ────────────────────────────────────────────────


def test_export_fills_in_card_names_from_the_catalog(client):
    resp = client.post(
        "/api/trades/export",
        json={"to_username": "bob", "items": [{"card_id": "UNL-003", "foil": False, "quantity": 2}]},
    )
    assert resp.status_code == 200
    text = resp.json()["text"]
    assert "# From: testuser" in text
    assert "# To: bob" in text
    assert "2x UNL-003 Mosstomper" in text


def test_export_rejects_an_empty_basket(client):
    assert client.post("/api/trades/export", json={"to_username": "bob", "items": []}).status_code == 400


# ── preview ───────────────────────────────────────────────


def test_preview_shows_current_and_resulting_counts(client):
    client.patch("/api/inventory/UNL-003", json={"count": 3, "foil_count": 1})
    body = client.post(
        "/api/trades/preview",
        json={"text": "# From: alice\n# To: testuser\n2x UNL-003\n1x UNL-003 [foil]"},
    ).json()

    assert body["from_username"] == "alice"
    assert body["warnings"] == []
    normal, foil = body["lines"]
    assert (normal["requested"], normal["current_count"], normal["resulting_count"]) == (2, 3, 1)
    assert normal["card_name"] == "Mosstomper"
    assert normal["image_url"] == "/images/UNL-003.jpg"
    assert (foil["foil"], foil["current_count"], foil["resulting_count"]) == (True, 1, 0)
    assert normal["sufficient"] and foil["sufficient"]


def test_preview_flags_shortfalls_and_unknown_cards(client):
    client.patch("/api/inventory/UNL-003", json={"count": 1})
    body = client.post(
        "/api/trades/preview", json={"text": "5x UNL-003\n1x NOPE-999 Ghost Card"}
    ).json()

    short, unknown = body["lines"]
    assert short["sufficient"] is False
    assert short["resulting_count"] == 0  # never goes negative
    assert unknown["known"] is False
    assert unknown["image_url"] is None
    assert any("Unknown card id" in w for w in body["warnings"])


def test_preview_warns_when_addressed_to_someone_else(client):
    body = client.post(
        "/api/trades/preview", json={"text": "# To: someone-else\n1x UNL-003"}
    ).json()
    assert any("not you" in w for w in body["warnings"])


def test_preview_does_not_change_any_counts(client):
    client.patch("/api/inventory/UNL-003", json={"count": 3})
    client.post("/api/trades/preview", json={"text": "2x UNL-003"})
    cards = {c["id"]: c for c in client.get("/api/cards").json()}
    assert cards["UNL-003"]["count"] == 3


# ── fulfil ────────────────────────────────────────────────


def test_fulfil_deducts_only_the_confirmed_items(client):
    client.patch("/api/inventory/UNL-003", json={"count": 3, "foil_count": 2})
    client.patch("/api/inventory/UNL-011", json={"count": 4})

    resp = client.post(
        "/api/trades/fulfil",
        json={
            "items": [
                {"card_id": "UNL-003", "foil": False, "quantity": 2},
                {"card_id": "UNL-003", "foil": True, "quantity": 1},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] == 3

    cards = {c["id"]: c for c in client.get("/api/cards").json()}
    assert (cards["UNL-003"]["count"], cards["UNL-003"]["foil_count"]) == (1, 1)
    assert cards["UNL-011"]["count"] == 4  # the ignored line is untouched


def test_fulfil_returns_the_updated_cards_for_the_ui(client):
    client.patch("/api/inventory/UNL-003", json={"count": 3})
    body = client.post(
        "/api/trades/fulfil", json={"items": [{"card_id": "UNL-003", "foil": False, "quantity": 1}]}
    ).json()
    assert [c["id"] for c in body["cards"]] == ["UNL-003"]
    assert body["cards"][0]["count"] == 2


def test_fulfil_clamps_to_what_is_actually_held(client):
    """A stale preview (or an edited request) must never drive a count negative."""
    client.patch("/api/inventory/UNL-003", json={"count": 1})
    body = client.post(
        "/api/trades/fulfil", json={"items": [{"card_id": "UNL-003", "foil": False, "quantity": 9}]}
    ).json()
    assert body["applied"] == 1
    assert body["cards"][0]["count"] == 0


def test_fulfil_rejects_unknown_cards(client):
    resp = client.post(
        "/api/trades/fulfil", json={"items": [{"card_id": "NOPE-999", "foil": False, "quantity": 1}]}
    )
    assert resp.status_code == 404


def test_fulfil_only_ever_touches_the_caller(client):
    """The requester's own shelves are never modified by their request."""
    other = _register(client, "bob")
    client.patch("/api/inventory/UNL-003", json={"count": 5}, headers=other)  # bob
    client.patch("/api/inventory/UNL-003", json={"count": 2})  # testuser

    client.post(
        "/api/trades/fulfil", json={"items": [{"card_id": "UNL-003", "foil": False, "quantity": 2}]}
    )

    mine = {c["id"]: c for c in client.get("/api/cards").json()}
    theirs = {c["id"]: c for c in client.get("/api/cards", headers=other).json()}
    assert mine["UNL-003"]["count"] == 0
    assert theirs["UNL-003"]["count"] == 5  # bob is untouched


def test_trade_endpoints_require_auth(client):
    anon = {"Authorization": "Bearer nope"}
    assert client.post("/api/trades/preview", json={"text": "1x UNL-003"}, headers=anon).status_code == 401
    assert client.post("/api/trades/fulfil", json={"items": []}, headers=anon).status_code == 401
