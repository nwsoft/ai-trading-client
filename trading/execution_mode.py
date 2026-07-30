"""실행 모드 판정의 단일 소스.

LEARNING은 분석·학습만, PAPER는 내부 가상 체결, LIVE는 실제 주문 허용을
뜻한다. 전역 paper_trading은 안전을 위해 개별 LIVE 요청보다 우선한다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, Optional


class ExecutionMode(str, Enum):
    LEARNING = "learning"
    PAPER = "paper"
    LIVE = "live"


CRYPTO_EXCHANGES = {"binance", "bybit", "okx", "bitget", "upbit", "bithumb"}
TRADE_SCOPE_CONFIRMATION_KEY = "_trade_scope_user_confirmed_v3904"


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalized_scope(values: Any) -> set[str]:
    source: Iterable[Any] = values if isinstance(values, (list, tuple, set)) else []
    return {
        _normalize(item)
        for item in source
        if _normalize(item) in CRYPTO_EXCHANGES
    }


def live_order_scope(settings: Optional[Dict[str, Any]]) -> set[str]:
    cfg = settings if isinstance(settings, dict) else {}
    if not bool(cfg.get(TRADE_SCOPE_CONFIRMATION_KEY, False)):
        return set()
    configured = cfg.get("trade_enabled_exchanges", [])
    if isinstance(configured, list) and configured:
        return _normalized_scope(configured)
    if "trade_enabled_exchanges" in cfg:
        return set()
    selected = _normalize(cfg.get("selected_exchange", "binance"))
    return {selected} if selected in CRYPTO_EXCHANGES else {"binance"}


def resolve_crypto_execution_mode(
    settings: Optional[Dict[str, Any]],
    exchange: str,
    *,
    live_enabled: Optional[bool] = None,
) -> ExecutionMode:
    cfg = settings if isinstance(settings, dict) else {}
    normalized = _normalize(exchange)

    # 전역 PAPER는 실주문보다 항상 우선한다.
    if bool(cfg.get("paper_trading", False)):
        return ExecutionMode.PAPER

    explicit_modes = cfg.get("exchange_execution_modes", {})
    requested = (
        _normalize(explicit_modes.get(normalized))
        if isinstance(explicit_modes, dict)
        else ""
    )
    if requested == ExecutionMode.LEARNING.value:
        return ExecutionMode.LEARNING
    if requested == ExecutionMode.PAPER.value:
        return ExecutionMode.PAPER

    allowed_live = (
        bool(live_enabled)
        if live_enabled is not None
        else normalized in live_order_scope(cfg)
    )
    return ExecutionMode.LIVE if allowed_live else ExecutionMode.LEARNING


def resolve_stock_execution_mode(
    settings: Optional[Dict[str, Any]],
    *,
    allow_live_order: bool,
    adapter_api_type: str = "",
) -> ExecutionMode:
    cfg = settings if isinstance(settings, dict) else {}
    if bool(cfg.get("paper_trading", False)) or _normalize(adapter_api_type) == "mock":
        return ExecutionMode.PAPER
    return ExecutionMode.LIVE if bool(allow_live_order) else ExecutionMode.LEARNING
