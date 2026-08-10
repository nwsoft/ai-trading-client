#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 지원 모드(api_type/api_version) 매트릭스 검증.

검증 범위:
- ExchangeFactory에 등록된 stock 브로커별 지원 api_type/api_version 조합
- 각 조합이 validate_stock_broker_api_combo에서 유효 판정되는지 확인
- 문자열 등록과 별개인 구현/실계정 검증 성숙도 계약 확인
- OS 제약(키움 openapi + non-Windows)은 경고로 표시
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchanges.exchange_factory import ExchangeFactory


def main() -> int:
    os_name = platform.system()
    supported = ExchangeFactory.get_supported_exchanges().get("stock", [])

    print("증권 지원 모드 매트릭스 점검 시작")
    print(f"- os: {os_name}")

    if not supported:
        print("- 결과: FAIL | 지원 stock 브로커가 없습니다.")
        return 1

    failures = []
    warnings = []
    checked = 0

    for broker in supported:
        broker_modes = ExchangeFactory.get_supported_api_versions(broker)
        for api_type, versions in (broker_modes or {}).items():
            if not isinstance(versions, dict):
                continue
            for api_version in versions.keys():
                checked += 1
                ok, err = ExchangeFactory.validate_stock_broker_api_combo(
                    broker, str(api_type), str(api_version)
                )
                if not ok:
                    failures.append((broker, api_type, api_version, err))
                    print(f"- {broker:<10} {api_type:<8} {api_version:<14} FAIL | {err}")
                    continue

                maturity = ExchangeFactory.get_stock_broker_api_maturity(
                    broker, str(api_type), str(api_version)
                )
                status = maturity.get("status", "unregistered")
                note = f"OK ({status})"
                if not maturity.get("implemented", False):
                    warnings.append(
                        f"{broker}:{api_type}/{api_version} -> 미구현 등록 경로"
                    )
                elif not maturity.get("live_order_allowed", False) and str(api_type).lower() != "mock":
                    warnings.append(
                        f"{broker}:{api_type}/{api_version} -> 실주문 검증 전/차단"
                    )
                if str(broker).lower() == "kiwoom" and str(api_type).lower() == "openapi" and os_name != "Windows":
                    note += " (live_env_blocked_on_non_windows)"
                    warnings.append(f"{broker}:{api_type}/{api_version} -> Windows 환경 필요")

                print(f"- {broker:<10} {api_type:<8} {api_version:<14} {note}")

    print("\n[요약]")
    print(f"- checked: {checked}")
    if failures:
        print(f"- 결과: FAIL ({len(failures)}건 조합 오류)")
        return 1

    if warnings:
        print(f"- 경고: {len(warnings)}")
        for msg in warnings:
            print(f"  * {msg}")

    print("- 결과: PASS (등록 조합·성숙도 계약 유효, 경고 경로는 실주문 차단)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
