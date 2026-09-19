#!/usr/bin/env python3
"""Start the packaged Web engine and verify the desktop bootstrap API contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BOOTSTRAP_ROUTES = (
    "/api/v1/platform",
    "/api/v1/session",
    "/api/v1/features",
    "/api/v1/runtime/snapshot",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _read_json(url: str, token: str | None = None) -> tuple[int, dict[str, object], str]:
    headers = {"Origin": "noahai://app"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload, response.headers.get("Access-Control-Allow-Origin", "")


def main() -> int:
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/NoahAIEngine.exe").resolve()
    if not executable.is_file():
        print(f"[WEB_ENGINE_SMOKE] FAIL: executable missing: {executable}")
        return 1

    port = _free_port()
    env = os.environ.copy()
    token = secrets.token_urlsafe(36)
    env["NOAHAI_GATEWAY_TOKEN"] = token
    env["NOAHAI_ENABLE_WEB_RUNTIME"] = "1"
    process = subprocess.Popen(
        [str(executable), "--gateway-only", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(executable.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        deadline = time.monotonic() + 30
        last_error = "health endpoint did not respond"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=5)
                detail = (stderr or stdout or f"exit={process.returncode}").strip()
                print(f"[WEB_ENGINE_SMOKE] FAIL: {detail[-4000:]}")
                return 1
            try:
                status, payload, allow_origin = _read_json(
                    f"http://127.0.0.1:{port}/api/v1/health"
                )
                if status == 200 and payload.get("status") == "ok":
                    if allow_origin != "noahai://app":
                        raise ValueError(f"health CORS origin mismatch: {allow_origin!r}")
                    for route in BOOTSTRAP_ROUTES:
                        route_status, route_payload, route_origin = _read_json(
                            f"http://127.0.0.1:{port}{route}", token
                        )
                        if route_status != 200 or not isinstance(route_payload, dict):
                            raise ValueError(f"unexpected {route} response")
                        if route_origin != "noahai://app":
                            raise ValueError(f"{route} CORS origin mismatch: {route_origin!r}")
                    print(f"[WEB_ENGINE_SMOKE] PASS: port={port}; bootstrap_routes={len(BOOTSTRAP_ROUTES)}")
                    return 0
                last_error = f"unexpected health response: {payload!r}"
            except (HTTPError, OSError, URLError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.25)
        print(f"[WEB_ENGINE_SMOKE] FAIL: {last_error}")
        return 1
    finally:
        _stop_process_tree(process)


if __name__ == "__main__":
    raise SystemExit(main())
