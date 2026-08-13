"""Development/sidecar entry point for the loopback-only gateway."""

from __future__ import annotations

import argparse
import json
import os

import uvicorn

from .gateway import create_gateway_app, generate_gateway_token


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NoahAI read-only local gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3910, type=int)
    parser.add_argument("--print-bootstrap", action="store_true")
    args = parser.parse_args()

    if args.host not in LOOPBACK_HOSTS:
        parser.error("the local gateway may only bind to a loopback host")

    token = os.environ.get("NOAHAI_GATEWAY_TOKEN") or generate_gateway_token()
    if args.print_bootstrap:
        print(json.dumps({"baseUrl": f"http://{args.host}:{args.port}", "token": token}))

    app = create_gateway_app(token=token)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, server_header=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
