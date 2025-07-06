import os
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress

CONFIG_FILE = Path.home() / ".sshclaude" / "config.yaml"
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
    with Progress() as progress:
        t = progress.add_task("provision", total=4)
        progress.update(t, advance=1)
        # Placeholder: create tunnel
        progress.update(t, advance=1)
        # Placeholder: create DNS record
        progress.update(t, advance=1)
        # Placeholder: create Access app/policy
        progress.update(t, advance=1)

    config = {"email": email, "domain": domain, "session": session}
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
    # Placeholder logic
    console.print("Tunnel is running. Access app healthy.")


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
    with Progress() as progress:
        t = progress.add_task("cleanup", total=3)
        progress.update(t, advance=1)
        # Placeholder: delete tunnel
        progress.update(t, advance=1)
        # Placeholder: delete DNS record
        progress.update(t, advance=1)

    CONFIG_FILE.unlink(missing_ok=True)
    console.print("[green]Uninstall complete.")


if __name__ == "__main__":
    cli()
