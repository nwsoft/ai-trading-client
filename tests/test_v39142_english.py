import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from web_platform.display_preferences import read_preferences, save_preferences
from web_platform.english_guide import manual_snapshot, local_answer
from web_platform.gateway import create_gateway_app

TOKEN = 'display-preferences-test-token-at-least-32-chars'
HEADERS = {'Authorization': 'Bearer '+TOKEN, 'X-NoahAI-Intent': 'confirmed'}


def test_preferences_are_account_local_and_do_not_change_trading_state(tmp_path):
    first, second = tmp_path/'alice', tmp_path/'bob'
    first.mkdir()
    for name in ('settings.json', 'trading.db', 'remote_monitor.json'):
        (first/name).write_text('original-risk-and-ledger-bytes')
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in first.iterdir()}
    assert read_preferences(first) == {'locale': 'ko', 'saved': False}
    assert save_preferences(first, 'en') == {'locale': 'en', 'saved': True}
    assert read_preferences(second) == {'locale': 'ko', 'saved': False}
    assert all(hashlib.sha256((first/name).read_bytes()).hexdigest() == digest for name,digest in before.items())
    assert not list(first.glob('*.tmp'))
    if os.name != 'nt':
        assert (first/'display_preferences.json').stat().st_mode & 0o077 == 0
    assert save_preferences(first, 'ko')['locale'] == 'ko'


@pytest.mark.parametrize('value', ['zh', '../en', '', None, {}, ['en']])
def test_unsupported_locales_never_persist(tmp_path, value):
    with pytest.raises(ValueError): save_preferences(tmp_path, value)
    assert not list(tmp_path.iterdir())


def test_corrupt_preference_defaults_to_korean(tmp_path):
    for content in ('broken', '[]', 'null', '{"locale":"zh"}'):
        (tmp_path/'display_preferences.json').write_text(content)
        assert read_preferences(tmp_path)['locale'] == 'ko'


def test_gateway_auth_intent_schema_and_locale_forwarding(tmp_path):
    calls=[]
    services=SimpleNamespace(data_dir=tmp_path, runtime_snapshot=lambda:{},
        manual_snapshot=lambda **kw: calls.append(kw) or {'sections':[]},
        ask_assistant=lambda **kw: calls.append(kw) or {'answer':'fixture'})
    client=TestClient(create_gateway_app(token=TOKEN, application_services=services))
    assert client.get('/api/v1/display-preferences').status_code == 401
    assert client.post('/api/v1/display-preferences', headers={'Authorization':HEADERS['Authorization']}, json={'locale':'en'}).status_code == 428
    assert client.post('/api/v1/display-preferences',headers=HEADERS,json={'locale':'en','paper_trading':False}).status_code==400
    assert client.post('/api/v1/display-preferences',headers=HEADERS,json={'locale':'en'}).json()['locale']=='en'
    assert client.get('/api/v1/manual',headers={**HEADERS,'X-NoahAI-Locale':'en'}).status_code==200
    assert calls.pop()=={'output_locale':'en'}
    client.get('/api/v1/manual',headers={**HEADERS,'X-NoahAI-Locale':'../../en'})
    assert calls.pop()=={}
    result=client.post('/api/v1/assistant/ask',headers={**HEADERS,'X-NoahAI-Locale':'en'},json={'question':'Explain the risk','service':'stock','explanation_level':'beginner','mode':'guide'})
    assert result.status_code==200
    assert calls.pop()['output_locale']=='en'


def test_english_manual_and_local_fallback_preserve_evidence_boundaries():
    manual=manual_snapshot()
    assert len(manual['sections'])==11
    assert len({s['id'] for s in manual['sections']})==11
    assert manual['release_version']=='3.9.1.42'
    for text in ['UTC', 'Unresolved', 'PAPER', 'LIVE', 'funding', 'not actual', 'password', 'not proof']:
        assert text.lower() in manual['content'].lower()
    original='미대조 1건 · PnL -0.25001 USDT · 계정 없음'
    answer=local_answer(original,'stock')
    assert original in answer and 'not an English translation of your account-specific diagnosis' in answer


def test_english_ai_instruction_and_cache_context_are_explicit():
    source=Path('web_platform/application_services.py').read_text(encoding='utf-8')
    assert "context['assistant_policy']['output_locale'] = 'en'" in source
    assert 'Respond in English. Preserve identifiers' in source
    assert 'Do not translate or regenerate executable strategy rules.' in source


def test_english_explicit_ai_request_forwards_language_without_expanding_public_context(tmp_path, monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module, 'get_app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(module, 'set_current_user_account', lambda account: None)
    monkeypatch.setattr(module, 'load_settings', lambda **kw: {})
    service=module.ApplicationServices(account='fixture')
    calls=[]
    service.interactive_ai=SimpleNamespace(ask=lambda **kw: calls.append(kw) or {'answer':'English fixture response','provider_called':True})
    service._audit=lambda *args, **kw: None
    result=service.ask_assistant(question='Explain PAPER',service='settings',explanation_level='beginner',mode='deep_analysis',data_scope='public_general',output_locale='en')
    assert result['answer']=='English fixture response'
    assert len(calls)==1 and 'Respond in English.' in calls[0]['system_prompt']
    context=json.loads(calls[0]['context'])
    assert context['assistant_policy']['output_locale']=='en'
    assert not set(context).intersection({'runtime','account_workspace','settings','recent_conversation','strategies'})
    result=service.ask_assistant(question='Explain PAPER',service='settings',explanation_level='beginner',output_locale='en')
    assert result['provider_called'] is False and len(calls)==1
    assert result['answer'].startswith('English beta · Local operating guide')
