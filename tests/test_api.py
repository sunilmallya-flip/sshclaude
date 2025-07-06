import os

from fastapi.testclient import TestClient

from sshclaude import db
from sshclaude.api import app


def setup_module(module):
    os.environ["DATABASE_URL"] = ":memory:"
    db.init_db()


def test_provision_persistence(monkeypatch):
    calls = {}

    def fake_create_tunnel(sub):
        calls["tunnel"] = sub
        return {"result": {"id": "tid"}}

    def fake_create_dns(sub, tid):
        calls["dns"] = (sub, tid)
        return {"result": {"id": "did"}}

    def fake_create_access(email, sub):
        calls["access"] = (email, sub)
        return {"result": {"id": "aid"}}

    monkeypatch.setattr("sshclaude.cloudflare.create_tunnel", fake_create_tunnel)
    monkeypatch.setattr("sshclaude.cloudflare.create_dns_record", fake_create_dns)
    monkeypatch.setattr("sshclaude.cloudflare.create_access_app", fake_create_access)

    client = TestClient(app)
    resp = client.post("/provision", json={"email": "a@b.com", "subdomain": "foo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"tunnel_id": "tid", "dns_record_id": "did", "access_app_id": "aid"}

    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM tunnels")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM dns_access")
        assert cur.fetchone()[0] == 1


def test_delete_persistence(monkeypatch):
    def fake_delete_app(app_id):
        assert app_id == "aid"

    def fake_delete_dns(dns_id):
        assert dns_id == "did"

    def fake_delete_tunnel(tid):
        assert tid == "tid"

    monkeypatch.setattr("sshclaude.cloudflare.delete_access_app", fake_delete_app)
    monkeypatch.setattr("sshclaude.cloudflare.delete_dns_record", fake_delete_dns)
    monkeypatch.setattr("sshclaude.cloudflare.delete_tunnel", fake_delete_tunnel)

    client = TestClient(app)
    resp = client.delete("/provision/foo")
    assert resp.status_code == 200

    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tunnels")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM dns_access")
        assert cur.fetchone()[0] == 0
