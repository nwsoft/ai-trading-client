"""No credentials/network: actual producers -> indexed storage -> UI query."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from trading.execution_mode import ExecutionMode
from trading.learning_storage import LearningStore
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from web_platform.query_services import AccountQueryService

VENUES = ['binance', 'okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone']


@pytest.mark.parametrize('venue', VENUES)
@pytest.mark.parametrize('mode', list(ExecutionMode))
def test_runtime_indicators_survive_learning_store_and_query(tmp_path, monkeypatch, venue, mode):
    store = LearningStore(tmp_path)
    def save(row):
        row['_learning_event_id'] = 'test-event'
        store.append(venue, row)
    manager = SimpleNamespace(add_learning_data=save)
    trader = object.__new__(Trader if venue == 'binance' else UnifiedTrader)
    trader.logger = MagicMock()
    trader._learning_manager = manager
    trader._learning_managers = {venue: manager}
    trader._execution_mode = MagicMock(return_value=mode)
    trader._collect_symbol_performance_snapshot = MagicMock(return_value={})
    trader._collect_symbol_performance_snapshot_unified = MagicMock(return_value={})
    trader._generate_ai_learning_data(venue, 'BTCUSDT', {
        'signal': 'SHORT', 'confidence': .5, 'rsi': 0.0, 'macd': -.1826,
        'macd_signal': -.0691, 'trend': 'DOWN', 'reason': 'fixture',
    })
    monkeypatch.setattr('web_platform.query_services.get_exchange_ai_learning_data_path',
                        lambda source: str(tmp_path / 'legacy.json'))
    rows = AccountQueryService(str(tmp_path / 'unused.db')).learning_snapshot(source=venue)['records']
    assert len(rows) == 1
    assert rows[0]['rsi'] == 0.0
    assert rows[0]['macd'] == -.1826
    assert rows[0]['macd_signal'] == -.0691
    assert rows[0]['trend'] == 'DOWN'
    assert rows[0]['indicator_status'] == 'available'
    assert rows[0]['execution_mode'] == mode.value


@pytest.mark.parametrize('compact', [False, True])
def test_legacy_nested_and_absent_indicators_are_not_invented(tmp_path, monkeypatch, compact):
    rows = [
        {'exchange': 'binance', 'timestamp': '2026-09-22T00:00:00Z',
         '_learning_event_id': 'nested', 'indicators': {'rsi': 42, 'macd': 0}, 'market_trend': 'flat'},
        {'exchange': 'binance', 'timestamp': '2026-09-22T00:01:00Z',
         '_learning_event_id': 'missing', 'reason': 'MACD -0.1826; not a structured measurement'},
    ]
    path = tmp_path / 'legacy.json'
    if compact:
        store = LearningStore(tmp_path)
        for row in rows:
            store.append('binance', row)
    else:
        path.write_text(json.dumps(rows))
    monkeypatch.setattr('web_platform.query_services.get_exchange_ai_learning_data_path', lambda source: str(path))
    result = AccountQueryService(str(tmp_path / 'unused.db')).learning_snapshot(source='binance')['records']
    assert result[0]['rsi'] == 42
    assert result[0]['macd'] == 0
    assert result[0]['trend'] == 'flat'
    assert result[1]['rsi'] is None and result[1]['macd'] is None
    assert result[1]['indicator_status'] == 'not_recorded'


@pytest.mark.parametrize('invalid', [True, '', 'nan', float('inf'), {}, []])
def test_invalid_indicators_are_not_valid_numbers(invalid):
    from trading.indicator_evidence import indicator_snapshot
    result = indicator_snapshot({'rsi': invalid, 'macd': invalid})
    assert result['rsi'] is None and result['macd'] is None
    assert result['indicator_status'] == 'not_recorded'


@pytest.mark.parametrize('venue', ['kiwoom', 'kis', 'shinhan', 'miraeasset'])
@pytest.mark.parametrize('is_etf', [False, True])
def test_stock_etf_query_preserves_nested_evidence_and_missing_values(tmp_path, venue, is_etf):
    import sqlite3
    from trading.decision_storage import ensure_schema, save
    db = tmp_path / 'trading.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE ai_decisions(id INTEGER PRIMARY KEY, symbol TEXT, decision_type TEXT, decision_json TEXT, user_feedback TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        ensure_schema(conn)
        save(conn, '069500' if is_etf else '005930', 'stock_analyze_symbol', {
            'broker': venue, 'execution_mode': 'paper', 'is_etf': is_etf,
            'indicators': {'rsi': 45, 'macd': -.05}, 'trend': 'down',
        }, exchange=venue)
    rows = AccountQueryService(str(db)).learning_snapshot(source=venue)['records']
    assert len(rows) == 1
    assert (rows[0]['rsi'], rows[0]['macd'], rows[0]['trend']) == (45, -.05, 'down')
    assert rows[0]['instrument_type'] == ('etf' if is_etf else 'stock')


@pytest.mark.parametrize('indicators,expected', [
    (None, None), ({'rsi_15m': 50}, None), ({'rsi_15m': True, 'rsi_1h': 50}, None),
    ({'rsi_15m': float('nan'), 'rsi_1h': 50}, None),
    ({'rsi_15m': 0, 'rsi_1h': 0}, 50), ({'rsi_15m': 50, 'rsi_1h': 50}, 80),
])
def test_selection_technical_score_requires_both_real_rsi_values(indicators, expected):
    from trading.evaluator import Evaluator
    evaluator = Evaluator(analyzer=SimpleNamespace(), recorder=None, settings={})
    evaluator.calculate_technical_indicators = MagicMock(side_effect=AssertionError('no network'))
    coin = {'symbol': 'BTCUSDT', 'is_major': True, 'priceChange': 10, 'priceChangePercent': 12,
            'quoteVolume': 10000000, 'count': 1000000, '_selection_technical_indicators': indicators}
    rows = evaluator._calculate_trading_scores([coin])
    assert len(rows) == 1
    assert rows[0]['technical_score'] == expected
    assert rows[0]['technical_data_available'] == (expected is not None)
    evaluator.calculate_technical_indicators.assert_not_called()


@pytest.mark.parametrize('configured,expected', [(0, 0), (None, 600), (300, 300)])
def test_unified_start_uses_same_dwell_setting_as_running_loop(configured, expected):
    trader = object.__new__(UnifiedTrader)
    trader.settings = {'market_regime_min_dwell_seconds': configured}
    trader.logger = MagicMock()
    trader._is_trade_enabled = MagicMock(return_value=True)
    trader._is_learning_enabled = MagicMock(return_value=True)
    trader._ensure_exchange_initialized = MagicMock(return_value=True)
    trader.monitoring_flags = {}
    trader.selected_coins = {}
    trader.last_market_regime_by_exchange = {}
    trader._evaluate_current_market_conditions_unified_fast = MagicMock(return_value='normal')
    trader._regime_stabilizer = SimpleNamespace(observe=MagicMock(return_value=('normal', False)))
    # Stop before a worker is started; only verify the actual startup observation path.
    trader.select_trading_coins_unified = MagicMock(return_value=[])
    assert trader.start_trading('okx') is False
    assert trader._regime_stabilizer.observe.call_args.kwargs['min_dwell_seconds'] == expected
