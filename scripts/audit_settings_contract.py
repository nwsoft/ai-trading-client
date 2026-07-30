#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""설정 파일을 비밀값 없이 감사하는 v3.9.0.4 운영 도구."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings_contract import audit_settings_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="NoahAI 설정 정본 감사")
    parser.add_argument(
        "settings_file",
        nargs="?",
        default=str(PROJECT_ROOT / "config" / "settings_template.json"),
        help="감사할 settings JSON 경로",
    )
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    path = Path(args.settings_file).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        settings = json.load(handle)
    report = audit_settings_contract(settings)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if any(item["level"] == "error" for item in report["issues"]) else 0

    print(f"설정 파일: {path}")
    print(f"정본: {report['schema_version']} / 실행 모드: {report['mode']}")
    print(
        "분석·학습 거래소: "
        f"{report['enabled_exchanges_count']} / 실제 주문 거래소: "
        f"{report['trade_enabled_exchanges_count']}"
    )
    print(f"호환 보관 설정: {report['archived_legacy_count']}")
    if not report["issues"]:
        print("결과: 정본 모순 없음")
    else:
        for item in report["issues"]:
            print(f"{item['level'].upper()}: {item['message']} ({item['code']})")
    return 1 if any(item["level"] == "error" for item in report["issues"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
