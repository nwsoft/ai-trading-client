from utils.trade_operating_metrics import (
    calculate_trade_operating_metrics,
    format_hold_duration,
    infer_quote_currency,
)


def test_operating_metrics_split_quote_currencies_and_ignore_invalid_hold_time():
    trades = [
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "quantity": 2.0,
            "entry_time": "2026-07-27T00:00:00+00:00",
            "exit_time": "2026-07-27T01:30:00+00:00",
        },
        {
            "exchange": "upbit",
            "symbol": "BTC/KRW",
            "entry_price": 100_000.0,
            "quantity": 3.0,
            "entry_time": "2026-07-27T00:00:00",
            "exit_time": "2026-07-27T00:30:00",
        },
        {
            "exchange": "shinhan",
            "symbol": "005930",
            "entry_price": 70_000.0,
            "quantity": 1.0,
            "entry_time": "2026-07-27T00:00:00",
            "exit_time": "2026-07-27T00:00:00",
        },
        {
            "exchange": "okx",
            "symbol": "ETHUSDT",
            "entry_price": 2_000.0,
            "quantity": 0.1,
            "entry_time": "2026-07-27T00:00:00",
            "exit_time": None,
        },
    ]

    metrics = calculate_trade_operating_metrics(trades)

    assert metrics["notional_by_currency"] == {
        "USDT": 200.0,
        "KRW": 370_000.0,
    }
    assert metrics["closed_count"] == 3
    assert metrics["valid_hold_count"] == 2
    assert metrics["avg_hold_minutes"] == 60.0
    assert metrics["hold_coverage_rate"] == 2 / 3 * 100.0


def test_quote_currency_supports_domestic_and_future_overseas_brokers():
    assert infer_quote_currency("bithumb", "BTC/KRW") == "KRW"
    assert infer_quote_currency("shinhan", "005930") == "KRW"
    assert infer_quote_currency("binance", "BTCUSDT") == "USDT"
    assert infer_quote_currency("interactive_brokers", "AAPL") == "USD"
    assert infer_quote_currency(None, "BTCUSDT") == "USDT"


def test_hold_duration_is_readable_and_does_not_fabricate_missing_data():
    assert format_hold_duration(None) == "수집 대기"
    assert format_hold_duration(45) == "45.0분"
    assert format_hold_duration(90) == "1시간 30분"
    assert format_hold_duration(1500) == "1일 1시간"

