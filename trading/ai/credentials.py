#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 제공사 API 키의 안전한 참조 저장소.

설정 JSON에는 비밀값 대신 ``keyring://`` 참조만 남긴다. 기존
``openai_api_key`` 평문 설정은 keyring이 준비된 환경에서 저장 시
자동 이전하며, 이전에 실패하면 기존 사용자의 실행을 깨뜨리지 않는다.
"""

from __future__ import annotations

import copy
import getpass
import re
from typing import Any, Dict, Optional, Tuple


SERVICE_NAME = "NoahAI"
REFERENCE_PREFIX = "keyring://NoahAI/"
_SAFE_PART = re.compile(r"[^a-zA-Z0-9_.-]+")
_ALPHA_CREDENTIAL_FIELDS = {
    "deepseek": ("deepseek_api_key", "alphaarena_deepseek_api_key"),
    "qwen": ("qwen_api_key", "alphaarena_alibaba_api_key"),
    "openai": ("", "alphaarena_openai_api_key"),
    "anthropic": ("", "alphaarena_anthropic_api_key"),
    "google": ("", "alphaarena_google_api_key"),
    "xai": ("", "alphaarena_xai_api_key"),
}


class CredentialStoreError(RuntimeError):
    """운영체제 보안 저장소를 사용할 수 없을 때 발생한다."""


def _keyring_module():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception as exc:  # pragma: no cover - 설치 환경에 따라 달라짐
        raise CredentialStoreError(
            "운영체제 보안 저장소(keyring)를 사용할 수 없습니다. "
            "requirements.txt 의 keyring 패키지를 설치해 주세요."
        ) from exc


def _account_name() -> str:
    try:
        from path_utils import get_current_user_account

        value = str(get_current_user_account() or "").strip()
        if value:
            return value
    except Exception:
        pass
    return getpass.getuser() or "default"


def _safe_part(value: str) -> str:
    normalized = _SAFE_PART.sub("-", str(value or "").strip()).strip("-")
    return normalized or "default"


def credential_reference(provider: str, account: Optional[str] = None) -> str:
    username = f"{_safe_part(account or _account_name())}.{_safe_part(provider)}"
    return f"{REFERENCE_PREFIX}{username}"


def _username_from_reference(reference: str) -> str:
    value = str(reference or "").strip()
    if not value.startswith(REFERENCE_PREFIX):
        raise CredentialStoreError("지원하지 않는 credential_ref 형식입니다.")
    username = value[len(REFERENCE_PREFIX):].strip()
    if not username or "/" in username or "\\" in username:
        raise CredentialStoreError("잘못된 credential_ref입니다.")
    return username


def store_credential(
    provider: str,
    secret: str,
    *,
    reference: Optional[str] = None,
    account: Optional[str] = None,
) -> str:
    value = str(secret or "").strip()
    if not value:
        raise CredentialStoreError("저장할 API 키가 비어 있습니다.")
    ref = reference or credential_reference(provider, account=account)
    username = _username_from_reference(ref)
    try:
        _keyring_module().set_password(SERVICE_NAME, username, value)
    except CredentialStoreError:
        raise
    except Exception as exc:
        raise CredentialStoreError("운영체제 보안 저장소에 API 키를 저장하지 못했습니다.") from exc
    return ref


def resolve_credential(reference: str) -> str:
    username = _username_from_reference(reference)
    try:
        return str(_keyring_module().get_password(SERVICE_NAME, username) or "")
    except CredentialStoreError:
        raise
    except Exception as exc:
        raise CredentialStoreError("운영체제 보안 저장소에서 API 키를 읽지 못했습니다.") from exc


def hydrate_ai_credentials(settings: Dict[str, Any]) -> Dict[str, Any]:
    """credential_ref를 런타임 메모리의 ``api_key``로 해석한다.

    반환값은 실행용 복사본이다. 이 객체를 저장하더라도
    :func:`prepare_ai_credentials_for_storage`가 다시 비밀값을 제거한다.
    """
    hydrated = copy.deepcopy(settings or {})
    credentials = hydrated.get("ai_credentials")
    if not isinstance(credentials, dict):
        credentials = {}
        hydrated["ai_credentials"] = credentials

    for provider, raw_cfg in list(credentials.items()):
        if not isinstance(raw_cfg, dict):
            continue
        cfg = raw_cfg
        reference = str(cfg.get("credential_ref") or "").strip()
        if reference and not str(cfg.get("api_key") or "").strip():
            try:
                cfg["api_key"] = resolve_credential(reference)
            except CredentialStoreError:
                cfg["api_key"] = ""

    active_provider = str(hydrated.get("ai_provider") or "openai").strip().lower()
    active_cfg = credentials.get(active_provider, {})
    if isinstance(active_cfg, dict):
        active_key = str(active_cfg.get("api_key") or "").strip()
        if active_key:
            # 기존 코드가 그대로 실행되도록 런타임에서만 레거시 키를 채운다.
            hydrated["openai_api_key"] = active_key
        if active_cfg.get("base_url") is not None:
            hydrated["openai_base_url"] = str(active_cfg.get("base_url") or "")

    # 최초 이전 전 기존 OpenAI 설정은 OpenAI credential 런타임 항목으로 보인다.
    legacy_key = str(hydrated.get("openai_api_key") or "").strip()
    if legacy_key and "openai" not in credentials:
        credentials["openai"] = {
            "api_key": legacy_key,
            "base_url": str(hydrated.get("openai_base_url") or ""),
        }

    alpha = hydrated.get("alpha_arena")
    if isinstance(alpha, dict):
        refs = alpha.get("credential_refs", {})
        if isinstance(refs, dict):
            for provider, (nested_key, legacy_field) in _ALPHA_CREDENTIAL_FIELDS.items():
                reference = str(refs.get(provider) or "").strip()
                if not reference:
                    continue
                try:
                    secret = resolve_credential(reference)
                except CredentialStoreError:
                    secret = ""
                if nested_key:
                    alpha[nested_key] = secret
                if legacy_field:
                    hydrated[legacy_field] = secret
    return hydrated


def prepare_ai_credentials_for_storage(
    settings: Dict[str, Any],
    *,
    strict: bool = False,
) -> Tuple[Dict[str, Any], list[str]]:
    """AI 비밀값을 keyring으로 이동하고 JSON 저장용 복사본을 반환한다."""
    stored = copy.deepcopy(settings or {})
    warnings: list[str] = []
    credentials = stored.get("ai_credentials")
    if not isinstance(credentials, dict):
        credentials = {}
        stored["ai_credentials"] = credentials

    active_provider = str(stored.get("ai_provider") or "openai").strip().lower()
    legacy_key = str(stored.get("openai_api_key") or "").strip()
    legacy_injected_provider = ""
    if legacy_key:
        target = active_provider if active_provider in credentials else "openai"
        target_cfg = credentials.setdefault(target, {})
        if isinstance(target_cfg, dict) and not str(target_cfg.get("api_key") or "").strip():
            target_cfg["api_key"] = legacy_key
            legacy_injected_provider = target
            if target == "openai":
                target_cfg.setdefault("base_url", str(stored.get("openai_base_url") or ""))

    for provider, raw_cfg in list(credentials.items()):
        if not isinstance(raw_cfg, dict):
            continue
        cfg = raw_cfg
        secret = str(cfg.get("api_key") or "").strip()
        reference = str(cfg.get("credential_ref") or "").strip()
        if secret:
            try:
                reference = store_credential(
                    str(provider),
                    secret,
                    reference=reference or None,
                )
                cfg["credential_ref"] = reference
                cfg.pop("api_key", None)
            except CredentialStoreError as exc:
                message = f"{provider} API 키 보안 저장 실패: {exc}"
                warnings.append(message)
                if str(provider) == legacy_injected_provider:
                    # 보안 저장소가 없을 때 레거시 평문을 중복 저장하지 않는다.
                    cfg.pop("api_key", None)
                if strict:
                    raise
        elif reference:
            cfg.pop("api_key", None)

    alpha = stored.get("alpha_arena")
    if isinstance(alpha, dict):
        refs = alpha.get("credential_refs")
        if not isinstance(refs, dict):
            refs = {}
            alpha["credential_refs"] = refs
        for provider, (nested_key, legacy_field) in _ALPHA_CREDENTIAL_FIELDS.items():
            nested_secret = str(alpha.get(nested_key) or "").strip() if nested_key else ""
            legacy_secret = str(stored.get(legacy_field) or "").strip() if legacy_field else ""
            secret = nested_secret or legacy_secret
            reference = str(refs.get(provider) or "").strip()
            if secret:
                try:
                    reference = store_credential(
                        f"alphaarena-{provider}",
                        secret,
                        reference=reference or None,
                    )
                    refs[provider] = reference
                    if nested_key:
                        alpha[nested_key] = ""
                    if legacy_field:
                        stored[legacy_field] = ""
                except CredentialStoreError as exc:
                    warnings.append(f"AlphaArena {provider} API 키 보안 저장 실패: {exc}")
                    if strict:
                        raise

    active_cfg = credentials.get(active_provider, {})
    if isinstance(active_cfg, dict) and active_cfg.get("credential_ref"):
        # 레거시 키 이름은 유지하되 비밀값은 디스크에 중복 저장하지 않는다.
        stored["openai_api_key"] = ""
    return stored, warnings
