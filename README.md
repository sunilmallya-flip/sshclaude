# **SSHCLAUDE** – Zero‑Install Browser SSH for Humans

> **Mission**  Deliver a dead‑simple, zero‑trust path into your Mac’s Bash prompt—visible in **any mobile browser**, protected by SSO + MFA/Face ID, with *one* command: `pip install sshclaude`.

---

## ✨ Key Features

| Capability               | Details                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| **One‑line setup**       | `pip install sshclaude && sshclaude init` → we bootstrap Cloudflare Tunnel, Access app, and DNS. |
| **Personal sub‑domain**  | Auto‑provisioned as `<user>.sshclaude.com` (or bring‑your‑own domain via flag).                  |
| **Browser‑rendered SSH** | Uses Cloudflare’s Web‑SSH so Safari/Chrome behaves like Termius — no mobile app.                 |
| **Strong auth**          | SSO to your IdP ➟ MFA ➟ optional Face ID via Cloudflare One/WARP posture checks.                 |
| **Zero open ports**      | Outbound `cloudflared` only; Mac firewall stays shut.                                            |
| **SaaS control‑plane**   | sshclaude.com API owns all Cloudflare objects; users never touch API tokens.                     |

---

## 🏗 High‑Level Architecture

```text
┌─────────────┐  HTTPS   ┌──────────────┐   mTLS   ┌────────────┐
│   iPhone    │◀────────▶│ Cloudflare POP│◀────────▶│  Mac (SSH) │
└─────────────┘          └──────────────┘           └────────────┘
       ▲                        ▲                          ▲
       │                        │                          │
  Face ID / MFA          Access App                cloudflared
       │                        │                          │
       ▼                        ▼                          ▼
            ┌──────────────── sshclaude SaaS ─────────────┐
            │  DNS + Access + Tunnel Provisioning API     │
            └──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install CLI

```bash
pip install sshclaude        # Requires Python ≥3.9 on macOS
```

### 2. Initialize (one‑time)

```bash
sshclaude init --email you@corp.com
```

*Prompts you for:*

* Cloudflare sign‑in (OAuth device flow)
* Desired sub‑domain (press Enter for default `<user>.sshclaude.com`)
* SSH username (defaults to macOS short name)

Behind the scenes we:

1. Install/upgrade **cloudflared** via Homebrew.
2. Generate & store a short‑lived service token with least‑priv perms.
3. Create **Tunnel**, **DNS CNAME**, **Access app**, and **policy** bound to your email.
4. Write & start a `launchd` plist so the connector survives reboots.

### 3. Connect from phone

Open **https\://\<user>.sshclaude.com** in Safari → SSO prompt → MFA / Face ID → streaming Bash shell appears.

> Tip: run `tmux` on the Mac so sessions persist if the phone sleeps.

---

## 🔒 Security Model

* **Zero Trust**: every request evaluated by Cloudflare Access before TCP handshake.
* **E2E encryption**: TLS 1.3 iPhone↟Cloudflare; mTLS Cloudflare↟Mac.
* **Key‑only SSH**: during `init` we disable password auth (`sshd_config`).
* **Session TTL**: default 15 min; configurable via `--session 5m|1h`.
* **Auditing**: all logins visible in sshclaude.com dashboard (user, IP, duration).

---

## 🧩 Components

| Component            | Language      | Responsibility                                    |
| -------------------- | ------------- | ------------------------------------------------- |
| **sshclaude‑cli**    | Python        | Local installer, daemon bootstrap, local UX.      |
| **Provisioning API** | Node + tRPC   | Orbit on sshclaude.com; calls Cloudflare REST.    |
| **State store**      | Postgres      | Maps user→sub‑domain→tunnel ID.                   |
| **Web Console**      | React/Next.js | Shows login history, rotate keys, delete service. |

---

## ⚙️ CLI Commands (draft)

```bash
sshclaude init [--email] [--domain] [--session]
sshclaude status         # Show tunnel + Access health
sshclaude rotate-key     # Regenerate SSH host key & update Access
sshclaude uninstall      # Remove tunnel + launchd service + DNS
```

---

## 📦 Python Package Details

* Published as **sshclaude** on PyPI.
* Pure‑Py + `rich` for TUI, depends on `click`, `pyyaml`, `requests`, `tqdm`.
* Wheels for macOS arm64/x86; falls back to source install.

---

## 🛠 Development

1. `git clone` & `make dev` (uses Poetry + pre‑commit).
2. `.env.example` → `.env` and add Cloudflare API token for staging zone.
3. Run local tunnel e2e with `make e2e` (uses ngrok for callback stubs).

---

## 🤝 Contributing

PRs welcome! Please file an issue first if you plan large changes.  All code under **MIT license**.

---

## © 2025 **SSHCLAUDE Inc.**  All rights reserved.
