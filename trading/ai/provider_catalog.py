#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human-facing provider/model price snapshot. Prices are guidance, never billing truth."""

from __future__ import annotations

from typing import Any, Dict, List

from .model_registry import MODEL_REGISTRY, STATUS_LABELS, selectable_models


PRICE_SNAPSHOT_AS_OF = "2026-09-11"

OFFICIAL_PRICING_URLS = {
    "openai": "https://developers.openai.com/api/docs/models",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "kimi": "https://platform.kimi.ai/docs/pricing/chat",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
}

PROVIDER_PRICE_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "openai": [
        {"model": "gpt-6-astra", "input": 10.00, "output": 50.00, "use": "최상위 정밀형", "strength": "가장 복잡한 추론·장문 전략 검토", "limitation": "높은 비용·빈번 호출 비권장"},
        {"model": "gpt-5.6-luna", "input": 0.20, "output": 1.20, "use": "절약형", "strength": "대량·반복 구조화와 짧은 도움말", "limitation": "최고 난도 장문 추론에는 부적합"},
        {"model": "gpt-5.6-terra", "input": 2.00, "output": 12.00, "use": "균형형", "strength": "품질·속도·비용 균형", "limitation": "단순 반복 작업에는 Luna보다 비쌈"},
        {"model": "gpt-5.6-sol", "input": 4.00, "output": 20.00, "use": "정밀형", "strength": "복잡한 전문 분석과 전략 검토", "limitation": "빈번한 일반 질문에는 과한 비용"},
    ],
    "deepseek": [
        {"model": "deepseek-v4-flash", "input": 0.44, "output": 1.32, "use": "절약형·표준형", "strength": "저비용 텍스트·JSON 구조화", "limitation": "이미지 입력 미지원", "note": "피크·캐시 미적중 보수 추정; 비피크/캐시 적중은 더 낮을 수 있음"},
        {"model": "deepseek-v4-pro", "input": 1.32, "output": 3.96, "use": "정밀형", "strength": "복합 텍스트 추론", "limitation": "Flash보다 비용·지연 증가", "note": "피크·캐시 미적중 보수 추정; 비피크/캐시 적중은 더 낮을 수 있음"},
        {"model": "deepseek-v4-flash-vision-exp", "input": 0.44, "output": 1.32, "use": "차트·이미지 실험형", "strength": "이미지 입력 실험 연동", "limitation": "계정 제공 여부와 안정성 확인 필요", "note": "피크 보수 추정; 이미지 토큰 포함·실험형"},
    ],
    "kimi": [
        {"model": "kimi-k2.6", "input": 0.95, "output": 4.00, "use": "절약형·텍스트/JSON/비전", "strength": "장문·비전의 비용 균형", "limitation": "계정 모델 권한 확인 필요", "note": "캐시 미적중 입력"},
        {"model": "kimi-k3", "input": None, "output": None, "use": "정밀형·장문 추론/비전", "strength": "장문 추론과 비전", "limitation": "단가를 앱이 확정하지 않음", "note": "공식 가격 페이지에서 확인"},
    ],
    "anthropic": [
        {"model": "claude-haiku-4-5", "input": 1.00, "output": 5.00, "use": "절약형", "strength": "빠른 텍스트·JSON 응답", "limitation": "NoahAI 어댑터의 이미지 입력은 미지원"},
        {"model": "claude-sonnet-5", "input": 2.00, "output": 10.00, "use": "균형형", "strength": "속도와 지능의 균형", "limitation": "NoahAI 어댑터의 이미지 입력은 미지원", "note": "공식 표준 가격"},
        {"model": "claude-opus-5", "input": 5.00, "output": 25.00, "use": "정밀형", "strength": "복잡한 전문·에이전트 작업", "limitation": "비용과 지연이 큼"},
        {"model": "claude-fable-5-1", "input": 10.00, "output": 50.00, "use": "최상위 정밀형", "strength": "가장 까다로운 장기 추론", "limitation": "가장 높은 비용·일반 질문 비권장"},
    ],
    "gemini": [
        {"model": "gemini-3.5-flash-lite", "input": 0.30, "output": 2.50, "use": "절약형", "strength": "대량·저지연 멀티모달", "limitation": "복잡한 장기 추론에는 부적합"},
        {"model": "gemini-3.8-flash", "input": 0.75, "output": 3.75, "use": "최신 균형형", "strength": "복잡한 멀티모달·장기 작업", "limitation": "프로모션 종료 뒤 단가 변경 예정", "note": "2026-12-31까지 Standard 소개 가격"},
        {"model": "gemini-3.7-flash", "input": 0.75, "output": 3.75, "use": "균형형", "strength": "빠른 다단계·도구 작업", "limitation": "3.8 이전 세대", "note": "2026-12-31까지 Standard 소개 가격"},
        {"model": "gemini-3.6-flash", "input": 0.75, "output": 3.75, "use": "호환형", "strength": "멀티모달 범용 작업", "limitation": "이전 세대", "note": "2026-12-31까지 Standard 소개 가격"},
        {"model": "gemini-3.5-flash", "input": 1.50, "output": 9.00, "use": "호환형", "strength": "일반 고처리량 멀티모달", "limitation": "최신 Flash보다 가격 효율이 낮을 수 있음"},
        {"model": "gemini-3.1-pro-preview", "input": 2.00, "output": 12.00, "use": "정밀형", "strength": "복잡한 문제 해결", "limitation": "Preview·계정 권한 확인 필요", "note": "20만 토큰 이하"},
    ],
}


def provider_price_rows(provider: str) -> List[Dict[str, Any]]:
    return [dict(row) for row in PROVIDER_PRICE_CATALOG.get(str(provider or "").lower(), [])]


def model_catalog_details(provider: str, *, capability: str | None = None) -> List[Dict[str, Any]]:
    """Return secret-free UI guidance for models NoahAI can route to.

    The static catalog is a dated compatibility snapshot, not proof that the
    user's provider account can call a model.  Account availability remains a
    separate, explicit provider diagnostic.
    """
    provider_key = str(provider or "").strip().lower()
    prices = {str(row.get("model")): row for row in provider_price_rows(provider_key)}
    registry = {str(row.get("model")): row for row in MODEL_REGISTRY.get(provider_key, [])}
    details: List[Dict[str, Any]] = []
    if capability:
        models = selectable_models(provider_key, capability=capability)
    else:
        models = []
        for record in MODEL_REGISTRY.get(provider_key, []):
            if str(record.get("status") or "") not in {"retired"}:
                model = str(record.get("model") or "")
                if model and model not in models:
                    models.append(model)
    for model in models:
        record = dict(registry.get(model) or {})
        price = dict(prices.get(model) or {})
        details.append({
            "model": model,
            "status": str(record.get("status") or "unknown"),
            "status_label": STATUS_LABELS.get(str(record.get("status") or "unknown"), "계정 확인 필요"),
            "capabilities": list(record.get("capabilities") or ()),
            "replacement": str(record.get("replacement") or ""),
            "note": str(price.get("note") or record.get("note") or ""),
            "use": str(price.get("use") or "용도는 실제 연결 점검 후 확인"),
            "strength": str(price.get("strength") or "NoahAI 호환 목록에 등록됨"),
            "limitation": str(price.get("limitation") or "계정 제공 여부와 공식 문서 확인 필요"),
            "input_per_mtok_usd": price.get("input"),
            "output_per_mtok_usd": price.get("output"),
        })
    return details


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
