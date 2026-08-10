#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NoahAI 멀티 AI 제공사 라우터와 공통 응답 계약."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .credentials import hydrate_ai_credentials
from .anthropic_client import AnthropicClient
from .model_registry import selectable_models, validate_model_route
from .openai_client import OpenAIClient


@dataclass(frozen=True)
class ProviderCapabilities:
    chat_text: bool = True
    chat_json: bool = True
    list_models: bool = True
    usage: bool = True
    vision: bool = False
    transcribe: bool = False
    structured_output: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    label: str
    base_url: Optional[str]
    default_model: str
    model_prefixes: tuple[str, ...]
    fallback_models: tuple[str, ...]
    capabilities: ProviderCapabilities
    status: str = "stable"


@dataclass
class NormalizedProviderError:
    provider: str
    code: str
    message: str
    status_code: Optional[int] = None
    retryable: bool = False


@dataclass
class ProviderResponse:
    provider: str
    model: str
    content: Any = None
    finish_reason: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    error: Optional[NormalizedProviderError] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.content is not None


PROVIDER_SPECS: Dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        provider="openai",
        label="OpenAI",
        base_url=None,
        default_model="gpt-5.6-luna",
        model_prefixes=("gpt-", "o1", "o3", "o4"),
        fallback_models=tuple(selectable_models("openai")),
        capabilities=ProviderCapabilities(
            vision=True,
            transcribe=True,
            structured_output=True,
        ),
    ),
    "deepseek": ProviderSpec(
        provider="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        model_prefixes=("deepseek-",),
        fallback_models=tuple(selectable_models("deepseek")),
        capabilities=ProviderCapabilities(structured_output=True),
    ),
    "kimi": ProviderSpec(
        provider="kimi",
        label="Kimi (Moonshot AI)",
        base_url="https://api.moonshot.ai/v1",
        default_model="kimi-k3",
        model_prefixes=("kimi-", "moonshot-"),
        fallback_models=tuple(selectable_models("kimi")),
        capabilities=ProviderCapabilities(
            vision=True,
            structured_output=True,
        ),
        status="stable",
    ),
    "anthropic": ProviderSpec(
        provider="anthropic",
        label="Anthropic Claude",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-5",
        model_prefixes=("claude-",),
        fallback_models=tuple(selectable_models("anthropic")),
        capabilities=ProviderCapabilities(
            vision=False,
            transcribe=False,
            structured_output=False,
        ),
    ),
    "gemini": ProviderSpec(
        provider="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.6-flash",
        model_prefixes=("gemini-",),
        fallback_models=tuple(selectable_models("gemini")),
        capabilities=ProviderCapabilities(
            vision=True,
            transcribe=False,
            structured_output=True,
        ),
    ),
}


def provider_capability_schema() -> Dict[str, Dict[str, Any]]:
    return {
        name: {
            "label": spec.label,
            "status": spec.status,
            "capabilities": spec.capabilities.to_dict(),
        }
        for name, spec in PROVIDER_SPECS.items()
    }


def normalize_model_route(
    value: Any,
    *,
    fallback_provider: str,
    fallback_model: str,
) -> Dict[str, str]:
    """레거시 모델 문자열과 새 ``{provider, model}`` 값을 같은 형식으로 만든다."""
    provider = str(fallback_provider or "openai").strip().lower()
    model = str(fallback_model or "").strip()
    if isinstance(value, dict):
        provider = str(value.get("provider") or provider).strip().lower()
        model = str(value.get("model") or model).strip()
    elif str(value or "").strip():
        model = str(value).strip()
    if provider not in PROVIDER_SPECS:
        provider = "openai"
    if not model:
        model = PROVIDER_SPECS[provider].default_model
    return {"provider": provider, "model": model}


class OpenAICompatibleAdapter:
    """OpenAI Chat Completions 호환 제공사를 공통 클라이언트로 연결한다."""

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.model = str(model or spec.default_model)
        client_base_url = base_url if base_url is not None else spec.base_url
        if spec.provider == "anthropic":
            self.client = AnthropicClient(
                api_key=api_key,
                model=self.model,
                base_url=client_base_url,
                provider=spec.provider,
            )
        else:
            self.client = OpenAIClient(
                api_key=api_key,
                model=self.model,
                base_url=client_base_url,
                provider=spec.provider,
            )

    def is_ready(self) -> bool:
        return self.client.is_ready()

    def list_models(
        self,
        *,
        include_fallback: bool = True,
        capability: str = "chat_text",
    ) -> List[str]:
        if capability == "transcribe" and hasattr(self.client, "list_transcription_models"):
            discovered = self.client.list_transcription_models()
            fallback = selectable_models(self.spec.provider, capability="transcribe")
        else:
            discovered = self.client.list_chat_models(allowed_prefixes=self.spec.model_prefixes)
            fallback = list(self.spec.fallback_models)
        if discovered or not include_fallback:
            return list(dict.fromkeys(discovered))
        return list(fallback)

    def health_check(self) -> Dict[str, Any]:
        if not self.is_ready():
            return {
                "ok": False,
                "provider": self.spec.provider,
                "error": {"code": "credential_missing", "message": "API 키가 없거나 클라이언트를 초기화하지 못했습니다."},
            }
        models = self.client.list_chat_models(allowed_prefixes=self.spec.model_prefixes)
        error = self.client.get_last_error()
        if error:
            return {"ok": False, "provider": self.spec.provider, "error": error}
        return {"ok": True, "provider": self.spec.provider, "models": models}

    def chat_text(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> ProviderResponse:
        model = str(kwargs.pop("model", None) or self.model)
        content = self.client.chat(system_prompt, user_prompt, model=model, **kwargs)
        error = self._normalized_error()
        return ProviderResponse(
            provider=self.spec.provider,
            model=model,
            content=content,
            finish_reason=self.client.get_last_response_meta().get("finish_reason"),
            usage=self.client.get_last_usage(),
            error=error if content is None else None,
        )

    def chat_json(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> ProviderResponse:
        model = str(kwargs.pop("model", None) or self.model)
        content = self.client.chat_json(system_prompt, user_prompt, model=model, **kwargs)
        error = self._normalized_error()
        return ProviderResponse(
            provider=self.spec.provider,
            model=model,
            content=content,
            finish_reason=self.client.get_last_response_meta().get("finish_reason"),
            usage=self.client.get_last_usage(),
            error=error if content is None else None,
        )

    def _normalized_error(self) -> Optional[NormalizedProviderError]:
        raw = self.client.get_last_error()
        if not raw:
            return None
        return NormalizedProviderError(
            provider=self.spec.provider,
            code=str(raw.get("code") or "provider_error"),
            message=str(raw.get("message") or "AI 제공사 호출에 실패했습니다."),
            status_code=raw.get("status_code"),
            retryable=bool(raw.get("retryable", False)),
        )


class ProviderClientFacade:
    """기존 OpenAIClient 호출 계약을 유지하는 Router facade."""

    def __init__(self, adapter: OpenAICompatibleAdapter):
        self.adapter = adapter
        self.provider = adapter.spec.provider
        self.model = adapter.model

    def is_ready(self) -> bool:
        return self.adapter.is_ready()

    def list_chat_models(self) -> List[str]:
        return self.adapter.list_models()

    def get_last_usage(self) -> Dict[str, Any]:
        usage = self.adapter.client.get_last_usage()
        usage.setdefault("provider", self.provider)
        return usage

    def get_last_error(self) -> Dict[str, Any]:
        return self.adapter.client.get_last_error()

    def chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, **kwargs: Any) -> Optional[str]:
        return self.adapter.chat_text(
            system_prompt,
            user_prompt,
            model=model or self.model,
            **kwargs,
        ).content

    def chat_json(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return self.adapter.chat_json(
            system_prompt,
            user_prompt,
            model=model or self.model,
            **kwargs,
        ).content

    def vision_json(self, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if not self.adapter.spec.capabilities.vision:
            return None
        return self.adapter.client.vision_json(*args, **kwargs)

    def transcribe_audio(self, *args: Any, **kwargs: Any) -> str:
        if not self.adapter.spec.capabilities.transcribe:
            return ""
        return self.adapter.client.transcribe_audio(*args, **kwargs)


class AIProviderRouter:
    def __init__(
        self,
        provider: str,
        *,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        normalized = str(provider or "openai").strip().lower()
        if normalized not in PROVIDER_SPECS:
            raise ValueError(f"지원하지 않는 AI 제공사입니다: {normalized}")
        self.spec = PROVIDER_SPECS[normalized]
        self.adapter = OpenAICompatibleAdapter(
            self.spec,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )

    @classmethod
    def from_settings(
        cls,
        settings: Dict[str, Any],
        *,
        workload: str = "analyst",
    ) -> "AIProviderRouter":
        original_credentials = settings.get("ai_credentials")
        has_structured_credentials = bool(
            isinstance(original_credentials, dict) and original_credentials
        )
        runtime = hydrate_ai_credentials(settings)
        profiles = runtime.get("ai_provider_profiles", {})
        profile = profiles.get(workload, {}) if isinstance(profiles, dict) else {}
        roles = runtime.get("ai_model_roles", {})
        if (
            workload in {"frequent_cheap", "standard", "premium"}
            and isinstance(roles, dict)
            and roles.get(workload) is not None
        ):
            profile = normalize_model_route(
                roles.get(workload),
                fallback_provider=str(runtime.get("ai_provider") or "openai"),
                fallback_model=str(runtime.get("openai_model") or ""),
            )
        if workload == "transcription":
            transcription = runtime.get("ai_custom_transcription", {})
            if isinstance(transcription, dict):
                profile = normalize_model_route(
                    transcription,
                    fallback_provider="openai",
                    fallback_model="gpt-4o-mini-transcribe",
                )
        provider = str(
            (profile.get("provider") if isinstance(profile, dict) else None)
            or runtime.get("ai_provider")
            or "openai"
        ).lower()
        spec = PROVIDER_SPECS.get(provider, PROVIDER_SPECS["openai"])
        credentials = runtime.get("ai_credentials", {})
        credential_cfg = credentials.get(provider, {}) if isinstance(credentials, dict) else {}
        if not isinstance(credential_cfg, dict):
            credential_cfg = {}
        models = runtime.get("ai_models", {})
        model = ""
        if isinstance(profile, dict):
            model = str(profile.get("model") or "")
        if not model and isinstance(models, dict):
            model = str(models.get(workload) or "")
        if not model:
            legacy_key = "assistant_ai_model" if workload == "assistant" else "openai_model"
            model = str(runtime.get(legacy_key) or spec.default_model)
        active_provider = str(runtime.get("ai_provider") or "openai").lower()
        legacy_route_key = ""
        if provider == "openai":
            legacy_route_key = str(runtime.get("openai_api_key") or "")
        elif provider == active_provider and not has_structured_credentials:
            # 구버전은 선택 Provider 키도 openai_api_key 한 칸에 저장했다.
            # 새 ai_credentials가 존재하면 다른 Provider 키를 빌려 쓰지 않는다.
            legacy_route_key = str(runtime.get("openai_api_key") or "")
        api_key = str(credential_cfg.get("api_key") or legacy_route_key or "")
        base_url = credential_cfg.get("base_url")
        if base_url is None:
            base_url = spec.base_url if provider != "openai" else runtime.get("openai_base_url")
        return cls(provider, api_key=api_key, model=model, base_url=base_url)

    def client_facade(self) -> ProviderClientFacade:
        return ProviderClientFacade(self.adapter)

    def list_models(
        self,
        *,
        include_fallback: bool = True,
        capability: str = "chat_text",
    ) -> List[str]:
        return self.adapter.list_models(
            include_fallback=include_fallback,
            capability=capability,
        )

    def health_check(self) -> Dict[str, Any]:
        return self.adapter.health_check()

    def validate_model(
        self,
        *,
        capability: str = "chat_json",
        verify_account: bool = False,
    ) -> Dict[str, Any]:
        """정적 capability와 선택적으로 실제 계정 모델 목록을 함께 검사한다."""
        account_models: Optional[List[str]] = None
        if verify_account:
            if not self.adapter.is_ready():
                result = validate_model_route(
                    self.spec.provider,
                    self.adapter.model,
                    capability=capability,
                )
                result["ok"] = False
                result["errors"] = list(result["errors"]) + ["API 자격증명이 설정되지 않았습니다."]
                return result
            account_models = self.list_models(
                include_fallback=False,
                capability=capability,
            )
            error = self.adapter.client.get_last_error()
            if error:
                return {
                    "ok": False,
                    "provider": self.spec.provider,
                    "model": self.adapter.model,
                    "status": "unknown",
                    "errors": [str(error.get("message") or "모델 목록 조회에 실패했습니다.")],
                    "warnings": [],
                    "replacement": "",
                }
        return validate_model_route(
            self.spec.provider,
            self.adapter.model,
            capability=capability,
            account_models=account_models,
        )
