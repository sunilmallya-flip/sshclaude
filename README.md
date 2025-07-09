# **SSHCLAUDE** – Secure Claude Terminal in Your Browser

> **Mission**  Deliver a zero-trust, browser-accessible Claude CLI with no open ports, no full shell exposure, and bi-directional interaction secured by Cloudflare Tunnel and Access.

---

## ✨ Key Features

| Capability                  | Details                                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------------- |
| **Zero-port networking**    | Uses Cloudflare Tunnel to route HTTPS traffic to localhost without exposing public ports. |
| **Browser-based Claude**    | Launches Claude CLI via `ttyd` in a web terminal; not a full shell or SSH session.        |
| **Access control**          | Only specific emails/IPs can access using Cloudflare Access + MFA.                        |
| **No SSH exposure**         | Runs Claude directly via a CLI wrapper; does not expose bash or shell access.             |
| **Launch-once tunnel**      | Uses dashboard-created token to launch tunnel with `cloudflared --token`                  |
| **Cloudflare Access gated** | MFA, session TTL, email or IP-based rules apply before tunnel is reached.                 |

---

## 🧑‍💻 What the End User Does (sshclaude client setup)

> All of this will be fully automated by the `sshclaude` CLI.

### 🔹 Step-by-step (manual for now, automated soon)

1. **Install prerequisites**:

```bash
brew install cloudflared ttyd
pip install sshclaude  # if CLI wrapper is provided
```

2. **Download config from SSHCLAUDE**:

* Receive a `token.json` and a suggested `config.yml`
* Place them in `~/.cloudflared/`

3. **Start Claude securely**:

```bash
ttyd --once /usr/local/bin/claude  # or ./run_claude.sh
```

4. **Run the secure tunnel**:

```bash
cloudflared tunnel run --token $(cat ~/.cloudflared/token.json | jq -r .tunnel_token)
```

5. **Verify it's working**:

* Visit `https://your-name.sshclaude.com` in any browser
* Log in with email + MFA via Cloudflare Access
* Claude CLI is fully interactive in the browser

---

## ⚙️ What the `sshclaude` CLI Will Automate

When a user runs:

```bash
sshclaude init
```

The CLI will:

1. Install or upgrade `cloudflared` and `ttyd`
2. Download and place the correct `token.json` and `config.yml`
3. Write a launcher script to start Claude via `ttyd`
4. Launch `cloudflared` with the proper token
5. Print the public tunnel URL and test connectivity

> The CLI may also support autostart via launchd (macOS), systemd (Linux), or login hook

---

## 🛠 TODO: SSHCLAUDE Server Responsibilities

The `sshclaude.com` provisioning backend will handle:

| Task                        | Description                                                               |
| --------------------------- | ------------------------------------------------------------------------- |
| **Tunnel provisioning**     | Use Cloudflare API to create a new tunnel (named or token-based)          |
| **DNS routing**             | Create CNAME: `<user>.sshclaude.dev` → `tunnel-id.cfargotunnel.com`       |
| **Access app creation**     | Define a Cloudflare Access application for each tunnel                    |
| **Policy enforcement**      | Include only allowed emails or IPs + enforce MFA                          |
| **Token issuance**          | Return connector `*.json` token to CLI for `cloudflared --token` usage    |
| **Audit tracking**          | Log login attempts, success, session durations, and activity metadata     |
| **Token revocation API**    | Invalidate credentials and remove public hostnames if revoked/uninstalled |
| **Expiration enforcement**  | Optionally expire tunnels on TTL (e.g., 24 hours unless refreshed)        |
| **Multi-tenant separation** | Isolate per-user tunnels, Access apps, and DNS mappings                   |

---

## 🛡 Security Summary for End User

| Area         | Secured How                                                 |
| ------------ | ----------------------------------------------------------- |
| Shell access | ❌ Not exposed; Claude CLI only                              |
| Tunnel auth  | 🔐 Token-based; no need for cert.pem or SSH keys            |
| Session TTL  | ⏱️ Short-lived sessions (e.g., 15 min) enforced by Access   |
| User control | ✅ User runs `ttyd` and Claude locally; nothing runs as root |

---

## 🏗 Architecture Overview

```text
Browser (User)
   │
   ▼ HTTPS
Cloudflare Access (SSO + MFA + IP check)
   │
   ▼ TLS + mTLS
Cloudflare Tunnel (cloudflared with token)
   │
   ▼
Local Claude CLI (wrapped in ttyd, single command only)
```

---

## ✅ Status: Confirmed Working

* Claude running locally via ttyd
* Tunnel live via `cloudflared --token`
* Access gated and no shell exposure

You're ready to give this to users or build out the CLI to automate it.
