"""No real exchange calls; fault injection at the common startup boundary."""
from unittest.mock import Mock, patch
import pytest


@pytest.mark.parametrize('venue', ['okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone'])
@pytest.mark.parametrize('failure', ['mode', 'constructor', 'start'])
def test_failed_worker_start_never_leaves_running_flags(venue, failure):
    from trading.unified_trader import UnifiedTrader
    from trading.execution_mode import ExecutionMode
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = Mock()
    trader._is_trade_enabled = lambda _: True
    trader._is_learning_enabled = lambda _: False
    trader._ensure_exchange_initialized = lambda _: True
    trader.selected_coins = {venue: [{'symbol': 'TEST'}]}
    trader.monitoring_flags = {}; trader.trading_cycles = {}; trader.monitoring_threads = {}
    trader._monitoring_loop = Mock()
    trader._execution_mode = Mock(return_value=ExecutionMode.PAPER,
                                 side_effect=ValueError('private raw detail') if failure == 'mode' else None)
    worker = Mock(); worker.is_alive.return_value = False
    if failure == 'start': worker.start.side_effect = RuntimeError('private raw detail')
    with patch('trading.unified_trader.threading.Thread', return_value=worker,
               side_effect=RuntimeError('private raw detail') if failure == 'constructor' else None) as factory:
        with pytest.raises(RuntimeError, match=f'^runtime_start_exception:{venue}:worker_start$'):
            trader.start_trading_checked(venue)
        assert not trader.monitoring_flags.get(venue)
        assert not trader.trading_cycles.get(venue)
        assert venue not in trader.monitoring_threads
        if failure == 'mode': factory.assert_not_called()


def test_start_rejection_audit_preserves_only_known_stage():
    from web_platform.application_services import ApplicationServices
    service = ApplicationServices.__new__(ApplicationServices); service._audit = Mock()
    service.record_runtime_rejection('request', 'trading.start', 'okx', 'runtime_start_exception:okx:market_observation')
    assert service._audit.call_args.args[1]['stage'] == 'market_observation'
    service.record_runtime_rejection('request', 'trading.start', 'okx', 'runtime_start_exception:okx:SECRET')
    assert 'stage' not in service._audit.call_args.args[1]


def start_ready_trader(venue='okx'):
    from trading.unified_trader import UnifiedTrader
    from trading.execution_mode import ExecutionMode
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = Mock()
    trader._is_trade_enabled = lambda _: True
    trader._is_learning_enabled = lambda _: False
    trader._ensure_exchange_initialized = Mock(return_value=True)
    trader.selected_coins = {venue: [{'symbol': 'TEST'}]}
    trader.monitoring_flags = {}; trader.trading_cycles = {}; trader.monitoring_threads = {}
    trader._monitoring_loop = Mock()
    trader._execution_mode = lambda _: ExecutionMode.PAPER
    return trader


@pytest.mark.parametrize('venue', ['okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone'])
def test_stopping_worker_must_not_be_replaced_before_exit(venue):
    trader = start_ready_trader(venue)
    old_worker = Mock(); old_worker.is_alive.return_value = True
    trader.monitoring_threads[venue] = old_worker
    trader.monitoring_flags[venue] = False
    with patch('trading.unified_trader.threading.Thread') as factory:
        with pytest.raises(RuntimeError, match=f'^runtime_source_stopping:{venue}:worker_start$'):
            trader.start_trading_checked(venue)
        factory.assert_not_called()
        assert trader.monitoring_threads[venue] is old_worker
        assert trader.monitoring_flags[venue] is False
    old_worker.is_alive.return_value = False
    new_worker = Mock(); new_worker.is_alive.return_value = True
    with patch('trading.unified_trader.threading.Thread', return_value=new_worker):
        assert trader.start_trading_checked(venue) is True
        assert trader.monitoring_threads[venue] is new_worker
        new_worker.start.assert_called_once()


def test_same_source_simultaneous_starts_create_only_one_worker():
    import threading
    real_thread = threading.Thread
    trader = start_ready_trader()
    entered = threading.Event(); release = threading.Event(); second_entered = threading.Event()
    def initialize(_):
        if entered.is_set(): second_entered.set()
        entered.set()
        assert release.wait(3)
        return True
    trader._ensure_exchange_initialized = initialize
    worker = Mock(); worker.is_alive.return_value = True
    outcomes = []
    def run():
        try: outcomes.append(trader.start_trading_checked('okx'))
        except Exception as error: outcomes.append(error)
    first = real_thread(target=run); second = real_thread(target=run)
    with patch('trading.unified_trader.threading.Thread', return_value=worker) as factory:
        first.start()
        assert entered.wait(2)
        second.start()
        try:
            assert not second_entered.wait(.15), 'second start entered initialization before first completed'
        finally:
            release.set(); first.join(3); second.join(3)
        assert outcomes == [True, True]
        assert factory.call_count == 1


@pytest.mark.parametrize('venue', ['okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone'])
def test_stop_during_initialization_cancels_start_and_allows_explicit_retry(venue):
    trader = start_ready_trader(venue)
    def initialize(_):
        trader.request_trading_stop(venue)
        return True
    trader._ensure_exchange_initialized = initialize
    worker = Mock(); worker.is_alive.return_value = False
    with patch('trading.unified_trader.threading.Thread', return_value=worker):
        with pytest.raises(RuntimeError, match=f'^runtime_start_cancelled:{venue}:worker_start$'):
            trader.start_trading_checked(venue)
        worker.start.assert_not_called()
        assert not trader.monitoring_flags[venue]
        trader._ensure_exchange_initialized = lambda _: True
        assert trader.start_trading_checked(venue) is True
        worker.start.assert_called_once()
        assert trader.monitoring_flags[venue]


def test_blocked_venue_initialization_does_not_serialize_other_venues():
    import threading
    real_thread = threading.Thread
    trader = start_ready_trader()
    trader.selected_coins['bybit'] = [{'symbol': 'TEST'}]
    entered = threading.Event(); release = threading.Event(); other_done = threading.Event()
    def initialize(venue):
        if venue == 'okx':
            entered.set()
            assert release.wait(3)
        return True
    trader._ensure_exchange_initialized = initialize
    worker = Mock(); worker.is_alive.return_value = True
    results = []
    def run(venue):
        try: results.append(trader.start_trading_checked(venue))
        except Exception as error: results.append(error)
        finally:
            if venue == 'bybit': other_done.set()
    first = real_thread(target=run, args=('okx',)); other = real_thread(target=run, args=('bybit',))
    with patch('trading.unified_trader.threading.Thread', return_value=worker):
        first.start(); assert entered.wait(2); other.start()
        try: assert other_done.wait(1), 'unrelated venue blocked by OKX initialization'
        finally: release.set(); first.join(3); other.join(3)
    assert results == [True, True]


def test_stop_join_does_not_erase_a_replacement_worker():
    trader = start_ready_trader()
    old = Mock(); new = Mock()
    old.is_alive.side_effect = [True, False]
    old.join.side_effect = lambda **_: trader.monitoring_threads.update(okx=new)
    trader.monitoring_threads['okx'] = old
    with patch('trading.unified_trader.flush_kpi_events'):
        result = trader.wait_for_trading_stops(['okx'], timeout=.1)
    assert trader.monitoring_threads['okx'] is new
    assert result == {'stopped': [], 'alive': ['okx']}
