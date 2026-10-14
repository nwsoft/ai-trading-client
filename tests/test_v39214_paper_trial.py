"""PAPER goals are separate from readiness and measured execution evidence."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sqlite3
import pytest
from tests.test_v39214_stock_studio import prepared_pipeline
from trading.paper_runtime_evidence import record_interval, runtime_summary, evidence_path, measure_paper_pool
from web_platform.contracts import StrategyActionContract


@pytest.mark.parametrize('days',[1,3,7])
def test_goal_is_saved_but_does_not_gate_samples_or_auto_stop(tmp_path,days):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id']
    p.start_paper_observation(k,vid,trial_days=days)
    before=p.record_paper_validation(k,vid,trades=2,metrics={'observation_days':20,'require_forward_days':True})
    assert not before['paper_validation']['passed']
    ready=p.record_paper_validation(k,vid,trades=3,metrics={'observation_days':0.01,'require_forward_days':True})
    assert ready['paper_validation']['passed']
    assert ready['status']=='paper_observing' and p.paper_versions[k]==vid
    assert ready['paper_trial']['target_days']==days
    assert not p.active_versions
    paused=p.stop_paper_observation(k,vid)
    resumed=p.start_paper_observation(k,vid)
    assert resumed['paper_trial']['target_days']==days
    assert resumed['paper_validation']==paused['paper_validation']
    with pytest.raises(ValueError):p.activate(k,vid,live_confirmation=False)
    p.activate(k,vid,live_confirmation=True)
    assert not p.paper_versions and p.active_versions[k]==vid
    assert p.get_version(k,vid)['paper_observation_windows'][-1]['stopped_at']


@pytest.mark.parametrize('value',[True,False,0,2,4,8,1.0,'1'])
def test_invalid_period_is_rejected_without_mutating_attempt(tmp_path,value):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id'];before=p.get_version(k,vid)
    with pytest.raises(ValueError):p.start_paper_observation(k,vid,trial_days=value)
    assert p.get_version(k,vid)==before
    with pytest.raises(ValueError):StrategyActionContract(scope='binance',strategy_key=k,version_id=vid,action='start_paper',trial_days=value)


@pytest.mark.parametrize('violations,known,expected',[(0,True,True),(1,True,False),(0,False,False)])
def test_risk_and_missing_risk_are_independent_of_goal(tmp_path,violations,known,expected):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id'];p.start_paper_observation(k,vid,trial_days=1)
    r=p.record_paper_validation(k,vid,trades=3,guardrail_violations=violations,metrics={'observation_days':30,'risk_evidence_complete':known})
    assert r['paper_validation']['passed']==expected
    assert r['status']=='paper_observing'
    if not expected:
        with pytest.raises(ValueError):p.activate(k,vid,live_confirmation=True)


def observed(tmp_path):
    p,v=prepared_pipeline(tmp_path);k,vid=v['strategy_key'],v['version_id'];p._now=lambda:'2026-10-14T00:00:00+00:00'
    v=p.start_paper_observation(k,vid,trial_days=3)
    return p,v,{'strategy_key':k,'version_id':vid,'_paper_attempt_id':v['paper_observation_attempt_id']}


def test_measured_union_excludes_overlap_pause_and_offline_permission_time(tmp_path):
    p,v,item=observed(tmp_path);epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    assert runtime_summary(p.storage_path,v)['seconds'] is None
    record_interval(p.storage_path,[item],epoch+10,epoch+20)
    record_interval(p.storage_path,[item],epoch+15,epoch+25)
    p._now=lambda:'2026-10-14T00:00:30+00:00';p.stop_paper_observation(v['strategy_key'],v['version_id'])
    record_interval(p.storage_path,[item],epoch+28,epoch+35)
    record_interval(p.storage_path,[item],epoch+40,epoch+50)
    summary=runtime_summary(p.storage_path,v)
    assert summary['seconds']==17 # 10..25 plus 28..30, not 30 elapsed seconds
    assert summary['evaluations']==3
    p._now=lambda:'2026-10-17T00:00:00+00:00';p.start_paper_observation(v['strategy_key'],v['version_id'])
    assert runtime_summary(p.storage_path,v)==summary # no UI/resume/offline time inflation


def test_restart_preserves_old_time_and_rejects_late_old_attempt_receipts(tmp_path):
    p,v,item=observed(tmp_path);epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    record_interval(p.storage_path,[item],epoch+1,epoch+2)
    p._now=lambda:'2026-10-14T00:00:03+00:00';p.stop_paper_observation(v['strategy_key'],v['version_id'])
    new=p.restart_paper_observation(v['strategy_key'],v['version_id'],trial_days=1)
    assert new['paper_validation_attempt_history'][0]['runtime_evidence']['seconds']==1
    record_interval(p.storage_path,[item],epoch+4,epoch+5)
    assert runtime_summary(p.storage_path,new)['seconds'] is None
    assert new['paper_trial']['target_days']==1


def test_sqlite_errors_are_unknown_not_zero(tmp_path):
    p,v,item=observed(tmp_path);evidence_path(p.storage_path).write_bytes(b'broken')
    assert runtime_summary(p.storage_path,v)['status']=='unavailable'
    assert runtime_summary(p.storage_path,v)['seconds'] is None


def test_real_engine_wrapper_records_success_only_and_preserves_exception(tmp_path):
    p,v,item=observed(tmp_path);item.update(operation_mode='paper_validation',_paper_store_path=str(p.storage_path),target_scope='asset:crypto')
    @measure_paper_pool
    def call(cls, strategies, context, **kw):
        if context.get('fail'):raise RuntimeError('fixture')
        return {'allowed':False}
    epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    with patch('trading.paper_runtime_evidence.time.time',side_effect=[epoch+1,epoch+1.25]),patch('trading.paper_runtime_evidence.time.monotonic',side_effect=[10,10.25]):
        assert call(None,[item],{},asset_class='crypto',target='binance')=={'allowed':False}
    assert runtime_summary(p.storage_path,v)['seconds']==.25
    with pytest.raises(RuntimeError,match='fixture'):call(None,[item],{'fail':True},asset_class='crypto',target='binance')
    assert runtime_summary(p.storage_path,v)['evaluations']==1


def services_fixture(tmp_path,monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module,'get_app_data_dir',lambda:str(tmp_path))
    monkeypatch.setattr(module,'set_current_user_account',lambda account:None)
    monkeypatch.setattr(module,'load_settings',lambda **kw:{'paper_trading':True})
    service=module.ApplicationServices(account='trial-fixture')
    service._refresh_runtime_after_strategy_change=lambda:{}
    p,v=prepared_pipeline(tmp_path)
    # Persist fixture in the service's existing scoped strategy store.
    p.storage_path=tmp_path/'custom_strategies/binance_private.json';p._save()
    service.strategy_action(scope='binance',strategy_key=v['strategy_key'],version_id=v['version_id'],action='start_paper',trial_days=1)
    return service,v


def ledger_rows(version,count=3):
    now=datetime.now(timezone.utc)+timedelta(seconds=1)
    return [dict(event_id=f'close-{i}',scope='binance',strategy_scope='binance',execution_scope='binance',exchange='binance',strategy_key=version['strategy_key'],version_id=version['version_id'],execution_mode='paper',symbol='BTCUSDT',opened_at=now.isoformat(),closed_at=now.isoformat(),gross_pnl=2,net_pnl=1.7,fees=.2,estimated_taxes=0,estimated_slippage=.1,quote_currency='USDT',calculation_status='valid',cost_calculation_status='recorded_contract',guardrail_violations=0) for i in range(count)]


def test_catalog_goal_reached_never_fabricates_runtime_or_samples(tmp_path,monkeypatch):
    service,v=services_fixture(tmp_path,monkeypatch);p=service._strategy_pipeline('binance_private.json');current=p._find(v['strategy_key'],v['version_id'])
    current['paper_observation_started_at']='2026-01-01T00:00:00+00:00';current['paper_observation_windows']=[{'started_at':current['paper_observation_started_at'],'stopped_at':None}];p._save()
    row=service.strategy_catalog()['strategies'][0]['versions'][0];progress=row['paper_progress']
    assert progress['target_reached'] and progress['target_days']==1
    assert progress['runtime']['seconds'] is None
    assert not progress['promotion']['ready'] and progress['trades']==0
    assert row['paper_observing']


@pytest.mark.parametrize('problem',['missing','risk','unknown_risk','cost','none'])
def test_activation_rechecks_real_ledger_and_manual_counts_cannot_bypass(tmp_path,monkeypatch,problem):
    service,v=services_fixture(tmp_path,monkeypatch);kwargs=dict(scope='binance',strategy_key=v['strategy_key'],version_id=v['version_id'])
    with pytest.raises(ValueError):service.record_strategy_paper_validation(**kwargs,trades=100,metrics={'source':'strategy_paper_outcomes_ledger'})
    rows=ledger_rows(v,count=2 if problem=='missing' else 3)
    if problem=='risk':rows[0]['guardrail_violations']=1
    if problem=='unknown_risk':rows[0].pop('guardrail_violations')
    if problem=='cost':rows[0]['calculation_status']='invalid'
    (tmp_path/'strategy_paper_outcomes.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    if problem=='none':
        result=service.strategy_action(**kwargs,action='activate',live_confirmation=True)
        assert result['status']=='active'
    else:
        with pytest.raises(ValueError):service.strategy_action(**kwargs,action='activate',live_confirmation=True)

@pytest.mark.parametrize('asset,target',[('crypto','binance'),('stock','kis'),('stock','kiwoom')])
def test_real_engine_candidate_evaluation_is_measured_but_mode_filtered_is_not(tmp_path,asset,target):
    from trading.declarative_strategy_engine import DeclarativeStrategyEngine
    p,v,item=observed(tmp_path)
    item.update(operation_mode='paper_validation',_paper_store_path=str(p.storage_path),target_scope=f'asset:{asset}',signal_mode='independent',market_regimes=['all'],rules={'executable_entry':{'all':[{'field':'rsi','operator':'lte','value':30}]}})
    epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    with patch('trading.paper_runtime_evidence.time.time',side_effect=[epoch+1,epoch+1.25]),patch('trading.paper_runtime_evidence.time.monotonic',side_effect=[10,10.25]):
        DeclarativeStrategyEngine.evaluate_strategy_pool([item],{'rsi':20,'signal':'LONG'},asset_class=asset,target=target)
    assert runtime_summary(p.storage_path,v)['seconds']==.25
    DeclarativeStrategyEngine.evaluate_strategy_pool([item],{'_eligible_strategy_modes':['confirm']},asset_class=asset,target=target)
    assert runtime_summary(p.storage_path,v)['evaluations']==1


def test_concurrent_receipts_union_without_double_count(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    p,v,item=observed(tmp_path);epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda offset:record_interval(p.storage_path,[item],epoch+offset,epoch+offset+10),[4,2,3,1]))
    summary=runtime_summary(p.storage_path,v)
    assert summary['seconds']==13 and summary['evaluations']==4


def test_manual_counts_before_start_are_not_new_version_proof(tmp_path,monkeypatch):
    service,v=services_fixture(tmp_path,monkeypatch)
    p=service._strategy_pipeline('binance_private.json')
    new=p.submit(name='not started',rules=v['rules']);p.approve(new['strategy_key'],new['version_id'],approved_by='fixture')
    with pytest.raises(ValueError,match='수동 거래 건수'):
        service.record_strategy_paper_validation(scope='binance',strategy_key=new['strategy_key'],version_id=new['version_id'],trades=100)


def test_clock_jump_does_not_invent_execution_time(tmp_path):
    p,v,item=observed(tmp_path);item.update(operation_mode='paper_validation',_paper_store_path=str(p.storage_path),target_scope='asset:crypto')
    @measure_paper_pool
    def call(cls,strategies,context,**kw):return 'unchanged'
    epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    with patch('trading.paper_runtime_evidence.time.time',side_effect=[epoch,epoch+3600]),patch('trading.paper_runtime_evidence.time.monotonic',side_effect=[1,1.5]):
        assert call(None,[item],{},asset_class='crypto',target='binance')=='unchanged'
    assert runtime_summary(p.storage_path,v)['seconds'] is None
    assert runtime_summary(p.storage_path,v)['status'] == 'partial'


def test_rollback_rechecks_paper_ledger_not_just_old_passed_flag(tmp_path,monkeypatch):
    service,v=services_fixture(tmp_path,monkeypatch);kwargs=dict(scope='binance',strategy_key=v['strategy_key'],version_id=v['version_id'])
    p=service._strategy_pipeline('binance_private.json');p.record_paper_validation(v['strategy_key'],v['version_id'],trades=3)
    with pytest.raises(ValueError,match='원장'):
        service.strategy_action(**kwargs,action='rollback')


def test_evidence_write_failure_preserves_strategy_result_and_marks_partial(tmp_path):
    p,v,item=observed(tmp_path);item.update(operation_mode='paper_validation',_paper_store_path=str(p.storage_path),target_scope='asset:crypto')
    @measure_paper_pool
    def call(cls, strategies, context, **kw):return {'allowed': False}
    epoch=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    with patch('trading.paper_runtime_evidence.time.time',side_effect=[epoch+1,epoch+1.25]),patch('trading.paper_runtime_evidence.time.monotonic',side_effect=[10,10.25]),patch('trading.paper_runtime_evidence.record_interval',side_effect=sqlite3.OperationalError('fixture busy')):
        assert call(None,[item],{},asset_class='crypto',target='binance')=={'allowed':False}
    record_interval(p.storage_path,[item],epoch+2,epoch+3)
    result=runtime_summary(p.storage_path,v)
    assert result['status']=='partial' and result['seconds']==1


def test_internal_runtime_evidence_metadata_never_reaches_workspace_response():
    from web_platform.runtime_bridge import _runtime_safe
    value={'active_custom_strategies':[{'version_id':'fixture','operation_mode':'paper_validation','_paper_store_path':'private-local-store','_paper_attempt_id':'internal-attempt'}]}
    assert _runtime_safe(value)=={'active_custom_strategies':[{'version_id':'fixture','operation_mode':'paper_validation'}]}
