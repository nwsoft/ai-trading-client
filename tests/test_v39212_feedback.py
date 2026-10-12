from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,json
import pytest
from config.paper_recovery_guide import ANSWER_KO,TRIGGERS,matches
from config.assistant_support_knowledge import support_topic
from trading.paper_capital import paper_available_funds
from trading.paper_funds_session import start_session
from web_platform.application_services import ApplicationServices
from web_platform.runtime_bridge import HeadlessRuntimeBridge
from trading.opportunity_coordinator import OpportunityCoordinator

QUESTIONS=['기관을 정지하고 운용 요약에서 보유·예약을 확인한 뒤 과거 기록을 보존하는 새 PAPER 평가를 준비하세요. 라는게 뭐야 무슨소리야?',
 'paper 다 off하고 새검증 1개인데 왜 안돼? PAPER 전략들 삭제해야 하나요?',
 'paper_ledger_currency_unverified는 무슨 뜻이야?','과거 PAPER 결제통화 근거 누락']
@pytest.mark.parametrize('service',['blockchain','stock','portfolio','personal_finance','ai_analyst'])
@pytest.mark.parametrize('mode',['guide','deep_analysis'])
def test_recovery_help_is_local_even_if_provider_settings_and_runtime_fail(service,mode):
    obj=ApplicationServices.__new__(ApplicationServices)
    with patch('web_platform.application_services.load_settings',side_effect=AssertionError('settings or network must not be touched')):
        for q in QUESTIONS:
            result=obj.ask_assistant(question=q,service=service,explanation_level='beginner',mode=mode)
            assert result['provider_called'] is False and result['guide_topic']=='paper_funds_recovery'
            assert '전략을 삭제하지 마세요' in result['answer'] and '거래 정지' in result['answer']
            assert '현재 계정' in result['answer']

def test_shipped_browser_fallback_matches_python_guide_and_ignores_data_markers():
    data=json.loads(Path('webui/src/generated/paper-recovery-guide.json').read_text(encoding='utf-8'))
    assert data['ko']==ANSWER_KO and data['triggers']==list(TRIGGERS)
    assert matches(QUESTIONS[0])
    assert not matches('NOAH_STRATEGY_EXPLANATION_V1\n'+QUESTIONS[0])
    assert not matches('[MARKET_TREND_SNAPSHOT]'+QUESTIONS[0])
    assert support_topic(QUESTIONS[0]).key=='paper_funds_recovery'

@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone'])
def test_new_evaluation_is_venue_wallet_boundary_not_strategy_deletion(tmp_path,venue):
    ledger=tmp_path/'strategy_paper_outcomes.jsonl'
    original=(json.dumps({'exchange':venue,'execution_mode':'paper','event_id':'legacy','net_pnl':12})+'\n').encode();ledger.write_bytes(original)
    quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
    assert paper_available_funds(10000,{},venue=venue,quote=quote,ledger_file=ledger)['reason']=='paper_ledger_currency_unverified'
    result=start_session(ledger,venue=venue,quote=quote,initial_equity=10000,positions={},stopped=True,pending_orders=0)
    assert ledger.read_bytes()==original and result['preserved_sha256']==hashlib.sha256(original).hexdigest()
    funds=paper_available_funds(10000,{},venue=venue,quote=quote,ledger_file=ledger)
    assert funds['capital_basis']=='paper_reconciled_funds' and funds['available_capital']==10000
    assert funds['historical_pnl_restored'] is False

@pytest.mark.parametrize('source',['binance','okx','upbit','bitget','bybit','bithumb','coinone'])
def test_readiness_projects_only_existing_memory_no_disk_or_coordinator_creation(tmp_path,source):
    owner=SimpleNamespace(settings={'paper_trading':True},paper_active_positions={},paper_positions={source:{'fixture':{}}})
    app=SimpleNamespace(trader=owner,unified_trader=owner,settings=owner.settings,running_crypto_exchanges=lambda:[source])
    obj=HeadlessRuntimeBridge(account='qa');obj._app=app
    with patch('trading.opportunity_coordinator.get_opportunity_coordinator',side_effect=AssertionError('summary must not create coordinator')):
        r=obj.operation_summary_snapshot(source=source,include_paper_pool=False)['paper_session_readiness']
    assert r['running'] is True and r['pending_and_reserved'] is None
    assert r['open_positions']==(0 if source=='binance' else 1)
    assert r['strategy_validation_off_is_not_trading_stop'] is True
    assert list(tmp_path.iterdir())==[]

def test_skip_audit_rejects_unexpected_exclusions_and_requires_windows_pe(tmp_path):
    from scripts.audit_release_test_skips import audit,WINDOWS_PE
    p=tmp_path/'report.xml';p.write_text('<testsuites><testcase classname="tests.unexpected" name="case"><skipped message="temporary"/></testcase></testsuites>')
    assert audit(p,'darwin')['status']=='FAIL'
    module,name=WINDOWS_PE.rsplit('.',1)
    p.write_text(f'<testsuites><testcase classname="{module}" name="{name}"><skipped message="not Windows"/></testcase></testsuites>')
    assert audit(p,'darwin')['status']=='PASS'
    assert audit(p,'win32')['errors']==['windows_pe_must_run']
    p.write_text(f'<testsuites><testcase classname="{module}" name="{name}"/></testsuites>')
    assert audit(p,'win32')['status']=='PASS'
