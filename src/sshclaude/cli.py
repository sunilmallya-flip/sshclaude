import os
import subprocess
from pathlib import Path

import click
import shutil
import requests
from rich.console import Console
from rich.progress import Progress

CONFIG_FILE = Path.home() / ".sshclaude" / "config.yaml"
LAUNCHER_FILE = Path.home() / ".sshclaude" / "launch_claude.sh"
PLIST_FILE = Path.home() / "Library/LaunchAgents" / "com.sshclaude.tunnel.plist"
API_URL = os.getenv("SSHCLAUDE_API", "http://localhost:8000")
console = Console()


def ensure_config_dir():
    (CONFIG_FILE.parent).mkdir(parents=True, exist_ok=True)


def install_ttyd():
    """Install ttyd via Homebrew if not already installed."""
    if shutil.which("ttyd"):
        console.print("[green]ttyd already installed.")
        return

    console.print("[bold]Installing ttyd via Homebrew...")
    subprocess.run(
        ["env", "HOMEBREW_NO_AUTO_UPDATE=1", "brew", "install", "ttyd"],
        check=False
    )


def install_cloudflared():
    """Install cloudflared via Homebrew if not already installed."""
    if shutil.which("cloudflared"):
        console.print("[green]cloudflared already installed.")
        return

    console.print("[bold]Installing cloudflared via Homebrew...")
    subprocess.run(
        ["env", "HOMEBREW_NO_AUTO_UPDATE=1", "brew", "install", "cloudflared"],
        check=False
    )


def write_launcher() -> None:
    """Create a launcher script that runs Claude via ttyd."""
    ensure_config_dir()
    script = "#!/bin/bash\nexec ttyd --once $(which claude)\n"
    LAUNCHER_FILE.write_text(script)
    LAUNCHER_FILE.chmod(0o755)


def write_tunnel_files(subdomain: str, token: str) -> None:
    """Write cloudflared token and config files."""
    import json

    cf_dir = Path.home() / ".cloudflared"
    cf_dir.mkdir(parents=True, exist_ok=True)
    (cf_dir / "token.json").write_text(json.dumps({"tunnel_token": token}))
    config = f"tunnel: {subdomain}\ncredentials-file: {cf_dir/'token.json'}\n"
    (cf_dir / "config.yml").write_text(config)


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
    subprocess.run(["launchctl", "load", str(PLIST_FILE)], check=False)


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
@click.option("--github", required=True, help="Your GitHub login for SSO")
@click.option("--domain", help="Custom domain if not using default")
@click.option("--session", default="15m", help="Session TTL")
def init(github: str, domain: str | None, session: str):
    """Bootstrap Cloudflare Tunnel and Access app."""

    config = read_config()
    if config:
        console.print("[yellow]sshclaude already initialized.")
        return

    install_cloudflared()
    install_ttyd()

    console.print("[bold]Creating Cloudflare tunnel and access application...")
    subdomain = domain or f"{os.getlogin()}.sshclaude.com"
    with Progress() as progress:
        t = progress.add_task("provision", total=5)
        progress.update(t, advance=1)
        try:
            resp = requests.post(
                f"{API_URL}/provision",
                json={"github_id": github, "subdomain": subdomain},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # requests.exceptions.RequestException
            console.print(f"[red]Provisioning failed: {e}")
            return
        progress.update(t, advance=3)

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
    """Show tunnel and Access health."""
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


@cli.command(name="rotate-key")
def rotate_key():
    """Regenerate SSH host key and update Access."""
    config = read_config()
    if not config:
        console.print("[red]sshclaude not initialized.")
        return
    console.print("[bold]Rotating SSH host key...")
    subprocess.run(["ssh-keygen", "-f", str(Path.home() / ".ssh" / "sshclaude"), "-N", ""], check=False)
    subdomain = config.get("domain")
    try:
        resp = requests.post(f"{API_URL}/rotate-key/{subdomain}", timeout=30)
        resp.raise_for_status()
        console.print("[green]Host key rotated.")
    except Exception as e:
        console.print(f"[red]Failed to notify server: {e}")


@cli.command()
def uninstall():
    """Remove tunnel, launchd service, and DNS."""
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
            resp = requests.delete(
                f"{API_URL}/provision/{subdomain}", timeout=30
            )
            if resp.status_code != 200:
                console.print(f"[red]Delete failed: {resp.text}")
                return
        except Exception as e:
            console.print(f"[red]Failed to delete resources: {e}")
            return
        progress.update(t, advance=2)

    subprocess.run(["launchctl", "unload", str(PLIST_FILE)], check=False)
    PLIST_FILE.unlink(missing_ok=True)
    LAUNCHER_FILE.unlink(missing_ok=True)
    CONFIG_FILE.unlink(missing_ok=True)
    console.print("[green]Uninstall complete.")


if __name__ == "__main__":
    cli()
