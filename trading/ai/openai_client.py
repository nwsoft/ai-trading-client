#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI 클라이언트 래퍼
"""

from typing import Optional, Dict, Any, List
import json
import os

try:
    from openai import OpenAI
except Exception:  # 패키지 미설치 시에도 임포트 에러 방지
    OpenAI = None  # type: ignore


class OpenAIClient:
    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY', '')
        # 🔥 설정 파일에서 모델을 받아오므로 하드코딩 제거
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')  # 기본값은 fallback용
        self.base_url = base_url  # DeepSeek 등 다른 API 엔드포인트 지원
        self._client = None
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

    def chat_json(self,
                  system_prompt: str,
                  user_prompt: str,
                  temperature: float = 0.2,
                  max_tokens: int = 800,
                  model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None
        try:
            completion = self._client.chat.completions.create(
                model=model or self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = completion.choices[0].message.content
            text = (content or "").strip()
            return self._safe_parse_json(text)
        except Exception:
            return None

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
            return None
        try:
            # 사용할 모델 결정
            use_model = model or self.model
            
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"OpenAI API 호출: 모델={use_model}, api_key 길이={len(self.api_key) if self.api_key else 0}")
            
            completion = self._client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                **kwargs
            )
            content = completion.choices[0].message.content
            result = (content.strip() if content else None)
            
            if result:
                logger.debug(f"OpenAI API 응답 성공: 길이={len(result)}")
            else:
                logger.warning(f"OpenAI API 응답이 비어있음: 모델={use_model}")
            
            return result
        except Exception as e:
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

