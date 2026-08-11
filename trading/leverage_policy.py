"""Single effective-leverage policy for every crypto execution path."""

from __future__ import annotations

from typing import Any, Mapping


SPOT_EXCHANGES = frozenset({"upbit", "bithumb"})


def resolve_effective_leverage(
    *,
    configured_leverage: Any,
    exchange: str,
    market_level: Any = "NORMAL",
    exchange_max_leverage: Any = 20,
    cold_start_max_leverage: Any = None,
) -> dict[str, Any]:
    """Resolve requested leverage into the value that may reach the exchange.

    The configured value is a ceiling, not a promise.  Market and cold-start
    safety caps are explicit so the UI/XAI can explain every reduction.
    """
    venue = str(exchange or "").strip().lower()
    try:
        configured = max(1, int(round(float(configured_leverage))))
    except (TypeError, ValueError):
        configured = 1
    try:
        venue_cap = max(1, int(round(float(exchange_max_leverage))))
    except (TypeError, ValueError):
        venue_cap = 20

    if venue in SPOT_EXCHANGES:
        return {
            "configured": configured,
            "effective": 1,
            "cap": 1,
            "market_level": "SPOT",
            "reason": "현물 거래소는 레버리지를 사용하지 않음",
        }

    level = str(market_level or "NORMAL").strip().upper()
    market_caps = {"HIGH": 1, "NORMAL": 2, "LOW": 3}
    market_cap = market_caps.get(level, market_caps["NORMAL"])
    effective_cap = min(venue_cap, market_cap)
    reasons = [f"{level} 시장 안전상한 {market_cap}x", f"거래소 설정상한 {venue_cap}x"]

    if cold_start_max_leverage not in (None, ""):
        try:
            cold_cap = max(1, int(round(float(cold_start_max_leverage))))
        except (TypeError, ValueError):
            cold_cap = 1
        effective_cap = min(effective_cap, cold_cap)
        reasons.append(f"신규/회복 제한운용 상한 {cold_cap}x")

    effective = max(1, min(configured, effective_cap))
    return {
        "configured": configured,
        "effective": effective,
        "cap": effective_cap,
        "market_level": level,
        "reason": ", ".join(reasons),
    }


def exchange_leverage_cap(settings: Mapping[str, Any], exchange: str) -> int:
    overrides = dict((settings.get("exchange_risk_overrides", {}) or {}).get(exchange, {}) or {})
    raw = overrides.get("max_leverage", settings.get("max_leverage", 20))
    try:
        return max(1, int(round(float(raw))))
    except (TypeError, ValueError):
        return 20
