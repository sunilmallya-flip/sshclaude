"""Simplified Cloudflare API client."""
# SUNIL

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
    print("[DEBUG] Reuse-aware create_tunnel logic is active")

    list_url = f"{ACCOUNT_BASE}/tunnels"
    headers = _headers()

    # Check existing tunnels
    try:
        resp = requests.get(list_url, headers=headers, timeout=30)
        resp.raise_for_status()
        tunnels = resp.json().get("result", [])
        for t in tunnels:
            if t["name"] == name:
                print("[DEBUG] Reusing existing tunnel:", t["id"])
                return {"result": t}  # NO token available here
    except Exception as e:
        print("[ERROR] Failed to list tunnels:", e)
        raise

    # Create tunnel
    payload = {"name": name}
    print("[DEBUG] Creating tunnel:", payload)
    resp = requests.post(list_url, json=payload, headers=headers, timeout=30)
    if not resp.ok:
        print("[CLOUDFLARE ERROR]", resp.status_code, resp.text)
    resp.raise_for_status()

    data = resp.json()
    token = data["result"].get("token")
    if not token:
        raise RuntimeError("Tunnel token missing from create_tunnel response.")

    data["tunnel_token"] = token
    print("[DEBUG] New tunnel created. ID:", data["result"]["id"])
    return data


def create_dns_record(subdomain: str, tunnel_id: str) -> dict[str, Any]:
    headers = _headers()

    zone_name = ".".join(subdomain.split(".")[-2:])
    name = subdomain.replace(f".{zone_name}", "")  # e.g. "ubuntu"

    # Exact match query
    list_url = f"{ZONE_BASE}/dns_records?name={name}&match=all"
    resp = requests.get(list_url, headers=headers, timeout=30)
    resp.raise_for_status()
    records = resp.json().get("result", [])
    print(f"[DEBUG] Existing DNS record query returned: {records}")

    if records:
        # Optional: delete conflicting record
        record = records[0]
        print(f"[DEBUG] Deleting existing DNS record: {record['id']}")
        del_url = f"{ZONE_BASE}/dns_records/{record['id']}"
        del_resp = requests.delete(del_url, headers=headers, timeout=30)
        del_resp.raise_for_status()

    # Now safely create CNAME
    payload = {
        "type": "CNAME",
        "name": name,
        "content": f"{tunnel_id}.cfargotunnel.com",
        "proxied": True,
    }

    print("[DEBUG] Creating DNS record with payload:", payload)

    create_url = f"{ZONE_BASE}/dns_records"
    resp = requests.post(create_url, json=payload, headers=headers, timeout=30)
    print("[DEBUG] Create DNS response:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


def delete_dns_record(record_id: str) -> None:
    url = f"{ZONE_BASE}/dns_records/{record_id}"
    resp = requests.delete(url, headers=_headers(), timeout=30)
    resp.raise_for_status()

def _build_email_rule(address: str) -> dict:
    """
    Return a Cloudflare Access rule that allows a single email address.
    """
    return {
        "email": {          # selector
            "email": address.strip().lower()
        }
    }

def create_access_app(email: str, subdomain: str) -> dict[str, Any]:
    headers = _headers()
    app_url = f"{ACCOUNT_BASE}/access/apps"

    # 1. Reuse existing Access App if it already exists
    try:
        list_resp = requests.get(app_url, headers=headers, timeout=30)
        list_resp.raise_for_status()
        apps = list_resp.json().get("result", [])
        for app in apps:
            if app.get("domain") == subdomain:
                print("[DEBUG] Reusing existing Access App:", app["id"])
                return {"result": app}
    except Exception as e:
        print("[ERROR] Failed to list Access Apps:", e)

    # 2. Create new Access App
    app_payload = {
        "name": subdomain,
        "domain": subdomain,
        "session_duration": "15m",
        "type": "self_hosted",
        "app_launcher_visible": False
    }

    print("[DEBUG] Creating Access App:", app_payload)

    create_resp = requests.post(app_url, json=app_payload, headers=headers, timeout=30)
    print("[DEBUG] Access App creation response:", create_resp.status_code, create_resp.text)

    if not create_resp.ok:
        raise RuntimeError(f"Failed to create Access App: {create_resp.text}")

    app = create_resp.json()
    app_id = app["result"]["id"]

    # 3. Attach access policy using verified GitHub email
    policy_url = f"{ACCOUNT_BASE}/access/apps/{app_id}/policies"

    policy_payload = {
        "name": "default",
        "precedence": 1,
        "decision": "allow",
        "include": [
            _build_email_rule(email)
        ],
        "exclude": [],
        "require": []
    }

    print("[DEBUG] Attaching Access Policy:", policy_payload)

    policy_resp = requests.post(policy_url, json=policy_payload, headers=headers, timeout=30)
    print("[DEBUG] Access Policy response:", policy_resp.status_code, policy_resp.text)

    if not policy_resp.ok:
        raise RuntimeError(f"Failed to attach Access policy: {policy_resp.text}")

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

