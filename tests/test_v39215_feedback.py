"""Released .14 feedback: packaged assistant, source metadata and UI contracts."""
import builtins
from pathlib import Path
from unittest.mock import patch
import pytest


def service_fixture(tmp_path,monkeypatch):
    import web_platform.application_services as m
    monkeypatch.setattr(m,'get_app_data_dir',lambda:str(tmp_path))
    monkeypatch.setattr(m,'set_current_user_account',lambda account:None)
    monkeypatch.setattr(m,'load_settings',lambda **kw:{})
    s=m.ApplicationServices(account='feedback-fixture')
    s._assistant_operational_context=lambda **kw:{}
    s.runtime_snapshot=lambda:{}
    s.workspace_snapshot=lambda **kw:{}
    return s


@pytest.mark.parametrize('mode',['guide','deep_analysis'])
def test_packaged_assistant_never_imports_legacy_ui(tmp_path,monkeypatch,mode):
    service=service_fixture(tmp_path,monkeypatch)
    service.interactive_ai.ask=lambda **kw:{'answer':'synthetic provider answer','provider_called':True}
    real_import=builtins.__import__
    def packaged_import(name,*args,**kw):
        if name=='ui' or name.startswith('ui.'):
            raise ModuleNotFoundError('UI is intentionally excluded from packaged engine')
        return real_import(name,*args,**kw)
    with patch('builtins.__import__',side_effect=packaged_import):
        result=service.ask_assistant(question='레버리지가 올랐는데 거래금액이 같은 이유를 알려줘',service='ai_custom',explanation_level='simple',mode=mode)
    assert result['answer']


def source_text(*,scope='BINANCE + OKX',priority='7'):
    return f'''STRATEGY_NAME = synthetic_check
ENTRY_SIGNAL = LONG
[UI]
거래소 = {scope}
국면 기준 = 종목별
우선순위 = {priority}
시장상황 = 상승장
RISK_PER_TRADE_PERCENT = 0.50%
MAX_MARGIN_USAGE_PERCENT = 5.00%
손절: 1%
익절: 2%
포지션 크기: 5%
TIMEFRAME: 5m
ENTRY:
signal == "LONG" AND rsi >= 43 AND rsi <= 64
EXIT:
rsi >= 70
'''


def test_explicit_file_metadata_preserved_by_authoritative_compiler():
    from trading.strategy_source_ingestor import StrategySourceIngestor
    result=StrategySourceIngestor().analyze(source_text(),kind='text');r=result['rules']
    assert result['ready_for_execution']
    assert r['strategy_name']=='synthetic_check' and result['name']=='synthetic_check'
    assert r['target_scope']=='exchange:binance,okx' and r['regime_scope']=='symbol' and r['priority']==7
    assert r['risk_model']['risk_per_trade_percent']==.5 and r['risk_model']['max_margin_usage_percent']==5
    assert r['decision_timeframe']=='5m' and r['entry_signal']=='LONG'


@pytest.mark.parametrize('scope,priority',[('UNKNOWN_EXCHANGE','7'),('BINANCE','99'),('BINANCE','²')])
def test_invalid_source_routing_cannot_silently_fall_back_to_all_venues(scope,priority):
    from trading.strategy_source_ingestor import StrategySourceIngestor
    result=StrategySourceIngestor().analyze(source_text(scope=scope,priority=priority),kind='text')
    assert not result['ready_for_execution']
    assert result['rules']['compiler_issues']


def test_all_builtin_ui_prototypes_compile_without_missing_risk_or_entry_fields():
    import re,json
    from trading.strategy_source_ingestor import StrategySourceIngestor
    s=(Path(__file__).resolve().parents[1]/'webui/src/components/StrategyStudio.tsx').read_text()
    for key in ['trend_follow','trend_pullback','range_rsi','volume_breakout']:
        match=re.search(r'\{ key: "'+key+r'"[^\n]*source: (".*") \},',s)
        assert match,key
        result=StrategySourceIngestor().analyze(json.loads(match[1]),kind='text')
        assert result['ready_for_execution'],(key,result['missing_conditions'])
        from web_platform.application_services import ApplicationServices
        assert ApplicationServices.__new__(ApplicationServices).validate_strategy_draft(rules=result['rules'])['ready']
        stock=StrategySourceIngestor().analyze(json.loads(match[1]).replace('15m','1d'),kind='text')
        assert stock['ready_for_execution'] and ApplicationServices.__new__(ApplicationServices).validate_strategy_draft(rules=stock['rules'])['ready']


def test_unexpected_assistant_failure_has_cors_and_safe_request_id(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app,ALLOWED_ORIGINS
    s=service_fixture(tmp_path,monkeypatch)
    def failed(**kw):raise AttributeError('private-secret-placeholder')
    s.ask_assistant=failed
    token='test-feedback-token-32-characters-long'
    client=TestClient(create_gateway_app(token=token,application_services=s),raise_server_exceptions=False)
    origin=next(iter(ALLOWED_ORIGINS))
    response=client.post('/api/v1/assistant/ask',headers={'Authorization':'Bearer '+token,'X-NoahAI-Intent':'confirmed','Origin':origin},json={'question':'일반 질문 테스트','service':'blockchain'})
    assert response.status_code==500 and response.headers['access-control-allow-origin']==origin
    assert 'assistant_processing_failed' in response.text and '요청 ID' in response.text
    assert 'private-secret-placeholder' not in response.text


def test_live_strategy_performance_excludes_paper_unknown_mode_and_unreconciled_pnl(tmp_path):
    import sqlite3
    from web_platform.query_services import AccountQueryService
    p=tmp_path/'trading.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE trade_log(strategy_key TEXT,strategy_version_id TEXT,exchange TEXT,settlement_currency TEXT,execution_mode TEXT,exit_time TEXT,net_pnl REAL,reconciliation_status TEXT,fees REAL)')
        rows=[('k','v1','binance','USDT','live','2026-10-15',2,'exchange_confirmed',.2),('k','v1','binance','USDT','live','2026-10-15',-1,'exchange_confirmed',.1),('k','v1','binance','USDT','live','2026-10-15',999,'unverified',None),('k','v1','binance','USDT','paper','2026-10-15',999,'exchange_confirmed',.1),('k','v1','binance','USDT','','2026-10-15',999,'exchange_confirmed',.1),('k','v2','kis','KRW','live','2026-10-15',100,'broker_order_linked',3)]
        db.executemany('INSERT INTO trade_log VALUES(?,?,?,?,?,?,?,?,?)',rows)
    result=AccountQueryService(db_path=str(p)).strategy_live_performance()
    row=result['versions'][('k','v1')][0]
    assert row['recorded_closes']==3 and row['confirmed_closes']==2 and row['win_rate']==50
    assert row['net_pnl']==1 and row['recorded_costs']==pytest.approx(.3) and row['cost_records']==2
    assert result['versions'][('k','v2')][0]['settlement_currency']=='KRW'


def test_stock_candidate_snapshot_is_actual_source_scoped_without_account_details():
    from types import SimpleNamespace
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge=HeadlessRuntimeBridge.__new__(HeadlessRuntimeBridge)
    bridge._app=SimpleNamespace(stock_runtime_controller=SimpleNamespace(snapshot=lambda:{'running_sources':['kis'],'last_results':{'kis':{'candidate_symbols':['005930'],'candidate_observed_at':123,'decisions':[{'symbol':'005930','score':63,'action':'HOLD','quantity':999,'account_no':'private'}]},'kiwoom':{'candidate_symbols':['000660'],'decisions':[]}}}))
    result=bridge.stock_candidate_snapshot(source='kis')
    assert [row['symbol'] for row in result['candidates']]==['005930']
    assert result['candidates'][0]['score']==63 and 'quantity' not in str(result) and 'private' not in str(result)
    assert not bridge.stock_candidate_snapshot(source='binance')['candidates']


def test_fast_regime_diagnostics_publish_existing_thresholds_without_changing_regime(monkeypatch):
    from types import SimpleNamespace
    from trading.regime_diagnostics import record_fast_metrics
    from trading.operation_evidence import snapshot
    import trading.runtime_observability as module
    monkeypatch.setattr(module,'emit_runtime_status',lambda *a,**kw:None)
    owner=SimpleNamespace(settings={'paper_trading':True})
    record_fast_metrics(owner,'okx',rsi=40,trend_change_percent=-1,volume_ratio=.8,trend_threshold_percent=3,volume_required=1.2)
    module.emit_regime_observation(owner,'okx','normal','normal',False,mode='paper')
    result=snapshot(owner,'okx','paper')['regime']
    assert result['confirmed']=='normal' and result['trend_threshold_percent']==3 and result['trend_change_percent']==-1


def test_declared_routing_edit_requires_new_source_proof_but_legacy_hash_is_stable():
    from copy import deepcopy
    from trading.strategy_source_ingestor import StrategySourceIngestor
    r=StrategySourceIngestor().analyze(source_text(),kind='text')['rules']
    before=StrategySourceIngestor._execution_contract_digest(r)
    changed=deepcopy(r);changed['priority']=8
    assert StrategySourceIngestor._execution_contract_digest(changed)!=before
    changed=deepcopy(r);changed['target_scope']='exchange:binance'
    assert StrategySourceIngestor._execution_contract_digest(changed)!=before
    assert r['source_grounding']['compiler_contract_sha256']==before


@pytest.mark.parametrize('explicit',[False,True])
def test_single_file_name_fallback_respects_explicit_strategy_name(tmp_path,monkeypatch,explicit):
    from types import SimpleNamespace
    import web_platform.application_services as module
    s=service_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(module.AIProviderRouter,'from_settings',lambda *a,**kw:SimpleNamespace(client_facade=lambda:SimpleNamespace(is_ready=lambda:False)))
    text=source_text() if explicit else source_text().replace('STRATEGY_NAME = synthetic_check\n','')
    result=s.analyze_strategy_source(source_kind='text',value=text,encoding='text',file_name='folder\\ExampleFile.txt')
    assert result['name']==('synthetic_check' if explicit else 'ExampleFile')
    assert s.validate_strategy_draft(rules=result['rules'])['ready']


def test_legacy_contract_ignores_routing_without_new_source_declaration():
    from trading.strategy_source_ingestor import StrategySourceIngestor
    text='\n'.join(v for v in source_text().splitlines() if not v.startswith(('거래소','국면 기준','우선순위')))
    r=StrategySourceIngestor().analyze(text,kind='text')['rules']
    assert 'source_routing_contract' not in r
    before=StrategySourceIngestor._execution_contract_digest(r)
    r.update(priority=4,target_scope='exchange:okx')
    assert StrategySourceIngestor._execution_contract_digest(r)==before



def test_live_attribution_missing_or_nonfinite_money_never_becomes_zero_or_win_rate(tmp_path):
    import sqlite3
    from web_platform.query_services import AccountQueryService
    p=tmp_path/'trading.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE trade_log(strategy_key TEXT,strategy_version_id TEXT,exchange TEXT,settlement_currency TEXT,execution_mode TEXT,exit_time TEXT,net_pnl REAL,reconciliation_status TEXT,fees REAL)')
        db.executemany('INSERT INTO trade_log VALUES(?,?,?,?,?,?,?,?,?)', [('k','v','okx','USDT','live','2026-10-15',pnl,'exchange_confirmed',fee) for pnl,fee in [(None,None),('not recorded','not recorded'),(float('inf'),float('inf'))]])
    row=AccountQueryService(db_path=str(p)).strategy_live_performance()['versions'][('k','v')][0]
    assert row['recorded_closes']==3 and row['confirmed_closes']==0
    assert row['net_pnl'] is None and row['win_rate'] is None and row['recorded_costs'] is None and row['cost_records']==0
