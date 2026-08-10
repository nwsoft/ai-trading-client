"""거래 통계·리포트에서 공통으로 사용하는 실제 운용 지표.

통화가 다른 체결금액을 합산하지 않고, 검증 가능한 진입/청산 시각만
평균 보유시간에 포함한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional


KRW_EXCHANGES = {
    "bithumb",
    "upbit",
    "kiwoom",
    "kiwoom_stock",
    "kis",
    "korea_investment",
    "mirae",
    "mirae_asset",
    "nh",
    "shinhan",
    "stock_mock",
}
USDT_EXCHANGES = {
    "binance",
    "bitget",
    "bybit",
    "kucoin",
    "okx",
}


def _number(value: Any) -> float:
    try:
        number = float(value or 0.0)
        return number if number == number else 0.0
    except (TypeError, ValueError):
        return 0.0


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def infer_quote_currency(
    exchange: Any = None,
    symbol: Any = None,
    explicit_currency: Any = None,
) -> str:
    """거래소·심볼·명시 통화 순으로 결제 통화를 판정한다."""
    explicit = str(explicit_currency or "").strip().upper()
    if explicit in {"KRW", "USDT", "USD", "USDC"}:
        return explicit

    normalized_symbol = (
        str(symbol or "")
        .strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace(":", "")
    )
    for currency in ("USDT", "USDC", "KRW", "USD"):
        if normalized_symbol.endswith(currency):
            return currency

    # 같은 거래소에서도 결제통화가 다른 시장을 지원할 수 있으므로 종목 표기를
    # 거래소 기본 통화보다 먼저 신뢰한다. 종목만으로 판단할 수 없을 때만
    # 거래소 기본값을 사용한다.
    normalized_exchange = str(exchange or "").strip().lower()
    if normalized_exchange in KRW_EXCHANGES:
        return "KRW"
    if normalized_exchange in USDT_EXCHANGES:
        return "USDT"
    if "interactive" in normalized_exchange or normalized_exchange in {"ib", "ibkr"}:
        return "USD"

    # exchange가 비어 있는 기존 trade_log는 과거 Binance 기록이다.
    return "USDT"


def calculate_currency_financial_metrics(
    trades: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """손익과 수수료를 결제통화별로 분리한다.

    서로 환산되지 않은 KRW·USDT·USD 등을 하나의 숫자로 합치지 않는다.
    수수료 자산이 명시된 경우에는 해당 자산을 별도 버킷으로 보존한다.
    """
    by_currency: Dict[str, Dict[str, float]] = {}
    fees_by_currency: Dict[str, float] = {}

    for trade in trades:
        currency = infer_quote_currency(
            trade.get("exchange") or trade.get("broker"),
            trade.get("symbol"),
            trade.get("pnl_currency")
            or trade.get("quote_currency")
            or trade.get("settlement_currency"),
        )
        bucket = by_currency.setdefault(
            currency,
            {"trades": 0.0, "wins": 0.0, "pnl": 0.0},
        )
        pnl = _number(trade.get("pnl"))
        bucket["trades"] += 1.0
        bucket["wins"] += 1.0 if pnl > 0.0 else 0.0
        bucket["pnl"] += pnl

        fee = _number(trade.get("fees") or trade.get("fee"))
        if fee:
            explicit_fee_currency = str(
                trade.get("fee_asset") or trade.get("fee_currency") or ""
            ).strip().upper()
            fee_currency = explicit_fee_currency or currency
            fees_by_currency[fee_currency] = (
                fees_by_currency.get(fee_currency, 0.0) + fee
            )

    normalized: Dict[str, Dict[str, Any]] = {}
    for currency, bucket in by_currency.items():
        trades_count = int(bucket["trades"])
        pnl = float(bucket["pnl"])
        normalized[currency] = {
            "trades": trades_count,
            "wins": int(bucket["wins"]),
            "pnl": pnl,
            "avg_pnl": pnl / trades_count if trades_count else 0.0,
        }

    return {
        "by_currency": normalized,
        "fees_by_currency": fees_by_currency,
        "currencies": sorted(normalized),
        "mixed_currency": len(normalized) > 1,
    }


def format_currency_amount(currency: str, amount: Any, *, signed: bool = False) -> str:
    """손익·수수료용 통화 금액을 동일한 규칙으로 표시한다."""
    value = _number(amount)
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:,.2f} {str(currency or 'UNKNOWN').upper()}"


def calculate_trade_operating_metrics(
    trades: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """청산 거래의 통화별 체결금액과 유효 평균 보유시간을 계산한다."""
    notional_by_currency: Dict[str, float] = {}
    hold_minutes = []
    closed_count = 0

    for trade in trades:
        exit_time = _as_datetime(trade.get("exit_time") or trade.get("closed_at"))
        if exit_time is None:
            continue
        closed_count += 1

        explicit_notional = _number(
            trade.get("notional")
            or trade.get("entry_notional")
            or trade.get("entry_amount")
            or trade.get("notional_estimate")
        )
        notional = abs(explicit_notional)
        if notional <= 0.0:
            notional = abs(
                _number(trade.get("entry_price") or trade.get("price"))
                * _number(trade.get("quantity") or trade.get("qty"))
            )

        currency = infer_quote_currency(
            trade.get("exchange") or trade.get("broker"),
            trade.get("symbol"),
            trade.get("quote_currency") or trade.get("settlement_currency"),
        )
        notional_by_currency[currency] = (
            notional_by_currency.get(currency, 0.0) + notional
        )

        entry_time = _as_datetime(trade.get("entry_time") or trade.get("opened_at"))
        if entry_time is None:
            continue
        elapsed_minutes = (exit_time - entry_time).total_seconds() / 60.0
        # 동일 시각으로 생성된 구형/모의 스냅샷은 실제 보유시간이 아니다.
        if elapsed_minutes > 0.0:
            hold_minutes.append(elapsed_minutes)

    valid_hold_count = len(hold_minutes)
    return {
        "notional_by_currency": notional_by_currency,
        "closed_count": closed_count,
        "valid_hold_count": valid_hold_count,
        "avg_hold_minutes": (
            sum(hold_minutes) / valid_hold_count if valid_hold_count else None
        ),
        "hold_coverage_rate": (
            valid_hold_count / closed_count * 100.0 if closed_count else None
        ),
    }


def format_hold_duration(minutes: Any) -> str:
    """평균 보유시간을 짧고 읽기 쉬운 한국어로 표시한다."""
    value = _number(minutes)
    if value <= 0.0:
        return "수집 대기"
    if value < 60.0:
        return f"{value:.1f}분"
    if value < 1440.0:
        hours = int(value // 60)
        remaining = int(round(value % 60))
        return f"{hours}시간 {remaining}분" if remaining else f"{hours}시간"
    days = int(value // 1440)
    remaining_hours = int(round((value % 1440) / 60))
    return (
        f"{days}일 {remaining_hours}시간"
        if remaining_hours
        else f"{days}일"
    )


def format_notional(currency: str, amount: Any) -> str:
    value = _number(amount)
    if str(currency).upper() == "KRW":
        return f"{value:,.0f} KRW"
    return f"{value:,.2f} {str(currency).upper()}"
