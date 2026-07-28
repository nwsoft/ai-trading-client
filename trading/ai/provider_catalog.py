#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human-facing provider/model price snapshot. Prices are guidance, never billing truth."""

from __future__ import annotations

from typing import Any, Dict, List


PRICE_SNAPSHOT_AS_OF = "2026-07-28"

OFFICIAL_PRICING_URLS = {
    "openai": "https://developers.openai.com/api/docs/models",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "kimi": "https://platform.moonshot.ai/docs",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
}

PROVIDER_PRICE_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "openai": [
        {"model": "gpt-5.6-luna", "input": 1.00, "output": 6.00, "use": "절약형"},
        {"model": "gpt-5.6-terra", "input": 2.50, "output": 15.00, "use": "균형형"},
        {"model": "gpt-5.6-sol", "input": 5.00, "output": 30.00, "use": "정밀형"},
    ],
    "deepseek": [
        {"model": "deepseek-v4-flash", "input": 0.14, "output": 0.28, "use": "절약형", "note": "캐시 미적중 입력"},
        {"model": "deepseek-v4-pro", "input": 0.435, "output": 0.87, "use": "정밀형", "note": "캐시 미적중 입력"},
    ],
    "kimi": [
        {"model": "kimi-k2.6", "input": 0.95, "output": 4.00, "use": "어시스턴트 절약형 시험", "note": "캐시 미적중 입력"},
        {"model": "kimi-k3", "input": None, "output": None, "use": "어시스턴트 정밀형 시험", "note": "공식 가격 페이지에서 확인"},
    ],
    "anthropic": [
        {"model": "claude-haiku-4-5", "input": 1.00, "output": 5.00, "use": "절약형"},
        {"model": "claude-sonnet-5", "input": 3.00, "output": 15.00, "use": "균형형", "note": "2026-08-31까지 소개 가격 별도"},
        {"model": "claude-opus-5", "input": 5.00, "output": 25.00, "use": "정밀형"},
        {"model": "claude-fable-5", "input": 10.00, "output": 50.00, "use": "최상위 정밀형"},
    ],
    "gemini": [
        {"model": "gemini-3.5-flash-lite", "input": 0.30, "output": 2.50, "use": "절약형"},
        {"model": "gemini-3.6-flash", "input": 1.50, "output": 7.50, "use": "균형형"},
        {"model": "gemini-3.1-pro-preview", "input": 2.00, "output": 12.00, "use": "정밀형", "note": "20만 토큰 이하"},
    ],
}


def provider_price_rows(provider: str) -> List[Dict[str, Any]]:
    return [dict(row) for row in PROVIDER_PRICE_CATALOG.get(str(provider or "").lower(), [])]


def format_provider_price_guide(provider: str) -> str:
    rows = provider_price_rows(provider)
    lines = [f"가격 참고 ({PRICE_SNAPSHOT_AS_OF}, USD / 100만 토큰)"]
    for row in rows:
        if row.get("input") is None:
            price = "공식 페이지 확인"
        else:
            price = f"입력 ${row['input']:g} · 출력 ${row['output']:g}"
        suffix = f" · {row['note']}" if row.get("note") else ""
        lines.append(f"{row['model']} | {row['use']} | {price}{suffix}")
    lines.append("실제 청구는 캐시·장문·배치·지역·서비스 티어에 따라 달라질 수 있습니다.")
    return "\n".join(lines)
