#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI/DeepSeek/Kimi 연결 계약을 비밀값 노출 없이 확인한다.

환경 변수:
  OPENAI_API_KEY, DEEPSEEK_API_KEY, MOONSHOT_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.ai.provider_router import AIProviderRouter  # noqa: E402


KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="NoahAI AI 제공사 모델 조회/인증 검증")
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=sorted(KEY_ENV),
        default=["openai", "deepseek"],
    )
    parser.add_argument(
        "--require-configured",
        action="store_true",
        help="요청한 제공사의 환경 변수가 없으면 실패로 처리",
    )
    args = parser.parse_args()

    results = []
    failed = False
    for provider in args.providers:
        env_name = KEY_ENV[provider]
        api_key = str(os.getenv(env_name, "") or "").strip()
        if not api_key:
            results.append({
                "provider": provider,
                "ok": False,
                "skipped": True,
                "reason": f"{env_name} not configured",
            })
            failed = failed or args.require_configured
            continue
        result = AIProviderRouter(provider, api_key=api_key).health_check()
        # 모델 ID와 정규화 오류만 출력하며 키는 절대 출력하지 않는다.
        results.append(result)
        failed = failed or not bool(result.get("ok"))

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
