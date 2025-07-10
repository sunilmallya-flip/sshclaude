# **SSHCLAUDE** – Secure Claude Terminal in Your Browser

> **Mission**  Deliver a zero-trust, browser-accessible Claude CLI with no open ports, no full shell exposure, and bi-directional interaction secured by Cloudflare Tunnel and Access.

---

## ✨ Key Features

| Capability                  | Details                                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------------- |
| **Zero-port networking**    | Uses Cloudflare Tunnel to route HTTPS traffic to localhost without exposing public ports. |
| **Browser-based Claude**    | Launches Claude CLI via `ttyd` in a web terminal; not a full shell or SSH session.        |
| **Access control**          | Only approved GitHub logins or IPs can access using Cloudflare Access + MFA.              |
| **No SSH exposure**         | Runs Claude directly via a CLI wrapper; does not expose bash or shell access.             |
| **Launch-once tunnel**      | Uses dashboard-created token to launch tunnel with `cloudflared --token`                  |
| **Cloudflare Access gated** | MFA, session TTL, GitHub login or IP-based rules apply before tunnel is reached.          |

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
* Log in with your GitHub account + MFA via Cloudflare Access
* Claude CLI is fully interactive in the browser

---

## ⚙️ What the `sshclaude` CLI Will Automate

When a user runs:

```bash
sshclaude init --github <your-login>
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
| **Policy enforcement**      | Include only allowed GitHub logins or IPs + enforce MFA                   |
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


flowchart TD
    %% ─────────────────────────────────────────
    %%  Legend / groupings
    subgraph LOCAL [Developerʼs laptop]
        CLI[[sshclaude CLI\n(`sshclaude init`)]]
        TTYD[ttyd ⇄ Claude CLI]
        Launchd([cloudflared launchd])
    end

    subgraph API [sshclaude API (api.sshclaude.dev)]
        Login[/POST /login/]
        GitHubCB[/GET /oauth/callback/]
        WhoAmI[/GET /login/{uid}/whoami/]
        Provision[/POST /provision/]
        SQLite[(SQLite DB)]
    end

    subgraph GITHUB [GitHub]
        GHLogin[GitHub OAuth\n(login & consent)]
    end

    subgraph CF_API[Cloudflare API]
        CFTunnel[Tunnel\ncreate/reuse]
        CFDNS[DNS CNAME]
        CFApp[Access App]
        CFPolicy[Policy\n(email rule)]
    end

    subgraph CF_EDGE[Cloudflare Edge]
        CFProxy[cloudflared tunnel\n(wss <--> origin)]
        Access[Cloudflare Access\n(email check)]
    end
    %% ─────────────────────────────────────────
    %%  Flow
    CLI --1️⃣ POST /login --> Login
    Login --session {uid,token,client_id}--> CLI

    CLI --2️⃣ open browser\n(GitHub OAuth URL)--> GHLogin
    GHLogin --code,state--> GitHubCB
    GitHubCB -->|verify email| SQLite
    GitHubCB --> CLI

    CLI --3️⃣ GET /whoami --> WhoAmI
    WhoAmI -->|verified email| CLI

    CLI --4️⃣ POST /provision --> Provision
    Provision --> CFTunnel
    Provision --> CFDNS
    Provision --> CFApp
    CFApp --> CFPolicy
    CFTunnel -->|token| CLI
    Provision --> SQLite

    CLI --5️⃣ write cloudflared\nconfig & plist--> Launchd
    Launchd --> CFProxy

    BrowserUser[(Any browser)] -->|https://<subdomain>.sshclaude.dev| Access
    Access --GitHub login if needed--> GHLogin
    Access --> CFProxy
    CFProxy -->|http://localhost:7681| TTYD
    TTYD --> BrowserUser



## ✅ Status: Confirmed Working

* Claude running locally via ttyd
* Tunnel live via `cloudflared --token`
* Access gated and no shell exposure

You're ready to give this to users or build out the CLI to automate it.
