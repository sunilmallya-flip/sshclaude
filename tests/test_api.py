import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from sshclaude.api import app, init_db
from sshclaude.db import Base


def setup_module(module):
    # Use in-memory SQLite for tests
    test_url = "sqlite:///:memory:"
    os.environ["DATABASE_URL"] = test_url
    test_engine = create_engine(test_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    init_db()


def test_provision_cycle(monkeypatch):
    client = TestClient(app)

    class Dummy:
        def __init__(self, result):
            self.result = result

    def fake_create_tunnel(name):
        return {"result": {"id": "tid"}}

    def fake_create_dns_record(subdomain, tid):
        return {"result": {"id": "dns"}}

    def fake_create_access_app(email, subdomain):
        return {"result": {"id": "app"}}

    monkeypatch.setattr("sshclaude.cloudflare.create_tunnel", fake_create_tunnel)
    monkeypatch.setattr(
        "sshclaude.cloudflare.create_dns_record", fake_create_dns_record
    )
    monkeypatch.setattr(
        "sshclaude.cloudflare.create_access_app", fake_create_access_app
    )
    monkeypatch.setattr("sshclaude.cloudflare.rotate_host_key", lambda tid: None)
    monkeypatch.setattr("sshclaude.cloudflare.delete_access_app", lambda app_id: None)
    monkeypatch.setattr("sshclaude.cloudflare.delete_dns_record", lambda rec_id: None)
    monkeypatch.setattr("sshclaude.cloudflare.delete_tunnel", lambda tid: None)

    resp = client.post("/provision", json={"email": "a@b.com", "subdomain": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tunnel_id"] == "tid"
    assert "tunnel_token" in data

    resp = client.get("/provision/test")
    assert resp.status_code == 200
    assert resp.json() == {
        "tunnel_id": "tid",
        "tunnel_token": data["tunnel_token"],
        "dns_record_id": "dns",
        "access_app_id": "app",
    }

    resp = client.post("/rotate-key/test")
    assert resp.status_code == 200

    resp = client.delete("/provision/test")
    assert resp.status_code == 200

    resp = client.get("/provision/test")
    assert resp.status_code == 404


def test_login_flow():
    client = TestClient(app)

    resp = client.post("/login")
    assert resp.status_code == 200
    data = resp.json()
    uid = data["url"].split("/")[-1]
    token = data["token"]

    resp = client.get(f"/login/{uid}/status")
    assert resp.status_code == 200
    assert resp.json() == {"verified": False}

    resp = client.post(f"/login/{uid}", json={"token": "wrong"})
    assert resp.status_code == 400

    resp = client.post(f"/login/{uid}", json={"token": token})
    assert resp.status_code == 200

    resp = client.get(f"/login/{uid}/status")
    assert resp.status_code == 200
    assert resp.json() == {"verified": True}
