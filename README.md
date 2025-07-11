# **SSHCLAUDE** – Secure Claude Terminal in Your Browser

> **Mission** Deliver a zero-trust, browser-accessible Claude CLI with no open ports, no full shell exposure, and bi-directional interaction secured by Cloudflare Tunnel and Access.

---

## 1. What the Project Is About

SSHCLAUDE lets you interact with Claude from any browser without ever exposing a local shell or public ports. It spins up a local Claude CLI wrapped in `ttyd`, then connects that single command to the internet through a short-lived Cloudflare Tunnel gated by Cloudflare Access.

---

## 2. Features

| Capability                  | Details |
| --------------------------- | ------- |
| **Zero-port networking**    | Uses Cloudflare Tunnel to route HTTPS traffic to localhost without exposing public ports. |
| **Browser-based Claude**    | Launches Claude CLI via `ttyd` in a web terminal; not a full shell or SSH session. |
| **Access control**          | Only approved GitHub logins or IPs can access using Cloudflare Access + MFA. |
| **No SSH exposure**         | Runs Claude directly via a CLI wrapper; does not expose bash or shell access. |
| **Launch-once tunnel**      | Uses dashboard-created token to launch tunnel with `cloudflared --token`. |
| **Cloudflare Access gated** | MFA, session TTL, GitHub login or IP-based rules apply before tunnel is reached. |

---

## 3. Architecture

From a user's point of view, everything flows through Cloudflare before touching your local machine:

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

<details>
<summary>Full sequence diagram</summary>

```mermaid
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
```

</details>

---

## 4. How to Get Started

1. `pip install sshclaude`
2. Run `sshclaude init --github <your-login>` and follow the browser login to verify your GitHub account.
3. Visit the printed URL (e.g. `https://<user>.sshclaude.com`) to access Claude securely in your browser.
4. Optional commands:
   * `sshclaude status` – check the tunnel and Access app health
   * `sshclaude refresh-token` – rotate the Cloudflare tunnel token
   * `sshclaude uninstall` – remove all Cloudflare resources and local files

When `sshclaude init` runs it will:

1. Install `cloudflared` and `ttyd` if missing
2. Verify your GitHub identity via the provisioning API
3. Create or reuse the Cloudflare tunnel and Access policy
4. Write a launcher script and LaunchAgent plist
5. Start the tunnel and print the public URL

---

## 5. Protections in the Backend

The `sshclaude.com` provisioning service performs several safety checks before issuing a tunnel token:

| Task                        | Description |
| --------------------------- | ----------- |
| **Tunnel provisioning**     | Use Cloudflare API to create a new tunnel (named or token-based). |
| **DNS routing**             | Create CNAME: `<user>.sshclaude.dev` → `tunnel-id.cfargotunnel.com`. |
| **Access app creation**     | Define a Cloudflare Access application for each tunnel. |
| **Policy enforcement**      | Include only allowed GitHub logins or IPs and enforce MFA. |
| **Token issuance**          | Return connector `*.json` token to the CLI for `cloudflared --token` usage. |
| **Audit tracking**          | Log login attempts, success, session durations, and activity metadata. |
| **Token revocation API**    | Invalidate credentials and remove public hostnames if revoked or uninstalled. |
| **Expiration enforcement**  | Optionally expire tunnels on a TTL (for example, 24 hours unless refreshed). |
| **Multi-tenant separation** | Isolate per-user tunnels, Access apps, and DNS mappings. |

---

## 6. Why Is This Secure?

| Area         | Secured How |
| ------------ | ----------- |
| Shell access | ❌ Not exposed; Claude CLI only. |
| Tunnel auth  | 🔐 Token-based; no need for cert.pem or SSH keys. |
| Session TTL  | ⏱️ Short-lived sessions (e.g., 15 min) enforced by Access. |
| User control | ✅ User runs `ttyd` and Claude locally; nothing runs as root. |

---

## Status

* Claude running locally via ttyd
* Tunnel live via `cloudflared --token`
* Access gated and no shell exposure

You're ready to give this to users or build out the CLI to automate it.
