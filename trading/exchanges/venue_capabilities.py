"""Canonical execution capabilities for supported venues.

This contract prevents the Web UI and reporting layer from inferring market
semantics from a symbol suffix.  In particular, Upbit/Bithumb are KRW spot
venues where ``SELL`` reduces an owned asset; it is never a futures short.
"""

from __future__ import annotations

from typing import Any


COMMON_RUNTIME_CONTRACT = {
    "runtime_event_contract": "noahai.execution.v1",
    "xai_contract": "noahai.xai.v1",
    "execution_mode_contract": "learning_paper_live",
}

_VENUES: dict[str, dict[str, Any]] = {
    "upbit": {"market_type": "spot", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "ccxt", "order_amount_unit": "quote_on_market_buy", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "bithumb": {"market_type": "spot", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "ccxt", "order_amount_unit": "base", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "coinone": {
        "market_type": "spot", "quote_currency": "KRW", "can_short": False,
        "can_leverage": False, "adapter_family": "ccxt_hybrid",
        "order_amount_unit": "quote_on_market_buy", "requires_contract_size": False,
        "onboarding_status": "source_ready_account_e2e_required",
        "paper_supported": True, "live_supported": False,
        "position_mode_contract": "owned_cash_asset_only",
        "protective_order_contract": "client_managed_exit_no_exchange_tp_sl",
        "reconciliation_contract": "coinone_v2_1_order_detail_and_completed_orders",
        "client_order_id_contract": "user_order_id_if_supported_else_no_retry_after_unknown",
        "fee_contract": "order_detail_fee_currency_and_amount",
        "time_sync_contract": "uuid_nonce_and_server_timestamp_observation",
        "rate_limit_contract": "ccxt_limiter_plus_bounded_native_backoff",
        "native_escape_hatches": ("market_order", "order_detail", "completed_orders", "candles"),
    },
    "binance": {"market_type": "futures", "quote_currency": "USDT", "can_short": True, "can_leverage": True, "adapter_family": "native", "order_amount_unit": "base", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "bybit": {"market_type": "futures", "quote_currency": "USDT", "can_short": True, "can_leverage": True, "adapter_family": "ccxt", "order_amount_unit": "contracts", "requires_contract_size": True, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "okx": {"market_type": "futures", "quote_currency": "USDT", "can_short": True, "can_leverage": True, "adapter_family": "ccxt", "order_amount_unit": "contracts", "requires_contract_size": True, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "bitget": {"market_type": "futures", "quote_currency": "USDT", "can_short": True, "can_leverage": True, "adapter_family": "ccxt", "order_amount_unit": "contracts", "requires_contract_size": True, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "kiwoom": {"market_type": "stock", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "broker_native", "order_amount_unit": "whole_shares", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "shinhan": {"market_type": "stock", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "broker_native", "order_amount_unit": "whole_shares", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "mirae": {"market_type": "stock", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "broker_native", "order_amount_unit": "whole_shares", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
    "kis": {"market_type": "stock", "quote_currency": "KRW", "can_short": False, "can_leverage": False, "adapter_family": "broker_native", "order_amount_unit": "whole_shares", "requires_contract_size": False, "onboarding_status": "live_ready", "paper_supported": True, "live_supported": True},
}

KRW_SPOT_VENUES = frozenset(
    venue for venue, profile in _VENUES.items()
    if profile.get("market_type") == "spot" and profile.get("quote_currency") == "KRW"
)
USDT_FUTURES_VENUES = frozenset(
    venue for venue, profile in _VENUES.items()
    if profile.get("market_type") == "futures" and profile.get("quote_currency") == "USDT"
)
CRYPTO_VENUES = frozenset(
    venue for venue, profile in _VENUES.items()
    if profile.get("market_type") in {"spot", "futures", "derivative"}
)
STOCK_VENUES = frozenset(
    venue for venue, profile in _VENUES.items()
    if profile.get("market_type") == "stock"
)
SUPPORTED_VENUES = frozenset(_VENUES)
_CRYPTO_DISPLAY_PRIORITY = ("binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget")
_STOCK_DISPLAY_PRIORITY = ("kiwoom", "shinhan", "mirae", "kis")
CRYPTO_VENUE_ORDER = tuple(dict.fromkeys(
    venue for venue in (*_CRYPTO_DISPLAY_PRIORITY, *_VENUES) if venue in CRYPTO_VENUES
))
STOCK_VENUE_ORDER = tuple(dict.fromkeys(
    venue for venue in (*_STOCK_DISPLAY_PRIORITY, *_VENUES) if venue in STOCK_VENUES
))

_MARKETPLACE_IDS = {"mirae": "miraeasset", "kis": "koreainvestment"}
_VENUE_DISPLAY_NAMES = {
    "binance": "Binance", "upbit": "Upbit", "bithumb": "Bithumb", "coinone": "Coinone",
    "bybit": "Bybit", "bitget": "Bitget", "okx": "OKX",
    "kiwoom": "키움증권", "shinhan": "신한투자증권",
    "mirae": "미래에셋증권", "kis": "한국투자증권",
}


def public_venue_registry() -> dict[str, Any]:
    """Return the versioned, non-secret venue artifact used by Strategy Hub.

    NoahAI owns execution meaning.  daltrading consumes a generated JSON copy
    of this projection so Marketplace filters never maintain a second manual
    exchange list.  Only discovery-safe capability fields are exported.
    """

    ordered = (*CRYPTO_VENUE_ORDER, *STOCK_VENUE_ORDER)
    venues = []
    for client_id in ordered:
        profile = dict(_VENUES[client_id])
        public_id = _MARKETPLACE_IDS.get(client_id, client_id)
        service = venue_service(client_id)
        market_type = str(profile.get("market_type") or "unknown")
        venues.append({
            "id": public_id,
            "client_id": client_id,
            "aliases": list(dict.fromkeys((public_id, client_id))),
            "display_name": _VENUE_DISPLAY_NAMES.get(client_id, public_id.upper()),
            "service": service,
            "asset_class": "crypto" if service == "blockchain" else "stock",
            "market_type": market_type,
            "instrument_group": (
                "perpetual_futures" if market_type == "futures"
                else "cash_spot" if market_type == "spot"
                else "cash_stock_etf" if market_type == "stock"
                else market_type
            ),
            "quote_currency": str(profile.get("quote_currency") or ""),
            "can_short": bool(profile.get("can_short")),
            "can_leverage": bool(profile.get("can_leverage")),
            "adapter_family": str(profile.get("adapter_family") or ""),
            "order_amount_unit": str(profile.get("order_amount_unit") or ""),
            "requires_contract_size": bool(profile.get("requires_contract_size")),
            "onboarding_status": str(profile.get("onboarding_status") or "blocked"),
            "paper_supported": bool(profile.get("paper_supported")),
            "live_supported": bool(profile.get("live_supported")),
        })
    return {
        "schema_version": 1,
        "registry_version": "2026-09-12.2",
        "source": "noahai_client.trading.exchanges.venue_capabilities",
        "venues": venues,
    }


def normalize_venue(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return {"miraeasset": "mirae", "koreainvestment": "kis"}.get(normalized, normalized)


def venue_capabilities(value: Any) -> dict[str, Any]:
    venue = normalize_venue(value)
    base = _VENUES.get(venue, {"market_type": "unknown", "quote_currency": "", "can_short": False, "can_leverage": False})
    return {"venue": venue, **COMMON_RUNTIME_CONTRACT, **base}


def venue_service(value: Any) -> str:
    """Return the product service that owns one canonical institution."""

    venue = normalize_venue(value)
    if venue in CRYPTO_VENUES:
        return "blockchain"
    if venue in STOCK_VENUES:
        return "stock"
    return ""


def validate_venue_onboarding_profile(profile: dict[str, Any]) -> tuple[bool, list[str]]:
    """Fail-closed checklist for a future exchange/broker adapter.

    CCXT may provide transport and normalized market data, but production use
    additionally requires explicit order units, position mode, protection,
    reconciliation, idempotency, fees, time sync and rate-limit behaviour.
    """
    required = {
        "venue", "adapter_family", "market_type", "quote_currency",
        "order_amount_unit", "can_short", "can_leverage",
        "onboarding_status", "paper_supported", "live_supported",
        "position_mode_contract", "protective_order_contract",
        "reconciliation_contract", "client_order_id_contract",
        "fee_contract", "time_sync_contract", "rate_limit_contract",
        "runtime_event_contract", "xai_contract", "execution_mode_contract",
    }
    missing = sorted(
        key for key in required
        if profile.get(key) is None or profile.get(key) == ""
    )
    errors = [f"missing:{key}" for key in missing]
    if str(profile.get("onboarding_status") or "") != "live_ready":
        errors.append("live_onboarding_not_ready")
    market_type = str(profile.get("market_type") or "").lower()
    if market_type == "spot" and bool(profile.get("can_short")):
        errors.append("spot_short_requires_explicit_margin_market_type")
    if market_type in {"futures", "derivative"} and profile.get("order_amount_unit") == "contracts":
        if not bool(profile.get("requires_contract_size")):
            errors.append("contract_size_required")
    if str(profile.get("adapter_family") or "").lower() == "ccxt" and not profile.get("native_escape_hatches"):
        errors.append("ccxt_native_escape_hatches_not_declared")
    return not errors, errors


def venue_quote_currency(value: Any, fallback: str = "") -> str:
    return str(venue_capabilities(value).get("quote_currency") or fallback)


def is_krw_spot_venue(value: Any) -> bool:
    return normalize_venue(value) in KRW_SPOT_VENUES


def is_usdt_futures_venue(value: Any) -> bool:
    return normalize_venue(value) in USDT_FUTURES_VENUES


def venue_supports_execution(value: Any, mode: Any) -> bool:
    """Return an explicit PAPER/LIVE capability without inferring readiness."""

    profile = venue_capabilities(value)
    normalized_mode = str(getattr(mode, "value", mode) or "").strip().lower()
    if normalized_mode == "paper":
        return bool(profile.get("paper_supported"))
    if normalized_mode == "live":
        return bool(profile.get("live_supported"))
    return False


def signal_execution_action(
    value: Any,
    signal: Any,
    *,
    has_managed_long: bool = False,
) -> str:
    """Map an analysis signal to the only execution action the venue permits.

    ``SHORT`` is retained as an analysis/strategy compatibility token.  On a
    KRW spot venue (and the currently supported cash-stock venues) it can only
    mean EXIT of a NoahAI-owned long; it must never create a short position.
    """

    caps = venue_capabilities(value)
    normalized_signal = str(signal or "HOLD").strip().upper()
    if normalized_signal == "HOLD":
        return "hold"
    if normalized_signal == "LONG":
        return "open_long"
    if normalized_signal != "SHORT":
        return "reject_unknown_signal"
    if bool(caps.get("can_short")):
        return "open_short"
    return "exit_managed_long" if has_managed_long else "skip_unowned_exit"


def validate_entry_direction(value: Any, signal: Any) -> tuple[bool, str]:
    """Fail closed if an entry direction contradicts the venue contract."""

    action = signal_execution_action(value, signal)
    if action in {"open_long", "open_short"}:
        return True, action
    if action == "hold":
        return False, "HOLD is not an entry direction"
    if action == "skip_unowned_exit":
        return False, "spot/stock SHORT is an exit signal, not a new short entry"
    return False, f"unsupported entry signal: {signal}"
