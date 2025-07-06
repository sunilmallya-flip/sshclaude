import os
import subprocess
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.progress import Progress

CONFIG_FILE = Path.home() / ".sshclaude" / "config.yaml"
API_URL = os.getenv("SSHCLAUDE_API", "http://localhost:8000")
console = Console()


def ensure_config_dir():
    (CONFIG_FILE.parent).mkdir(parents=True, exist_ok=True)


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


def install_cloudflared():
    """Install or upgrade cloudflared via Homebrew."""
    console.print("[bold]Installing cloudflared via Homebrew...")
    subprocess.run(["brew", "install", "cloudflared"], check=False)


@click.group()
def cli():
    """sshclaude command line interface."""


@cli.command()
@click.option("--email", required=True, help="Your email for SSO")
@click.option("--domain", help="Custom domain if not using default")
@click.option("--session", default="15m", help="Session TTL")
def init(email: str, domain: str | None, session: str):
    """Bootstrap Cloudflare Tunnel and Access app."""

    config = read_config()
    if config:
        console.print("[yellow]sshclaude already initialized.")
        return

    install_cloudflared()

    console.print("[bold]Creating Cloudflare tunnel and access application...")
    subdomain = domain or f"{os.getlogin()}.sshclaude.com"
    with Progress() as progress:
        t = progress.add_task("provision", total=4)
        progress.update(t, advance=1)
        try:
            resp = requests.post(
                f"{API_URL}/provision",
                json={"email": email, "subdomain": subdomain},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # requests.exceptions.RequestException
            console.print(f"[red]Provisioning failed: {e}")
            return
        progress.update(t, advance=3)

    config = {
        "email": email,
        "domain": subdomain,
        "session": session,
        "tunnel_id": data.get("tunnel_id"),
        "dns_record_id": data.get("dns_record_id"),
        "access_app_id": data.get("access_app_id"),
    }
    write_config(config)
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
    console.print("[green]Host key rotated. Update your Access policy accordingly.")


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

    CONFIG_FILE.unlink(missing_ok=True)
    console.print("[green]Uninstall complete.")


if __name__ == "__main__":
    cli()
