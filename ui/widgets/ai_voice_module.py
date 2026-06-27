#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 어시스턴트 음성 모듈 (초기 버전)

목표:
- 외부 의존성 없이 OS 기본 TTS를 우선 사용
- STT는 옵션 의존성(speech_recognition, pyaudio) 기반으로 안전하게 동작
- 기존 UI 흐름을 깨지 않도록 기본 비활성 상태 유지
"""

from __future__ import annotations

import importlib
import platform
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class VoiceConfig:
    enabled: bool = False
    auto_tts: bool = False
    lang: str = 'ko-KR'
    rate: int = 180


class AIVoiceModule:
    """AI 어시스턴트 음성 입출력 래퍼."""

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()

    def set_enabled(self, enabled: bool) -> None:
        self.config.enabled = bool(enabled)

    def set_auto_tts(self, auto_tts: bool) -> None:
        self.config.auto_tts = bool(auto_tts)

    def _has_module(self, module_name: str) -> bool:
        try:
            importlib.import_module(module_name)
            return True
        except Exception:
            return False

    def tts_engine(self) -> str:
        os_name = platform.system()
        if os_name == 'Darwin':
            return 'say'
        if os_name == 'Windows':
            return 'powershell'
        return 'none'

    def stt_engine(self) -> str:
        if self._has_module('speech_recognition'):
            return 'speech_recognition'
        return 'none'

    def has_microphone_backend(self) -> bool:
        # speech_recognition 마이크 입력은 PyAudio 백엔드가 필요하다.
        return self._has_module('pyaudio')

    def can_speak(self) -> bool:
        return self.config.enabled and self.tts_engine() in ('say', 'powershell')

    def can_transcribe(self) -> bool:
        return self.config.enabled and self.stt_engine() == 'speech_recognition'

    def can_transcribe_microphone(self) -> bool:
        return self.can_transcribe() and self.has_microphone_backend()

    def speak(self, text: str) -> bool:
        """텍스트를 음성으로 출력한다. 실패해도 예외를 던지지 않는다."""
        if not self.can_speak():
            return False

        text = (text or '').strip()
        if not text:
            return False

        # 너무 긴 메시지는 TTS 지연을 줄이기 위해 자른다.
        if len(text) > 300:
            text = text[:300] + '...'

        try:
            engine = self.tts_engine()
            if engine == 'say':
                rate = str(max(120, min(340, int(self.config.rate or 180))))
                subprocess.run(['say', '-r', rate, text], check=False)
                return True
            if engine == 'powershell':
                escaped_text = text.replace("'", "''")
                script = (
                    "Add-Type -AssemblyName System.Speech;"
                    "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                    f"$speak.Rate = {max(-5, min(5, int((self.config.rate - 180) / 30)))};"
                    f"$speak.Speak('{escaped_text}');"
                )
                subprocess.run(['powershell', '-Command', script], check=False)
                return True
        except Exception:
            return False

        return False

    def transcribe(self, _audio_path: str) -> Dict[str, Any]:
        """STT 엔진 연동 전까지는 비활성 상태를 명확히 반환한다."""
        if not self.can_transcribe():
            return {
                'status': 'not_implemented',
                'text': '',
                'reason': 'stt_engine_not_configured',
            }

        try:
            sr = importlib.import_module('speech_recognition')
            recognizer = sr.Recognizer()
            with sr.AudioFile(_audio_path) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language=self.config.lang)
            return {'status': 'ok', 'text': text, 'reason': ''}
        except Exception as exc:
            return {'status': 'error', 'text': '', 'reason': str(exc)}

    def transcribe_microphone(self, timeout: int = 5, phrase_time_limit: int = 10) -> Dict[str, Any]:
        """마이크 입력을 받아 텍스트로 변환한다 (옵션 의존성)."""
        if not self.config.enabled:
            return {
                'status': 'not_available',
                'text': '',
                'reason': 'voice_disabled',
            }

        if self.stt_engine() != 'speech_recognition':
            return {
                'status': 'not_available',
                'text': '',
                'reason': 'speech_recognition_not_installed',
            }

        if not self.has_microphone_backend():
            return {
                'status': 'not_available',
                'text': '',
                'reason': 'pyaudio_not_installed',
            }

        try:
            sr = importlib.import_module('speech_recognition')
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            text = recognizer.recognize_google(audio, language=self.config.lang)
            return {'status': 'ok', 'text': text, 'reason': ''}
        except Exception as exc:
            return {'status': 'error', 'text': '', 'reason': str(exc)}

