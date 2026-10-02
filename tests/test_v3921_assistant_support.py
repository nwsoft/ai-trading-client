from copy import deepcopy
from pathlib import Path
import pytest

from config.assistant_support_knowledge import TOPICS, GUIDE_REVISION, build_support_answer, support_topic
from config.ai_custom_knowledge import build_ai_custom_knowledge


@pytest.mark.parametrize('topic', TOPICS, ids=lambda topic: topic.key)
def test_all_topics_are_bilingual_readonly_and_have_source(topic):
    assert Path(topic.source).exists()
    for locale in ('ko', 'en'):
        answer = build_support_answer(topic.triggers[0], locale=locale)
        assert answer and GUIDE_REVISION in answer
        assert topic.ko in answer if locale == 'ko' else topic.en in answer
    assert topic.ko in build_ai_custom_knowledge(topic.triggers[0], {'api_key':'never-echo'})
    assert 'never-echo' not in build_ai_custom_knowledge(topic.triggers[0], {'api_key':'never-echo'})


@pytest.mark.parametrize('question,key', [
    ('3.9.1.50 OKX PAPER 409 trading_candidates_unavailable candidate_selection', 'candidate_selection'),
    ('3.9.2.0 worker_shutdown_timeout runtime_still_alive 업데이트', 'shutdown'),
    ('409 pnl_reconciliation_required 복구', 'reconciliation'),
    ('start_refused_check_displayed_reason 미확정 사유 {}', 'start_diagnostic'),
    ('상태 429 업데이트 이후', 'rate_limit'),
    ('프리미엄 30개 전략', 'paper_capacity'),
    ('JEV로 409를 없앨 수 있나?', 'start_diagnostic'),
    ('백테스트 없이 PAPER', 'strategy_flow'),
])
def test_specific_diagnostic_precedes_version_or_marketing(question,key):
    assert support_topic(question).key == key


@pytest.fixture
def services(tmp_path, monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module, 'get_app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(module, 'set_current_user_account', lambda account: None)
    settings = {'api_key':'secret-not-for-answer', 'paper_trading':True}
    def load(**kwargs):
        assert kwargs.get('persist_migrations') is False
        return deepcopy(settings)
    monkeypatch.setattr(module, 'load_settings', load)
    obj = module.ApplicationServices(account='qa-guide')
    monkeypatch.setattr(obj, '_audit', lambda *args,**kwargs: None)
    def forbidden(*args, **kwargs):
        raise AssertionError('guide must not call external provider, runtime or workspace')
    monkeypatch.setattr(obj.interactive_ai, 'ask', forbidden)
    monkeypatch.setattr(obj, '_assistant_operational_context', forbidden)
    monkeypatch.setattr(obj, 'runtime_snapshot', forbidden)
    return obj


@pytest.mark.parametrize('service', ['blockchain','stock','ai_custom','settings','portfolio','ai_analyst','personal_finance'])
@pytest.mark.parametrize('locale', ['ko','en'])
@pytest.mark.parametrize('question', ['trading_candidates_unavailable','worker_shutdown_timeout','JEV 지원 여부'])
def test_every_assistant_surface_uses_shared_guide_without_calls(services,service,locale,question):
    answer = services.ask_assistant(question=question, service=service, explanation_level='standard', output_locale=locale)
    assert not answer['provider_called']
    assert answer['guide_revision'] == GUIDE_REVISION
    assert answer['guide_topic'] == support_topic(question).key
    assert 'secret-not-for-answer' not in answer['answer']
    assert (support_topic(question).en if locale == 'en' else support_topic(question).ko) in answer['answer']


def test_unknown_questions_are_not_fabricated_as_known_diagnostics():
    assert support_topic('지금 BTC 포지션을 유지하는 이유는?') is None
    assert build_support_answer('future_error_code_xyz') is None
    assert support_topic('요청 ID abc409defabc429def') is None
    assert support_topic('support_level 정의는?').key == 'indicator_contract'


def test_embedded_strategy_data_does_not_override_snapshot_explanation():
    import json
    question = '설명해줘\nNOAH_STRATEGY_EXPLANATION_V1\n' + json.dumps({
        'name':'자료 속 JEV 409 주장', 'rules':{'entry':'support_level 이상'},
    })
    assert support_topic(question) is None
    assert '현재 초안 쉽게 읽기' in build_ai_custom_knowledge(question)


def test_historical_replay_is_not_reported_as_a_required_pass():
    answer = build_ai_custom_knowledge('백테스트 PnL과 MDD는?')
    assert '선택적 과거 시뮬레이션' in answer
    assert '최소 통과조건' not in answer


@pytest.mark.parametrize('level', ['beginner','advanced'])
def test_english_help_wrappers_remain_english(services,level):
    result = services.ask_assistant(question='worker_shutdown_timeout',service='stock',explanation_level=level,output_locale='en')
    assert '초보자 안내' not in result['answer'] and '고급 확인' not in result['answer']


def test_optional_replay_flow_has_single_shared_source():
    from ui.ai_custom_guidance import build_ai_custom_safe_flow
    flow = build_ai_custom_safe_flow()
    assert '선택' in flow and '백테스트 합격 없이' in flow
    source = Path('web_platform/application_services.py').read_text(encoding='utf-8')
    assert 'safe_flow = build_ai_custom_safe_flow()' in source
    assert '최소 3건·7일 결과 확인 뒤' not in source
