#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI 클라이언트 래퍼
"""

from typing import Optional, Dict, Any, List
import base64
import json
import mimetypes
import os
import threading

try:
    from openai import OpenAI
except Exception:  # 패키지 미설치 시에도 임포트 에러 방지
    OpenAI = None  # type: ignore


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: str = "openai",
    ):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY', '')
        # 🔥 설정 파일에서 모델을 받아오므로 하드코딩 제거
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')  # 기본값은 fallback용
        self.base_url = base_url  # DeepSeek 등 다른 API 엔드포인트 지원
        self.provider = str(provider or "openai").strip().lower()
        self._client = None
        self._usage_local = threading.local()
        self._error_local = threading.local()
        self._response_local = threading.local()
        if OpenAI and self.api_key:
            # base_url이 있으면 사용 (DeepSeek 등)
            client_kwargs = {'api_key': self.api_key}
            if self.base_url:
                client_kwargs['base_url'] = self.base_url
            self._client = OpenAI(**client_kwargs)
            # 모델 정보 로깅 (환경변수 NOAHAI_VERBOSE_AI=1 일 때만)
            if os.getenv('NOAHAI_VERBOSE_AI') == '1':
                print(f"OpenAI Client 초기화: 모델={self.model}, base_url={self.base_url}")

    def is_ready(self) -> bool:
        return self._client is not None

    def _record_contract_error(self, code: str, message: str) -> None:
        self._error_local.value = {
            "provider": self.provider,
            "code": code,
            "message": message,
            "status_code": None,
            "retryable": False,
        }

    def list_chat_models(self, allowed_prefixes: Optional[tuple[str, ...]] = None) -> List[str]:
        """현재 API 키/조직에서 실제 사용할 수 있는 텍스트 모델을 반환한다."""
        if not self._client:
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return []
        try:
            self._clear_error()
            response = self._client.models.list()
            excluded = (
                'audio', 'realtime', 'transcribe', 'tts', 'whisper', 'embedding',
                'moderation', 'image', 'dall-e', 'sora', 'search', 'codex', 'chatgpt',
            )
            models = []
            for item in getattr(response, 'data', []) or []:
                model_id = str(getattr(item, 'id', '') or '')
                lower = model_id.lower()
                prefixes = allowed_prefixes or ('gpt-', 'o1', 'o3', 'o4')
                if prefixes and not lower.startswith(prefixes):
                    continue
                if any(token in lower for token in excluded):
                    continue
                models.append(model_id)
            return sorted(set(models), reverse=True)
        except Exception as exc:
            self._record_error(exc)
            return []

    def list_transcription_models(self) -> List[str]:
        """현재 API 계정에서 노출되는 비실시간 음성 전사 모델을 반환한다."""
        if not self._client:
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return []
        try:
            self._clear_error()
            response = self._client.models.list()
            return sorted({
                str(getattr(item, "id", "") or "")
                for item in (getattr(response, "data", []) or [])
                if "transcribe" in str(getattr(item, "id", "") or "").lower()
                and "realtime" not in str(getattr(item, "id", "") or "").lower()
            })
        except Exception as exc:
            self._record_error(exc)
            return []

    def _completion_limits(self, model: str, max_tokens: int) -> Dict[str, Any]:
        """신형 reasoning 모델과 구형 Chat Completions 파라미터 차이를 흡수한다."""
        lower = str(model or '').lower()
        if lower.startswith(('gpt-5', 'o1', 'o3', 'o4', 'kimi-k3')):
            return {'max_completion_tokens': max_tokens}
        return {'max_tokens': max_tokens}

    def _supports_temperature(self, model: str) -> bool:
        lower = str(model or '').lower()
        if self.provider == "kimi":
            return False
        if self.provider == "gemini" and lower.startswith(("gemini-3.5", "gemini-3.6")):
            return False
        return not lower.startswith(('gpt-5', 'o1', 'o3', 'o4'))

    def chat_json(self,
                  system_prompt: str,
                  user_prompt: str,
                  temperature: float = 0.2,
                  max_tokens: int = 800,
                  model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self._client:
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return None
        try:
            self._clear_error()
            use_model = model or self.model
            request_kwargs: Dict[str, Any] = {
                'model': use_model,
                'messages': [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                **self._completion_limits(use_model, max_tokens),
            }
            if self.provider in ("deepseek", "kimi", "gemini"):
                request_kwargs["response_format"] = {"type": "json_object"}
            if self._supports_temperature(use_model):
                request_kwargs['temperature'] = temperature
            completion = self._client.chat.completions.create(
                **request_kwargs,
            )
            self._record_usage(completion, use_model)
            content = completion.choices[0].message.content
            text = (content or "").strip()
            parsed = self._safe_parse_json(text)
            if parsed is None:
                self._record_contract_error("invalid_json", "AI 응답이 유효한 JSON 객체가 아닙니다.")
            return parsed
        except Exception as exc:
            self._record_error(exc)
            return None

    def _record_usage(self, completion: Any, model: str) -> None:
        usage = getattr(completion, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cached_tokens = 0
        try:
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        except Exception:
            cached_tokens = 0
        if not cached_tokens:
            cached_tokens = int(getattr(usage, "cached_tokens", 0) or 0)
        self._usage_local.value = {
            "provider": self.provider,
            "model": str(model or self.model),
            "input_tokens": prompt_tokens,
            "cached_input_tokens": cached_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0),
        }
        choices = getattr(completion, "choices", []) or []
        first_choice = choices[0] if choices else None
        self._response_local.value = {
            "finish_reason": getattr(first_choice, "finish_reason", None),
        }

    def get_last_usage(self) -> Dict[str, Any]:
        return dict(getattr(self._usage_local, "value", {}) or {})

    def get_last_response_meta(self) -> Dict[str, Any]:
        return dict(getattr(self._response_local, "value", {}) or {})

    def _clear_error(self) -> None:
        self._error_local.value = {}

    def _record_error(self, exc: Exception) -> None:
        status_code = getattr(exc, "status_code", None)
        raw_code = getattr(exc, "code", None)
        if not raw_code:
            error_body = getattr(exc, "body", None)
            if isinstance(error_body, dict):
                raw_code = error_body.get("code") or (error_body.get("error") or {}).get("code")
        code = str(raw_code or exc.__class__.__name__ or "provider_error")
        try:
            numeric_status = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            numeric_status = None
        self._error_local.value = {
            "provider": self.provider,
            "code": code,
            "message": str(exc) or "AI 제공사 호출에 실패했습니다.",
            "status_code": numeric_status,
            "retryable": numeric_status in (408, 409, 425, 429, 500, 502, 503, 504),
        }

    def get_last_error(self) -> Dict[str, Any]:
        return dict(getattr(self._error_local, "value", {}) or {})

    def vision_json(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: List[str],
        *,
        max_tokens: int = 1800,
        model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """사용자 로컬 차트 이미지를 멀티모달 입력으로 분석해 JSON을 반환한다."""
        if not self._client:
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return None
        content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        try:
            self._clear_error()
            for path in image_paths[:4]:
                mime = mimetypes.guess_type(path)[0] or "image/jpeg"
                with open(path, "rb") as image_file:
                    encoded = base64.b64encode(image_file.read()).decode("ascii")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
                })
            use_model = model or self.model
            request_kwargs: Dict[str, Any] = {
                "model": use_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                **self._completion_limits(use_model, max_tokens),
            }
            if self._supports_temperature(use_model):
                request_kwargs["temperature"] = 0.1
            completion = self._client.chat.completions.create(**request_kwargs)
            self._record_usage(completion, use_model)
            text = str(completion.choices[0].message.content or "").strip()
            parsed = self._safe_parse_json(text)
            if parsed is None:
                self._record_contract_error("invalid_json", "비전 응답이 유효한 JSON 객체가 아닙니다.")
            return parsed
        except Exception as exc:
            self._record_error(exc)
            return None

    def transcribe_audio(
        self,
        audio_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """사용자가 분석을 요청한 영상 음성을 전략 근거용 텍스트로 전사한다."""
        if not self._client:
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return ""
        try:
            self._clear_error()
            request: Dict[str, Any] = {
                "model": model or os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
                "response_format": "json",
            }
            if language:
                request["language"] = language
            with open(audio_path, "rb") as audio_file:
                response = self._client.audio.transcriptions.create(file=audio_file, **request)
            if isinstance(response, str):
                return response.strip()
            return str(getattr(response, "text", "") or "").strip()
        except Exception as exc:
            self._record_error(exc)
            return ""

    def chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, **kwargs) -> Optional[str]:
        """일반 채팅 완성 (빌드 환경 대응 에러 로깅 강화)"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not self._client:
            # 🔥 상세한 디버그 로그 추가
            error_msg = f"OpenAI 클라이언트가 준비되지 않음 (api_key 존재: {bool(self.api_key)}, api_key 길이: {len(self.api_key) if self.api_key else 0}, client 초기화: {self._client is not None})"
            logger.error(error_msg)
            # 빌드 환경에서도 확인 가능하도록 print도 출력
            if os.getenv('NOAHAI_DEBUG_AI') == '1':
                print(f"[ERROR] {error_msg}")
            self._record_contract_error("credential_missing", "API 키가 없거나 AI 클라이언트를 초기화하지 못했습니다.")
            return None
        try:
            self._clear_error()
            # 사용할 모델 결정
            use_model = model or self.model
            request_options = dict(kwargs)
            if not self._supports_temperature(use_model):
                if 'max_tokens' in request_options and 'max_completion_tokens' not in request_options:
                    request_options['max_completion_tokens'] = request_options.pop('max_tokens')
                request_options.pop('temperature', None)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"OpenAI API 호출: 모델={use_model}, api_key 길이={len(self.api_key) if self.api_key else 0}")
            
            completion = self._client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                **request_options
            )
            self._record_usage(completion, use_model)
            content = completion.choices[0].message.content
            result = (content.strip() if content else None)
            
            if result:
                logger.debug(f"OpenAI API 응답 성공: 길이={len(result)}")
            else:
                logger.warning(f"OpenAI API 응답이 비어있음: 모델={use_model}")
                self._record_contract_error("empty_response", "AI 제공사가 빈 응답을 반환했습니다.")
            
            return result
        except Exception as e:
            self._record_error(e)
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_detail = traceback.format_exc()
            error_msg = f"OpenAI API 호출 오류: {e}"
            logger.error(error_msg)
            logger.error(f"상세 오류 정보:\n{error_detail}")
            # 빌드 환경에서도 확인 가능하도록 print도 출력
            if os.getenv('NOAHAI_DEBUG_AI') == '1':
                print(f"[ERROR] {error_msg}")
                print(f"[ERROR] 상세 정보:\n{error_detail}")
            return None

    @staticmethod
    def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
        try:
            t = text.strip()
            if t.startswith("```json"):
                t = t[7:-3].strip()
            elif t.startswith("```"):
                t = t[3:-3].strip()
            # 첫 번째 완전한 JSON 객체만 추출
            if t.count('{') > 0:
                start_idx = t.find('{')
                brace = 0
                end_idx = start_idx
                for i, ch in enumerate(t[start_idx:], start_idx):
                    if ch == '{':
                        brace += 1
                    elif ch == '}':
                        brace -= 1
                        if brace == 0:
                            end_idx = i + 1
                            break
                t = t[start_idx:end_idx]
            return json.loads(t)
        except Exception:
            return None
