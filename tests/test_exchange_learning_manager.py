from datetime import datetime, timedelta, timezone

from trading.exchange_learning_manager import ExchangeLearningManager


def test_should_apply_api_delay_handles_timezone_aware_timestamps():
    manager = ExchangeLearningManager(exchange="okx")
    now = datetime.now(timezone.utc)
    manager.learning_history = [
        {"timestamp": now - timedelta(seconds=10)},
        {"timestamp": now - timedelta(seconds=20)},
    ]

    assert manager.should_apply_api_delay() is False


def test_get_recent_learning_data_handles_timezone_aware_timestamps():
    manager = ExchangeLearningManager(exchange="okx")
    now = datetime.now(timezone.utc)
    manager.learning_history = [
        {"timestamp": now - timedelta(hours=1), "symbol": "BTCUSDT"},
        {"timestamp": now - timedelta(days=2), "symbol": "ETHUSDT"},
    ]

    recent = manager.get_recent_learning_data(hours=24)
    assert len(recent) == 1
    assert recent[0]["symbol"] == "BTCUSDT"