#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 음성 모듈 테스트"""

import importlib.util
import os
import sys
from unittest.mock import patch


def _load_voice_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(root, 'ui', 'widgets', 'ai_voice_module.py')
    spec = importlib.util.spec_from_file_location('ai_voice_module_test_target', target)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


voice_module = _load_voice_module()
AIVoiceModule = voice_module.AIVoiceModule
VoiceConfig = voice_module.VoiceConfig


def test_default_disabled():
    m = AIVoiceModule()
    assert m.can_speak() is False


def test_engine_detection():
    m = AIVoiceModule(VoiceConfig(enabled=True))
    with patch('platform.system', return_value='Darwin'):
        assert m.tts_engine() == 'say'
    with patch('platform.system', return_value='Windows'):
        assert m.tts_engine() == 'powershell'


def test_speak_noop_when_disabled():
    m = AIVoiceModule(VoiceConfig(enabled=False, auto_tts=True))
    assert m.speak('테스트') is False


def test_speak_darwin_calls_say():
    m = AIVoiceModule(VoiceConfig(enabled=True, auto_tts=True, rate=190))
    with patch('platform.system', return_value='Darwin'), patch('subprocess.run') as run_mock:
        ok = m.speak('안녕하세요')
        assert ok is True
        run_mock.assert_called_once()


def test_transcribe_missing_file_is_structured_not_available():
    m = AIVoiceModule(VoiceConfig(enabled=True))
    result = m.transcribe('/tmp/audio.wav')
    assert result['status'] == 'not_available'
    assert result['reason'] == 'audio_file_not_found'


def test_stt_engine_none_without_dependency():
    m = AIVoiceModule(VoiceConfig(enabled=True))
    with patch('importlib.import_module', side_effect=ImportError):
        assert m.stt_engine() == 'none'
        assert m.can_transcribe() is False


def test_transcribe_microphone_not_available():
    m = AIVoiceModule(VoiceConfig(enabled=False))
    result = m.transcribe_microphone()
    assert result['status'] == 'not_available'
    assert result['reason'] == 'voice_disabled'


def test_transcribe_microphone_requires_pyaudio():
    m = AIVoiceModule(VoiceConfig(enabled=True))
    with patch.object(m, 'stt_engine', return_value='speech_recognition'), patch.object(
        m, 'has_microphone_backend', return_value=False
    ):
        result = m.transcribe_microphone()
        assert result['status'] == 'not_available'
        assert result['reason'] == 'pyaudio_not_installed'
