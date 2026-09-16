"""Local setup checks that work before a remote MCP connector exists."""
import argparse
import json
import shutil
import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from .config import BridgeConfig, load_config
from .chart_inventory import ChartInventory


class SetupCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    status: Literal["pass", "attention", "blocked", "pending"]
    message: str
    next_action: str
    human_action_required: bool = False


class SetupReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["read_only_preflight"] = "read_only_preflight"
    local_endpoint: str
    proposed_public_endpoint: str | None
    ready_for_public_exposure: Literal[False] = False
    checks: list[SetupCheck]


def validate_public_base(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Use an HTTPS origin without credentials, path, query or fragment")
    if any(char.isspace() for char in value):
        raise ValueError("Invalid public URL")
    return value.rstrip("/")


def check_port(port: int) -> bool:
    """Whether a new loopback listener can bind. Does not identify or stop occupants."""
    with socket.socket() as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def inspect_setup(config: BridgeConfig, port: int = 8765, public_base: str | None = None,
                  client: str | None = None, auth_provider: str | None = None,
                  find_executable=shutil.which, port_available=check_port) -> SetupReport:
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    public_base = validate_public_base(public_base)
    checks = []
    reader = ChartInventory(config)
    for chart in reader.charts.values():
        result = reader.read(chart.id)
        readable = result.data is not None
        checks.append(SetupCheck(stage=f"snapshot:{chart.id}",
                      status="attention" if readable else "blocked",
                      message=f"Snapshot status: {result.status}; " + ", ".join(result.warnings),
                      next_action="Snapshot can be queried; retain quality warnings during transport validation." if readable
                      else "Check the configured path, chart number and Sierra Message Log before starting a tunnel."))
    if config.discovery and config.discovery.enabled:
        checks.append(SetupCheck(stage="discovery", status="attention" if reader.warnings else "pass",
                      message="Discovery diagnostics: " + (", ".join(sorted(reader.warnings)) or "none"),
                      next_action="Use startup context to inspect inventory; empty discovery needs a revision 1.6 export."))
    available = port_available(port)
    checks.append(SetupCheck(stage="local_port", status="pass" if available else "attention",
                  message="Loopback port available." if available else "Loopback port unavailable; occupant not identified.",
                  next_action="Start only the bridge process owned by the exposure launcher." if available
                  else "Inspect the existing listener or choose another port; do not stop a process merely by its port."))
    ngrok = bool(find_executable("ngrok"))
    checks.append(SetupCheck(stage="ngrok", status="pass" if ngrok else "blocked",
                  message="ngrok executable found; account login and domain rights not checked." if ngrok else "ngrok executable not found.",
                  next_action="Verify ngrok account configuration privately during deployment setup." if ngrok
                  else "Install the official ngrok agent or select an alternative adapter.", human_action_required=not ngrok))
    checks.append(SetupCheck(stage="client", status="pass" if client else "pending",
                  message=f"Selected client: {client}" if client else "Remote client not selected.",
                  next_action="Validate this client's OAuth redirect/metadata requirements." if client
                  else "Choose the first remote MCP client.", human_action_required=not bool(client)))
    checks.append(SetupCheck(stage="authentication", status="pending",
                  message=("Entra adapter is implemented; credentials, consent and endpoint authorization are not checked here."
                           if auth_provider == "entra" else "Auth0 adapter is not implemented."
                           if auth_provider == "auth0" else "Choose Entra for public OAuth or configure a documented local transport."),
                  next_action="Follow connections.md and verify an authenticated tool read. Enter secrets privately, not in chat.",
                  human_action_required=not bool(auth_provider)))
    checks.append(SetupCheck(stage="public_url", status="pending",
                  message="Proposed HTTPS origin validated syntactically; no network or ownership check performed." if public_base
                  else "Stable public HTTPS origin not selected.",
                  next_action="Select an ngrok domain/HTTPS origin and align OAuth callbacks; no tunnel has been started.",
                  human_action_required=not bool(public_base)))
    return SetupReport(local_endpoint=f"http://127.0.0.1:{port}/mcp",
                       proposed_public_endpoint=f"{public_base}/mcp" if public_base else None, checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--public-base-url")
    parser.add_argument("--client", choices=["chatgpt", "claude", "other"])
    parser.add_argument("--auth-provider", choices=["auth0", "entra"])
    args = parser.parse_args()
    try:
        result = inspect_setup(load_config(args.config), args.port, args.public_base_url, args.client, args.auth_provider)
    except (ValueError, OSError):
        parser.error("Invalid configuration, HTTPS origin or port. See the setup guide; no service was started.")
    print(json.dumps(result.model_dump(), indent=2))
    return 2 if any(c.status == "blocked" for c in result.checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
