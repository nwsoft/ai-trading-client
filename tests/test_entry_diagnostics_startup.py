from types import SimpleNamespace

import pytest

from trading.entry_diagnostics import monitored_cycle
from trading.operation_evidence import reset, snapshot


def owner():
    return SimpleNamespace(settings={'paper_trading': True})


def test_cycle_preserves_result_and_records_completion():
    runtime = owner()
    result = object()

    @monitored_cycle('binance')
    def cycle(runtime):
        return result

    assert cycle(runtime) is result
    evidence = snapshot(runtime, 'binance', 'paper')
    assert evidence['activity']['returned_cycles'] == 1
    assert evidence['cycle']['phase'] == 'returned'


def test_cycle_failure_propagates_without_claiming_completion():
    runtime = owner()
    error = RuntimeError('cycle failed')

    @monitored_cycle('binance')
    def cycle(runtime):
        raise error

    with pytest.raises(RuntimeError) as caught:
        cycle(runtime)
    assert caught.value is error
    assert 'returned_cycles' not in snapshot(runtime, 'binance', 'paper')['activity']


def test_reset_during_cycle_does_not_republish_old_session():
    runtime = owner()

    @monitored_cycle('binance')
    def cycle(runtime):
        reset(runtime, 'binance')

    cycle(runtime)
    assert snapshot(runtime, 'binance', 'paper')['status'] == 'unavailable'
