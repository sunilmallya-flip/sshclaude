from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import cloudflare

PROVISIONED: dict[str, dict[str, str]] = {}
LOGIN_HISTORY: dict[str, list[dict[str, str]]] = {}


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
    PROVISIONED[req.subdomain] = data
    return ProvisionResponse(**data)


@app.delete("/provision/{subdomain}")
def delete_provision(subdomain: str) -> dict[str, str]:
    try:
        info = PROVISIONED.pop(subdomain)
        cloudflare.delete_access_app(info["access_app_id"])
        cloudflare.delete_dns_record(info["dns_record_id"])
        cloudflare.delete_tunnel(info["tunnel_id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"status": "deleted"}


@app.get("/history/{subdomain}")
def history(subdomain: str) -> list[dict[str, str]]:
    """Return login history for a subdomain."""
    return LOGIN_HISTORY.get(subdomain, [])


@app.post("/rotate-key/{subdomain}")
def rotate_key(subdomain: str) -> dict[str, str]:
    """Rotate SSH host key for the given subdomain."""
    if subdomain not in PROVISIONED:
        raise HTTPException(status_code=404, detail="unknown subdomain")
    # Placeholder for real rotation logic
    return {"status": "rotated"}


def main() -> None:
    import uvicorn

    uvicorn.run("sshclaude.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
