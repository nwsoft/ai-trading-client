"""CCXT 주문을 거래소 수량·최소금액 규격에 맞춰 제출 전 검증한다."""

from typing import Any, Dict, Optional


def resolve_ccxt_order_limits(exchange: Any, symbol: str) -> Dict[str, float]:
    """CCXT market limit을 읽고 누락된 기준통화 최소금액을 보수적으로 보완한다."""
    market = exchange.market(symbol) or {}
    limits = market.get("limits", {}) if isinstance(market, dict) else {}
    amount_limits = limits.get("amount", {}) if isinstance(limits, dict) else {}
    cost_limits = limits.get("cost", {}) if isinstance(limits, dict) else {}
    try:
        min_amount = float(amount_limits.get("min") or 0.0)
    except (TypeError, ValueError):
        min_amount = 0.0
    try:
        min_cost = float(cost_limits.get("min") or 0.0)
    except (TypeError, ValueError):
        min_cost = 0.0

    quote = str(market.get("quote") or "").upper() if isinstance(market, dict) else ""
    if not quote:
        normalized = str(symbol or "").upper().split(":", 1)[0]
        quote = normalized.rsplit("/", 1)[-1] if "/" in normalized else ""
    fallback_cost = {"KRW": 5000.0, "USDT": 5.0}.get(quote, 0.0)
    return {
        "min_amount": min_amount,
        "min_cost": max(min_cost, fallback_cost),
    }


def ccxt_amount_ceiling(exchange: Any, symbol: str, minimum: float) -> float:
    """CCXT 정밀도로 표현 가능하면서 minimum 이상인 가장 작은 수량을 찾는다."""
    required = float(minimum or 0.0)
    if required <= 0:
        return 0.0

    def _precise(candidate: float) -> float:
        return float(exchange.amount_to_precision(symbol, candidate))

    direct = _precise(required)
    if direct >= required:
        return direct

    low = required
    high = max(required * 1.01, required + 1e-12)
    for _ in range(64):
        if _precise(high) >= required:
            break
        low = high
        high *= 2.0
    else:
        raise ValueError(f"cannot resolve amount precision ceiling for {symbol}")

    for _ in range(64):
        middle = (low + high) / 2.0
        if _precise(middle) >= required:
            high = middle
        else:
            low = middle
    result = _precise(high)
    if result < required:
        raise ValueError(f"amount precision ceiling below minimum for {symbol}")
    return result


def prepare_ccxt_order_quantity(
    exchange: Any,
    symbol: str,
    quantity: float,
    *,
    reference_price: Optional[float] = None,
) -> Dict[str, Any]:
    """수량 정밀도를 적용하고 거래소 최소수량·최소금액 미달을 차단한다."""
    try:
        requested = float(quantity or 0.0)
    except (TypeError, ValueError):
        requested = 0.0
    if requested <= 0:
        return {"allowed": False, "quantity": 0.0, "reason": "order quantity must be positive"}

    try:
        resolved_limits = resolve_ccxt_order_limits(exchange, symbol)
    except Exception as exc:
        return {
            "allowed": False,
            "quantity": requested,
            "reason": f"market constraints unavailable: {exc}",
        }

    try:
        precise = float(exchange.amount_to_precision(symbol, requested))
    except Exception as exc:
        return {
            "allowed": False,
            "quantity": requested,
            "reason": f"amount precision unavailable: {exc}",
        }
    if precise <= 0:
        return {"allowed": False, "quantity": precise, "reason": "quantity became zero after precision"}

    min_amount = resolved_limits["min_amount"]
    min_cost = resolved_limits["min_cost"]
    try:
        price = float(reference_price or 0.0)
    except (TypeError, ValueError):
        price = 0.0

    if min_cost > 0 and price <= 0:
        try:
            ticker = exchange.fetch_ticker(symbol) or {}
            price = float(ticker.get("last") or ticker.get("close") or 0.0)
        except Exception:
            price = 0.0

    if min_amount > 0 and precise < min_amount:
        return {
            "allowed": False,
            "quantity": precise,
            "reason": f"minimum quantity not met: {precise:g} < {min_amount:g}",
        }
    if min_cost > 0 and price <= 0:
        return {
            "allowed": False,
            "quantity": precise,
            "reason": "reference price required for minimum notional validation",
        }
    notional = precise * price if price > 0 else 0.0
    if min_cost > 0 and notional < min_cost:
        return {
            "allowed": False,
            "quantity": precise,
            "notional": notional,
            "reason": f"minimum notional not met: {notional:.8f} < {min_cost:g}",
        }
    return {
        "allowed": True,
        "quantity": precise,
        "notional": notional,
        "min_amount": min_amount,
        "min_cost": min_cost,
    }