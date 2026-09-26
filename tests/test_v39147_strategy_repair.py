"""No external API / live orders; preserve source and old validation evidence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from threading import RLock
import json
import sqlite3
import pytest

from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from web_platform.application_services import ApplicationServices


def compiled():
    return StrategySourceIngestor().analyze(
        '15분봉 RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.', kind='text')['rules']


def test_real_source_validate_submit_approve_reload(tmp_path):
    rules = compiled()
    result = ApplicationServices.validate_strategy_draft(None, rules=rules)
    assert result['ready'], result
    pipeline = CustomStrategyPipeline(storage_path=tmp_path/'strategies.json')
    version = pipeline.submit(name='source', rules=result['rules'])
    pipeline.approve(version['strategy_key'], version['version_id'], approved_by='fixture')
    loaded = CustomStrategyPipeline(storage_path=tmp_path/'strategies.json').get_version(version['strategy_key'], version['version_id'])
    assert loaded['status'] == 'approved'
    assert loaded['rules']['executable_entry'] == rules['executable_entry']
    assert not pipeline.active_versions


def test_form_default_mutation_reproduces_registration_failure():
    rules = compiled()
    rules['risk_model'] = {'risk_per_trade_percent': .5, 'max_margin_usage_percent': 10, 'max_leverage': 3}
    result = ApplicationServices.validate_strategy_draft(None, rules=rules)
    assert not result['ready']
    assert 'source_grounding_stale_after_execution_edit' in result['compiler_issues']


def test_javascript_number_roundtrip_preserves_hash_without_hiding_real_edits():
    rules = compiled()
    def js_numbers(value):
        if isinstance(value, dict): return {k:js_numbers(v) for k,v in value.items()}
        if isinstance(value, list): return [js_numbers(v) for v in value]
        if isinstance(value, float) and value.is_integer(): return int(value)
        return value
    transported = js_numbers(rules)
    assert ApplicationServices.validate_strategy_draft(None, rules=transported)['ready']
    transported['executable_entry']['all'][0]['value'] = 31
    assert not ApplicationServices.validate_strategy_draft(None, rules=transported)['ready']


def test_legacy_exact_hash_remains_accepted():
    rules = compiled()
    rules['source_grounding']['compiler_contract_sha256'] = StrategySourceIngestor._execution_contract_digest(rules, legacy_numbers=True)
    assert ApplicationServices.validate_strategy_draft(None, rules=rules)['ready']


def test_multiple_uncompiled_source_clauses_have_unique_question_ids():
    result = StrategySourceIngestor().analyze('''ENTRY:
undefined_sweep
undefined_retest
EXIT:
undefined_structure_exit
RISK:
손절 1%, 익절 2%, 자산 5%. 횡보장. 15분봉.''', kind='text')
    questions = result['clarification_questions']
    assert len(questions) >= 3
    assert len({q['id'] for q in questions}) == len(questions)
    assert len([q for q in questions if q['code'].startswith('source_condition_not_compiled:')]) == 3
    assert not result['ready_for_execution']


def test_version_limit_archives_old_evidence_and_survives_restart(tmp_path):
    path=tmp_path/'strategies.json'
    pipeline=CustomStrategyPipeline(storage_path=path, max_versions=2)
    first=pipeline.submit(name='original', rules=compiled())
    key=first['strategy_key']; original=deepcopy(first)
    pipeline.submit(name='revision',rules=compiled(),strategy_key=key)
    pipeline.submit(name='revision2',rules=compiled(),strategy_key=key)
    reloaded=CustomStrategyPipeline(storage_path=path,max_versions=2)
    assert reloaded.archived_versions[key][0] == original
    assert len(reloaded.strategies[key]) == 2
    assert not reloaded.active_versions and not reloaded.paper_versions


def test_incomplete_draft_can_be_saved_but_not_approved(tmp_path):
    rules = compiled(); rules['executable_entry'] = {'all':[], 'any':[]}
    pipeline = CustomStrategyPipeline(storage_path=tmp_path/'strategies.json')
    row = pipeline.submit(name='incomplete', rules=rules)
    assert not row['execution_readiness']['ready']
    with pytest.raises(ValueError):
        pipeline.approve(row['strategy_key'], row['version_id'], approved_by='fixture')
    assert not pipeline.active_versions and not pipeline.paper_versions


@pytest.mark.parametrize('confirmed', [False, True])
def test_explicit_base_entry_does_not_claim_source_validation(confirmed):
    rules = compiled(); original = deepcopy(rules['source_evidence'])
    rules['executable_entry'] = {'all':[], 'any':[]}; rules['signal_mode']='confirm'
    rules['entry_contract']={'mode':'noah_base','confirmed_by_user':confirmed}
    rules['source_grounding']={'status':'user_declared_override','confirmed_by_user':True}
    result = ApplicationServices.validate_strategy_draft(None, rules=rules)
    assert result['ready'] is confirmed
    assert result['validation_subject'] == 'noah_base_with_custom_risk_exit'
    assert result['source_strategy_logic_executed'] is False
    assert rules['source_evidence']==original
    assert DeclarativeStrategyEngine.evaluate_entry(rules,{})['allowed'] is confirmed


def test_noah_base_cannot_hide_independent_conditions():
    rules = compiled(); rules['entry_contract']={'mode':'noah_base','confirmed_by_user':True}
    assert not CustomStrategyPipeline.paper_execution_readiness({'rules':rules})['ready']
    assert not DeclarativeStrategyEngine.evaluate_entry(rules,{})['allowed']


def test_recovery_does_not_skip_legacy_owner_and_exposes_row_reason(tmp_path):
    from test_v39143_record_recovery import make
    from trading.record_recovery import RecordRecovery
    recorder, tid, _, _, worker = make(tmp_path)
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("UPDATE trade_log SET position_owner='legacy_unknown',reason='external close',execution_mode='' WHERE id=?",(tid,))
    state=worker.start('binance',background=False)
    assert state['remaining']==1
    item=state['unresolved_items'][0]
    assert item['trade_id']==tid and item['reason']=='execution_mode_evidence_missing'
    assert set(item)=={'trade_id','symbol','exit_time','state','reason'}
    assert not state['resume_authorized']


@pytest.mark.parametrize('reason,worker_alert', [('risk_data_unavailable',False),('risk_data_unavailable:binance',False),('daily_loss_limit_exceeded',False),('trading_candidates_unavailable:okx',False),('runtime_source_not_enabled:coinone',False),('runtime_start_exception:okx',True),('unexpected_failure',True)])
def test_expected_risk_block_is_not_reported_as_worker_crash(monkeypatch,reason,worker_alert):
    import web_platform.application_services as module
    import trading.notifications as notifications
    monkeypatch.setattr(module,'load_settings',lambda **kw:{'paper_trading':True})
    send=Mock();monkeypatch.setattr(notifications,'publish_notification',send)
    service=SimpleNamespace(_accepting_runtime_commands=True,_lock=RLock(),_command_results={},
        refresh_membership_status=lambda **kw:{'active':True},
        runtime_bridge=SimpleNamespace(execute=Mock(side_effect=RuntimeError(reason))))
    with pytest.raises(RuntimeError,match=reason):
        ApplicationServices.execute_runtime_command(service,command_id='qa47-start-0000001',command='trading.start',payload={'source':'binance'})
    assert send.called is worker_alert
