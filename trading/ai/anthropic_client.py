#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small native Anthropic Messages API client with the NoahAI provider contract."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from .openai_client import OpenAIClient


class AnthropicClient:
    """Use Anthropic's production Messages API instead of its evaluation-only OpenAI shim."""

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None, provider: str = "anthropic"):
        self.api_key = str(api_key or "")
        self.model = str(model or "claude-sonnet-5")
        self.base_url = str(base_url or "https://api.anthropic.com").rstrip("/")
        self.provider = provider
        self._usage_local = threading.local()
        self._error_local = threading.local()
        self._response_local = threading.local()

    def is_ready(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "NoahAI/3.9",
        }

    def _request_json(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib_request.urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib_error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                detail = {}
            message = str(((detail.get("error") or {}).get("message")) or exc.reason or exc)
            self._error_local.value = {
                "provider": self.provider,
                "code": str(((detail.get("error") or {}).get("type")) or f"http_{exc.code}"),
                "message": message,
                "status_code": int(exc.code),
                "retryable": int(exc.code) in (408, 409, 425, 429, 500, 502, 503, 504),
            }
            return None
        except Exception as exc:
            self._error_local.value = {
                "provider": self.provider,
                "code": exc.__class__.__name__,
                "message": str(exc) or "Anthropic API 호출에 실패했습니다.",
                "status_code": None,
                "retryable": True,
            }
            return None

    def list_chat_models(self, allowed_prefixes: Optional[tuple[str, ...]] = None) -> List[str]:
        if not self.is_ready():
            self._record_contract_error("credential_missing", "Anthropic API 키가 없습니다.")
            return []
        self._error_local.value = {}
        data = self._request_json("GET", "/v1/models?limit=100")
        if not isinstance(data, dict):
            return []
        prefixes = allowed_prefixes or ("claude-",)
        return sorted({
            str(item.get("id") or "")
            for item in (data.get("data") or [])
            if isinstance(item, dict) and str(item.get("id") or "").startswith(prefixes)
        }, reverse=True)

    def _message(self, system_prompt: str, user_prompt: str, model: str, **kwargs: Any) -> Optional[str]:
        if not self.is_ready():
            self._record_contract_error("credential_missing", "Anthropic API 키가 없습니다.")
            return None
        self._error_local.value = {}
        payload: Dict[str, Any] = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": int(kwargs.pop("max_completion_tokens", kwargs.pop("max_tokens", 800)) or 800),
        }
        supports_sampling = model not in {
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-fable-5",
        }
        if "temperature" in kwargs and supports_sampling:
            payload["temperature"] = max(0.0, min(float(kwargs["temperature"]), 1.0))
        data = self._request_json("POST", "/v1/messages", payload)
        if not isinstance(data, dict):
            return None
        text = "".join(
            str(block.get("text") or "")
            for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        self._usage_local.value = {
            "provider": self.provider,
            "model": model,
            "input_tokens": input_tokens,
            "cached_input_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        self._response_local.value = {"finish_reason": data.get("stop_reason")}
        if not text:
            self._record_contract_error("empty_response", "Anthropic API가 빈 응답을 반환했습니다.")
            return None
        return text

    def chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, **kwargs: Any) -> Optional[str]:
        return self._message(system_prompt, user_prompt, str(model or self.model), **kwargs)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        json_system = (
            f"{system_prompt}\n\n반드시 설명이나 마크다운 없이 유효한 JSON 객체 하나만 반환하세요."
        )
        text = self._message(
            json_system,
            user_prompt,
            str(model or self.model),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = OpenAIClient._safe_parse_json(text or "") if text else None
        if parsed is None and text is not None:
            self._record_contract_error("invalid_json", "Anthropic 응답이 유효한 JSON 객체가 아닙니다.")
        return parsed

    def get_last_usage(self) -> Dict[str, Any]:
        return dict(getattr(self._usage_local, "value", {}) or {})

    def get_last_error(self) -> Dict[str, Any]:
        return dict(getattr(self._error_local, "value", {}) or {})

    def get_last_response_meta(self) -> Dict[str, Any]:
        return dict(getattr(self._response_local, "value", {}) or {})

    def _record_contract_error(self, code: str, message: str) -> None:
        self._error_local.value = {
            "provider": self.provider,
            "code": code,
            "message": message,
            "status_code": None,
            "retryable": False,
        }

    def vision_json(self, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        self._record_contract_error("capability_unsupported", "현재 NoahAI Claude 연결은 텍스트/JSON만 지원합니다.")
        return None

    def transcribe_audio(self, *args: Any, **kwargs: Any) -> str:
        self._record_contract_error("capability_unsupported", "Anthropic 제공사는 음성 전사를 지원하지 않습니다.")
        return ""
