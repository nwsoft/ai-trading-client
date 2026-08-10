from pathlib import Path
from types import SimpleNamespace
import logging


ROOT = Path(__file__).resolve().parents[1]


def test_ccxt_balance_normalizer_keeps_quote_and_all_positive_assets():
    from trading.exchanges.balance_normalizer import normalize_ccxt_total_balances

    result = normalize_ccxt_total_balances(
        {
            "total": {
                "KRW": 1_000_000,
                "BTC": 0,
                "ETH": 0,
                "XRP": 125.5,
                "SOL": 2.25,
            },
            "free": {"KRW": 900_000},
            "info": {"private": "ignored"},
        },
        quote_asset="KRW",
    )

    assert result == {
        "KRW": 1_000_000.0,
        "XRP": 125.5,
        "SOL": 2.25,
    }


def test_all_ccxt_crypto_adapters_return_dynamic_assets():
    for relative in (
        "trading/exchanges/adapters/upbit_spot_adapter.py",
        "trading/exchanges/adapters/bithumb_spot_adapter.py",
        "trading/exchanges/adapters/bybit_futures_adapter.py",
        "trading/exchanges/adapters/okx_futures_adapter.py",
        "trading/exchanges/adapters/bitget_futures_adapter.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "normalize_ccxt_total_balances" in source
        assert "'BTC':" not in source.split("def get_balance", 1)[1].split(
            "def get_account_info", 1
        )[0]
        assert "'ETH':" not in source.split("def get_balance", 1)[1].split(
            "def get_account_info", 1
        )[0]


def test_binance_snapshot_uses_one_account_call_and_keeps_all_positive_assets():
    from api.binance_client import BinanceClient

    class RawClient:
        def __init__(self):
            self.calls = 0

        def futures_account(self, **_kwargs):
            self.calls += 1
            return {
                "totalWalletBalance": "100",
                "totalUnrealizedProfit": "1",
                "totalMarginBalance": "101",
                "availableBalance": "80",
                "totalPositionInitialMargin": "10",
                "totalOpenOrderInitialMargin": "2",
                "totalCrossWalletBalance": "100",
                "totalCrossUnPnl": "1",
                "updateTime": 1,
                "assets": [
                    {"asset": "USDT", "walletBalance": "0"},
                    {"asset": "BTC", "walletBalance": "0"},
                    {"asset": "XRP", "walletBalance": "125"},
                    {"asset": "SOL", "walletBalance": "2"},
                ],
            }

    client = object.__new__(BinanceClient)
    client.client = RawClient()
    client.config = SimpleNamespace(recv_window=5000)
    client.logger = logging.getLogger("test.binance.snapshot")
    client._has_api_keys = lambda: True
    client.get_synced_timestamp = lambda: 1

    snapshot = client.get_balance_snapshot()

    assert client.client.calls == 1
    assert list(snapshot["balance"]) == ["USDT", "XRP", "SOL"]
    assert snapshot["account_info"]["total_wallet_balance"] == 100.0


def test_binance_order_submission_rounds_up_below_min_notional():
    from api.binance_client import BinanceClient, OrderRequest

    class RawClient:
        def __init__(self):
            self.order_params = None

        def futures_create_order(self, **kwargs):
            self.order_params = kwargs
            return {"orderId": 1}

    client = object.__new__(BinanceClient)
    client.client = RawClient()
    client.logger = logging.getLogger("test.binance.min_notional")
    client._has_api_keys = lambda: True
    client.get_symbol_precisions = lambda _symbol: {"quantity_precision": 0}
    client.get_symbol_filters = lambda _symbol: {
        "stepSize": 1.0,
        "tickSize": 0.000001,
        "minQty": 1.0,
        "minNotional": 5.0,
    }
    client.get_current_price = lambda _symbol: 0.00471

    client.place_order(OrderRequest("VETUSDT", "BUY", "MARKET", 1061.0))

    submitted_quantity = float(client.client.order_params["quantity"])
    assert submitted_quantity == 1073.0
    assert submitted_quantity * 0.00471 >= 5.05


def test_precise_quantity_never_rounds_target_notional_down():
    from api.binance_client import BinanceClient

    client = object.__new__(BinanceClient)
    client.logger = logging.getLogger("test.binance.precise_quantity")
    client.get_symbol_info_direct = lambda _symbol: {
        "stepSize": 1.0,
        "quantityPrecision": 0,
    }
    client.get_current_price = lambda _symbol: 0.00471

    quantity = client.calculate_precise_quantity("VETUSDT", 5.05)

    assert quantity == 1073.0
    assert quantity * 0.00471 >= 5.05


def test_settings_help_covers_every_settings_tab_without_secrets():
    from config.settings_knowledge import build_settings_knowledge

    settings = {
        "paper_trading": True,
        "enabled_exchanges": ["bithumb", "okx"],
        "trade_enabled_exchanges": [],
        "multi_venue_execution": {"mode": "parallel"},
        "max_positions": 3,
        "ui_settings": {"always_on_top": True},
        "ai_custom_runtime": {"enabled": True},
        "advanced_trading_layers": {
            "strategy_engine": {
                "high_vol_action": "evaluate",
                "consensus_threshold": 0.6,
                "cooldown_sec": 60,
            }
        },
        "stock_auto_trading": {"auto_start": False},
        "openai_api_key": "must-not-leak",
        "bithumb_secret_key": "must-not-leak",
    }

    response = build_settings_knowledge("설정 화면 전체를 설명해줘", settings)

    for tab in (
        "일반",
        "거래소 선택",
        "거래소 API",
        "AI 엔진/API",
        "고급 매매 계층",
        "AlphaArena",
        "AI 시스템 상태",
        "업데이트",
    ):
        assert tab in response
    assert "현재 모드: PAPER" in response
    assert "대시보드 최상단: ON" in response
    assert "must-not-leak" not in response


def test_ai_assistant_injects_settings_reference_and_has_offline_fallback():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(
        encoding="utf-8"
    )
    assert "def _settings_knowledge_for_question" in source
    assert 'context = f"{settings_knowledge}\\n\\n[현재 거래 상황]\\n{context}"' in source
    assert "외부 AI 호출 없이 호환 설정 계약 정본" in source
    assert "('docs', 'docs')" in (ROOT / "aiautotrade.spec").read_text(encoding="utf-8")


def test_settings_tabs_have_contextual_ai_help_and_reopen_after_hiding():
    settings_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")

    assert 'text="AI에게 묻기"' in settings_source
    assert "def _ask_ai_about_settings" in settings_source
    assert "API 키나 비밀값은 표시하지 말고" in settings_source
    assert "self.root.grab_release()" in settings_source
    assert "self.root.withdraw()" in settings_source
    assert "existing.deiconify()" in dashboard_source
    assert "existing.grab_set()" in dashboard_source


def test_ai_assistant_faq_column_scrolls_independently():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(
        encoding="utf-8"
    )
    method = source.split("def create_quick_question_buttons", 1)[1].split(
        "def _build_input_placeholder", 1
    )[0]

    assert "questions_frame = CTkScrollableFrame(" in method
    assert "scrollbar_button_color=" in method


def test_demo_balances_do_not_invent_zero_btc_eth_slots():
    from trading.demo_trader import DemoTrader

    trader = DemoTrader({})

    assert trader.virtual_balances["binance"] == {"USDT": 10_000.0}
    assert trader.virtual_balances["upbit"] == {"KRW": 15_000_000.0}
    assert all(
        "BTC" not in balance and "ETH" not in balance
        for balance in trader.virtual_balances.values()
    )


def test_learning_crypto_filter_accepts_krw_altcoins_and_all_supported_venues():
    from utils.asset_context import filter_learning_rows

    rows = [
        {"symbol": "KRW-XRP", "exchange": "upbit"},
        {"symbol": "SOL/KRW", "source": "bithumb"},
        {"symbol": "XRP/USDT:USDT", "exchange": "okx"},
        {"symbol": "005930", "source": "kiwoom"},
    ]

    filtered = filter_learning_rows(rows, "blockchain")

    assert [row["symbol"] for row in filtered] == [
        "KRW-XRP",
        "SOL/KRW",
        "XRP/USDT:USDT",
    ]


def test_learning_stock_filter_accepts_all_supported_brokers_and_etfs():
    from utils.asset_context import filter_learning_rows

    rows = [
        {"symbol": "005930.KS", "exchange": "koreaInvestment"},
        {"symbol": "069500", "asset_type": "etf"},
        {"symbol": "AAPL", "source": "mirae_asset"},
        {"symbol": "KRW-XRP", "exchange": "upbit"},
    ]

    filtered = filter_learning_rows(rows, "stock")

    assert [row["symbol"] for row in filtered] == ["005930.KS", "069500", "AAPL"]


def test_demo_trade_log_uses_exchange_quote_currency():
    from trading.demo_trader import DemoTrader

    trader = DemoTrader({})
    result = {"is_winning": True, "profit_amount": 1.0, "symbol": "XRP/KRW",
              "side": "buy", "profit_percent": 0.1}

    trader.log_demo_trade(result, "bithumb")
