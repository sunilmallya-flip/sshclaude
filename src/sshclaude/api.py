from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import os
import secrets
import uuid
import requests
import traceback

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
import base64
import json

from . import cloudflare
from .db import LoginEvent, LoginSession, Provision, get_session, init_db

API_TOKEN = os.getenv("API_TOKEN")

def verify_token(authorization: str = Header("")) -> None:
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


class ProvisionRequest(BaseModel):
    github_id: str
    email: str
    subdomain: str

class ProvisionResponse(BaseModel):
    tunnel_id: str
    tunnel_token: str
    dns_record_id: str
    access_app_id: str

class LoginEventRequest(BaseModel):
    user: str
    ip: str


class LoginSessionResponse(BaseModel):
    url: str
    token: str
    client_id: str

class TokenRequest(BaseModel):
    token: str


class DeleteRequest(BaseModel):
    tunnel_token: str

app = FastAPI(title="sshclaude Provisioning API")
init_db()


@app.post("/login", response_model=LoginSessionResponse)
def create_login() -> LoginSessionResponse:
    uid = uuid.uuid4().hex
    token = secrets.token_urlsafe(8)

    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Missing GITHUB_CLIENT_ID in environment")

    with get_session() as db:
        db.add(LoginSession(id=uid, token=token))
        db.commit()

    return LoginSessionResponse(
        url=f"/login/{uid}",
        token=token,
        client_id=client_id
    )


@app.post("/login/{uid}")
def verify_login(uid: str, req: TokenRequest) -> dict[str, str]:
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session or session.token != req.token:
            raise HTTPException(status_code=400, detail="invalid token")
        session.verified = True
        db.commit()
    return {"status": "verified"}


@app.get("/login/{uid}")
def verify_login_redirect(uid: str, token: str = Query(...)) -> dict[str, str]:
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session or session.token != token:
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


@app.get("/login/{uid}/whoami")
def whoami(uid: str, authorization: str = Header("")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session or session.token != token or not session.verified:
            raise HTTPException(status_code=401, detail="unauthorized")
        if not session.email:
            raise HTTPException(status_code=400, detail="email not set")
        return {"email": session.email}


@app.get("/oauth/callback")
def github_callback(code: str, state: str = Query(...)):
    """Handles GitHub OAuth redirect and updates the login session with verified identity."""
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Missing GitHub client credentials")

    # Decode the 'state' value (which includes uid and token)
    try:
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        parsed = json.loads(decoded)
        uid = parsed["uid"]
        token = parsed["token"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid state: {e}")

    # Exchange code for access token
    try:
        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code
            },
            timeout=10
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token returned from GitHub")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")

    # Fetch GitHub user info
    user_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10
    )
    emails_resp = requests.get(
        "https://api.github.com/user/emails",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10
    )

    if not user_resp.ok or not emails_resp.ok:
        raise HTTPException(status_code=502, detail="Failed to fetch GitHub user profile")

    github_login = user_resp.json().get("login")
    github_id = user_resp.json().get("id")
    email_data = emails_resp.json()

    # Extract primary, verified email
    primary_email = next((e["email"] for e in email_data if e.get("primary") and e.get("verified")), None)
    if not primary_email:
        raise HTTPException(status_code=400, detail="No verified email found")

    # Store session
    with get_session() as db:
        session = db.query(LoginSession).filter_by(id=uid).first()
        if not session or session.token != token:
            raise HTTPException(status_code=400, detail="Invalid session or token")
        session.verified = True
        session.email = primary_email
        session.github_id = str(github_id)
        session.github_login = github_login
        db.commit()

    print(f"[DEBUG] Verified: {github_login} <{primary_email}>")
    return RedirectResponse("https://sshclaude.dev/success")



@app.post("/provision", response_model=ProvisionResponse, dependencies=[Depends(verify_token)])
def provision(req: ProvisionRequest) -> ProvisionResponse:
    try:
        print("[DEBUG] Starting provision for", req.subdomain)
        print("[DEBUG] Request body:", req.dict())

        tunnel = cloudflare.create_tunnel(req.subdomain)
        tunnel_id = tunnel["result"]["id"]
        print("[DEBUG] Tunnel ID:", tunnel_id)

        if "tunnel_token" in tunnel:
            token = tunnel["tunnel_token"]
        else:
            print("[DEBUG] Tunnel exists. Attempting to fetch token from DB...")
            with get_session() as db:
                existing = db.query(Provision).filter_by(subdomain=req.subdomain).first()
                if existing and existing.tunnel_token:
                    token = existing.tunnel_token
                    print("[DEBUG] Retrieved tunnel token from DB.")
                else:
                    raise HTTPException(status_code=409, detail="Tunnel exists but no token found.")

        dns = cloudflare.create_dns_record(req.subdomain, tunnel_id)
        dns_id = dns["result"]["id"]
        print("[DEBUG] DNS record ID:", dns_id)

        access = cloudflare.create_access_app(req.email, req.subdomain)
        access_id = access["result"]["id"]
        print("[DEBUG] Access App ID:", access_id)

    except requests.RequestException as re:
        print("[ERROR] Cloudflare API error:", re)
        raise HTTPException(status_code=502, detail=f"Cloudflare API error: {str(re)}")
    except Exception as e:
        print("[ERROR] Internal error during /provision")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error") from e

    data = {
        "tunnel_id": tunnel_id,
        "tunnel_token": token,
        "dns_record_id": dns_id,
        "access_app_id": access_id,
    }

    with get_session() as db:
        existing = db.query(Provision).filter_by(subdomain=req.subdomain).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            provision = Provision(github_id=req.github_id, subdomain=req.subdomain, **data)
            db.add(provision)
        db.commit()

    print("[DEBUG] Provision record saved:", data)
    return ProvisionResponse(**data)


@app.get("/provision/{subdomain}", response_model=ProvisionResponse, dependencies=[Depends(verify_token)])
def get_provision(subdomain: str) -> ProvisionResponse:
    with get_session() as db:
        provision = db.query(Provision).filter_by(subdomain=subdomain).first()
        if not provision:
            raise HTTPException(status_code=404, detail="unknown subdomain")
        return ProvisionResponse(
            tunnel_id=provision.tunnel_id,
            tunnel_token=provision.tunnel_token,
            dns_record_id=provision.dns_record_id,
            access_app_id=provision.access_app_id,
        )


@app.delete("/provision/{subdomain}", dependencies=[Depends(verify_token)])
def delete_provision(subdomain: str, req: DeleteRequest) -> dict[str, str]:
    with get_session() as db:
        provision = db.query(Provision).filter_by(subdomain=subdomain).first()
        if not provision:
            raise HTTPException(status_code=404, detail="unknown subdomain")
        if provision.tunnel_token != req.tunnel_token:
            raise HTTPException(status_code=403, detail="invalid token")
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

