"""Development/sidecar entry point for the loopback-only gateway."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys


def configure_utf8_runtime() -> None:
    """Make the Windows sidecar's diagnostic streams Unicode-safe.

    Exchange connection checks construct the headless runtime and therefore
    execute legacy diagnostic output from settings and exchange modules.  A
    packaged Windows process may otherwise inherit cp949 and turn a harmless
    status glyph into a failed account check before any provider API is called.
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


configure_utf8_runtime()

import uvicorn

from web_platform.gateway import create_gateway_app, generate_gateway_token


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def main() -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Run the NoahAI read-only local gateway")
    parser.add_argument("--gateway-only", action="store_true", help="desktop sidecar compatibility flag")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3910, type=int)
    args = parser.parse_args()

    if args.host not in LOOPBACK_HOSTS:
        parser.error("the local gateway may only bind to a loopback host")

    token = os.environ.get("NOAHAI_GATEWAY_TOKEN") or generate_gateway_token()
    app = create_gateway_app(token=token)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        access_log=False,
        server_header=False,
        use_colors=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
