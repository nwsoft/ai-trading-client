"""Release regressions: scope before limits, declared candles and broker RPC."""
import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from trading.paper_strategy_ledger import read_paper_strategy_outcomes, summarize_paper_outcomes
from trading.strategy_timeframes import strategy_timeframe_contract
from trading.custom_strategy_validator import enrich_advanced_indicator_context, run_historical_replay, _enrich_replay_context
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.exchanges.venue_capabilities import CRYPTO_VENUES, STOCK_VENUES
from web_platform.application_services import ApplicationServices
from web_platform.market_data import MultiSourcePublicMarketData


def outcome(venue, event, pnl=1.0):
    krw = venue not in {'binance', 'bybit', 'bitget', 'okx'}
    return dict(event_id=event, execution_mode='paper', exchange=venue,
                symbol='005930' if venue in STOCK_VENUES else 'BTCKRW' if krw else 'BTCUSDT',
                opened_at='2026-09-10T00:00:00+00:00', closed_at='2026-09-10T01:00:00+00:00',
                net_pnl=pnl, gross_pnl=pnl + .1, fees=.1, entry_price=100, quantity=1,
                quote_currency='KRW' if krw else 'USDT', calculation_status='valid',
                cost_calculation_status='recorded_contract')


@pytest.mark.parametrize('venue', sorted(set(CRYPTO_VENUES) | set(STOCK_VENUES)))
def test_other_venues_cannot_evict_selected_venue_statistics(tmp_path, venue):
    path = tmp_path / 'strategy_paper_outcomes.jsonl'
    other = 'upbit' if venue != 'upbit' else 'binance'
    selected = [outcome(venue, 'win', 2), outcome(venue, 'loss', -1)]
    unrelated = [outcome(other, str(i), 999) for i in range(650)]
    path.write_text('\n'.join(json.dumps(row) for row in selected + unrelated) + '\n', encoding='utf-8')
    rows = read_paper_strategy_outcomes(path=path, limit=2, sources={venue})
    assert [row['event_id'] for row in rows] == ['win', 'loss']
    service = object.__new__(ApplicationServices)
    service.data_dir = tmp_path
    stats = service._paper_statistics_snapshot(asset_class='stock' if venue in STOCK_VENUES else 'crypto', source=venue, period='all')
    summary = summarize_paper_outcomes(rows, default_currency=selected[0]['quote_currency'])
    assert stats['closed_count'] == summary['closed_count'] == 2
    assert stats['pnl_by_currency'] == summary['pnl_by_currency']
    assert stats['win_rate'] == summary['win_rate'] == 50
    assert stats['groups'][0]['rows'][0]['max_profit'] == 2
    assert stats['groups'][0]['rows'][0]['max_loss'] == -1


def test_period_limit_late_import_duplicates_and_malformed_lines(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    wanted = outcome('binance', 'wanted', 5)
    recent = {**outcome('binance', 'recent'), 'closed_at': '2026-09-12T00:00:00Z'}
    path.write_bytes((json.dumps(wanted) + '\n' + json.dumps(recent) + '\n' + json.dumps(wanted) + '\n{broken\n').encode())
    end = datetime(2026, 9, 11, tzinfo=timezone.utc).timestamp()
    rows = read_paper_strategy_outcomes(path=path, sources={'binance'}, end_epoch=end, limit=1)
    assert len(rows) == 1 and rows[0]['net_pnl'] == 5


def test_aggregate_cache_invalidates_on_append(tmp_path):
    path = tmp_path / 'strategy_paper_outcomes.jsonl'
    path.write_text(json.dumps(outcome('kis', 'a')) + '\n')
    service = object.__new__(ApplicationServices)
    service.data_dir = tmp_path
    assert service._paper_statistics_snapshot(asset_class='stock', source='kis', period='all')['closed_count'] == 1
    with path.open('a') as handle:
        handle.write(json.dumps(outcome('kis', 'b', -3)) + '\n')
    result = service._paper_statistics_snapshot(asset_class='stock', source='kis', period='all')
    assert result['closed_count'] == 2 and result['pnl_by_currency']['KRW'] == -2


def candles(step=60_000, count=220):
    start = 1785000000000
    return [[start + i * step, 100+i, 102+i, 99+i, 101+i, 1000, start+(i+1)*step-1] for i in range(count)]


@pytest.mark.parametrize('timeframe', ['1m', '5m', '15m', '4h', '1d'])
def test_declared_interval_drives_runtime_indicators(timeframe):
    rules = {'decision_timeframe': timeframe, 'executable_entry': {'all': [{'field': 'rsi', 'operator': 'gte', 'value': 70}]}}
    fetch = Mock(return_value=candles())
    context = enrich_advanced_indicator_context({'rsi': 0, 'signal': 'LONG'}, rules, fetch)
    assert fetch.call_args.args[0] == timeframe
    assert DeclarativeStrategyEngine.evaluate_entry(rules, context)['allowed']
    assert not DeclarativeStrategyEngine.evaluate_entry(rules, {'rsi': 100})['allowed']


def test_timeframe_missing_or_different_execution_interval_does_not_fallback():
    with pytest.raises(ValueError, match='미지정'):
        strategy_timeframe_contract({})
    with pytest.raises(ValueError, match='다른'):
        strategy_timeframe_contract({'decision_timeframe': '4h', 'execution_timeframe': '1m'})


def test_branch_timeframes_are_collected():
    rules = {'decision_timeframe': '5m', 'independent_entries': {'LONG': {'all': [
        {'indicator': 'rsi', 'period': 14, 'timeframe': '4h', 'operator': 'lte', 'value': 30}
    ]}}}
    assert strategy_timeframe_contract(rules)['required_timeframes'] == ['5m', '4h']


def test_coinone_public_chart_is_sorted_and_does_not_require_credentials():
    response = Mock()
    response.json.return_value = {'result': 'success', 'error_code': '0', 'chart': [
        {'timestamp': 1785000900000, 'open': '2', 'high': '3', 'low': '1', 'close': '2', 'target_volume': '4'},
        {'timestamp': 1785000000000, 'open': '1', 'high': '3', 'low': '1', 'close': '2', 'target_volume': '4'},
    ]}
    session = Mock()
    session.get.return_value = response
    result = MultiSourcePublicMarketData(session=session).get_candles('coinone', 'spot', 'BTCKRW', '15m', 100)
    assert [c.open_time for c in result.candles] == [1785000000000, 1785000900000]
    assert session.get.call_args.args[0].endswith('/chart/KRW/BTC')
    assert session.get.call_args.kwargs['params'] == {'interval': '15m', 'size': 100}


@pytest.mark.parametrize('explicit_close', [True, False])
def test_higher_timeframe_candle_not_visible_until_closed(explicit_close):
    rows = [{'timestamp': i * 3600 + 1000, 'close_timestamp': i * 3600 + 4599,
             'open': 100, 'high': 101, 'low': 99, 'close': 100+i, 'volume': 10} for i in range(100)]
    if not explicit_close:
        for row in rows:
            row.pop('close_timestamp')
    rules = {'executable_entry': {'all': [{'indicator': 'rsi', 'period': 14, 'timeframe': '1h', 'operator': 'gte', 'value': 0}]}}
    context = _enrich_replay_context({}, rules, [], timeframe_rows={'1h': rows}, cutoff_timestamp=rows[14]['timestamp'])
    assert context['_advanced_indicator_values'][0]['status'] == 'insufficient_data'


def test_kiwoom_timeout_drops_late_reply_without_order_retry():
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    proxy = KiwoomProcessProxy('qa', 'qa', '')
    proxy._ensure_process = Mock()
    proxy._connection = Mock()
    connection = proxy._connection
    connection.poll.return_value = False
    proxy._process = Mock()
    proxy._process.is_alive.return_value = False
    with pytest.raises(TimeoutError):
        proxy.place_order('005930', 'BUY', 1)
    assert connection.send.call_count == 2  # one order, one shutdown sentinel
    assert proxy._connection is None and not proxy.is_connected
    assert proxy.get_live_readiness()[0] is False
    with pytest.raises(RuntimeError, match='outcome_unknown'):
        proxy.place_order('005930', 'BUY', 1)


def test_kiwoom_connect_timeout_latches_and_does_not_restart_until_user_disconnects():
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    proxy = KiwoomProcessProxy('qa', 'qa', '')
    ensure_process = proxy._ensure_process = Mock()
    connection = proxy._connection = Mock()
    connection.poll.return_value = False
    proxy._process = Mock()
    proxy._process.is_alive.return_value = False

    with pytest.raises(TimeoutError, match='kiwoom_rpc_transport_error:connect'):
        proxy.connect()

    assert ensure_process.call_count == 1
    assert connection.send.call_count == 2  # connect request + shutdown sentinel
    assert proxy.connect() is False
    assert ensure_process.call_count == 1  # worker retry cannot create a new host
    assert 'kiwoom_manual_reconnect_required' in proxy.last_error
    assert proxy.get_live_readiness() == (False, proxy.last_error)

    assert proxy.disconnect() is True
    assert proxy._restart_blocked_reason == ''


def test_first_version_has_no_previous_version_diff(tmp_path):
    from trading.custom_strategy_pipeline import CustomStrategyPipeline
    rules = {'entry':'RSI < 30','exit':'MACD dead cross','stop_loss':1.0,'take_profit':2.0,'position_size':.05,'market_conditions':['trend','range']}
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / 'strategy.json'))
    first = pipeline.submit(name='initial', rules=rules)
    assert first['version_diff']['changes'] == []
    assert first['version_diff']['kind'] == 'initial_version'
    second = pipeline.submit(name='revised', rules={**rules, 'entry':'RSI < 25'}, strategy_key=first['strategy_key'])
    assert second['version_diff']['changes']


def test_bithumb_2h_is_complete_1h_groups_not_renamed_candles():
    response = Mock()
    start = 1785000000000 // 7200000 * 7200000
    response.json.return_value = {'status':'0000','data':[
        [start+i*3600000, 10+i, 11+i, 12+i, 9+i, 2] for i in range(5)
    ]}
    session = Mock()
    session.get.return_value = response
    result = MultiSourcePublicMarketData(session=session).get_candles('bithumb','spot','BTCKRW','2h',100)
    assert session.get.call_args.args[0].endswith('/1h')
    assert len(result.candles) == 2  # last partial group is not evidence
    assert result.candles[0].interval == '2h'
    assert result.candles[0].open == 10 and result.candles[0].close == 12
    assert result.candles[0].volume == 4


@pytest.mark.parametrize('interval,minutes', [('15m',15),('4h',240)])
def test_bithumb_native_interval_avoids_legacy_sample_truncation(interval,minutes):
    response = Mock()
    response.json.return_value = [{'candle_date_time_utc':'2026-09-01T00:00:00',
        'opening_price':10,'trade_price':11,'high_price':12,'low_price':9,'candle_acc_trade_volume':7}]
    session = Mock()
    session.get.return_value = response
    result = MultiSourcePublicMarketData(session=session).get_candles('bithumb','spot','BTCKRW',interval,200)
    assert session.get.call_args.args[0].endswith(f'/minutes/{minutes}')
    assert session.get.call_args.kwargs['params']['count'] == 200
    assert result.candles[0].interval == interval
    assert result.candles[0].close == 11


@pytest.mark.parametrize('failure', ['eof', 'mismatch'])
def test_kiwoom_broken_response_is_not_reused_or_retried(failure):
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    proxy = KiwoomProcessProxy('qa', 'qa', '')
    proxy._ensure_process = Mock()
    connection = proxy._connection = Mock()
    connection.poll.return_value = True
    if failure == 'eof':
        connection.recv.side_effect = EOFError()
    else:
        connection.recv.return_value = (999, True, {'order_id':'unrelated'})
    proxy._process = Mock()
    proxy._process.is_alive.return_value = False
    with pytest.raises((EOFError, OSError)):
        proxy.place_order('005930', 'BUY', 1)
    assert proxy._connection is None
    assert proxy.get_live_readiness()[0] is False
    assert connection.send.call_count == 2


def test_runtime_candles_drop_explicit_open_bars_and_sort_deduplicate():
    rules = {'decision_timeframe':'5m', 'executable_entry':{'all':[{'field':'rsi','operator':'gte','value':70}]}}
    rows = [{'timestamp':1700000000+i*300, 'open':100+i, 'high':101+i,
             'low':99+i, 'close':100+i, 'volume':10} for i in range(100)]
    polluted = [dict(rows[-1], closed=False, close=.01)] + list(reversed(rows)) + [rows[0]]
    clean = enrich_advanced_indicator_context({}, rules, lambda tf,n: rows)
    result = enrich_advanced_indicator_context({}, rules, lambda tf,n: polluted)
    assert result['_strategy_timeframe_contexts'] == clean['_strategy_timeframe_contexts']


def test_local_assistant_explains_declared_timeframe_and_publication_boundary():
    from config.ai_custom_knowledge import build_ai_custom_knowledge
    answer = build_ai_custom_knowledge('4시간봉인데 왜 15분봉 검증인가요?')
    assert '실제 확보된 봉 수' in answer and '미지원 분봉' in answer
    assert '실시간 PAPER' in answer
    update = build_ai_custom_knowledge('3.9.1.30 업데이트는?')
    assert '모든 기관의 연결과 배포 완료를 보장하지 않습니다' in update
