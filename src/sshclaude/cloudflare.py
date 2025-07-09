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


ACCOUNT_ID = _require_env("CLOUDFLARE_ACCOUNT_ID")
ZONE_ID = _require_env("CLOUDFLARE_ZONE_ID")

# Base URLs
ACCOUNT_BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
ZONE_BASE = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['CLOUDFLARE_TOKEN']}",
        "Content-Type": "application/json",
    }


def create_tunnel(name: str) -> dict[str, Any]:
    url = f"{ACCOUNT_BASE}/tunnels"
    payload = {"name": name}
    print("[DEBUG] Creating tunnel:", payload)
    resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
    if not resp.ok:
        print("[CLOUDFLARE ERROR]", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


def delete_tunnel(tunnel_id: str) -> None:
    url = f"{ACCOUNT_BASE}/tunnels/{tunnel_id}"
    resp = requests.delete(url, headers=_headers(), timeout=30)
    resp.raise_for_status()


def create_dns_record(subdomain: str, tunnel_id: str) -> dict[str, Any]:
    name = subdomain.split(".")[0]

    payload = {
        "type": "CNAME",
        "name": name,
        "content": f"{tunnel_id}.cfargotunnel.com",
        "proxied": True,
    }

    print("[DEBUG] Creating DNS record with payload:", payload)

    resp = requests.post(
        f"{ZONE_BASE}/dns_records",
        json=payload,
        headers=_headers(),
        timeout=30,
    )
    if not resp.ok:
        print("[CLOUDFLARE ERROR]", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


def delete_dns_record(record_id: str) -> None:
    url = f"{ZONE_BASE}/dns_records/{record_id}"
    resp = requests.delete(url, headers=_headers(), timeout=30)
    resp.raise_for_status()


def create_access_app(login: str, subdomain: str) -> dict[str, Any]:
    app_url = f"{ACCOUNT_BASE}/access/apps"

    app_payload = {
        "name": subdomain,
        "domain": subdomain,
        "session_duration": "15m",
        "type": "ssh",
    }

    print("[DEBUG] Creating Access App:", app_payload)

    resp = requests.post(app_url, json=app_payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    app = resp.json()

    policy_url = f"{ACCOUNT_BASE}/access/apps/{app['result']['id']}/policies"
    policy_payload = {
        "name": "default",
        "decision": "allow",
        "include": [{"github": [login]}],
    }

    print("[DEBUG] Attaching Access Policy:", policy_payload)

    policy = requests.post(policy_url, json=policy_payload, headers=_headers(), timeout=30)
    policy.raise_for_status()

    return app


def delete_access_app(app_id: str) -> None:
    url = f"{ACCOUNT_BASE}/access/apps/{app_id}"
    resp = requests.delete(url, headers=_headers(), timeout=30)
    resp.raise_for_status()


def rotate_host_key(tunnel_id: str) -> None:
    """Trigger host key rotation via Cloudflare API."""
    url = f"{ACCOUNT_BASE}/tunnels/{tunnel_id}/hostkey/rotate"
    resp = requests.post(url, headers=_headers(), timeout=30)
    resp.raise_for_status()


def generate_tunnel_token(tunnel_id: str) -> str:
    """Return a new connector token for the tunnel."""
    # Replace this stub with real tunnel token creation API if needed
    return secrets.token_urlsafe(32)

