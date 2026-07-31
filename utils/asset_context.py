"""자산 서비스 컨텍스트 판정 공통 함수.

UI 위젯이 거래소명이나 BTC/ETH 같은 대표 종목을 직접 가정하지 않도록
가상자산·주식/ETF 학습 행의 분류 계약을 한곳에 둔다.
"""

from __future__ import annotations

from typing import Any, Dict, List


CRYPTO_VENUES = {
    "binance", "upbit", "bithumb", "bybit", "okx", "bitget",
}

STOCK_VENUES = {
    "kiwoom", "shinhan", "mirae", "miraeasset", "mirae_asset",
    "koreainvestment", "korea_investment", "korea-investment",
}


def filter_learning_rows(
    data: List[Dict[str, Any]],
    service_context: str,
) -> List[Dict[str, Any]]:
    """서비스별 학습 행을 거래소·자산유형·심볼 형식으로 분류한다."""
    if not isinstance(data, list):
        return []

    context = str(service_context or "").strip().lower()
    if context not in {"stock", "blockchain"}:
        return data

    filtered: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            symbol = str(item.get("symbol") or "").strip().upper()
            venue = str(
                item.get("exchange") or item.get("source") or ""
            ).strip().lower()
            asset_type = str(
                item.get("asset_type") or item.get("market_type") or ""
            ).strip().lower()

            if context == "stock":
                domestic_code = symbol.split(".", 1)[0]
                if (
                    venue in STOCK_VENUES
                    or asset_type in {"stock", "equity", "etf"}
                    or (len(domestic_code) == 6 and domestic_code.isdigit())
                ):
                    filtered.append(item)
                continue

            is_crypto_symbol = bool(
                symbol.endswith(("USDT", "USDC"))
                or symbol.startswith(("KRW-", "USDT-", "USDC-"))
                or "/USDT" in symbol
                or "/USDC" in symbol
                or symbol.endswith("/KRW")
            )
            if (
                venue in CRYPTO_VENUES
                or asset_type in {"crypto", "cryptocurrency", "coin"}
                or is_crypto_symbol
            ):
                filtered.append(item)
        except Exception:
            continue

    return filtered
