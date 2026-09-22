"""Read-only strategy conversation. No real provider, accounts, orders or DB."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from web_platform.contracts import AssistantQueryContract
from web_platform.application_services import ApplicationServices
from web_platform.strategy_dialogue import FIELDS, SYSTEM_POLICY, normalize_dialogue

EVIDENCE = dict(goal='PAPER 검증할 초안 만들기', market='키움 국내 ETF 현물',
                budget='예산 100만원', loss_limit='계좌 기준 거래당 0.5% 손실',
                horizon='일봉 보유 일주일 확인 매일', leverage='레버리지 사용 안함')


def response(**kwargs):
    return json.dumps(dict(intent='design', answer='추세와 횡보 전략을 비교합니다.',
                           user_evidence=EVIDENCE, clarification_question='',
                           draft_text='검토 초안: 일봉 추세 진입. 비용·최소 수량 검증 필요.', **kwargs), ensure_ascii=False)


@pytest.mark.parametrize('raw', ['', 'not json', '[]', '{}', '{"answer":null}', '```json\n{}\n```'])
def test_invalid_output_cannot_be_handed_off(raw):
    result = normalize_dialogue(raw, question='전략 만들기', recent=[])
    assert result['status'] == 'response_invalid'
    assert not result['draft_text']


def test_exact_user_quotes_make_review_draft_never_approval():
    result = normalize_dialogue(response(), question='; '.join(EVIDENCE.values()), recent=[])
    assert result['status'] == 'review_draft'
    assert result['understanding'] == EVIDENCE
    assert not any(result[key] for key in ('auto_saved', 'auto_approved', 'order_submitted'))


@pytest.mark.parametrize('key', list(FIELDS))
def test_missing_condition_requires_question_and_blocks_handoff(key):
    quotes = [value for field, value in EVIDENCE.items() if field != key]
    result = normalize_dialogue(response(), question=' '.join(quotes), recent=[])
    assert result['missing_fields'] == [key]
    assert result['status'] == 'needs_clarification'
    assert not result['draft_text']


@pytest.mark.parametrize('role', ['assistant', 'system', 'tool'])
def test_assistant_examples_are_not_user_choices(role):
    result = normalize_dialogue(response(), question='모르겠어요', recent=[{'role':role,'content':' '.join(EVIDENCE.values())}])
    assert not result['understanding']


@pytest.mark.parametrize('marker', ['[MARKET_TREND_SNAPSHOT]', 'NOAH_STRATEGY_EXPLANATION_V1'])
def test_attached_evidence_is_not_user_consent(marker):
    result = normalize_dialogue(response(), question='알려줘\n'+marker+' '.join(EVIDENCE.values()), recent=[])
    assert not result['understanding']


@pytest.mark.parametrize('quote', ['예산 미정', '알아서 정해줘', 'not sure', 'you decide'])
def test_uncertain_user_words_are_not_confirmed(quote):
    payload = json.loads(response()); payload['user_evidence']['budget'] = quote
    result = normalize_dialogue(json.dumps(payload), question=' '.join(EVIDENCE.values())+' '+quote, recent=[])
    assert result['status'] == 'needs_clarification'
    assert 'budget' in result['missing_fields']


def test_learning_requires_no_financial_questionnaire():
    raw = json.dumps({'intent':'learn','answer':'장기 가치투자 원칙 설명','user_evidence':{},'draft_text':'bad draft'})
    result = normalize_dialogue(raw, question='버핏의 원칙은?', recent=[])
    assert result['status'] == 'discussion'
    assert not result['draft_text']
    assert '확인 질문' not in result['answer']


def test_conflicting_model_conditions_must_not_be_handed_off():
    payload = json.loads(response()); payload['clarification_question'] = '예산을 변경하신 건가요?'
    result = normalize_dialogue(json.dumps(payload), question=' '.join(EVIDENCE.values()), recent=[])
    assert result['status'] == 'needs_clarification'
    assert not result['draft_text']


@pytest.mark.parametrize('field,value', [('strategy_service','portfolio'),('conversation_kind','execute'),
                                      ('strategy_preferences',{'budget':'a'*501})])
def test_request_contract_rejects_invalid_fields(field,value):
    with pytest.raises(ValidationError):
        AssistantQueryContract.model_validate({'question':'전략 상담',field:value})


def make_service(monkeypatch, *, fail=False):
    import web_platform.application_services as module
    monkeypatch.setattr(module, 'load_settings', lambda **kw: {'assistant_token_budget':{'standard':{'max_output_tokens':900}}})
    service = object.__new__(ApplicationServices)
    service._assistant_operational_context = Mock(return_value={'captured_at':'fixture','latest_signals':[]})
    service._assistant_operational_answer = Mock(return_value='local evidence')
    service.runtime_snapshot = Mock(return_value={})
    service.workspace_snapshot = Mock(return_value={})
    service.strategy_catalog = Mock(return_value={'strategies':[]})
    service._audit = Mock()
    provider = Mock(side_effect=RuntimeError('provider_unavailable')) if fail else Mock(return_value={'answer':response(),'provider_called':True})
    service.interactive_ai = SimpleNamespace(ask=provider, status=Mock(return_value={}))
    return service


@pytest.mark.parametrize('service_name,market', [('blockchain','blockchain'),('stock','stock'),('ai_custom','stock')])
def test_real_service_routes_read_only_consultation_and_old_quotes(monkeypatch, service_name, market):
    service = make_service(monkeypatch)
    result = service.ask_assistant(question='앞서 조건으로 초안 부탁해요', service=service_name,
                                  explanation_level='beginner', mode='deep_analysis', conversation_kind='strategy',
                                  strategy_service=market, strategy_preferences=EVIDENCE)
    assert result['strategy_consultation']['status'] == 'review_draft'
    kwargs = service.interactive_ai.ask.call_args.kwargs
    assert kwargs['max_tokens'] == 900
    assert kwargs['privacy_class'] == 'private'
    assert SYSTEM_POLICY in kwargs['system_prompt']
    context = json.loads(kwargs['context'])
    assert context['strategy_consultation']['web_search_available'] is False
    assert context['strategy_consultation']['previous_user_quotes'] == EVIDENCE


@pytest.mark.parametrize('mode,scope', [('guide','private'),('deep_analysis','public_general')])
def test_no_implicit_external_call_or_public_private_mix(monkeypatch,mode,scope):
    service = make_service(monkeypatch)
    with pytest.raises(ValueError, match='requires_explicit_private_analysis'):
        service.ask_assistant(question='전략 상담', service='ai_custom', explanation_level='beginner',
                              conversation_kind='strategy', mode=mode,data_scope=scope)
    service.interactive_ai.ask.assert_not_called()


def test_provider_failure_is_not_ready_draft(monkeypatch):
    service = make_service(monkeypatch,fail=True)
    result = service.ask_assistant(question='전략 알려줘', service='ai_custom', explanation_level='beginner',
                                  conversation_kind='strategy',mode='deep_analysis')
    assert result['provider_failed'] is True
    assert result['strategy_consultation']['status'] == 'provider_unavailable'
    assert not result['strategy_consultation']['draft_text']


def test_local_help_explains_feature_without_provider(monkeypatch):
    service = make_service(monkeypatch)
    for target in ['ai_custom', 'blockchain', 'stock']:
        result = service.ask_assistant(question='전략 상담 어떻게 하나요?',service=target,explanation_level='beginner')
        assert '전략 상담 · 외부 AI' in result['answer']
        assert '실시간 웹 검색은 없고' in result['answer']
    service.interactive_ai.ask.assert_not_called()


def test_gateway_carries_consultation_and_requires_intent(monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    service = make_service(monkeypatch)
    token = 'fixture-only-token-at-least-32-characters'
    client = TestClient(create_gateway_app(token=token, application_services=service))
    body = dict(question='초안 만들기',service='ai_custom', mode='deep_analysis',
                conversation_kind='strategy',strategy_service='stock',strategy_preferences=EVIDENCE)
    headers = {'Authorization':f'Bearer {token}'}
    assert client.post('/api/v1/assistant/ask',headers=headers,json=body).status_code == 428
    result = client.post('/api/v1/assistant/ask',headers={**headers,'X-NoahAI-Intent':'confirmed'},json=body)
    assert result.status_code == 200
    assert result.json()['strategy_consultation']['status'] == 'review_draft'
    service._assistant_operational_context.assert_called_with(service='stock',question='초안 만들기')


@pytest.mark.parametrize('allocation', ['증거금 사용은 최대 10%.', '종목당 투자 비중은 최대 10%.'])
def test_reviewed_draft_enters_existing_deterministic_compiler(allocation):
    from trading.strategy_source_ingestor import StrategySourceIngestor
    payload = json.loads(response())
    payload['draft_text'] = ('RSI 30 이하이면 LONG 진입. RSI 55 이상이면 청산. '
                            '손절 1%, 익절 2%. 횡보장에서 사용. 거래당 계좌 손실 0.5%. '+allocation)
    dialogue = normalize_dialogue(json.dumps(payload),question=' '.join(EVIDENCE.values()),recent=[])
    assert dialogue['status'] == 'review_draft'
    result = StrategySourceIngestor().analyze(dialogue['draft_text'],'text',authoring_mode='guided_clarification')
    assert result['ready_for_execution'] is True  # Rules compile; NOT approval/PAPER/LIVE.
    assert not result['missing_conditions']
