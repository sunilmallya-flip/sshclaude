from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel

from . import cloudflare
from .db import Provision, LoginEvent, get_session, init_db

API_TOKEN = os.getenv("API_TOKEN")


def verify_token(authorization: str = Header("")) -> None:
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


class ProvisionRequest(BaseModel):
    email: str
    subdomain: str


class ProvisionResponse(BaseModel):
    tunnel_id: str
    dns_record_id: str
    access_app_id: str


class LoginEventRequest(BaseModel):
    user: str
    ip: str


app = FastAPI(title="sshclaude Provisioning API")
init_db()


@app.post("/provision", response_model=ProvisionResponse, dependencies=[Depends(verify_token)])
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
    with get_session() as db:
        provision = Provision(
            email=req.email,
            subdomain=req.subdomain,
            **data,
        )
        db.add(provision)
        db.commit()
    return ProvisionResponse(**data)


@app.delete("/provision/{subdomain}", dependencies=[Depends(verify_token)])
def delete_provision(subdomain: str) -> dict[str, str]:
    with get_session() as db:
        provision = db.query(Provision).filter_by(subdomain=subdomain).first()
        if not provision:
            raise HTTPException(status_code=404, detail="unknown subdomain")
        try:
            cloudflare.delete_access_app(provision.access_app_id)
            cloudflare.delete_dns_record(provision.dns_record_id)
            cloudflare.delete_tunnel(provision.tunnel_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        db.delete(provision)
        db.commit()
    return {"status": "deleted"}


@app.get("/history/{subdomain}", dependencies=[Depends(verify_token)])
def history(subdomain: str):
    """Return login history for a subdomain."""
    with get_session() as db:
        events = (
            db.query(LoginEvent)
            .filter_by(subdomain=subdomain)
            .order_by(LoginEvent.timestamp.desc())
            .all()
        )
        return [
            {
                "user": e.user,
                "ip": e.ip,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ]


@app.post("/login/{subdomain}", dependencies=[Depends(verify_token)])
def record_login(subdomain: str, event: LoginEventRequest) -> dict[str, str]:
    with get_session() as db:
        db.add(
            LoginEvent(subdomain=subdomain, user=event.user, ip=event.ip)
        )
        db.commit()
    return {"status": "recorded"}


@app.post("/rotate-key/{subdomain}", dependencies=[Depends(verify_token)])
def rotate_key(subdomain: str) -> dict[str, str]:
    """Rotate SSH host key for the given subdomain."""
    with get_session() as db:
        provision = db.query(Provision).filter_by(subdomain=subdomain).first()
        if not provision:
            raise HTTPException(status_code=404, detail="unknown subdomain")
        try:
            cloudflare.rotate_host_key(provision.tunnel_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    return {"status": "rotated"}


def main() -> None:
    import uvicorn

    uvicorn.run("sshclaude.api:app", host="0.0.0.0", port=8000)


def lambda_handler(event, context):
    from mangum import Mangum

    handler = Mangum(app)
    return handler(event, context)


if __name__ == "__main__":
    main()
