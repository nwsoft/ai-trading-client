import math
from datetime import datetime, timezone

import pytest

from trading.condition_fields import CONTRACT, FIELDS, values
from trading.custom_strategy_validator import _context, enrich_advanced_indicator_context
from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
from trading.source_condition_compiler import ConditionCompiler


def candles(count=100):
    return [dict(timestamp=(i+1)*300000, open=100+i, high=102+i,
                 low=98+i, close=100+i, volume=20) for i in range(count)]


def test_definitions_and_no_lookahead():
    rows = candles()
    result = values(rows)
    assert result['support_level'] == 179
    assert result['resistance_level'] == 198  # current close is 199
    returns = [math.log((180+i)/(179+i)) for i in range(20)]
    mean = sum(returns)/20
    assert result['volatility'] == pytest.approx(math.sqrt(sum((v-mean)**2 for v in returns)/20)*100)
    assert result['historical_volatility'] == result['volatility']
    assert result['di_plus'] == 25
    assert result['di_minus'] == 0
    before = _context(rows, 90, 'LONG')
    rows[-1]['close'] = 99999
    assert _context(rows, 90, 'LONG') == before


@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), -1, True])
def test_invalid_is_unknown_not_zero(bad):
    rows = candles()
    rows[-1]['high'] = bad
    assert all(v is None for v in values(rows).values())
    assert all(v is None for v in values(rows[:20]).values())


def test_analyzer_fields_cannot_impersonate_closed_bar_fields():
    node = ConditionCompiler().compile('close > support_level')
    assert not Engine._evaluate_expression_node(node, {'close': 200, 'support_level': 180})[0]
    assert Engine._evaluate_expression_node(node, {'close': 200, 'support_level': 180, '_condition_fields_contract': CONTRACT})[0]
    assert not Engine.validate_rule_spec({'executable_entry': {'expression': node}})['valid']
    assert Engine.validate_rule_spec({'decision_timeframe': '5m', 'executable_entry': {'expression': node}})['valid']


@pytest.mark.parametrize('venue', ['binance','upbit','bithumb','coinone','bybit','okx','bitget','kis','mirae','kiwoom','shinhan'])
def test_common_live_replay_temporal_contract(venue):
    now = int(datetime.now(timezone.utc).timestamp())*1000
    rows = [[now-(110-i)*300000, 100+i, 102+i, 98+i, 100+i, 20] for i in range(100)]
    rows.append([now, 99999, 99999, 99999, 99999, 20])
    rules = {'decision_timeframe': '5m', 'executable_entry': {'expression': ConditionCompiler().compile('all_for(close > support_level AND di_plus > di_minus, 2)')}}
    calls = []
    enriched = enrich_advanced_indicator_context({'exchange': venue}, rules, lambda tf,n: calls.append(tf) or rows)
    scoped = enriched['_strategy_timeframe_contexts']['5m']
    assert calls == ['5m']
    assert scoped['close'] == 199
    assert scoped['_condition_fields_contract'] == CONTRACT
    assert all(b['_condition_fields_contract'] == CONTRACT for b in scoped['_closed_bar_contexts'])
    assert Engine.evaluate_entry(rules, enriched)['allowed']


def test_all_new_names_compile():
    for name in FIELDS:
        assert ConditionCompiler().compile(f'{name} > 0')


def test_legacy_named_state_is_not_reinterpreted_as_new_indicator():
    from trading.numeric_strategy_state import NumericStateStore, fields, validate
    for name in FIELDS:
        program={'initial':{name:1},'updates':{name:f'{name} + 1'}}
        assert validate(program)==[]
        assert fields(program)==set()
        result=NumericStateStore().advance(program,{'version':'legacy'},[{'_bar_timestamp':1,name:999}])
        assert result['values'][name]==2


def test_numeric_update_new_indicator_on_closed_bars():
    from trading.numeric_strategy_state import NumericStateStore
    program={'initial':{'saved':0},'updates':{'saved':'support_level'}}
    result=NumericStateStore().advance(program,{'version':'v49'},[{'_bar_timestamp':1, **values(candles())}])
    assert result['values']['saved']==179


@pytest.mark.parametrize('level', range(1,6))
@pytest.mark.parametrize('scope', ['exchange:binance','asset:stock','broker:kis'])
def test_new_fields_same_ir_approval_and_optional_replay_all_levels(tmp_path,level,scope):
    from copy import deepcopy
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    from trading.noah_strategy_ir import NoahStrategyIR
    from test_v39147_strategy_repair import compiled
    rules=compiled()
    rules.pop('source_grounding',None)
    rules.pop('source_evidence',None)
    rules.update(target_scope=scope,decision_timeframe='15m',execution_timeframe='15m',entry='close > support_level')
    rules['executable_entry']={'expression':ConditionCompiler().compile('close > support_level')}
    pipeline=CustomStrategyPipeline(storage_path=tmp_path/'v49.json')
    row=pipeline.submit(name='manual closed bar fixture',rules=rules)
    before=deepcopy(row['strategy_ir'])
    projected=NoahStrategyIR.project(row['strategy_ir'],level)
    assert projected['integrity_sha256']==row['ir_hash']
    assert row['strategy_ir']==before
    pipeline.approve(row['strategy_key'],row['version_id'],approved_by='fixture')
    result=pipeline.start_paper_observation(row['strategy_key'],row['version_id'])
    assert result['status']=='paper_observing'
    assert not result.get('execution_validation')
    assert not pipeline.active_versions


def test_etf_uses_stock_venue_contract_not_an_invented_ir_scope():
    from trading.noah_strategy_ir import NoahStrategyIR
    # The UI offers asset:stock/broker:* for stocks and ETFs. The literal
    # asset:etf is not a registered IR venue profile; do not silently approve it.
    assert 'asset:stock' in NoahStrategyIR.CAPABILITY_REGISTRY['venue_profiles']
    assert 'asset:etf' not in NoahStrategyIR.CAPABILITY_REGISTRY['venue_profiles']
