"""Upgrade audit uses explicit disposable copies and never exposes source text."""
from copy import deepcopy
import json
import re
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.audit_strategy_upgrade import run
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.custom_strategy_presets import get_beginner_preset
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.strategy_source_ingestor import StrategySourceIngestor

ROOT=Path(__file__).resolve().parents[1]


def test_private_copy_audit_preserves_source_bytes_permissions_and_hides_identifiers(tmp_path):
    stores=tmp_path/'stores';stores.mkdir();source=stores/'synthetic_private.json'
    pipeline=CustomStrategyPipeline(str(source))
    preset=get_beginner_preset('trend_follow')
    rules=StrategySourceIngestor().analyze(preset['source_text'],kind='text')['rules']
    pipeline.submit(name='PRIVATE-NAME-MUST-NOT-APPEAR',rules=rules,source_reference='private-reference')
    before=(source.read_bytes(),source.stat().st_mtime_ns,source.stat().st_mode)
    report=run(stores,baseline_root=ROOT)
    assert report['status']=='PASS' and report['counts']['versions']==1
    assert report['counts']['all_nonstatus_fields_preserved']==1
    assert not any(report['differences'].values()) and report['execution_grants_equal']
    assert (source.read_bytes(),source.stat().st_mtime_ns,source.stat().st_mode)==before
    serialized=json.dumps(report)
    assert 'PRIVATE-NAME' not in serialized and 'private-reference' not in serialized
    assert rules['entry'] not in serialized and not report['network_attempts']


def test_empty_store_is_a_valid_zero_sample_audit(tmp_path):
    (tmp_path/'empty_private.json').write_text('{"strategies":{}}')
    report=run(tmp_path)
    assert report['status']=='PASS' and report['counts']['versions']==0


def test_output_cannot_overwrite_any_original_store(tmp_path):
    source=tmp_path/'private_private.json';source.write_text('{"strategies":{}}')
    before=source.read_bytes()
    process=subprocess.run([sys.executable,str(ROOT/'scripts/audit_strategy_upgrade.py'),'--stores',str(tmp_path),
                            '--output',str(source)],capture_output=True)
    assert process.returncode!=0 and source.read_bytes()==before


@pytest.mark.parametrize('scope',['전체시장','시장전체','market','시장'])
def test_explicit_whole_market_source_alias_preserves_market_scope(scope):
    source=re.sub(r'(?m)^국면\s*기준:.*$', '국면기준: '+scope, get_beginner_preset('trend_follow')['source_text'])
    parsed=StrategySourceIngestor().analyze(source,kind='text')
    assert parsed['ready_for_execution']
    assert parsed['rules']['regime_scope']=='market'
    assert parsed['rules']['source_evidence']['text']==source


@pytest.mark.parametrize('scope',['자동','전체','whatever'])
def test_undefined_regime_scope_is_not_widened_to_market(scope):
    source=re.sub(r'(?m)^국면\s*기준:.*$', '국면기준: '+scope, get_beginner_preset('trend_follow')['source_text'])
    parsed=StrategySourceIngestor().analyze(source,kind='text')
    assert not parsed['ready_for_execution']
    assert 'source_regime_scope_invalid' in parsed['missing_conditions']


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('boundary',['real_cross','equal_previous','no_cross','missing_previous'])
def test_pullback_source_crossing_preserves_existing_field_pair_operator(direction,boundary):
    preset=get_beginner_preset('trend_pullback')
    parsed=StrategySourceIngestor().analyze(preset['source_text'],kind='text')
    assert parsed['ready_for_execution']
    base=deepcopy(preset['rules_template']);base.update(decision_timeframe='15m',execution_timeframe='15m')
    base['executable_entry']=base['independent_entries'][direction]
    compiled=deepcopy(parsed['rules']);compiled['executable_entry']=compiled['independent_entries'][direction]
    is_long=direction=='LONG'
    previous_price=99 if is_long else 101
    if boundary=='equal_previous':previous_price=100
    if boundary=='no_cross':previous_price=101 if is_long else 99
    previous=dict(current_price=previous_price,ema20=100,ema50=95 if is_long else 105,ema200=90 if is_long else 110)
    now=dict(current_price=101 if is_long else 99,ema20=100,ema50=95 if is_long else 105,
             ema200=90 if is_long else 110,rsi=50,volume_ratio=1.1)
    if boundary!='missing_previous':now['_previous']=previous
    # Completed bars deliberately did NOT cross. A live field-pair cross must
    # not silently become became_true(closed_bar_condition).
    closed=[{**previous,'_bar_timestamp':1},{**previous,'_bar_timestamp':2}]
    scoped={**now,'_closed_bar_contexts':closed}
    context={**now,'_strategy_timeframe_contexts':{'15m':scoped}}
    expected=Engine.evaluate_entry(base,context)['allowed']
    assert expected is (boundary in {'real_cross','equal_previous'})
    assert Engine.evaluate_entry(compiled,context)['allowed']==expected
    assert 'became_true' not in json.dumps(compiled['executable_entry'])


@pytest.mark.parametrize('call',['crosses_above(current_price, unknown)','crosses_below(signal, ema20)',
                                 'crosses_above(current_price, 1)','crosses_above(current_price)',
                                 'crosses_above(__import__("os"), ema20)'])
def test_crossing_call_accepts_only_existing_engine_field_pair_contract(call):
    text=get_beginner_preset('trend_pullback')['source_text']
    text=text.replace('crosses_above(current_price, ema20)',call)
    result=StrategySourceIngestor().analyze(text,kind='text')
    assert not result['ready_for_execution'] and result['rules']['source_condition_gaps']


@pytest.mark.parametrize('risk',[0.049,2.001,5,float('nan'),float('inf')])
def test_mentor_rejects_risk_values_that_existing_save_guard_rejects(risk):
    from trading.custom_strategy_mentor import validate_mentor_profile,recommend_strategy_candidates
    profile=dict(asset_class='crypto',capital_band='small',max_loss_percent=risk,review_frequency='daily',trade_frequency='medium',leverage_allowed=False,experience_level='beginner',paper_ready=True)
    assert not validate_mentor_profile(profile)['valid']
    assert recommend_strategy_candidates(profile)==[]


@pytest.mark.parametrize('risk',[0.05,2])
def test_mentor_risk_boundary_candidates_really_pass_final_save_validation(risk):
    from trading.custom_strategy_mentor import recommend_strategy_candidates
    from web_platform.application_services import ApplicationServices
    profile=dict(asset_class='stock',capital_band='small',max_loss_percent=risk,review_frequency='daily',trade_frequency='medium',leverage_allowed=False,experience_level='beginner',paper_ready=True)
    for candidate in recommend_strategy_candidates(profile):
        assert candidate['draft_rules']['risk_model']['risk_per_trade_percent']==risk
        assert ApplicationServices.__new__(ApplicationServices).validate_strategy_draft(rules=candidate['draft_rules'])['ready']
