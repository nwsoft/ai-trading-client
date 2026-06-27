#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""무키(mock) 기반 증권 고도화 점검 스크립트.

실계정 키 없이도 4개 증권사(키움/신한/미래에셋/한국투자)의 공통 플로우를
factory -> adapter -> connect/list/balance/order까지 검증한다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchanges.exchange_factory import ExchangeFactory


def _mock_settings_for(broker: str) -> dict:
    return {
        "enabled_stock_brokers": [broker],
        "stock_broker_configs": {
            broker: {
                "enabled": True,
                "api_type": "mock",
                "api_version": "mock",
                "allow_live_order": False,
                "id": "",
                "password": "",
                "cert_password": "",
                "account_no": "",
            }
        },
    }


def _run_one(broker: str) -> tuple[bool, str]:
    try:
        adapter = ExchangeFactory.create_stock_exchange(broker, _mock_settings_for(broker))
        if not adapter.connect():
            return False, "connect failed"

        stocks = adapter.get_stock_list("KOSPI")
        etfs = adapter.get_etf_list()
        balance = adapter.get_balance()

        if not stocks or not etfs:
            return False, "empty stock/etf list"
        if not isinstance(balance, dict) or balance.get("status") != "ok":
            return False, "balance not ok"

        first = stocks[0]
        price = float(first.get("current_price") or 10000)
        order = adapter.place_order(str(first.get("code")), "BUY", 1, price)
        if order.get("status") != "filled":
            return False, f"order failed: {order}"

        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    print("무키(mock) 증권 고도화 점검 시작")
    failures = []
    for broker in ("kiwoom", "shinhan", "miraeAsset", "koreaInvestment"):
        ok, msg = _run_one(broker)
        print(f"- {broker:<10} : {'OK' if ok else 'FAIL'} | {msg}")
        if not ok:
            failures.append((broker, msg))

    if failures:
        print("\n결과: FAIL")
        return 1

    print("\n결과: PASS (키 없이도 공통 경로 정상)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
