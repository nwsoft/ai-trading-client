#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 모델 수명주기, 기능, 계정 확인 상태를 한곳에서 관리한다.

정적 목록은 앱이 오프라인일 때 보여 주는 공식 기준 스냅샷이다. 실제 호출
가능 여부는 제공사의 ``list models`` 응답과 별도로 확인해야 한다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


CATALOG_AS_OF = "2026-07-28"

STATUS_LABELS = {
    "recommended": "권장",
    "available": "사용 가능",
    "preview": "미리보기",
    "deprecated": "비권장·종료 예정",
    "retired": "종료",
    "experimental": "NoahAI 시험 연동",
    "unknown": "계정 확인 필요",
}


def _entry(
    model: str,
    status: str,
    *,
    capabilities: Iterable[str] = ("chat_text", "chat_json"),
    replacement: str = "",
    note: str = "",
) -> Dict[str, Any]:
    return {
        "model": model,
        "status": status,
        "capabilities": tuple(capabilities),
        "replacement": replacement,
        "note": note,
    }


MODEL_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    "openai": [
        _entry("gpt-5.6-luna", "recommended", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.6-terra", "recommended", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.6-sol", "recommended", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.6", "available", capabilities=("chat_text", "chat_json", "vision"), note="gpt-5.6-sol 별칭"),
        _entry("gpt-5.5", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.4-nano", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.4-mini", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5.4", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5-mini", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-5", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-4.1-mini", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-4.1", "available", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gpt-4o-mini", "deprecated", capabilities=("chat_text", "chat_json", "vision"), replacement="gpt-5.6-luna"),
        _entry("gpt-4o", "deprecated", capabilities=("chat_text", "chat_json", "vision"), replacement="gpt-5.6-terra"),
        _entry("gpt-4o-mini-transcribe", "recommended", capabilities=("transcribe",)),
        _entry("gpt-4o-transcribe", "recommended", capabilities=("transcribe",)),
        _entry("gpt-4o-transcribe-diarize", "available", capabilities=("transcribe",), note="다중 화자 구분"),
    ],
    "deepseek": [
        _entry("deepseek-v4-flash", "recommended"),
        _entry("deepseek-v4-pro", "recommended"),
        _entry("deepseek-chat", "retired", replacement="deepseek-v4-flash"),
        _entry("deepseek-reasoner", "retired", replacement="deepseek-v4-flash"),
    ],
    "kimi": [
        _entry(
            "kimi-k3",
            "recommended",
            capabilities=("chat_text", "chat_json", "vision"),
            note="OpenAI 호환 정식 API · 계정별 모델 권한 확인",
        ),
        _entry(
            "kimi-k2.6",
            "available",
            capabilities=("chat_text", "chat_json", "vision"),
            note="텍스트·JSON·비전 지원 · 비용 절약 선택지",
        ),
        _entry("kimi-latest", "retired", replacement="kimi-k3"),
        _entry("kimi-k2", "retired", replacement="kimi-k2.6"),
    ],
    "anthropic": [
        # 현재 NoahAI Anthropic 어댑터는 텍스트/JSON만 구현한다. 모델 자체의
        # 외부 기능과 앱에서 실제 호출 가능한 capability를 섞어 표시하지 않는다.
        _entry("claude-haiku-4-5", "recommended", capabilities=("chat_text", "chat_json")),
        _entry("claude-sonnet-5", "recommended", capabilities=("chat_text", "chat_json")),
        _entry("claude-opus-5", "recommended", capabilities=("chat_text", "chat_json")),
        _entry("claude-fable-5", "available", capabilities=("chat_text", "chat_json")),
        _entry("claude-sonnet-4-6", "available", capabilities=("chat_text", "chat_json")),
        _entry("claude-opus-4-8", "available", capabilities=("chat_text", "chat_json")),
        _entry("claude-opus-4-7", "available", capabilities=("chat_text", "chat_json")),
    ],
    "gemini": [
        _entry("gemini-3.5-flash-lite", "recommended", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gemini-3.6-flash", "recommended", capabilities=("chat_text", "chat_json", "vision")),
        _entry("gemini-3.1-pro-preview", "preview", capabilities=("chat_text", "chat_json", "vision")),
        _entry(
            "gemini-3.1-flash-lite",
            "deprecated",
            capabilities=("chat_text", "chat_json", "vision"),
            replacement="gemini-3.5-flash-lite",
            note="2027-05-07 종료 예정",
        ),
        _entry("gemini-3.1-flash-lite-preview", "retired", replacement="gemini-3.1-flash-lite"),
        _entry("gemini-3-pro-preview", "retired", replacement="gemini-3.1-pro-preview"),
    ],
}


def model_record(provider: str, model: str) -> Dict[str, Any]:
    provider_key = str(provider or "").strip().lower()
    model_id = str(model or "").strip()
    for item in MODEL_REGISTRY.get(provider_key, []):
        if item["model"] == model_id:
            return dict(item)
    return _entry(model_id, "unknown")


def selectable_models(
    provider: str,
    *,
    capability: str = "chat_text",
    include_deprecated: bool = True,
    include_experimental: bool = True,
) -> List[str]:
    allowed_status = {"recommended", "available", "preview"}
    if include_deprecated:
        allowed_status.add("deprecated")
    if include_experimental:
        allowed_status.add("experimental")
    return [
        str(item["model"])
        for item in MODEL_REGISTRY.get(str(provider or "").lower(), [])
        if item.get("status") in allowed_status
        and capability in set(item.get("capabilities") or ())
    ]


def merge_account_models(
    provider: str,
    discovered: Optional[Iterable[str]],
    *,
    capability: str = "chat_text",
) -> List[Dict[str, Any]]:
    discovered_set = {str(value).strip() for value in (discovered or []) if str(value).strip()}
    records: List[Dict[str, Any]] = []
    seen = set()
    for model in selectable_models(provider, capability=capability):
        record = model_record(provider, model)
        record["account_available"] = model in discovered_set if discovered is not None else None
        records.append(record)
        seen.add(model)
    for model in sorted(discovered_set):
        if model in seen:
            continue
        record = model_record(provider, model)
        record["account_available"] = True
        records.append(record)
    return records


def model_status_text(
    provider: str,
    model: str,
    *,
    account_models: Optional[Iterable[str]] = None,
) -> str:
    record = model_record(provider, model)
    status = str(record.get("status") or "unknown")
    parts = [STATUS_LABELS.get(status, status)]
    if account_models is not None:
        parts.append("계정 확인됨" if model in set(account_models) else "계정에서 미확인")
    if record.get("replacement"):
        parts.append(f"대체 권장: {record['replacement']}")
    if record.get("note"):
        parts.append(str(record["note"]))
    return " · ".join(parts)


def validate_model_route(
    provider: str,
    model: str,
    *,
    capability: str,
    account_models: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    record = model_record(provider, model)
    errors: List[str] = []
    warnings: List[str] = []
    status = str(record.get("status") or "unknown")
    if status == "retired":
        errors.append(f"{model} 모델은 종료됐습니다.")
    if status == "deprecated":
        warnings.append(f"{model} 모델은 비권장 또는 종료 예정입니다.")
    if status == "preview":
        warnings.append(f"{model} 모델은 미리보기 버전입니다.")
    if status == "experimental":
        warnings.append(f"{model} 모델은 NoahAI 시험 연동 상태입니다.")
    capabilities = set(record.get("capabilities") or ())
    if status != "unknown" and capability not in capabilities:
        errors.append(f"{model} 모델은 {capability} 기능을 지원하지 않습니다.")
    if account_models is not None and model not in set(account_models):
        errors.append(f"{model} 모델이 해당 API 계정의 사용 가능 목록에 없습니다.")
    return {
        "ok": not errors,
        "provider": str(provider or "").lower(),
        "model": str(model or ""),
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "replacement": str(record.get("replacement") or ""),
    }
