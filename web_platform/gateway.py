"""Loopback-only read gateway for the v3.9.1.0 parallel Web UI."""

from __future__ import annotations

import asyncio
import hmac
import os
import secrets
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config.app_version import RELEASE_BUILD_LABEL, RELEASE_VERSION

from .contracts import EventEnvelope, HealthContract, PlatformContract, RuntimeSnapshotContract
from .feature_inventory import load_feature_inventory
from .market_data import BinancePublicMarketData, PublicMarketDataError


ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "noahai://app",
)


def generate_gateway_token() -> str:
    return secrets.token_urlsafe(32)


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def create_gateway_app(
    *,
    token: str | None = None,
    runtime_provider: Callable[[], RuntimeSnapshotContract | dict[str, Any]] | None = None,
    market_data: BinancePublicMarketData | None = None,
) -> FastAPI:
    expected_token = str(token or os.environ.get("NOAHAI_GATEWAY_TOKEN") or "").strip()
    if len(expected_token) < 32:
        raise ValueError("NOAHAI_GATEWAY_TOKEN must contain at least 32 characters")

    provider = runtime_provider or (lambda: RuntimeSnapshotContract())
    market_provider = market_data or BinancePublicMarketData()

    app = FastAPI(
        title="NoahAI Local Gateway",
        version=RELEASE_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def enforce_local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return _forbidden_response()
        return await call_next(request)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        supplied = _extract_bearer(authorization)
        if not supplied or not hmac.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=401, detail="gateway_authentication_required")

    @app.get("/api/v1/health", response_model=HealthContract)
    def health() -> HealthContract:
        return HealthContract(release_version=RELEASE_VERSION)

    @app.get("/api/v1/platform", response_model=PlatformContract, dependencies=[Depends(require_token)])
    def platform() -> PlatformContract:
        return PlatformContract(
            release_version=RELEASE_VERSION,
            release_label=RELEASE_BUILD_LABEL,
        )

    @app.get("/api/v1/features", dependencies=[Depends(require_token)])
    def features() -> dict[str, Any]:
        return load_feature_inventory()

    @app.get("/api/v1/runtime/snapshot", response_model=RuntimeSnapshotContract, dependencies=[Depends(require_token)])
    def runtime_snapshot() -> RuntimeSnapshotContract:
        snapshot = provider()
        if isinstance(snapshot, RuntimeSnapshotContract):
            return snapshot
        return RuntimeSnapshotContract.model_validate(snapshot)

    @app.get("/api/v1/market/candles", dependencies=[Depends(require_token)])
    def market_candles(
        source: str = Query(default="binance"),
        symbol: str = Query(default="BTCUSDT"),
        interval: str = Query(default="1m"),
        limit: int = Query(default=300, ge=10, le=1000),
    ):
        if source.lower() != "binance":
            raise HTTPException(status_code=400, detail="unsupported_market_source")
        try:
            return market_provider.get_spot_candles(symbol, interval, limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PublicMarketDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            await websocket.close(code=4403, reason="origin_not_allowed")
            return
        await websocket.accept()
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            supplied = str(auth_message.get("token") or "") if isinstance(auth_message, dict) else ""
            if not supplied or not hmac.compare_digest(supplied, expected_token):
                await websocket.close(code=4401, reason="authentication_required")
                return

            sequence = 0
            await websocket.send_json(
                EventEnvelope(
                    event_id=str(uuid.uuid4()),
                    sequence=sequence,
                    event_type="gateway.ready",
                    source="local_gateway",
                    payload={"commands_enabled": False, "release_version": RELEASE_VERSION},
                ).model_dump(mode="json")
            )
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
                except TimeoutError:
                    sequence += 1
                    await websocket.send_json(
                        EventEnvelope(
                            event_id=str(uuid.uuid4()),
                            sequence=sequence,
                            event_type="gateway.heartbeat",
                            source="local_gateway",
                        ).model_dump(mode="json")
                    )
        except (WebSocketDisconnect, asyncio.TimeoutError):
            return

    return app


def _forbidden_response():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=403, content={"detail": "origin_not_allowed"})
