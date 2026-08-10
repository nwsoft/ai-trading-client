import logging
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_sync_updates_button_cache_and_running_set_together():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    method = source.split("def sync_exchange_runtime_state(", 1)[1].split(
        "def _reconcile_exchange_control_from_engine", 1
    )[0]

    assert "self._exchange_running[ex] = is_running" in method
    assert "self._running_exchanges.add(ex)" in method
    assert "self._running_exchanges.discard(ex)" in method
    assert "self._update_exchange_status(" in method
    assert "self._update_exchange_toggle_button(ex)" in method
    assert "self._update_global_status_ui()" in method
    assert "self.sync_exchange_runtime_state(e, next_running)" in source


def test_paper_runtime_status_is_not_rendered_as_stopped():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    method = source.split("def _update_exchange_status(", 1)[1].split(
        "def _runtime_status_for_exchange", 1
    )[0]

    assert 'normalized == "paper_running"' in method
    assert 'text="페이퍼 실행 중 · 실주문 차단"' in method


def test_ccxt_balance_uses_one_authenticated_balance_request():
    from trading.exchange_manager import ExchangeManager

    class CountingClient:
        is_connected = True
        last_error = ""
        last_auth_guidance = ""

        def __init__(self):
            self.balance_calls = 0

        def get_balance(self):
            self.balance_calls += 1
            return {"KRW": 12345.0, "BTC": 0.01, "ETH": 0.0}

        @staticmethod
        def get_account_info():
            raise AssertionError("잔고 갱신 중 인증 API를 두 번 호출하면 안 됩니다")

    client = CountingClient()
    manager = object.__new__(ExchangeManager)
    manager.logger = logging.getLogger("test.exchange_manager.single_balance")
    manager.invalid_api_keys = set()
    manager.balance_cache = {}
    manager.last_balance_update = {}
    manager._get_or_create_exchange_client = lambda _exchange: client

    result = manager._get_ccxt_balance("bithumb", force_refresh=True)

    assert result["status"] == "success"
    assert result["balance"]["KRW"] == 12345.0
    assert result["account_info"]["total_balance"] == 12345.0
    assert client.balance_calls == 1


def test_exchange_manager_reuses_unified_manager_adapter_as_single_source():
    from trading.exchange_manager import ExchangeManager

    shared_client = object()

    class UnifiedManager:
        def __init__(self):
            self.calls = []

        def get_exchange(self, exchange, trading_type):
            self.calls.append((exchange, trading_type))
            return shared_client

    unified = UnifiedManager()
    manager = object.__new__(ExchangeManager)
    manager.settings = {
        "enabled_exchanges": ["bithumb"],
        "bithumb_api_key": "key",
        "bithumb_secret_key": "secret",
    }
    manager.logger = logging.getLogger("test.exchange_manager.shared_adapter")
    manager.exchange_clients = {}
    manager.invalid_api_keys = set()
    manager.binance_client = None
    manager.unified_manager = unified

    result = manager._get_or_create_exchange_client("bithumb")

    assert result is shared_client
    assert manager.exchange_clients["bithumb"] is shared_client
    assert unified.calls == [("bithumb", "spot")]


def test_binance_position_snapshot_distinguishes_success_from_empty_or_error():
    from types import SimpleNamespace
    from api.binance_client import BinanceClient

    class RawClient:
        @staticmethod
        def futures_position_information(**kwargs):
            return [{
                "symbol": "ETHUSDT",
                "positionAmt": "-0.59",
                "entryPrice": "1882.01",
                "markPrice": "1885.87",
                "unRealizedProfit": "-2.27",
                "liquidationPrice": "2587.87",
                "leverage": "50",
                "marginType": "cross",
            }]

    client = object.__new__(BinanceClient)
    client.client = RawClient()
    client.config = SimpleNamespace(recv_window=5000)
    client.logger = logging.getLogger("test.binance.position_snapshot")
    client._has_api_keys = lambda: True
    client.get_synced_timestamp = lambda: 123456

    result = client.get_positions_result()
    assert result["status"] == "success"
    assert len(result["positions"]) == 1
    assert result["positions"][0].symbol == "ETHUSDT"
    assert result["positions"][0].side == "SHORT"
    assert result["positions"][0].size == 0.59


def test_binance_position_snapshot_resyncs_timestamp_once_before_error():
    from types import SimpleNamespace
    from api.binance_client import BinanceClient

    class RawClient:
        def __init__(self):
            self.calls = 0

        def futures_position_information(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("-1021 timestamp outside recvWindow")
            return []

    raw = RawClient()
    client = object.__new__(BinanceClient)
    client.client = raw
    client.config = SimpleNamespace(recv_window=5000)
    client.logger = logging.getLogger("test.binance.position_resync")
    client._has_api_keys = lambda: True
    client.get_synced_timestamp = lambda: 123456
    sync_calls = []
    client._sync_server_time = lambda: sync_calls.append(True)

    result = client.get_positions_result()
    assert result == {"status": "success", "positions": [], "fetched_at": result["fetched_at"]}
    assert raw.calls == 2
    assert len(sync_calls) == 1


def test_dashboard_binance_positions_use_canonical_wrapper_not_raw_client():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    method = source.split("def create_exchange_positions_section(", 1)[1].split(
        "def create_exchange_stats_section", 1
    )[0]
    assert "get_positions_result" in method
    assert "trader.binance_client.client.futures_position_information()" not in method
    assert method.index("paper_positions = self._paper_position_snapshot(exchange)") < method.index(
        "if exchange == 'binance'"
    )
