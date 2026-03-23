"""CLI entry point using click."""

from __future__ import annotations

import os
import sys
import warnings
import click

# Suppress asyncio ResourceWarnings on Windows (unclosed subprocess transports
# during garbage collection at exit — harmless but noisy).
warnings.filterwarnings("ignore", category=ResourceWarning)

# On Windows, prevent ALL subprocess calls from opening visible console windows.
# This patches subprocess.Popen to always include CREATE_NO_WINDOW.
if sys.platform == "win32":
    import subprocess as _sp
    _orig_popen_init = _sp.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):  # type: ignore
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)

    _sp.Popen.__init__ = _patched_popen_init  # type: ignore

from clawdia.app import ClawdiaApp
from clawdia.config import Config


@click.group(invoke_without_command=True)
@click.option("--continue", "continue_session", is_flag=True, help="Resume the most recent session")
@click.option("--session", "session_id", default=None, help="Resume a specific session by ID")
@click.version_option(package_name="clawdia")
@click.pass_context
def main(ctx, continue_session: bool, session_id: str | None) -> None:
    """Clawdia — WhatsApp-style TUI for Claude CLI."""
    if ctx.invoked_subcommand is not None:
        return

    config = Config.load()

    resume_id = session_id
    if continue_session and not resume_id:
        # Find the most recent session
        from clawdia.store import Store
        store = Store(config.db_path)
        sessions = store.list_sessions()
        store.close()
        if sessions:
            resume_id = sessions[0].id

    app = ClawdiaApp(config=config, resume_session_id=resume_id)
    app.run()

    # Suppress noisy asyncio tracebacks on Windows during cleanup
    if sys.platform == "win32":
        try:
            sys.stderr = open(os.devnull, "w")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# clawdia tunnel ...
# ---------------------------------------------------------------------------

@main.group()
def tunnel():
    """Manage named Cloudflare tunnel for stable group chat URLs."""


@tunnel.command()
@click.argument("hostname")
@click.option("--name", "tunnel_name", default="clawdia-relay", show_default=True,
              help="Name for the Cloudflare tunnel")
def setup(hostname: str, tunnel_name: str) -> None:
    """Set up a named tunnel for permanent group chat URLs.

    HOSTNAME is the subdomain to route, e.g. relay.yourdomain.com.
    The domain must already be on Cloudflare DNS.

    This is a one-time interactive setup that:

    \b
      1. Logs in to Cloudflare (opens browser)
      2. Creates a named tunnel
      3. Routes DNS from HOSTNAME to the tunnel
      4. Saves config so the daemon uses this tunnel automatically
    """
    from clawdia.relay.tunnel import (
        has_cloudflared, is_logged_in, tunnel_exists,
        create_tunnel, route_dns, generate_tunnel_config,
        _find_credentials_file,
    )

    config = Config.load()

    # Step 1: Check cloudflared
    if not has_cloudflared():
        click.secho("cloudflared not found on PATH.", fg="red")
        click.echo("Install it first:")
        click.echo("  macOS:   brew install cloudflared")
        click.echo("  Windows: winget install cloudflare.cloudflared")
        click.echo("  Linux:   sudo apt install cloudflared")
        raise SystemExit(1)

    click.secho("cloudflared found.", fg="green")

    # Step 2: Check/run login
    if not is_logged_in():
        click.echo("\nOpening browser for Cloudflare authentication...")
        click.echo("(Authorize the domain you want to use for the tunnel)")
        import subprocess
        result = subprocess.run(["cloudflared", "tunnel", "login"])
        if result.returncode != 0:
            click.secho("Login failed or was cancelled.", fg="red")
            raise SystemExit(1)
        if not is_logged_in():
            click.secho("Login did not complete — cert.pem not found.", fg="red")
            raise SystemExit(1)

    click.secho("Cloudflare authenticated.", fg="green")

    # Step 3: Create tunnel (or reuse existing)
    existing_uuid = tunnel_exists(tunnel_name)
    if existing_uuid:
        click.echo(f"\nTunnel '{tunnel_name}' already exists (UUID: {existing_uuid[:8]}...)")
        if not click.confirm("Reuse this tunnel?", default=True):
            click.echo("Aborting. Delete it first with: clawdia tunnel teardown")
            raise SystemExit(1)
        uuid = existing_uuid
        creds = _find_credentials_file(uuid)
        if creds is None:
            click.secho(
                f"Credentials file not found for {uuid}. "
                f"Delete and recreate: clawdia tunnel teardown && clawdia tunnel setup {hostname}",
                fg="red",
            )
            raise SystemExit(1)
    else:
        click.echo(f"\nCreating tunnel '{tunnel_name}'...")
        try:
            uuid, creds = create_tunnel(tunnel_name)
        except RuntimeError as exc:
            click.secho(str(exc), fg="red")
            raise SystemExit(1)
        click.secho(f"Tunnel created (UUID: {uuid[:8]}...)", fg="green")

    # Step 4: Route DNS
    click.echo(f"\nRouting {hostname} -> tunnel '{tunnel_name}'...")
    try:
        route_dns(tunnel_name, hostname)
    except RuntimeError as exc:
        click.secho(str(exc), fg="red")
        click.echo("Make sure the domain is on Cloudflare DNS.")
        raise SystemExit(1)
    click.secho(f"DNS routed: {hostname} -> {tunnel_name}", fg="green")

    # Step 5: Generate cloudflared config
    generate_tunnel_config(
        data_dir=config.data_dir,
        tunnel_uuid=uuid,
        credentials_file=creds,
        hostname=hostname,
        port=config.relay_port,
    )

    # Step 6: Save to config.toml
    config.tunnel_name = tunnel_name
    config.tunnel_uuid = uuid
    config.tunnel_hostname = hostname
    config.save()

    click.echo("")
    click.secho("Named tunnel configured!", fg="green", bold=True)
    click.echo(f"  Tunnel:   {tunnel_name}")
    click.echo(f"  Hostname: {hostname}")
    click.echo(f"  URL:      wss://{hostname}")
    click.echo("")
    click.echo("The relay daemon will use this tunnel automatically.")
    click.echo("Group chat connection strings will now use a permanent URL.")


@tunnel.command()
def status() -> None:
    """Show named tunnel configuration and status."""
    from clawdia.relay.tunnel import has_cloudflared, get_tunnel_url, _pid_alive
    from clawdia.relay.daemon import get_daemon_info

    config = Config.load()

    click.echo("Named Tunnel Status")
    click.echo("=" * 40)

    if not config.tunnel_hostname:
        click.echo("No named tunnel configured.")
        click.echo("Run: clawdia tunnel setup <hostname>")
        return

    click.echo(f"  Name:     {config.tunnel_name}")
    click.echo(f"  UUID:     {config.tunnel_uuid}")
    click.echo(f"  Hostname: {config.tunnel_hostname}")
    click.echo(f"  URL:      wss://{config.tunnel_hostname}")

    # Check process status
    info = get_daemon_info(config.data_dir)
    tunnel_pid = info.get("tunnel_pid") if info else None
    if tunnel_pid and _pid_alive(tunnel_pid):
        click.secho(f"  Process:  running (PID {tunnel_pid})", fg="green")
    else:
        click.secho("  Process:  not running", fg="yellow")
        click.echo("  (Starts automatically with the relay daemon)")

    # Check daemon
    daemon_pid = info.get("pid") if info else None
    if daemon_pid and _pid_alive(daemon_pid):
        click.secho(f"  Daemon:   running (PID {daemon_pid})", fg="green")
    else:
        click.secho("  Daemon:   not running", fg="yellow")


@tunnel.command()
def teardown() -> None:
    """Remove the named tunnel and revert to quick tunnels."""
    from clawdia.relay.tunnel import (
        has_cloudflared, tunnel_exists, delete_tunnel, stop_named_tunnel, _pid_alive,
    )
    from clawdia.relay.daemon import get_daemon_info

    config = Config.load()

    if not config.tunnel_name:
        click.echo("No named tunnel configured. Nothing to do.")
        return

    tunnel_name = config.tunnel_name

    if not click.confirm(
        f"Delete tunnel '{tunnel_name}' and revert to quick tunnels?",
        default=False,
    ):
        click.echo("Cancelled.")
        return

    # Stop running tunnel process
    info = get_daemon_info(config.data_dir)
    tunnel_pid = info.get("tunnel_pid") if info else None
    if tunnel_pid and _pid_alive(tunnel_pid):
        click.echo("Stopping tunnel process...")
        stop_named_tunnel(tunnel_pid)

    # Delete the Cloudflare tunnel
    if has_cloudflared() and tunnel_exists(tunnel_name):
        click.echo(f"Deleting tunnel '{tunnel_name}'...")
        try:
            delete_tunnel(tunnel_name)
            click.secho("Tunnel deleted.", fg="green")
        except RuntimeError as exc:
            click.secho(f"Warning: {exc}", fg="yellow")
            click.echo("You may need to delete it manually: cloudflared tunnel delete " + tunnel_name)

    # Clear config
    config.tunnel_name = None
    config.tunnel_uuid = None
    config.tunnel_hostname = None
    config.save()

    # Clean up daemon info
    if info and "tunnel_pid" in info:
        del info["tunnel_pid"]
        from clawdia.relay.daemon import _write_daemon_info
        _write_daemon_info(config.data_dir, info)

    # Remove config YAML
    cf_config = config.data_dir / "cloudflared-config.yml"
    if cf_config.exists():
        cf_config.unlink()

    click.secho("Named tunnel removed. Group chats will use quick tunnels.", fg="green")
