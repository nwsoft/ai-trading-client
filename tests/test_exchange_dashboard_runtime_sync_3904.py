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
