"""Simplified Cloudflare API client."""

from __future__ import annotations

import os
import secrets
from typing import Any
import requests


class MissingEnvError(RuntimeError):
    """Raised when a required environment variable is missing."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingEnvError(f"Environment variable {name} is required but not set")
    return value

API_BASE = "https://api.cloudflare.com/client/v4"


def _headers() -> dict[str, str]:
    token = _require_env("CLOUDFLARE_TOKEN")
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
    resp = requests.delete(
        f"{API_BASE}/tunnels/{tunnel_id}", headers=_headers(), timeout=30
    )
    resp.raise_for_status()


def create_dns_record(subdomain: str, tunnel_id: str) -> dict[str, Any]:
    zone_id = _require_env("CLOUDFLARE_ZONE_ID")
    resp = requests.post(
        f"{API_BASE}/zones/{zone_id}/dns_records",
        json={
            "type": "CNAME",
            "name": subdomain,
            "content": f"{tunnel_id}.cfargotunnel.com",
        },
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def delete_dns_record(record_id: str) -> None:
    zone_id = _require_env("CLOUDFLARE_ZONE_ID")
    resp = requests.delete(
        f"{API_BASE}/zones/{zone_id}/dns_records/{record_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()


def create_access_app(login: str, subdomain: str) -> dict[str, Any]:
    account_id = _require_env("CLOUDFLARE_ACCOUNT_ID")
    resp = requests.post(
        f"{API_BASE}/accounts/{account_id}/access/apps",
        json={
            "name": subdomain,
            "domain": f"{subdomain}",
            "session_duration": "15m",
            "type": "ssh",
        },
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    app = resp.json()
    policy = requests.post(
        f"{API_BASE}/accounts/{account_id}/access/apps/{app['result']['id']}/policies",
        json={
            "name": "default",
            "decision": "allow",
            # In a real implementation this would reference the GitHub identity
            # provider. We model it as a rule keyed by login name.
            "include": [{"github": [login]}],
        },
        headers=_headers(),
        timeout=30,
    )
    policy.raise_for_status()
    return app


def delete_access_app(app_id: str) -> None:
    account_id = _require_env("CLOUDFLARE_ACCOUNT_ID")
    resp = requests.delete(
        f"{API_BASE}/accounts/{account_id}/access/apps/{app_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()


def rotate_host_key(tunnel_id: str) -> None:
    """Trigger host key rotation via Cloudflare API."""
    resp = requests.post(
        f"{API_BASE}/tunnels/{tunnel_id}/hostkey/rotate",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()


def generate_tunnel_token(tunnel_id: str) -> str:
    """Return a new connector token for the tunnel."""
    # Real implementation would call Cloudflare API. Here we stub it.
    return secrets.token_urlsafe(32)
