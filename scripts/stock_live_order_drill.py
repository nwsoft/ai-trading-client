#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 실주문 직전 drill 스크립트.

기본 동작:
- 브로커 실연동 준비 상태 확인
- 연결 및 시세 확인
- 실제 주문은 하지 않음 (dry-run)

명시 옵션:
- --execute: 실제 주문 실행
- --cancel-after: 주문 성공 시 즉시 취소 시도
- --strict: 준비 미충족/skip도 실패 처리
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stock_d1_preflight import _build_rows, _load_settings
from trading.exchanges.exchange_factory import ExchangeFactory


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="증권 실주문 직전 drill")
    parser.add_argument("--broker", required=True, help="대상 브로커 (kiwoom/shinhan/miraeAsset)")
    parser.add_argument("--symbol", default="005930", help="종목코드")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"], help="주문 방향")
    parser.add_argument("--quantity", type=float, default=1.0, help="주문 수량")
    parser.add_argument("--order-type", default="LIMIT", choices=["LIMIT", "MARKET"], help="주문 유형")
    parser.add_argument("--price", type=float, default=None, help="지정가 주문 가격")
    parser.add_argument("--execute", action="store_true", help="실제 주문 실행")
    parser.add_argument("--cancel-after", action="store_true", help="주문 성공 시 즉시 취소 시도")
    parser.add_argument("--strict", action="store_true", help="skip/준비 부족 시 종료코드 1")
    return parser.parse_args()


def _normalize_broker_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    if lowered in ("miraeasset", "mirae_asset"):
        return "miraeAsset"
    return lowered


def _find_row(rows: list[Dict[str, Any]], broker: str) -> Optional[Dict[str, Any]]:
    normalized = _normalize_broker_name(broker)
    for row in rows:
        if _normalize_broker_name(row.get("broker")) == normalized:
            return row
    return None


def _skip_reason(row: Optional[Dict[str, Any]], execute: bool) -> str:
    if row is None:
        return "broker not configured"
    if not row.get("valid_combo"):
        return "invalid api_type/api_version"
    if row.get("execution_mode") != "live_api":
        return "not live_api path"
    if not row.get("credentials_ready"):
        missing = ",".join(row.get("missing_credentials") or [])
        return f"missing credentials: {missing}"
    if row.get("os_blocked"):
        return "os blocked"
    if execute and not row.get("live_order_enabled"):
        return "live order flags disabled"
    return ""


def _resolve_price(adapter: Any, symbol: str, requested_price: Optional[float], order_type: str) -> Optional[float]:
    if order_type == "MARKET":
        return None
    if requested_price is not None:
        return float(requested_price)
    quote = adapter.get_realtime_price(symbol)
    current_price = float(quote.get("current_price") or 0.0)
    return current_price if current_price > 0 else None


def main() -> int:
    args = _parse_args()
    settings, settings_path = _load_settings()
    rows = _build_rows(settings)
    row = _find_row(rows, args.broker)

    print("증권 live order drill 시작")
    print(f"- settings: {settings_path}")
    print(f"- broker: {args.broker}")

    reason = _skip_reason(row, execute=args.execute)
    if reason:
        print(f"- 결과: SKIP | {reason}")
        return 1 if args.strict else 0

    adapter = ExchangeFactory.create_stock_exchange(str(row.get("broker")), settings)
    if not adapter.connect():
        print("- 결과: FAIL | connect failed")
        return 1

    quote = adapter.get_realtime_price(args.symbol)
    current_price = float(quote.get("current_price") or 0.0)
    resolved_price = _resolve_price(adapter, args.symbol, args.price, args.order_type)

    print(f"- quote.current_price: {current_price}")
    print(f"- order_type: {args.order_type}")
    print(f"- resolved_price: {resolved_price}")

    if not args.execute:
        print("- 결과: READY (dry-run, no order sent)")
        return 0

    order_result = adapter.place_order(
        symbol=args.symbol,
        side=args.side,
        quantity=args.quantity,
        price=resolved_price,
        order_type=args.order_type,
    )
    print(f"- order_result: {order_result}")

    if str(order_result.get("status") or "").lower() not in ("success", "filled"):
        print("- 결과: FAIL | order not successful")
        return 1

    if args.cancel_after:
        order_id = str(order_result.get("order_id") or "").strip()
        if not order_id:
            print("- 결과: FAIL | order_id missing for cancel-after")
            return 1
        canceled = adapter.cancel_order(order_id, symbol=args.symbol)
        print(f"- cancel_after: {canceled}")
        if not canceled:
            print("- 결과: FAIL | cancel failed")
            return 1

    print("- 결과: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
