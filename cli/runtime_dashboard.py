"""
Terminal dashboard runtime helpers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERMINAL_DASHBOARD_APP = "src.backtest_engine.runtime.terminal_ui.app:app"
TERMINAL_DASHBOARD_HOST = "127.0.0.1"
TERMINAL_DASHBOARD_PORT = "8000"
HEALTH_HEADER = "X-Quant-Terminal"
HEALTH_HEADER_VALUE = "1"


def resolve_preferred_dashboard_port(cli_port: int | None) -> int:
    """
    Resolves the preferred dashboard HTTP port.

    Args:
        cli_port: Optional explicit CLI override.

    Returns:
        Resolved integer port.
    """
    if cli_port is not None:
        return cli_port
    raw = os.environ.get("TERMINAL_DASHBOARD_PORT", TERMINAL_DASHBOARD_PORT)
    try:
        return int(raw)
    except ValueError:
        return int(TERMINAL_DASHBOARD_PORT)


def dashboard_already_running(host: str, port: int) -> bool:
    """
    Returns whether this repository's terminal dashboard is already active.

    Args:
        host: Dashboard bind host.
        port: Dashboard port.

    Returns:
        ``True`` when the health endpoint matches the expected app signature.
    """
    url = f"http://{host}:{port}/health"
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=1.0) as response:
            if response.headers.get(HEALTH_HEADER) != HEALTH_HEADER_VALUE:
                return False
            body = json.loads(response.read().decode())
            return body.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def first_free_tcp_port(host: str, start: int, *, span: int = 32) -> int:
    """
    Returns the first free TCP port inside a small search range.

    Args:
        host: Bind host.
        start: First port to probe.
        span: Number of candidate ports to scan.

    Returns:
        First available TCP port.
    """
    last_error: OSError | None = None
    for port in range(start, start + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError as exc:
                last_error = exc
                continue
            return port
    hint = f": {last_error}" if last_error else ""
    raise RuntimeError(
        f"No free TCP port found for terminal dashboard on {host} "
        f"(tried {start}..{start + span - 1}){hint}"
    )


def launch_dashboard(*, dashboard_port: int | None = None) -> None:
    """
    Launches the FastAPI terminal dashboard as a child process.

    Methodology:
        The dashboard remains a separate uvicorn process. Duplicate launches
        are avoided via health checks, and port conflicts fall through to the
        next small free range for a Windows-friendly local workflow.

    Args:
        dashboard_port: Optional HTTP port override.
    """
    host = TERMINAL_DASHBOARD_HOST
    preferred = resolve_preferred_dashboard_port(dashboard_port)

    if dashboard_already_running(host, preferred):
        print(
            f"\n[Dashboard] Terminal UI already running - open "
            f"http://{host}:{preferred} (not starting a second server).\n"
        )
        return

    port = first_free_tcp_port(host, preferred)
    if port != preferred:
        print(
            f"\n[Dashboard] Port {preferred} is in use; "
            f"binding terminal dashboard on {port} instead.\n"
        )

    print("\n[Dashboard] Launching terminal dashboard...")
    print(f"[Dashboard] URL: http://{host}:{port}\n")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            TERMINAL_DASHBOARD_APP,
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
