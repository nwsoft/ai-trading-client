#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assistant_voice 설정 정합성 테스트"""

import json
import os


def test_default_settings_has_assistant_voice():
    from config.settings import get_default_settings

    settings = get_default_settings()
    assert 'assistant_voice' in settings
    voice = settings['assistant_voice']
    assert isinstance(voice, dict)
    assert 'enabled' in voice
    assert 'auto_tts' in voice
    assert 'lang' in voice
    assert 'rate' in voice


def test_settings_template_has_assistant_voice():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(root, 'config', 'settings_template.json')
    with open(template_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert 'assistant_voice' in data
    voice = data['assistant_voice']
    assert voice.get('enabled') is False
    assert voice.get('auto_tts') is False
    assert voice.get('lang') == 'ko-KR'
    assert isinstance(voice.get('rate'), int)
