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
    resp = requests.delete(
        f"{API_BASE}/tunnels/{tunnel_id}", headers=_headers(), timeout=30
    )
    resp.raise_for_status()


def create_dns_record(subdomain: str, tunnel_id: str) -> dict[str, Any]:
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    if not zone_id:
        raise RuntimeError("CLOUDFLARE_ZONE_ID not set")
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
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    if not zone_id:
        raise RuntimeError("CLOUDFLARE_ZONE_ID not set")
    resp = requests.delete(
        f"{API_BASE}/zones/{zone_id}/dns_records/{record_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()


def create_access_app(email: str, subdomain: str) -> dict[str, Any]:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID not set")
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
            "include": [{"emails": [email]}],
        },
        headers=_headers(),
        timeout=30,
    )
    policy.raise_for_status()
    return app


def delete_access_app(app_id: str) -> None:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID not set")
    resp = requests.delete(
        f"{API_BASE}/accounts/{account_id}/access/apps/{app_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
