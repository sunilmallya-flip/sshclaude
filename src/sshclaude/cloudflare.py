"""Simplified Cloudflare API client."""

from __future__ import annotations

import os
from typing import Any

import requests

API_BASE = "https://api.cloudflare.com/client/v4"


def _headers() -> dict[str, str]:
    token = os.getenv("CLOUDFLARE_TOKEN")
    if not token:
        raise RuntimeError("CLOUDFLARE_TOKEN not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_tunnel(name: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_BASE}/tunnels",
        json={"name": name},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_tunnel(tunnel_id: str) -> None:
    resp = requests.delete(f"{API_BASE}/tunnels/{tunnel_id}", headers=_headers(), timeout=30)
    resp.raise_for_status()
