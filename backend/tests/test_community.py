def _register(client, username, password="testpass1"):
    """Register a second account and return a client-usable auth header."""
    client.post("/api/auth/register", json={"username": username, "password": password})
    token = client.post(
        "/api/auth/token", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_lists_all_users_with_collection_stats(client):
    other = _register(client, "collector")
    # The other user owns 2 copies of one card and binders another.
    client.patch("/api/inventory/UNL-003", json={"count": 2}, headers=other)
    client.patch("/api/inventory/UNL-011", json={"in_binder": True}, headers=other)

    users = client.get("/api/community/users").json()
    by_name = {u["username"]: u for u in users}
    assert set(by_name) == {"testuser", "collector"}
    assert by_name["testuser"]["is_self"] is True
    assert by_name["collector"]["is_self"] is False
    assert by_name["collector"]["unique_cards"] == 2  # owned + binder-only
    assert by_name["collector"]["total_copies"] == 2
    assert by_name["testuser"]["unique_cards"] == 0


def test_view_another_users_collection(client):
    other = _register(client, "collector")
    client.patch("/api/inventory/UNL-003", json={"count": 2, "foil_count": 1}, headers=other)

    other_id = next(
        u["id"] for u in client.get("/api/community/users").json() if u["username"] == "collector"
    )
    cards = client.get(f"/api/community/users/{other_id}/cards")
    assert cards.status_code == 200
    body = {c["id"]: c for c in cards.json()}
    assert body["UNL-003"]["count"] == 2
    assert body["UNL-003"]["foil_count"] == 1
    # Same shape and ordering as the viewer's own collection…
    own = client.get("/api/cards").json()
    assert [c["id"] for c in cards.json()] == [c["id"] for c in own]
    # …but the viewer's own counts are untouched.
    assert {c["id"]: c for c in own}["UNL-003"]["count"] == 0


def test_unknown_user_404s(client):
    assert client.get("/api/community/users/9999/cards").status_code == 404


def test_community_requires_auth(client):
    anon = {"Authorization": "Bearer nope"}
    assert client.get("/api/community/users", headers=anon).status_code == 401
    assert client.get("/api/community/users/1/cards", headers=anon).status_code == 401
