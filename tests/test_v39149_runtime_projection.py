import json
import statistics
import time
from types import SimpleNamespace

import pytest

from trading.operation_evidence import publish, snapshot, reset, candidate
from trading.strategy_scope import runtime_paper_pool, scoped_pool, paper_pool_status
from trading.trade_candidate import evaluate_trade_candidate

VENUES = ['binance','upbit','bithumb','coinone','bybit','okx','bitget','kis','kiwoom','mirae','shinhan']


def test_regime_history_bounds_deduplicates_and_preserves_scope():
    owner = SimpleNamespace()
    for i in range(100):
        publish(owner, 'binance', 'regime', mode='paper',
                observed='bull' if i % 2 else 'range', confirmed='range', symbol='X')
    rows = snapshot(owner, 'binance', 'paper')['regime_history']
    assert len(rows) == 24
    publish(owner, 'binance', 'regime', mode='paper', observed='bull', confirmed='range', symbol='X')
    assert snapshot(owner, 'binance', 'paper')['regime_history'] == rows
    rows[0]['observed'] = 'mutated'
    assert snapshot(owner, 'binance', 'paper')['regime_history'][0]['observed'] != 'mutated'
    assert 'regime_history' not in snapshot(owner, 'binance', 'live')
    assert 'regime_history' not in snapshot(owner, 'upbit', 'paper')
    assert 'regime_history' not in snapshot(SimpleNamespace(), 'binance', 'paper')
    reset(owner, 'binance')
    assert 'regime_history' not in snapshot(owner, 'binance', 'paper')


def test_overview_projection_all_venues_no_io_partial_failure_isolated():
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge = HeadlessRuntimeBridge.__new__(HeadlessRuntimeBridge)
    bridge._app = None
    bridge._settings = lambda: pytest.fail('must not read settings file')
    bridge._ensure_app = lambda: pytest.fail('must not start engine')
    crypto = bridge.operation_overview_snapshot(service='blockchain')
    stock = bridge.operation_overview_snapshot(service='stock')
    assert len(crypto) == 7 and len(stock) == 4
    assert set(crypto) | set(stock) == set(VENUES)
    assert all(row['status'] == 'unavailable' for row in [*crypto.values(), *stock.values()])
    assert bridge.operation_overview_snapshot(service='portfolio') == {}
    original = bridge.operation_summary_snapshot
    def fail_one(*, source, **kwargs):
        if source == 'binance':
            raise RuntimeError('projection only')
        return original(source=source, **kwargs)
    bridge.operation_summary_snapshot = fail_one
    assert len(bridge.operation_overview_snapshot(service='blockchain')) == 7


def test_overview_payload_and_latency_are_bounded_without_pool_recalculation(monkeypatch):
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge = HeadlessRuntimeBridge.__new__(HeadlessRuntimeBridge)
    owner = SimpleNamespace()
    bridge._app = SimpleNamespace(settings={'paper_trading': True}, trader=owner, unified_trader=owner)
    monkeypatch.setattr('trading.strategy_scope.paper_pool_status', lambda *a, **k: pytest.fail('overview must not recalculate unused pool'))
    for venue in VENUES[:7]:
        for i in range(30):
            publish(owner, venue, 'regime', mode='paper', observed='bull' if i % 2 else 'range', confirmed='range')
    durations = []
    for _ in range(100):
        start = time.perf_counter()
        result = bridge.operation_overview_snapshot(service='blockchain')
        durations.append((time.perf_counter() - start) * 1000)
    size = len(json.dumps(result).encode())
    p95 = statistics.quantiles(durations, n=20)[18]
    print(f'overview 7 venues 24 transitions bytes={size} p95_ms={p95:.3f}')
    assert size < 64 * 1024
    assert p95 < 20
    assert all('paper_pool' not in row for row in result.values())


def test_projection_metadata_failure_does_not_raise_into_engine():
    from trading.operation_evidence import mode_for, generation
    class BrokenOwner:
        def __getattr__(self, name):
            raise RuntimeError('presentation metadata unavailable')
    owner = BrokenOwner()
    assert mode_for(owner, 'binance') == 'unknown'
    assert generation(owner, 'binance') is None
    publish(owner, 'binance', 'regime', observed='bull')


def test_engines_bound_primary_pool_before_indicator_enrichment():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('trader.py', 'unified_trader.py'):
        source = (root / 'trading' / name).read_text(encoding='utf-8')
        start = source.index("strategy_pool = getattr(self, 'active_custom_strategy_pool', []) or []")
        end = source.index('state_pool=strategy_pool', start)
        assert 'strategy_pool = scoped_pool(' in source[start:end]
    source = (root / 'trading' / 'stock_analysis_service.py').read_text(encoding='utf-8')
    assert 'state_pool=evaluation_pool' in source
    assert 'strategy_pool=evaluation_pool' in source


def pool(count=40):
    return [dict(id=str(i), version_id=f'v{i}', strategy_key=f's{i}', name=f'S{i}',
                 target_scope='asset:all', priority=5, operation_mode='paper_validation',
                 signal_mode='independent', market_regimes=['all'],
                 rules={'signal_mode':'independent','entry_signal':'LONG',
                        'executable_entry':{'all':[{'field':'rsi','operator':'lt','value':50}]}})
            for i in range(count)]


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('grade,cap', [('premium',30),('pro_coin',10),('pro_stock',10),('referral',10)])
def test_paper_selection_counts_match_execution_all_venues(venue, grade, cap):
    original = pool()
    tagged = runtime_paper_pool(original, SimpleNamespace(current_user_grade=grade, settings={}))
    selected = scoped_pool(tagged, asset_class='stock' if venue in VENUES[7:] else 'crypto', target=venue)
    assert len(selected) == cap
    assert len(scoped_pool(original, asset_class='crypto', target=venue)) == 10
    assert all('_runtime_paper_limit' not in row for row in original)
    status = paper_pool_status(tagged, asset_class='stock' if venue in VENUES[7:] else 'crypto', target=venue)
    assert (status['scope_eligible'], status['selected'], status['waiting']) == (40, cap, 40-cap)
    result = evaluate_trade_candidate(symbol='TEST', context={'rsi':30,'signal':'LONG'}, strategy_pool=tagged,
                                      asset_class='stock' if venue in VENUES[7:] else 'crypto', target=venue,market_regime='range')
    assert result.allowed
    assert len(result.evaluation['evaluated']) == cap


def test_limits_do_not_expand_live_or_change_saved_rows():
    items = pool()
    for row in items: row['operation_mode'] = 'standard'
    assert len(scoped_pool(runtime_paper_pool(items, SimpleNamespace(current_user_grade='premium', settings={})), asset_class='crypto',target='binance')) == 10
    for grade, requested, expected in [('premium',9999,30),('pro_coin',30,10),('premium',8,8),('premium','bad',30)]:
        tagged = runtime_paper_pool(pool(), SimpleNamespace(current_user_grade=grade,settings={'paper_strategy_evaluation_limit':requested}))
        assert len(scoped_pool(tagged,asset_class='crypto',target='binance')) == expected
    premium = runtime_paper_pool(pool(),SimpleNamespace(current_user_grade='premium',settings={}))
    downgraded = runtime_paper_pool(premium,SimpleNamespace(current_user_grade='pro_coin',settings={}))
    assert len(scoped_pool(downgraded,asset_class='crypto',target='binance')) == 10


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('mode', ['paper','live','learning'])
def test_projection_is_isolated_bounded_and_not_refreshed_on_read(venue, mode):
    owner = SimpleNamespace()
    publish(owner, venue, 'regime', mode=mode, observed='range', confirmed='bull', changed=False,
            api_key='secret', rules={'anything':'private'}, reason='x'*10000)
    first = snapshot(owner, venue, mode)
    assert snapshot(SimpleNamespace(), venue, mode)['status'] == 'unavailable'
    assert snapshot(owner, venue, 'other')['status'] == 'unavailable'
    assert first == snapshot(owner, venue, mode)
    serialized = json.dumps(first)
    assert len(serialized.encode()) < 32768 and 'secret' not in serialized and 'private' not in serialized
    assert first['regime']['observed'] != first['regime']['confirmed']
    reset(owner, venue)
    assert snapshot(owner, venue, mode)['status'] == 'unavailable'


def test_candidate_is_not_an_order_and_read_has_no_adapter():
    owner = SimpleNamespace()
    result = evaluate_trade_candidate(symbol='X',context={'rsi':30,'signal':'LONG'},strategy_pool=pool(1),asset_class='crypto',target='binance',market_regime='range')
    candidate(owner,result,{},'paper')
    projection = snapshot(owner,'binance','paper')
    assert projection['candidate']['allowed'] is True
    assert projection['candidate']['version_id'] == 'v0'
    assert projection['candidate']['checks'][0]['passed'] is True
    assert projection['protection_status'] == 'not_projected'
    assert 'regime' not in projection  # Candidate regime is not a fresh regime observation.


def test_late_worker_result_cannot_revive_previous_generation():
    from trading.operation_evidence import generation
    owner=SimpleNamespace()
    epoch=generation(owner,'binance')
    reset(owner,'binance')
    publish(owner,'binance','regime',mode='paper',expected_generation=epoch,observed='bull')
    assert snapshot(owner,'binance','paper')['status']=='unavailable'


def test_projection_benchmark_and_memory_bound():
    owner=SimpleNamespace()
    durations=[]
    for i in range(500):
        start=time.perf_counter()
        publish(owner, f'venue{i%100}', 'candidate', mode='paper', reason='x'*1000)
        snapshot(owner,f'venue{i%100}','paper')
        durations.append((time.perf_counter()-start)*1000)
    assert len(owner._operation_evidence) == 33
    p95=statistics.quantiles(durations,n=20)[18]
    print(f'projection write+read p95_ms={p95:.3f}')
    assert p95 < 5


def test_bridge_summary_reads_only_memory_and_is_optional():
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    bridge=HeadlessRuntimeBridge.__new__(HeadlessRuntimeBridge)
    bridge._settings=lambda: (_ for _ in ()).throw(AssertionError('disk read'))
    bridge._ensure_app=lambda: (_ for _ in ()).throw(AssertionError('engine start'))
    bridge._app=None
    assert bridge.operation_summary_snapshot(source='binance')['status']=='unavailable'
    risk=SimpleNamespace(source='binance',execution_mode='paper',blocked=False,status='not_applicable',checked_at=12,reason='PAPER')
    owner=SimpleNamespace()
    bridge._app=SimpleNamespace(settings={'paper_trading':True},trader=owner,
        active_custom_strategy_pool=runtime_paper_pool(pool(),SimpleNamespace(current_user_grade='premium',settings={})),
        risk_manager=SimpleNamespace(_last_daily_loss_decision={'binance':risk}))
    publish(owner,'binance','candidate',mode='paper',symbol='X',allowed=False)
    snapshot1=bridge.operation_summary_snapshot(source='binance')
    assert snapshot1['paper_pool']['waiting']==10
    assert snapshot1['risk']['observed_at']==12
    assert snapshot1==bridge.operation_summary_snapshot(source='binance')


def test_10_30_pool_shared_candles_and_projection_do_not_change_decisions():
    from trading.custom_strategy_validator import enrich_advanced_indicator_context
    from trading.source_condition_compiler import ConditionCompiler
    from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
    now=int(time.time()*1000)
    rows=[[now-(320-i)*300000,100+i/100,102+i/100,98+i/100,100+i/100,20] for i in range(310)]
    timings={}
    for size in (10,30):
        items=runtime_paper_pool(pool(size),SimpleNamespace(current_user_grade='premium',settings={}))
        for item in items:
            item['rules'].update(decision_timeframe='5m',executable_entry={'expression':ConditionCompiler().compile('all_for(close > support_level AND di_plus > di_minus, 5)')})
        durations=[]
        for _ in range(30):
            calls=[]
            started=time.perf_counter()
            context=enrich_advanced_indicator_context({'signal':'LONG'},items,lambda tf,n:calls.append((tf,n)) or rows)
            Engine._paper_rotation_counters={}
            result=evaluate_trade_candidate(symbol='TEST',context=context,strategy_pool=items,asset_class='crypto',target='binance',market_regime='range')
            before=result.to_dict()
            candidate(SimpleNamespace(),result,context,'paper')
            assert before==result.to_dict()
            assert len(calls)==1  # per timeframe, not per strategy
            assert result.allowed
            durations.append((time.perf_counter()-started)*1000)
        timings[size]=round(statistics.quantiles(durations,n=20)[18],3)
    print('synthetic_shared_context_candidate_p95_ms='+json.dumps(timings))
