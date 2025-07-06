from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import cloudflare
from .db import get_db, init_db

init_db()


class ProvisionRequest(BaseModel):
    email: str
    subdomain: str


class ProvisionResponse(BaseModel):
    tunnel_id: str
    dns_record_id: str
    access_app_id: str


app = FastAPI(title="sshclaude Provisioning API")


@app.post("/provision", response_model=ProvisionResponse)
def provision(req: ProvisionRequest) -> ProvisionResponse:
    try:
        tunnel = cloudflare.create_tunnel(req.subdomain)
        dns = cloudflare.create_dns_record(req.subdomain, tunnel["result"]["id"])
        access = cloudflare.create_access_app(req.email, req.subdomain)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    data = {
        "tunnel_id": tunnel["result"]["id"],
        "dns_record_id": dns["result"]["id"],
        "access_app_id": access["result"]["id"],
    }

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users(email) VALUES (?)", (req.email,))
        cur.execute("SELECT id FROM users WHERE email=?", (req.email,))
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO tunnels(subdomain, tunnel_id, user_id) VALUES (?, ?, ?)",
            (req.subdomain, data["tunnel_id"], user_id),
        )
        tunnel_db_id = cur.lastrowid
        cur.execute(
            "INSERT INTO dns_access(dns_record_id, access_app_id, tunnel_id) VALUES (?, ?, ?)",
            (data["dns_record_id"], data["access_app_id"], tunnel_db_id),
        )
        conn.commit()

    return ProvisionResponse(**data)


@app.delete("/provision/{subdomain}")
def delete_provision(subdomain: str) -> dict[str, str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tunnels.id, tunnels.tunnel_id, dns_access.dns_record_id, dns_access.access_app_id
            FROM tunnels JOIN dns_access ON dns_access.tunnel_id = tunnels.id
            WHERE tunnels.subdomain=?
            """,
            (subdomain,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="subdomain not found")
        tunnel_pk, tunnel_id, dns_id, access_id = row

    try:
        cloudflare.delete_access_app(access_id)
        cloudflare.delete_dns_record(dns_id)
        cloudflare.delete_tunnel(tunnel_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dns_access WHERE tunnel_id=?", (tunnel_pk,))
        cur.execute("DELETE FROM tunnels WHERE id=?", (tunnel_pk,))
        conn.commit()
    return {"status": "deleted"}


def main() -> None:
    import uvicorn

    uvicorn.run("sshclaude.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
