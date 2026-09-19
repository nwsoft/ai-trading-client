import logging
from pathlib import Path
from types import SimpleNamespace

from api.binance_client import BinanceClient
from trading.exchange_manager import ExchangeManager
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter


ROOT = Path(__file__).resolve().parents[1]


def _binance_account_payload():
    return {
        "totalWalletBalance": "10",
        "totalUnrealizedProfit": "0",
        "totalMarginBalance": "10",
        "availableBalance": "10",
        "totalPositionInitialMargin": "0",
        "totalOpenOrderInitialMargin": "0",
        "totalCrossWalletBalance": "10",
        "totalCrossUnPnl": "0",
        "updateTime": 1,
        "assets": [{"asset": "USDT", "walletBalance": "10"}],
    }


def test_binance_account_snapshot_resyncs_once_after_timestamp_error():
    class RawClient:
        def __init__(self):
            self.calls = 0

        def futures_account(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Timestamp for this request is outside of the recvWindow")
            return _binance_account_payload()

    client = object.__new__(BinanceClient)
    client.client = RawClient()
    client.config = SimpleNamespace(recv_window=5000)
    client.logger = logging.getLogger("test.binance.clock")
    client.last_error = ""
    client.last_error_category = ""
    client._has_api_keys = lambda: True
    client.get_synced_timestamp = lambda: 1
    sync_calls = []
    client._sync_server_time = lambda: sync_calls.append("sync")

    snapshot = client.get_balance_snapshot()

    assert snapshot["account_info"]["total_wallet_balance"] == 10.0
    assert client.client.calls == 2
    assert sync_calls == ["sync"]
    assert client.last_error == ""


def test_binance_clock_failure_is_not_reported_as_empty_account_or_bad_key():
    class ClockFailureClient:
        last_error = ""
        last_error_category = ""

        def get_balance_snapshot(self):
            self.last_error = "bybit-style server timestamp rejected"
            self.last_error_category = "clock_skew"
            return {}

    manager = object.__new__(ExchangeManager)
    manager.logger = logging.getLogger("test.exchange.clock")
    manager.binance_client = ClockFailureClient()
    manager.invalid_api_keys = set()
    manager.balance_cache = {}
    manager.last_balance_update = {}

    result = manager._get_binance_balance(force_refresh=True)

    assert result["status"] == "clock_skew"
    assert "API 키 오류로 판단하지 않습니다" in result["message"]
    assert manager.invalid_api_keys == set()


def test_bybit_balance_remeasures_provider_time_and_retries_once():
    class Exchange:
        def __init__(self):
            self.calls = 0
            self.sync_calls = 0

        def fetch_balance(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    'bybit {"retCode":10002,"retMsg":"invalid request, please check your server timestamp or recv_window param"}'
                )
            return {"total": {"USDT": 25.0}, "free": {"USDT": 20.0}}

        def load_time_difference(self):
            self.sync_calls += 1

    adapter = BybitFuturesAdapter("key", "secret")
    adapter.exchange = Exchange()
    adapter.is_connected = True

    result = adapter.get_balance()

    assert result == {"USDT": 25.0}
    assert adapter.exchange.calls == 2
    assert adapter.exchange.sync_calls == 1
    assert adapter.last_error == ""


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return dict(self.payload)


class _TokenHttp:
    def __init__(self, payload):
        self.payload = payload
        self.posts = 0

    def post(self, *_args, **_kwargs):
        self.posts += 1
        return _Response(self.payload)


def test_kis_rate_limit_response_starts_cooldown_instead_of_reissuing():
    http = _TokenHttp({
        "error_code": "EGW00133",
        "error_description": "접근토큰 발급 잠시 후 다시 시도하세요(1분당 1회)",
    })
    adapter = KoreaInvestmentStockAdapter(
        "user", "password", app_key="rate-limit-app", app_secret="secret", backend_client=http,
    )
    key = adapter._token_cache_key()
    adapter._shared_token_cache.pop(key, None)
    adapter._shared_next_issue_at.pop(key, None)

    assert adapter._refresh_token() is False
    assert adapter._refresh_token() is False
    assert http.posts == 1
    assert adapter._token_retry_at > 0


def test_kis_valid_token_is_reused_by_adjacent_dashboard_adapter():
    first_http = _TokenHttp({"access_token": "runtime-token", "expires_in": 3600})
    first = KoreaInvestmentStockAdapter(
        "user", "password", app_key="shared-token-app", app_secret="secret", backend_client=first_http,
    )
    key = first._token_cache_key()
    first._shared_token_cache.pop(key, None)
    first._shared_next_issue_at.pop(key, None)
    assert first._refresh_token() is True

    second_http = _TokenHttp({"access_token": "should-not-be-issued", "expires_in": 3600})
    second = KoreaInvestmentStockAdapter(
        "user", "password", app_key="shared-token-app", app_secret="secret", backend_client=second_http,
    )

    assert second._refresh_token() is True
    assert second._access_token == "runtime-token"
    assert first_http.posts == 1
    assert second_http.posts == 0


def test_webui_distinguishes_clock_error_and_learning_requires_start():
    account_view = (ROOT / "webui/src/accountConnection.ts").read_text(encoding="utf-8")
    workspace = (ROOT / "webui/src/components/LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "webui/src/components/SettingsCenter.tsx").read_text(encoding="utf-8")

    assert 'status === "clock_skew"' in account_view
    assert "API 키 재발급 사유가 아닙니다" in account_view
    assert "LEARNING 대기 · 시작 버튼 필요" in workspace
    assert "분석·학습 시작" in workspace
    assert "LEARNING은 자동으로 시작되지 않습니다" in workspace
    assert "Windows 설정 → 시간 및 언어 → 날짜 및 시간" in settings
