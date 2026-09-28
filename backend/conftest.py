import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient backed by a fresh, seeded database in a temp directory.
    Automatically registers and logs in a test user so all protected endpoints
    work without each test needing to handle auth."""
    monkeypatch.setenv("RIFTBOUND_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RIFTBOUND_SEED", "1")
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "testuser", "password": "testpass1"})
    resp = c.post("/api/auth/token", json={"username": "testuser", "password": "testpass1"})
    token = resp.json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c
