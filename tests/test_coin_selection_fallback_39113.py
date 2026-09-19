from trading.evaluator import Evaluator


def test_fallback_candidates_are_explicitly_unscored_not_zero():
    evaluator = object.__new__(Evaluator)

    rows = evaluator._fallback_to_major_coins(10, exchange="binance")

    assert len(rows) == 10
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["is_major"] is True
    assert rows[3]["symbol"] == "SOLUSDT"
    assert rows[3]["is_major"] is True
    assert all(row["overall_score"] is None for row in rows)
    assert all(row["selection_status"] == "fallback_unscored" for row in rows)
    assert all(row["execution_eligible"] is False for row in rows)
    assert all(row["analysis_only"] is True for row in rows)


def test_fallback_candidates_keep_spot_exchange_symbol_format():
    evaluator = object.__new__(Evaluator)

    assert evaluator._fallback_to_major_coins(1, exchange="upbit")[0]["symbol"] == "KRW-BTC"
    assert evaluator._fallback_to_major_coins(1, exchange="bithumb")[0]["symbol"] == "BTC/KRW"
