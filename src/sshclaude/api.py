from __future__ import annotations

import os
import secrets
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import cloudflare
from .db import LoginEvent, LoginSession, Provision, get_session, init_db

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


class LoginSessionResponse(BaseModel):
    url: str
    token: str


class TokenRequest(BaseModel):
    token: str


app = FastAPI(title="sshclaude Provisioning API")
init_db()


@app.post("/login", response_model=LoginSessionResponse)
def create_login() -> LoginSessionResponse:
    uid = uuid.uuid4().hex
    token = secrets.token_urlsafe(8)
    with get_session() as db:
        db.add(LoginSession(id=uid, token=token))
        db.commit()
    return LoginSessionResponse(url=f"/login/{uid}", token=token)


@app.post("/login/{uid}")
def verify_login(uid: str, req: TokenRequest) -> dict[str, str]:
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session or session.token != req.token:
            raise HTTPException(status_code=400, detail="invalid token")
        session.verified = True
        db.commit()
    return {"status": "verified"}


@app.get("/login/{uid}/status")
def login_status(uid: str) -> dict[str, bool]:
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session:
            raise HTTPException(status_code=404, detail="unknown uid")
        return {"verified": session.verified}


@app.post(
    "/provision", response_model=ProvisionResponse, dependencies=[Depends(verify_token)]
)
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


@app.get(
    "/provision/{subdomain}",
    response_model=ProvisionResponse,
    dependencies=[Depends(verify_token)],
)
def get_provision(subdomain: str) -> ProvisionResponse:
    """Return provision details for a subdomain."""
    with get_session() as db:
        provision = db.query(Provision).filter_by(subdomain=subdomain).first()
        if not provision:
            raise HTTPException(status_code=404, detail="unknown subdomain")
        return ProvisionResponse(
            tunnel_id=provision.tunnel_id,
            dns_record_id=provision.dns_record_id,
            access_app_id=provision.access_app_id,
        )


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


@app.post("/record-login/{subdomain}", dependencies=[Depends(verify_token)])
def record_login(subdomain: str, event: LoginEventRequest) -> dict[str, str]:
    with get_session() as db:
        db.add(LoginEvent(subdomain=subdomain, user=event.user, ip=event.ip))
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
