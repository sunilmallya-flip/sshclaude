import os
import uuid
import requests

API_URL = os.environ.get("SSHCLAUDE_API", "http://localhost:8000")
API_TOKEN = os.environ.get("API_TOKEN")
TEST_DOMAIN = os.environ.get("TEST_DOMAIN")
GITHUB_ID = os.environ.get("GITHUB_ID", "test-user")

if not TEST_DOMAIN:
    raise SystemExit("TEST_DOMAIN environment variable required")

headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}


def expect_status(resp, code):
    if resp.status_code != code:
        raise SystemExit(f"{resp.request.method} {resp.request.url} -> {resp.status_code} {resp.text}")


def main():
    subdomain = f"test-{uuid.uuid4().hex[:8]}.{TEST_DOMAIN}"
    print("Testing with subdomain", subdomain)

    # Login flow
    resp = requests.post(f"{API_URL}/login")
    expect_status(resp, 200)
    data = resp.json()
    uid = data["url"].split("/")[-1]
    token = data["token"]

    resp = requests.get(f"{API_URL}/login/{uid}/status")
    expect_status(resp, 200)
    assert resp.json() == {"verified": False}

    resp = requests.post(f"{API_URL}/login/{uid}", json={"token": "wrong"})
    assert resp.status_code == 400

    resp = requests.post(f"{API_URL}/login/{uid}", json={"token": token})
    expect_status(resp, 200)

    resp = requests.get(f"{API_URL}/login/{uid}/status")
    expect_status(resp, 200)
    assert resp.json() == {"verified": True}

    # Provision
    resp = requests.post(
        f"{API_URL}/provision",
        json={"github_id": GITHUB_ID, "subdomain": subdomain},
        headers=headers,
    )
    expect_status(resp, 200)
    provision = resp.json()
    print("Provision created", provision)

    # Fetch provision
    resp = requests.get(f"{API_URL}/provision/{subdomain}", headers=headers)
    expect_status(resp, 200)

    # Rotate host key
    resp = requests.post(f"{API_URL}/rotate-key/{subdomain}", headers=headers)
    expect_status(resp, 200)

    # Record login
    resp = requests.post(
        f"{API_URL}/record-login/{subdomain}",
        json={"user": GITHUB_ID, "ip": "127.0.0.1"},
        headers=headers,
    )
    expect_status(resp, 200)

    # History
    resp = requests.get(f"{API_URL}/history/{subdomain}", headers=headers)
    expect_status(resp, 200)
    print("History entries", resp.json())

    # Delete provision
    resp = requests.delete(f"{API_URL}/provision/{subdomain}", headers=headers)
    expect_status(resp, 200)

    resp = requests.get(f"{API_URL}/provision/{subdomain}", headers=headers)
    assert resp.status_code == 404

    print("All API endpoints succeeded")


if __name__ == "__main__":
    main()
