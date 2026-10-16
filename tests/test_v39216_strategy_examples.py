"""User's exact legacy example, canonical sources and safe failure boundaries."""
import json
from pathlib import Path
import pytest
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.custom_strategy_presets import get_beginner_preset, render_preset_source
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from web_platform.application_services import ApplicationServices

ORIGINAL = '''전략명: 추세 따라가기
목적: 명확한 추세에서만 이동평균 정렬 방향으로 진입한다.
시장상황: 상승장, 하락장, 추세장. 횡보장과 HIGH 고변동에서는 신규 진입하지 않는다.
LONG 진입: EMA20 > EMA50 > EMA200, 현재 가격 > EMA20, RSI는 50 이상 75 이하, 거래량은 최근 평균 이상.
SHORT 진입: EMA20 < EMA50 < EMA200, 현재 가격 < EMA20, RSI는 25 이상 50 이하, 거래량은 최근 평균 이상.
청산: EMA20과 EMA50 정렬이 반대로 바뀌거나 가격이 EMA50을 반대 방향으로 확정 이탈할 때.
손절: ATR 기반 또는 최근 스윙 지점 밖. 익절: 최소 예상 손익비 1.8 이상.
포지션: 1회 위험예산 0.5%, 증거금 최대 10%, 레버리지 상한 3배.
공통 안전: 큰 시간대와 진입 신호가 충돌하거나 유동성·스프레드·손익비 기준 미달이면 HOLD한다.
이 초안은 성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않는다.
판단 시간봉: 15m (완성된 봉 기준)'''


def test_exact_user_example_keeps_explicit_branches_and_reports_real_missing_definitions():
    result=StrategySourceIngestor().analyze(ORIGINAL,kind='text');rules=result['rules']
    assert not result['ready_for_execution']
    assert rules['source_evidence']['text']==ORIGINAL
    assert rules['decision_timeframe']=='15m'
    assert rules['market_conditions']==['상승장','하락장']
    assert set(rules['independent_entries'])=={'LONG','SHORT'}
    assert 'ema200' in json.dumps(rules['independent_entries'])
    assert '"value": 75' in json.dumps(rules['independent_entries']) and '"value": 25' in json.dumps(rules['independent_entries'])
    assert rules['stop_loss'].startswith('ATR') and '손익비 1.8' in rules['take_profit']
    assert 'sl_percent' not in rules['engine_settings'] and 'tp_percent' not in rules['engine_settings']
    codes=result['missing_conditions']
    assert 'stop_loss_definition_required' in codes and 'take_profit_risk_reward_requires_definition' in codes
    assert 'stop_loss' not in codes and 'take_profit_unit_missing' not in codes
    titles=[q['title'] for q in result['clarification_questions']]
    assert '손절 조건 항목이 없습니다' not in titles and '실행 가능한 확인 조건이 없습니다' not in titles
    assert {'volume_average_period_required','direction_exit_definition_required','safety_thresholds_require_definition','volatility_scope_definition_required'} <= {g['reason'] for g in rules['source_condition_gaps']}
    assert not ApplicationServices.__new__(ApplicationServices).validate_strategy_draft(rules=rules)['ready']


def test_fixing_only_rates_does_not_drop_unresolved_guards_or_enable_original():
    text=ORIGINAL.replace('ATR 기반 또는 최근 스윙 지점 밖','1%').replace('최소 예상 손익비 1.8 이상','1.8%')
    result=StrategySourceIngestor().analyze(text,kind='text')
    assert not result['ready_for_execution'] and 'source_conditions_require_definition' in result['missing_conditions']
    assert result['rules']['engine_settings']['tp_percent']==1.8


@pytest.mark.parametrize('extra',['AND unknown_filter > 0','AND __import__("os").system("unused")','AND rsi >'])
def test_unknown_clause_is_not_silently_reduced_to_known_ema_conditions(extra):
    source=get_beginner_preset('trend_follow')['source_text'].replace('ema20 > ema50', 'ema20 > ema50 '+extra,1)
    result=StrategySourceIngestor().analyze(source,kind='text')
    assert not result['ready_for_execution'] and result['rules']['source_condition_gaps']


@pytest.mark.parametrize('timeframe',['15m (완성된 봉 기준)','15m','1d (완성된 봉 기준)'])
def test_declared_timeframe_with_annotation_is_preserved(timeframe):
    source=get_beginner_preset('trend_follow')['source_text'].replace('15m (완성된 봉 기준)',timeframe)
    result=StrategySourceIngestor().analyze(source,kind='text')
    assert result['ready_for_execution'] and result['rules']['decision_timeframe']==timeframe.split()[0]


@pytest.mark.parametrize('timeframe',['9m (완성된 봉 기준)','15m (임의의 다른 기준)'])
def test_invalid_or_unknown_timeframe_annotation_is_never_executed(timeframe):
    source=get_beginner_preset('trend_follow')['source_text'].replace('15m (완성된 봉 기준)',timeframe)
    result=StrategySourceIngestor().analyze(source,kind='text')
    assert not result['ready_for_execution']


@pytest.mark.parametrize('direction,context',[
 ('LONG',dict(ema20=110,ema50=105,ema200=100,current_price=111,rsi=60,volume_ratio=1.1)),
 ('SHORT',dict(ema20=100,ema50=105,ema200=110,current_price=99,rsi=40,volume_ratio=1.1))])
def test_both_canonical_trend_directions_reach_existing_engine_without_base_signal(direction,context):
    rules=StrategySourceIngestor().analyze(get_beginner_preset('trend_follow')['source_text'],kind='text')['rules']
    branch={**rules,'executable_entry':rules['independent_entries'][direction]}
    assert not Engine.evaluate_entry(branch,context)['allowed']  # missing 15m is never a pass
    assert Engine.evaluate_entry(branch,{**context,'_strategy_timeframe_contexts':{'15m':context}})['allowed']
    assert not Engine.evaluate_entry(branch,{**context,'_strategy_timeframe_contexts':{'15m':{**context,'volume_ratio':0.5}}})['allowed']


def test_generated_browser_catalog_matches_backend_and_stock_is_explicitly_long_only():
    from scripts.export_strategy_presets import payload
    root=Path(__file__).resolve().parents[1]
    assert json.loads((root/'webui/src/generated/strategy-presets.json').read_text())==payload()
    for row in payload()[1:]:
        crypto=StrategySourceIngestor().analyze(row['source'],kind='text')
        stock=StrategySourceIngestor().analyze(row['stock_source'],kind='text')
        assert crypto['ready_for_execution'] and stock['ready_for_execution']
        assert set(crypto['rules']['independent_entries'])=={'LONG','SHORT'}
        assert stock['rules']['entry_signal']=='LONG' and stock['rules']['decision_timeframe']=='1d'
        assert not stock['rules'].get('independent_entries')


@pytest.mark.parametrize('asset',['crypto','stock'])
def test_mentor_source_preserves_custom_budget_and_actual_generated_rules(asset):
    from trading.custom_strategy_mentor import recommend_strategy_candidates
    profile=dict(asset_class=asset,capital_band='small',max_loss_percent=0.7,review_frequency='daily',
                 trade_frequency='medium',leverage_allowed=False,experience_level='beginner',paper_ready=True)
    candidates=recommend_strategy_candidates(profile)
    assert len(candidates)==3
    for candidate in candidates:
        original=candidate['draft_rules']
        result=StrategySourceIngestor().analyze(candidate['source_text'],kind='text')
        assert result['ready_for_execution'], result['missing_conditions']
        assert result['rules']['risk_model']['risk_per_trade_percent']==0.7
        assert result['rules']['engine_settings']==original['engine_settings']
        assert result['rules']['decision_timeframe']==original['decision_timeframe']
        assert result['rules'].get('independent_entries',{}).keys()==original.get('independent_entries',{}).keys()


@pytest.mark.parametrize('text',[
 '횡보장 예제 설명. 상승장, 하락장에만 사용. 횡보장과 HIGH 고변동에서는 신규 진입하지 않는다.',
 '상승장, 하락장. 횡보장 및 고변동성 사용하지 않는다.',
])
def test_joined_exclusions_and_repeated_mentions_never_widen_included_markets(text):
    suggestion=StrategySourceIngestor.infer_market_regimes(text)
    assert suggestion['regimes']==['bull','bear']
    assert set(suggestion['excluded_regimes'])=={'range','volatile'}


def test_conflicting_timeframes_and_duplicate_directions_fail_closed():
    source=get_beginner_preset('trend_follow')['source_text']
    for extra in ['\nTIMEFRAME: 1h','\nLONG 진입: rsi > 50']:
        result=StrategySourceIngestor().analyze(source+extra,kind='text')
        assert not result['ready_for_execution']


def test_source_compile_and_submit_cannot_start_or_approve_incomplete_original(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    pipeline=CustomStrategyPipeline(str(tmp_path/'isolated.json'))
    analysis=StrategySourceIngestor().analyze(ORIGINAL,kind='text')
    version=pipeline.submit(name='original',rules=analysis['rules'])
    assert version['status']=='needs_clarification'
    with pytest.raises(ValueError):
        pipeline.approve(version['strategy_key'],version['version_id'],approved_by='synthetic')
    assert not pipeline.active_versions and not pipeline.paper_versions
