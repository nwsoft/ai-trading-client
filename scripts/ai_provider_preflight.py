#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""저장된 사용자 설정으로 멀티 AI API 실제 기능을 점검한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import load_settings
from trading.ai.preflight import run_ai_provider_preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="", help="점검할 사용자 계정 데이터 디렉터리")
    parser.add_argument("--audio", default="", help="전사 검증용 짧은 음성 파일")
    parser.add_argument("--models-only", action="store_true", help="유료 텍스트/JSON 호출 생략")
    parser.add_argument("--output", default="", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    if args.account:
        from path_utils import set_current_user_account
        set_current_user_account(args.account)

    report = run_ai_provider_preflight(
        load_settings(persist_migrations=False),
        audio_path=args.audio or None,
        perform_calls=not args.models_only,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
