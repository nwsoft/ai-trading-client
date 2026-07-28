#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 빌드/테스터가 실행할 수 있는 멀티 Provider 기능 사전점검."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from .credentials import hydrate_ai_credentials
from .provider_router import AIProviderRouter, normalize_model_route


ROLE_CAPABILITIES = {
    "analyst": "chat_json",
    "assistant": "chat_text",
    "frequent_cheap": "chat_json",
    "standard": "chat_json",
    "premium": "chat_json",
}


def _configured_routes(settings: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    provider = str(settings.get("ai_provider") or "openai")
    model = str(settings.get("openai_model") or "gpt-5.6-luna")
    profiles = settings.get("ai_provider_profiles", {})
    routes: Dict[str, Dict[str, str]] = {}
    for workload in ("analyst", "assistant"):
        raw = profiles.get(workload) if isinstance(profiles, dict) else None
        routes[workload] = normalize_model_route(
            raw,
            fallback_provider=provider,
            fallback_model=(
                str(settings.get("assistant_ai_model") or model)
                if workload == "assistant"
                else model
            ),
        )
    roles = settings.get("ai_model_roles", {})
    for workload in ("frequent_cheap", "standard", "premium"):
        routes[workload] = normalize_model_route(
            roles.get(workload) if isinstance(roles, dict) else None,
            fallback_provider=routes["analyst"]["provider"],
            fallback_model=routes["analyst"]["model"],
        )
    return routes


def run_ai_provider_preflight(
    settings: Dict[str, Any],
    *,
    audio_path: Optional[str] = None,
    workloads: Optional[Iterable[str]] = None,
    perform_calls: bool = True,
) -> Dict[str, Any]:
    """모델 목록·텍스트·JSON·사용량·오류 계약과 선택적 전사를 점검한다."""
    runtime = hydrate_ai_credentials(settings)
    routes = _configured_routes(runtime)
    requested = set(workloads or routes)
    results: Dict[str, Any] = {}

    for workload, route in routes.items():
        if workload not in requested:
            continue
        capability = ROLE_CAPABILITIES[workload]
        if route["provider"] == "kimi" and workload != "assistant":
            results[workload] = {
                "ok": False,
                "status": "blocked",
                "provider": route["provider"],
                "model": route["model"],
                "error": "Kimi는 NoahAI 실제 키 검증 전까지 어시스턴트 역할만 허용됩니다.",
            }
            continue
        try:
            router = AIProviderRouter.from_settings(runtime, workload=workload)
            validation = router.validate_model(
                capability=capability,
                verify_account=True,
            )
            item: Dict[str, Any] = {
                "ok": bool(validation.get("ok")),
                "status": "verified" if validation.get("ok") else "failed",
                "provider": route["provider"],
                "model": route["model"],
                "validation": validation,
            }
            if perform_calls and validation.get("ok"):
                if capability == "chat_json":
                    response = router.adapter.chat_json(
                        "Return one JSON object only.",
                        '{"ping":"Reply with {\\"ok\\":true}"}',
                        max_tokens=64,
                    )
                else:
                    response = router.adapter.chat_text(
                        "Reply with NOAHAI_OK only.",
                        "connection test",
                        max_tokens=32,
                    )
                item["response_ok"] = bool(response.ok)
                item["usage"] = dict(response.usage or {})
                item["normalized_error"] = (
                    vars(response.error) if response.error is not None else None
                )
                item["ok"] = bool(
                    response.ok
                    and response.usage.get("provider") == route["provider"]
                    and response.usage.get("model") == route["model"]
                )
                item["status"] = "verified" if item["ok"] else "failed"
            results[workload] = item
        except Exception as exc:
            results[workload] = {
                "ok": False,
                "status": "failed",
                "provider": route["provider"],
                "model": route["model"],
                "error": str(exc) or exc.__class__.__name__,
            }

    transcription_cfg = dict(runtime.get("ai_custom_transcription", {}) or {})
    if transcription_cfg.get("enabled", True):
        try:
            router = AIProviderRouter.from_settings(runtime, workload="transcription")
            validation = router.validate_model(
                capability="transcribe",
                verify_account=True,
            )
            transcription_result: Dict[str, Any] = {
                "ok": bool(validation.get("ok")),
                "status": "model_verified" if validation.get("ok") else "failed",
                "provider": router.spec.provider,
                "model": router.adapter.model,
                "validation": validation,
            }
            if audio_path and validation.get("ok"):
                text = router.client_facade().transcribe_audio(
                    audio_path,
                    model=router.adapter.model,
                )
                transcription_result["ok"] = bool(str(text or "").strip())
                transcription_result["status"] = (
                    "verified" if transcription_result["ok"] else "failed"
                )
                transcription_result["text_length"] = len(str(text or ""))
                transcription_result["normalized_error"] = (
                    router.adapter.client.get_last_error() or None
                )
            elif validation.get("ok"):
                transcription_result["status"] = "audio_sample_required"
                transcription_result["ok"] = False
            results["transcription"] = transcription_result
        except Exception as exc:
            results["transcription"] = {
                "ok": False,
                "status": "failed",
                "provider": "openai",
                "model": str(transcription_cfg.get("model") or ""),
                "error": str(exc) or exc.__class__.__name__,
            }

    required = [
        item for key, item in results.items()
        if key != "transcription" or audio_path
    ]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": bool(required) and all(bool(item.get("ok")) for item in required),
        "results": results,
    }

