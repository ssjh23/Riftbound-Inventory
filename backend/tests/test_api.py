def test_cards_seeded_and_listed(client):
    cards = client.get("/api/cards").json()
    assert len(cards) == 16
    by_id = {c["id"]: c for c in cards}
    assert by_id["UNL-001"]["limit"] == 1  # legend (Master Yi, Unstoppable)
    assert by_id["UNL-003"]["limit"] == 3  # unit (Mosstomper)
    assert by_id["UNL-011"]["limit"] == 1  # battlefield (Baron Pit)
    assert by_id["UNL-015"]["limit"] == 12  # rune
    assert all(c["count"] == 0 and c["foil_count"] == 0 for c in cards)
    assert by_id["UNL-001"]["image_url"] == "/images/UNL-001.jpg"
    assert all(c["set_code"] == "UNL" for c in cards)


def test_cards_sorted_numerically(client):
    from app.models import Card

    with client.app.state.session_factory() as db:
        for n in ["2", "10", "1", "100", "21"]:
            db.add(Card(
                id=f"ZZZ-{n}", name=f"c{n}", set_code="ZZZ", number=n, rarity="Common",
                domain="X", card_type="unit", image_file="x.jpg", phash="0" * 16, source_url="",
            ))
        db.commit()
    numbers = [c["number"] for c in client.get("/api/cards", params={"set_code": "ZZZ"}).json()]
    assert numbers == ["1", "2", "10", "21", "100"]  # numeric, not "1 10 100 2 21"


def test_tokens_sort_to_back_and_labelled(client):
    from app.models import Card

    with client.app.state.session_factory() as db:
        rows = [
            ("TOK-5", "5", "Real Five"),
            ("TOK-1", "1", "Real One"),
            ("TOK-T02", "2", "Token Two"),  # token: id ends -T02
            ("TOK-T01", "1", "Token One"),  # token: id ends -T01
        ]
        for cid, number, name in rows:
            db.add(Card(
                id=cid, name=name, set_code="TOK", number=number, rarity="Common",
                domain="X", card_type="unit", image_file="x.jpg", phash="0" * 16, source_url="",
            ))
        db.commit()
    cards = client.get("/api/cards", params={"set_code": "TOK"}).json()
    # real cards first (numeric), tokens last, relabelled T01/T02
    assert [(c["name"], c["number"]) for c in cards] == [
        ("Real One", "1"),
        ("Real Five", "5"),
        ("Token One", "T01"),
        ("Token Two", "T02"),
    ]


def test_card_filters(client):
    legends = client.get("/api/cards", params={"card_type": "legend"}).json()
    assert {c["id"] for c in legends} == {"UNL-001", "UNL-002"}
    found = client.get("/api/cards", params={"search": "moss"}).json()
    assert [c["name"] for c in found] == ["Mosstomper"]


def test_increment_and_clamp_at_zero(client):
    out = client.post("/api/inventory/UNL-003/increment").json()
    assert out["count"] == 1
    out = client.post("/api/inventory/UNL-003/increment", params={"delta": -5}).json()
    assert out["count"] == 0  # never negative
    assert client.post("/api/inventory/NOPE/increment").status_code == 404


def test_foil_and_normal_counts_are_independent(client):
    out = client.post("/api/inventory/UNL-003/increment", params={"foil": True}).json()
    assert out == {**out, "count": 0, "foil_count": 1}  # foil up, normal untouched
    out = client.post("/api/inventory/UNL-003/increment", params={"delta": 2}).json()
    assert (out["count"], out["foil_count"]) == (2, 1)
    out = client.post(
        "/api/inventory/UNL-003/increment", params={"foil": True, "delta": -5}
    ).json()
    assert (out["count"], out["foil_count"]) == (2, 0)  # foil clamps, normal kept


def test_owned_filter_counts_foil(client):
    client.post("/api/inventory/UNL-004/increment", params={"foil": True})  # foil only
    owned = client.get("/api/cards", params={"owned": True}).json()
    assert [c["id"] for c in owned] == ["UNL-004"]  # a foil-only card is "owned"


def test_in_binder_is_owned_but_not_toward_limit(client):
    out = client.patch("/api/inventory/UNL-003", json={"in_binder": True}).json()
    assert out["in_binder"] is True
    assert out["count"] == 0 and out["foil_count"] == 0  # no physical copies
    # It's "owned" (in binder) despite zero copies...
    owned = {c["id"] for c in client.get("/api/cards", params={"owned": True}).json()}
    assert "UNL-003" in owned
    missing = {c["id"] for c in client.get("/api/cards", params={"owned": False}).json()}
    assert "UNL-003" not in missing
    # ...but the limit/count is untouched by the binder flag.
    assert out["limit"] == 3
    out = client.patch("/api/inventory/UNL-003", json={"in_binder": False}).json()
    assert out["in_binder"] is False


def test_binder_foil_implies_in_binder_and_clears_together(client):
    # Marking the binder copy as foil auto-marks it as in the binder.
    out = client.patch("/api/inventory/UNL-003", json={"binder_foil": True}).json()
    assert out["binder_foil"] is True and out["in_binder"] is True
    # Removing it from the binder also clears the binder-foil marker.
    out = client.patch("/api/inventory/UNL-003", json={"in_binder": False}).json()
    assert out["in_binder"] is False and out["binder_foil"] is False


def test_limit_override_roundtrip(client):
    out = client.patch("/api/inventory/UNL-012", json={"limit_override": 9}).json()
    assert out["limit"] == 9
    out = client.patch("/api/inventory/UNL-012", json={"limit_override": None}).json()
    assert out["limit"] == 3  # cleared -> back to type default (spell)


def test_settings_rules_persist_and_apply(client):
    rules = client.get("/api/settings/limits").json()
    rules["rarity_caps_enabled"] = True
    client.put("/api/settings/limits", json=rules)
    cards = {c["id"]: c for c in client.get("/api/cards").json()}
    # LeBlanc is an Epic unit: the epic cap drops her from 3 to 1.
    assert cards["UNL-007"]["limit"] == 1
    # Baron Pit (Epic battlefield) stays 1: min(type 1, cap 1).
    assert cards["UNL-011"]["limit"] == 1
    assert client.get("/api/settings/limits").json()["rarity_caps_enabled"] is True


def test_export_import_roundtrip(client):
    client.post("/api/inventory/UNL-005/increment", params={"delta": 3})
    client.post("/api/inventory/UNL-005/increment", params={"foil": True, "delta": 2})
    client.patch("/api/inventory/UNL-007", json={"binder_foil": True})  # foil binder card
    client.patch("/api/inventory/UNL-006", json={"limit_override": 5})
    backup = client.get("/api/backup/export").json()

    client.patch("/api/inventory/UNL-005", json={"count": 0, "foil_count": 0})
    client.patch("/api/inventory/UNL-007", json={"in_binder": False})
    client.patch("/api/inventory/UNL-006", json={"limit_override": None})

    result = client.post("/api/backup/import", json=backup).json()
    assert result["applied"] == 3
    cards = {c["id"]: c for c in client.get("/api/cards").json()}
    assert cards["UNL-005"]["count"] == 3
    assert cards["UNL-005"]["foil_count"] == 2  # foils survive the round-trip
    assert cards["UNL-007"]["in_binder"] is True  # binder + foil flags survive
    assert cards["UNL-007"]["binder_foil"] is True
    assert cards["UNL-006"]["limit"] == 5


def test_import_skips_unknown_cards(client):
    backup = client.get("/api/backup/export").json()
    backup["inventory"] = [{"card_id": "FUTURE-999", "count": 2, "limit_override": None}]
    result = client.post("/api/backup/import", json=backup).json()
    assert result == {"applied": 0, "skipped": 1}
