import os
import subprocess
import time
import webbrowser
from pathlib import Path

import click
import shutil
import requests
from rich.console import Console
from rich.progress import Progress

CONFIG_FILE = Path.home() / ".sshclaude" / "config.yaml"
LAUNCHER_FILE = Path.home() / ".sshclaude" / "launch_claude.sh"
PLIST_FILE = Path.home() / "Library/LaunchAgents" / "com.sshclaude.tunnel.plist"
API_URL = os.getenv("SSHCLAUDE_API", "https://api.sshclaude.dev")
console = Console()


def ensure_config_dir():
    (CONFIG_FILE.parent).mkdir(parents=True, exist_ok=True)


def install_ttyd():
    if shutil.which("ttyd"):
        console.print("[green]ttyd already installed.")
        return
    console.print("[bold]Installing ttyd via Homebrew...")
    subprocess.run(["env", "HOMEBREW_NO_AUTO_UPDATE=1", "brew", "install", "ttyd"], check=False)


def install_cloudflared():
    if shutil.which("cloudflared"):
        console.print("[green]cloudflared already installed.")
        return
    console.print("[bold]Installing cloudflared via Homebrew...")
    subprocess.run(["env", "HOMEBREW_NO_AUTO_UPDATE=1", "brew", "install", "cloudflared"], check=False)


def write_launcher() -> None:
    ensure_config_dir()
    script = "#!/bin/bash\nexec ttyd --once $(which claude)\n"
    LAUNCHER_FILE.write_text(script)
    LAUNCHER_FILE.chmod(0o755)


def write_tunnel_files(subdomain: str, token: str) -> None:
    import json
    cf_dir = Path.home() / ".cloudflared"
    cf_dir.mkdir(parents=True, exist_ok=True)
    (cf_dir / "token.json").write_text(json.dumps({"tunnel_token": token}))
    config = f"tunnel: {subdomain}\ncredentials-file: {cf_dir/'token.json'}\n"
    (cf_dir / "config.yml").write_text(config)


def _launchctl(action: str, plist: Path) -> None:
    """Run launchctl commands in the user domain if available."""
    if not shutil.which("launchctl"):
        return
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", action, domain, str(plist)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def write_plist(token: str) -> None:
    PLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE plist PUBLIC '-//Apple//DTD PLIST 1.0//EN' 'http://www.apple.com/DTDs/PropertyList-1.0.dtd'>
<plist version='1.0'>
<dict>
    <key>Label</key>
    <string>com.sshclaude.tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/cloudflared</string>
        <string>tunnel</string>
        <string>run</string>
        <string>--token</string>
        <string>{token}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    PLIST_FILE.write_text(plist)
    _launchctl("bootout", PLIST_FILE)
    _launchctl("bootstrap", PLIST_FILE)


def write_config(data: dict):
    import yaml
    ensure_config_dir()
    with CONFIG_FILE.open("w") as f:
        yaml.safe_dump(data, f)


def read_config() -> dict:
    import yaml
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open() as f:
            return yaml.safe_load(f) or {}
    return {}


@click.group()
def cli():
    """sshclaude command line interface."""

@cli.command()
@click.option("--github", required=True, help="Your GitHub login (used for display only)")
@click.option("--domain", help="Subdomain to use (default: <user>.sshclaude.com)")
@click.option("--session", default="15m", help="Session TTL for Access")
def init(github: str, domain: str | None, session: str):
    """Initialize a Claude tunnel after verifying GitHub identity."""

    console.print("[blue]sshclaude init started")

    config = read_config()
    if config:
        console.print("[yellow]Existing configuration found - reusing token.")
        subdomain = config.get("domain")
        token = config.get("tunnel_token")
        if not subdomain or not token:
            console.print("[red]Configuration incomplete. Remove ~/.sshclaude and re-run init.")
            return
        write_tunnel_files(subdomain, token)
        write_launcher()
        write_plist(token)
        console.print(f"[green]sshclaude started at https://{subdomain}")
        return

    install_cloudflared()
    install_ttyd()

    console.print("[bold]Verifying GitHub identity via browser login...")
    console.print(f"[cyan]Calling: {API_URL}/login")
    try:
        resp = requests.post(f"{API_URL}/login", timeout=10)
        resp.raise_for_status()
        login = resp.json()
        client_id = login["client_id"]
    except Exception as e:
        console.print(f"[red]Failed to initiate login: {e}")
        return

    uid = login["url"].split("/")[-1]
    token = login["token"]

    import base64
    import json

    state_obj = {"uid": uid, "token": token}
    state = base64.urlsafe_b64encode(json.dumps(state_obj).encode()).decode()

    login_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri=https://api.sshclaude.dev/oauth/callback"
        f"&state={state}"
        f"&allow_signup=false"
        f"&scope=user:email"
    )

    webbrowser.open(login_url)
    console.print(f"[cyan]Waiting for verification... (or open {login_url} manually)")

    for _ in range(60):
        time.sleep(2)
        try:
            check = requests.get(f"{API_URL}/login/{uid}/status", timeout=5).json()
            if check.get("verified"):
                console.print("[green]GitHub identity verified.")
                break
        except Exception:
            pass
    else:
        console.print("[red]Verification timed out.")
        return

    # 🔐 Fetch verified email
    try:
        userinfo = requests.get(
            f"{API_URL}/login/{uid}/whoami",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        userinfo.raise_for_status()
        verified_email = userinfo.json().get("email")
        if not verified_email:
            console.print("[red]Server did not return a verified email.")
            return
        console.print(f"[green]Verified email: {verified_email}")
    except Exception as e:
        console.print(f"[red]Failed to fetch verified email: {e}")
        return

    subdomain = domain or f"{os.getlogin()}.sshclaude.com"
    console.print("[bold]Provisioning tunnel and access policy...")

    try:
        resp = requests.post(
            f"{API_URL}/provision",
            json={
                "github_id": github,
                "email": verified_email,
                "subdomain": subdomain
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Provisioning failed: {e}")
        return

    config = {
        "github_id": github,
        "domain": subdomain,
        "session": session,
        "tunnel_id": data.get("tunnel_id"),
        "tunnel_token": data.get("tunnel_token"),
        "dns_record_id": data.get("dns_record_id"),
        "access_app_id": data.get("access_app_id"),
    }

    write_config(config)
    write_tunnel_files(subdomain, config["tunnel_token"])
    write_launcher()
    write_plist(config["tunnel_token"])
    console.print("[green]Initialization complete!")


@cli.command()
def status():
    config = read_config()
    if not config:
        console.print("[red]sshclaude not initialized.")
        return
    console.print("[bold]Checking tunnel status...")
    subdomain = config.get("domain")
    try:
        resp = requests.get(f"{API_URL}/provision/{subdomain}", timeout=15)
        if resp.status_code == 200:
            console.print("Tunnel is running. Access app healthy.")
        else:
            console.print("[red]Provision not found on server.")
    except Exception as e:
        console.print(f"[red]Failed to query status: {e}")


@cli.command()
def uninstall():
    config = read_config()
    if not config:
        console.print("[red]sshclaude not initialized.")
        return
    console.print("[bold]Removing Cloudflare resources...")
    subdomain = config.get("domain")
    with Progress() as progress:
        t = progress.add_task("cleanup", total=3)
        progress.update(t, advance=1)
        try:
            resp = requests.delete(f"{API_URL}/provision/{subdomain}", timeout=30)
            if resp.status_code != 200:
                console.print(f"[red]Delete failed: {resp.text}")
                return
        except Exception as e:
            console.print(f"[red]Failed to delete resources: {e}")
            return
        progress.update(t, advance=2)

    _launchctl("bootout", PLIST_FILE)
    PLIST_FILE.unlink(missing_ok=True)
    LAUNCHER_FILE.unlink(missing_ok=True)
    CONFIG_FILE.unlink(missing_ok=True)
    console.print("[green]Uninstall complete.")

@cli.command(name="refresh-token")
def refresh_token():
    """Refresh Cloudflare tunnel token and update local config."""
    config = read_config()
    if not config:
        console.print("[red]sshclaude is not initialized.")
        return

    subdomain = config.get("domain")
    console.print(f"[bold]Refreshing tunnel token for {subdomain}...")

    try:
        resp = requests.post(f"{API_URL}/rotate-key/{subdomain}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        new_token = data.get("tunnel_token")
        if not new_token:
            console.print("[red]No token returned from server.")
            return
    except Exception as e:
        console.print(f"[red]Failed to refresh token: {e}")
        return

    # Update config and files
    config["tunnel_token"] = new_token
    write_config(config)
    write_tunnel_files(subdomain, new_token)

    # Reload tunnel
    _launchctl("bootout", PLIST_FILE)
    write_plist(new_token)
    _launchctl("bootstrap", PLIST_FILE)

    console.print("[green]Tunnel token refreshed successfully.")


if __name__ == "__main__":
    cli()
