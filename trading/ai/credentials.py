#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 제공사 API 키의 v3.9.0.4 호환 저장 계약.

v3.9.0.3 후보는 AI 키만 운영체제 keyring으로 자동 이전했지만, 이는
기존 거래소·증권사 키의 로컬 설정 정책 및 무설치 배포 원칙과 달랐다.
v3.9.0.4는 운영체제 보안 저장소에 의존하지 않고 다른 API 키와 동일하게
사용자별 ``settings.json``에 저장한다.

과거 ``credential_ref``는 설정을 열거나 저장하는 것만으로 삭제하지 않는다.
해당 참조만 있고 로컬 키가 없는 사용자는 AI 키를 한 번 다시 입력하면
새 로컬 키가 정본이 되고 오래된 참조는 제거된다.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Tuple


REFERENCE_PREFIX = "keyring://NoahAI/"
_ALPHA_CREDENTIAL_FIELDS = {
    "deepseek": ("deepseek_api_key", "alphaarena_deepseek_api_key"),
    "qwen": ("qwen_api_key", "alphaarena_alibaba_api_key"),
    "openai": ("", "alphaarena_openai_api_key"),
    "anthropic": ("", "alphaarena_anthropic_api_key"),
    "google": ("", "alphaarena_google_api_key"),
    "xai": ("", "alphaarena_xai_api_key"),
}


class CredentialStoreError(RuntimeError):
    """구버전 import 호환용 예외.

    v3.9.0.4 로컬 저장 경로에서는 이 예외를 발생시키지 않는다.
    """


def hydrate_ai_credentials(settings: Dict[str, Any]) -> Dict[str, Any]:
    """저장 설정을 AI 실행용 복사본으로 정규화한다.

    keyring 조회나 운영체제 인증을 수행하지 않는다. ``credential_ref``만
    남은 v3.9.0.3 설정은 보존하되 키가 있는 것처럼 가장하지 않는다.
    """
    hydrated = copy.deepcopy(settings or {})
    credentials = hydrated.get("ai_credentials")
    if not isinstance(credentials, dict):
        credentials = {}
        hydrated["ai_credentials"] = credentials

    legacy_key = str(hydrated.get("openai_api_key") or "").strip()
    openai_cfg = credentials.get("openai")
    if not isinstance(openai_cfg, dict):
        openai_cfg = {}
        credentials["openai"] = openai_cfg
    if legacy_key and not str(openai_cfg.get("api_key") or "").strip():
        openai_cfg["api_key"] = legacy_key
        openai_cfg.setdefault("base_url", str(hydrated.get("openai_base_url") or ""))

    active_provider = str(hydrated.get("ai_provider") or "openai").strip().lower()
    active_cfg = credentials.get(active_provider, {})
    if isinstance(active_cfg, dict):
        active_key = str(active_cfg.get("api_key") or "").strip()
        if active_key:
            hydrated["openai_api_key"] = active_key
        if active_cfg.get("base_url") is not None:
            hydrated["openai_base_url"] = str(active_cfg.get("base_url") or "")

    return hydrated


def prepare_ai_credentials_for_storage(
    settings: Dict[str, Any],
    *,
    strict: bool = False,
) -> Tuple[Dict[str, Any], list[str]]:
    """AI 키를 OS 의존성 없이 로컬 설정 구조로 정규화한다.

    ``strict``는 v3.9.0.3 호출부 호환을 위해 남겨 두며, 로컬 저장은 외부
    보안 저장소 실패가 없으므로 경고 목록은 항상 비어 있다.
    """
    del strict
    stored = copy.deepcopy(settings or {})
    credentials = stored.get("ai_credentials")
    if not isinstance(credentials, dict):
        credentials = {}
        stored["ai_credentials"] = credentials

    active_provider = str(stored.get("ai_provider") or "openai").strip().lower()
    legacy_key = str(stored.get("openai_api_key") or "").strip()
    if legacy_key:
        active_cfg = credentials.setdefault(active_provider, {})
        if isinstance(active_cfg, dict) and not str(active_cfg.get("api_key") or "").strip():
            active_cfg["api_key"] = legacy_key
            if active_provider == "openai":
                active_cfg.setdefault("base_url", str(stored.get("openai_base_url") or ""))

    for raw_cfg in credentials.values():
        if not isinstance(raw_cfg, dict):
            continue
        secret = str(raw_cfg.get("api_key") or "").strip()
        if secret:
            raw_cfg["api_key"] = secret
            # 사용자가 키를 다시 입력한 경우 로컬 키가 정본이다.
            raw_cfg.pop("credential_ref", None)

    active_cfg = credentials.get(active_provider, {})
    if isinstance(active_cfg, dict):
        stored["openai_api_key"] = str(active_cfg.get("api_key") or "").strip()

    # AlphaArena 역시 기존 로컬 필드를 정본으로 유지한다. 과거 참조는
    # 로컬 키가 확인된 provider에 대해서만 제거해 롤백 단서를 보존한다.
    alpha = stored.get("alpha_arena")
    if isinstance(alpha, dict):
        refs = alpha.get("credential_refs")
        if not isinstance(refs, dict):
            refs = {}
        for provider, (nested_key, legacy_field) in _ALPHA_CREDENTIAL_FIELDS.items():
            nested_secret = str(alpha.get(nested_key) or "").strip() if nested_key else ""
            legacy_secret = str(stored.get(legacy_field) or "").strip() if legacy_field else ""
            secret = nested_secret or legacy_secret
            if not secret:
                continue
            if nested_key:
                alpha[nested_key] = secret
            if legacy_field:
                stored[legacy_field] = secret
            refs.pop(provider, None)
        if refs:
            alpha["credential_refs"] = refs
        else:
            alpha.pop("credential_refs", None)

    return stored, []


def unresolved_credential_references(settings: Dict[str, Any]) -> list[str]:
    """로컬 키 없이 v3.9.0.3 참조만 남은 provider 목록을 반환한다."""
    unresolved: list[str] = []
    credentials = (settings or {}).get("ai_credentials")
    if isinstance(credentials, dict):
        for provider, raw_cfg in credentials.items():
            if not isinstance(raw_cfg, dict):
                continue
            if raw_cfg.get("credential_ref") and not str(raw_cfg.get("api_key") or "").strip():
                unresolved.append(str(provider))
    return sorted(set(unresolved))
