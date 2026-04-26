"""One-command local launcher for ez-agent.

This script starts the FastAPI backend and Streamlit frontend together.
It avoids the common Windows port-conflict workflow by reusing a healthy
existing API or picking the next available ports automatically.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_PORT = int(os.getenv("API_PORT", "8000"))
DEFAULT_FRONTEND_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))


def _print(message: str) -> None:
    """Print a line with flushing for double-clicked console windows."""
    print(message, flush=True)


def _port_is_free(port: int) -> bool:
    """Return True when both IPv4 and IPv6 loopback binds appear available."""
    checks = [
        (socket.AF_INET, "0.0.0.0"),
        (socket.AF_INET, "127.0.0.1"),
    ]
    if socket.has_ipv6:
        checks.append((socket.AF_INET6, "::1"))

    for family, host in checks:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
    return True


def _find_port(preferred: int, *, limit: int = 50) -> int:
    """Find a free port starting at preferred."""
    for port in range(preferred, preferred + limit):
        if _port_is_free(port):
            return port
    raise RuntimeError(f"No free port found in range {preferred}-{preferred + limit - 1}")


def _http_ok(url: str, *, timeout: float = 1.0) -> bool:
    """Return True when a URL returns a 2xx/3xx response."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def _wait_for_url(
    url: str,
    *,
    process: subprocess.Popen[str] | None,
    timeout: float,
    label: str,
) -> bool:
    """Wait until a URL becomes available or the process exits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _http_ok(url, timeout=1.0):
            return True
        if process is not None and process.poll() is not None:
            _print(f"[ERROR] {label} exited early with code {process.returncode}")
            return False
        time.sleep(0.5)
    _print(f"[ERROR] Timed out waiting for {label}: {url}")
    return False


def _stream_output(process: subprocess.Popen[str], label: str) -> None:
    """Forward child process output with a small prefix."""
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if line:
            _print(f"[{label}] {line}")


def _start_process(
    args: list[str],
    *,
    env: dict[str, str],
    label: str,
) -> subprocess.Popen[str]:
    """Start a child process and stream its combined output."""
    process = subprocess.Popen(
        args,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    thread = threading.Thread(
        target=_stream_output,
        args=(process, label),
        daemon=True,
    )
    thread.start()
    return process


def _terminate(processes: Iterable[subprocess.Popen[str]]) -> None:
    """Terminate child processes started by this launcher."""
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 8
    for process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            process.kill()


def _validate_environment() -> None:
    """Load project settings once so config errors fail before servers start."""
    sys.path.insert(0, str(ROOT))
    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception as exc:
        raise RuntimeError(
            "Configuration failed. Check .env and required keys "
            "DEEPSEEK_API_KEY/TAVILY_API_KEY."
        ) from exc

    _print(f"[OK] config loaded: APP_ENV={settings.APP_ENV}, model={settings.DEEPSEEK_MODEL}")


def _build_env(extra: dict[str, str]) -> dict[str, str]:
    """Build a child environment with UTF-8 console output."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(extra)
    return env


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=45.0)
    args = parser.parse_args()

    _print("== ez-agent local launcher ==")
    _validate_environment()

    processes: list[subprocess.Popen[str]] = []
    api_process: subprocess.Popen[str] | None = None

    preferred_api_port = args.api_port
    preferred_api_url = f"http://127.0.0.1:{preferred_api_port}"
    if _http_ok(f"{preferred_api_url}/health", timeout=1.0):
        api_port = preferred_api_port
        api_url = preferred_api_url
        _print(f"[OK] reusing existing API: {api_url}")
    else:
        api_port = _find_port(preferred_api_port)
        api_url = f"http://127.0.0.1:{api_port}"
        if api_port != preferred_api_port:
            _print(f"[INFO] API port {preferred_api_port} is busy; using {api_port}")

        api_process = _start_process(
            [sys.executable, "-m", "app.main"],
            env=_build_env({"API_PORT": str(api_port)}),
            label="api",
        )
        processes.append(api_process)
        if not _wait_for_url(
            f"{api_url}/health",
            process=api_process,
            timeout=args.startup_timeout,
            label="API",
        ):
            _terminate(processes)
            return 1
        _print(f"[OK] API started: {api_url}")

    frontend_port = _find_port(args.frontend_port)
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    if frontend_port != args.frontend_port:
        _print(f"[INFO] frontend port {args.frontend_port} is busy; using {frontend_port}")

    frontend_process = _start_process(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/app.py",
            "--server.address=127.0.0.1",
            f"--server.port={frontend_port}",
            "--server.headless=true",
        ],
        env=_build_env({"EZ_AGENT_API_BASE_URL": api_url}),
        label="web",
    )
    processes.append(frontend_process)
    if not _wait_for_url(
        frontend_url,
        process=frontend_process,
        timeout=args.startup_timeout,
        label="frontend",
    ):
        _terminate(processes)
        return 1

    _print("")
    _print("[READY] ez-agent is running")
    _print(f"  API:      {api_url}")
    _print(f"  Frontend: {frontend_url}")
    _print("")
    _print("Keep this window open. Press Ctrl+C to stop servers started by this launcher.")

    if not args.no_browser:
        webbrowser.open(frontend_url)

    try:
        while True:
            for process in processes:
                if process.poll() is not None:
                    _print(f"[ERROR] child process exited with code {process.returncode}")
                    _terminate(processes)
                    return process.returncode or 1
            time.sleep(1)
    except KeyboardInterrupt:
        _print("\n[INFO] stopping servers...")
        _terminate(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
