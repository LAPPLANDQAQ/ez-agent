"""Check whether the local development ports are already occupied."""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PortStatus:
    """One port availability result."""

    port: int
    available: bool
    pids: tuple[int, ...]


def _can_bind(port: int) -> bool:
    """Return True when a development server can bind the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _listening_pids(port: int) -> tuple[int, ...]:
    """Return listening process IDs for a TCP port on Windows."""
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ()

    pids: set[int] = set()
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    for line in completed.stdout.splitlines():
        match = pattern.match(line)
        if match:
            pids.add(int(match.group(1)))
    return tuple(sorted(pids))


def check_port(port: int) -> PortStatus:
    """Check one TCP port."""
    return PortStatus(
        port=port,
        available=_can_bind(port),
        pids=_listening_pids(port),
    )


def _default_ports() -> list[int]:
    """Return default project ports."""
    api_port = int(os.getenv("API_PORT", "8000"))
    frontend_port = int(os.getenv("STREAMLIT_PORT", "8501"))
    return [api_port, frontend_port]


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ports",
        nargs="*",
        type=int,
        default=_default_ports(),
        help="Ports to check. Defaults to API_PORT/8000 and STREAMLIT_PORT/8501.",
    )
    args = parser.parse_args()

    blocked = False
    for status in [check_port(port) for port in args.ports]:
        if status.available:
            print(f"[OK] port {status.port} is available")
            continue

        blocked = True
        pid_text = ", ".join(str(pid) for pid in status.pids) or "unknown"
        print(f"[BUSY] port {status.port} is already in use by PID(s): {pid_text}")

    if blocked:
        print("\nStop the old process or choose another port before starting the server.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
