from types import SimpleNamespace

from trading.evaluator import Evaluator


class _DummyAnalyzer:
    def __init__(self):
        self.settings = {}
        self.binance_client = None


def test_select_trading_coins_skips_fallback_when_target_already_met(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})

    analyze_calls = []

    def fake_analyze_candidate_coins_by_exchange(exchange, exchange_client=None, adjustment_factor=1.0):
        analyze_calls.append(adjustment_factor)
        return [
            {"symbol": "BTCUSDT", "overall_score": 91.0},
            {"symbol": "ETHUSDT", "overall_score": 88.0},
        ]

    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        fake_analyze_candidate_coins_by_exchange,
    )
    monkeypatch.setattr(evaluator, "_select_final_coins", lambda coins, num_alt, num_major, regime: list(coins))
    monkeypatch.setattr(evaluator, "_evaluate_coins_with_ai", lambda valid, selected: [])

    selected = evaluator.select_trading_coins(num_alt=1, num_major=1, regime="normal", exchange="binance")

    assert len(selected) == 2
    assert analyze_calls == [1.0]
