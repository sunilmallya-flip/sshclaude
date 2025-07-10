from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # Automatically loads from .env in current working directory

import os
import secrets
import uuid
import requests
import traceback

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import cloudflare
from .db import LoginEvent, LoginSession, Provision, get_session, init_db

API_TOKEN = os.getenv("API_TOKEN")


def verify_token(authorization: str = Header("")) -> None:
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


class ProvisionRequest(BaseModel):
    github_id: str
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
        print("[DEBUG] Starting provision for", req.subdomain)
        print("[DEBUG] Request body:", req.dict())

        # 1. Create or reuse tunnel
        tunnel = cloudflare.create_tunnel(req.subdomain)
        tunnel_id = tunnel["result"]["id"]
        print("[DEBUG] Tunnel ID:", tunnel_id)

        # 2. Extract tunnel token (only present at creation time)
        if "tunnel_token" in tunnel:
            token = tunnel["tunnel_token"]
        else:
            print("[DEBUG] Tunnel already exists. Attempting to fetch token from DB...")
            with get_session() as db:
                existing = db.query(Provision).filter_by(subdomain=req.subdomain).first()
                if existing and existing.tunnel_token:
                    token = existing.tunnel_token
                    print("[DEBUG] Retrieved tunnel token from DB.")
                else:
                    raise HTTPException(
                        status_code=409,
                        detail="Tunnel exists but no token found. Please uninstall and try again.",
                    )

        # 3. Create or reuse DNS record
        dns = cloudflare.create_dns_record(req.subdomain, tunnel_id)
        dns_id = dns["result"]["id"]
        print("[DEBUG] DNS record ID:", dns_id)

        # 4. Create or reuse Access App
        access = cloudflare.create_access_app(req.github_id, req.subdomain)
        access_id = access["result"]["id"]
        print("[DEBUG] Access App ID:", access_id)

    except requests.RequestException as re:
        print("[ERROR] Cloudflare API error:", re)
        raise HTTPException(status_code=502, detail=f"Cloudflare API error: {str(re)}")
    except Exception as e:
        print("[ERROR] Internal error during /provision")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error") from e

    # 5. Save provision record to DB
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
            tunnel_token=provision.tunnel_token,
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


import webbrowser
import time

@cli.command()
@click.option("--github", required=True, help="Your GitHub username (will be verified)")
@click.option("--domain", help="Subdomain to use (default: <user>.sshclaude.com)")
@click.option("--session", default="15m", help="Session TTL for Access")
def init(github: str, domain: str | None, session: str):
    """Initialize tunnel with GitHub-verified identity."""

    config = read_config()
    if config:
        console.print("[yellow]sshclaude already initialized.")
        return

    install_cloudflared()
    install_ttyd()

    # 1. Start login session
    console.print("[bold]Verifying GitHub identity via browser login...")
    try:
        resp = requests.post(f"{API_URL}/login", timeout=10)
        resp.raise_for_status()
    except Exception as e:
        console.print(f"[red]Failed to initiate login: {e}")
        return

    login = resp.json()
    uid = login["url"].split("/")[-1]
    token = login["token"]
    login_url = f"https://sshclaude.dev{login['url']}?token={token}"

    webbrowser.open(login_url)
    console.print(f"[cyan]Waiting for verification... (open {login_url} if not auto-launched)")

    # 2. Poll for status
    for _ in range(60):
        time.sleep(2)
        try:
            check = requests.get(f"{API_URL}/login/{uid}/status", timeout=5).json()
            if check.get("verified"):
                console.print("[green]GitHub identity verified.")
                break
        except Exception:
            pass
    else:
        console.print("[red]Verification timed out.")
        return

    # 3. Provision resources
    subdomain = domain or f"{os.getlogin()}.sshclaude.com"
    console.print("[bold]Provisioning tunnel and access policy...")
    try:
        resp = requests.post(
            f"{API_URL}/provision",
            json={"github_id": github, "subdomain": subdomain},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Provisioning failed: {e}")
        return

    # 4. Save config and launch
    config = {
        "github_id": github,
        "domain": subdomain,
        "session": session,
        "tunnel_id": data.get("tunnel_id"),
        "tunnel_token": data.get("tunnel_token"),
        "dns_record_id": data.get("dns_record_id"),
        "access_app_id": data.get("access_app_id"),
    }
    write_config(config)
    write_tunnel_files(subdomain, config["tunnel_token"])
    write_launcher()
    write_plist(config["tunnel_token"])
    console.print("[green]Initialization complete!")



if __name__ == "__main__":
    cli()
