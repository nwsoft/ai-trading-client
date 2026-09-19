from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from trading.recorder import Recorder, TradeLog
from trading.execution_mode import ExecutionMode
from trading.stock_analysis_service import StockAnalysisService
from trading.trader import Position, PositionSide
from trading.unified_trader import UnifiedTrader
from web_platform.query_services import AccountQueryService


def _recorder(tmp_path, exchange="binance"):
    return Recorder(db_path=str(tmp_path / "trading.db"), log_path=str(tmp_path / "logs"), exchange=exchange)


def _closed_noah_trade(recorder: Recorder, *, exit_order_id="exit-1", fee_asset="USDT"):
    return recorder.insert_trade_log(TradeLog(
        id=None, symbol="BTCUSDT", entry_price=100.0, exit_price=105.0,
        quantity=2.0, leverage=2, pnl=10.0, pnl_percent=5.0,
        entry_time=datetime.now(timezone.utc), exit_time=datetime.now(timezone.utc),
        reason="AI close", side="LONG", tp_price=None, sl_price=None,
        fees=0.10, slippage=0.0, exchange="binance", order_id="entry-1",
        exit_order_id=exit_order_id, fee_asset=fee_asset, fee_source="entry_fill",
        position_owner="noahai", execution_mode="live", entry_fee=0.10,
        entry_fee_asset=fee_asset,
        settlement_currency="USDT", pnl_source="estimated_close_price",
        reconciliation_status="pending_exchange_reconciliation",
    ))


def test_exact_order_reconciliation_uses_provider_gross_and_net(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_noah_trade(recorder)
    recorder.save_exchange_execution_history("binance", [{
        "id": "fill-1", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 104.0, "amount": 2.0, "realized_pnl": 8.0,
        "fee": {"cost": 0.20, "currency": "USDT"}, "status": "closed",
        "timestamp": 1789130000000,
    }])
    row = recorder.execute_query(
        "SELECT exit_price, gross_pnl, net_pnl, pnl, fees, reconciliation_status FROM trade_log WHERE id = ?",
        (trade_id,),
    )[0]
    assert row[:4] == pytest.approx((104.0, 8.0, 7.7, 7.7))
    assert row[4] == pytest.approx(0.3)
    assert row[5] == "exchange_confirmed"

    stats = AccountQueryService(str(tmp_path / "trading.db")).trading_statistics(
        asset_class="crypto", source="binance", period="all",
    )
    summary = stats["groups"][0]["rows"][0]
    assert summary["gross_pnl"] == 8.0
    assert summary["total_pnl"] == 7.7
    assert summary["max_profit"] == 7.7


def test_unrelated_same_symbol_fill_does_not_rewrite_pnl(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_noah_trade(recorder)
    recorder.save_exchange_execution_history("binance", [{
        "id": "manual-fill", "order": "manual-order", "symbol": "BTCUSDT", "side": "sell",
        "price": 50.0, "amount": 2.0, "realized_pnl": -100.0,
        "fee": {"cost": 1.0, "currency": "USDT"}, "status": "closed",
        "timestamp": 1789130000000,
    }])
    row = recorder.execute_query(
        "SELECT pnl, reconciliation_status FROM trade_log WHERE id = ?", (trade_id,),
    )[0]
    assert row == (10.0, "exchange_fill_not_found")

    stats = AccountQueryService(str(tmp_path / "trading.db")).trading_statistics(
        asset_class="crypto", source="binance", period="all",
    )
    assert stats["closed_count"] == 1
    assert stats["reconciled_closed_count"] == 0
    assert stats["unresolved_closed_count"] == 1
    assert stats["pnl_by_currency"] == {}
    assert stats["groups"][0]["rows"][0]["max_profit"] is None


def test_short_execution_window_does_not_downgrade_confirmed_trade(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_noah_trade(recorder)
    recorder.save_exchange_execution_history("binance", [{
        "id": "fill-1", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 104.0, "amount": 2.0, "realized_pnl": 8.0,
        "fee": {"cost": 0.20, "currency": "USDT"}, "status": "closed",
        "timestamp": 1789130000000,
    }])
    recorder.execute_query("DELETE FROM exchange_execution_log WHERE order_id = ?", ("exit-1",))
    recorder.save_exchange_execution_history("binance", [{
        "id": "newer-fill", "order": "newer-order", "symbol": "ETHUSDT", "side": "sell",
        "price": 20.0, "amount": 1.0, "realized_pnl": 1.0,
        "fee": {"cost": 0.01, "currency": "USDT"}, "status": "closed",
        "timestamp": 1789131000000,
    }])
    row = recorder.execute_query(
        "SELECT pnl, reconciliation_status FROM trade_log WHERE id = ?", (trade_id,),
    )[0]
    assert row[0] == pytest.approx(7.7)
    assert row[1] == "exchange_confirmed"


def test_entry_fee_currency_mismatch_cannot_be_silently_netted(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_noah_trade(recorder, fee_asset="BNB")
    recorder.save_exchange_execution_history("binance", [{
        "id": "fill-usdt", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 104.0, "amount": 2.0, "realized_pnl": 8.0,
        "fee": {"cost": 0.20, "currency": "USDT"}, "status": "closed",
        "timestamp": 1789130000000,
    }])
    row = recorder.execute_query(
        "SELECT gross_pnl, net_pnl, entry_fee_asset, exit_fee_asset, reconciliation_status "
        "FROM trade_log WHERE id = ?", (trade_id,),
    )[0]
    assert row == (8.0, None, "BNB", "USDT", "exchange_confirmed_fee_conversion_required")


def test_fee_currency_mismatch_preserves_gross_and_marks_conversion_required(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_noah_trade(recorder)
    recorder.save_exchange_execution_history("binance", [{
        "id": "fill-bnb", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 104.0, "amount": 2.0, "realized_pnl": 8.0,
        "fee": {"cost": 0.001, "currency": "BNB"}, "status": "closed",
        "timestamp": 1789130000000,
    }])
    row = recorder.execute_query(
        "SELECT gross_pnl, net_pnl, pnl, reconciliation_status FROM trade_log WHERE id = ?", (trade_id,),
    )[0]
    assert row == (8.0, None, 8.0, "exchange_confirmed_fee_conversion_required")


def test_detailed_fills_replace_order_level_placeholder_without_double_count(tmp_path):
    recorder = _recorder(tmp_path)
    recorder.save_exchange_execution_history("binance", [{
        "id": "exit-1", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 104.0, "amount": 2.0, "status": "closed", "timestamp": 1789130000000,
    }])
    recorder.save_exchange_execution_history("binance", [{
        "id": "fill-a", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 103.0, "amount": 1.0, "status": "closed", "timestamp": 1789130000001,
    }, {
        "id": "fill-b", "order": "exit-1", "symbol": "BTCUSDT", "side": "sell",
        "price": 105.0, "amount": 1.0, "status": "closed", "timestamp": 1789130000002,
    }])
    assert recorder.execute_query(
        "SELECT trade_id FROM exchange_execution_log WHERE order_id = ? ORDER BY trade_id", ("exit-1",),
    ) == [("fill-a",), ("fill-b",)]


def test_partial_close_splits_closed_quantity_and_keeps_open_remainder(tmp_path):
    recorder = _recorder(tmp_path)
    recorder.insert_trade_log(TradeLog(
        id=None, symbol="ETHUSDT", entry_price=100.0, exit_price=None,
        quantity=2.0, leverage=1, pnl=None, pnl_percent=None,
        entry_time=datetime.now(timezone.utc), exit_time=None, reason="AI entry",
        side="LONG", tp_price=None, sl_price=None, fees=0.2, slippage=0.0,
        exchange="binance", order_id="entry-partial", fee_asset="USDT",
        position_owner="noahai", execution_mode="live", entry_fee=0.2,
        settlement_currency="USDT", reconciliation_status="open",
    ))
    assert recorder.record_partial_trade_close(
        symbol="ETHUSDT", exchange="binance", entry_order_id="entry-partial",
        exit_order_id="exit-partial", closed_quantity=0.5, exit_price=110.0,
        gross_pnl=5.0, exit_fee=0.05, fee_asset="USDT", reason="partial test",
        pnl_source="exchange_realized_pnl", reconciliation_status="exchange_confirmed_partial",
    )
    rows = recorder.execute_query(
        "SELECT quantity, exit_time, gross_pnl, net_pnl, entry_fee, exit_fee FROM trade_log ORDER BY id"
    )
    assert rows[0][0] == pytest.approx(1.5)
    assert rows[0][1] is None
    assert rows[0][4] == pytest.approx(0.15)
    assert rows[1][0] == pytest.approx(0.5)
    assert rows[1][1] is not None
    assert rows[1][2:6] == pytest.approx((5.0, 4.9, 0.05, 0.05))


def test_unified_exchange_partial_fill_keeps_live_position_and_splits_ledger(tmp_path, monkeypatch):
    recorder = _recorder(tmp_path, exchange="bybit")
    position = Position(
        symbol="ETHUSDT", side=PositionSide.LONG, entry_price=100.0,
        current_price=110.0, quantity=1.0, leverage=2,
        unrealized_pnl=10.0, unrealized_pnl_percent=10.0,
        entry_time=datetime.now(timezone.utc), position_id="position-bybit-1",
        entry_order_id="entry-bybit-1", position_owner="noahai",
    )
    assert recorder.log_trade_entry(position, {
        "exchange": "bybit", "order_id": "entry-bybit-1",
        "entry_fee": 0.10, "entry_fee_asset": "USDT",
        "settlement_currency": "USDT",
    })

    class Client:
        exchange = object()

        @staticmethod
        def place_order(**_kwargs):
            return {
                "status": "success", "order_id": "exit-bybit-partial",
                "filled": 0.4, "average": 110.0,
                "fee": {"cost": 0.04, "currency": "USDT"},
            }

        @staticmethod
        def get_trade_history(**_kwargs):
            return [{
                "id": "fill-bybit-partial", "order": "exit-bybit-partial",
                "symbol": "ETHUSDT", "side": "sell", "price": 110.0,
                "amount": 0.4, "realized_pnl": 4.0,
                "fee": {"cost": 0.04, "currency": "USDT"},
            }]

    client = Client()
    store = {"ETHUSDT": position}
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = MagicMock()
    trader.settings = {}
    trader.recorder = recorder
    trader.risk_manager = None
    trader.unified_manager = MagicMock()
    trader.position_sizing_snapshots = {}
    trader._execution_mode = lambda _exchange: ExecutionMode.LIVE
    trader._position_store = lambda _exchange: store
    trader.get_exchange_client = lambda _exchange: client
    trader._confirm_ccxt_order_result = lambda _client, result, symbol: {
        **result, "_execution_confirmed": True,
    }
    trader._record_exchange_execution = MagicMock()
    trader._is_order_success = lambda result: result.get("status") == "success"
    trader._update_trade_stats_unified = MagicMock()
    trader._perform_profit_analysis_unified = MagicMock()
    trader._perform_loss_analysis_unified = MagicMock()
    monkeypatch.setattr("trading.unified_trader.emit_position_reduced", MagicMock(return_value=True))

    assert trader._close_position_unified("bybit", "ETHUSDT", position, 109.0) is True
    assert store["ETHUSDT"].quantity == pytest.approx(0.6)
    rows = recorder.execute_query(
        "SELECT quantity, exit_time, gross_pnl, net_pnl, reconciliation_status "
        "FROM trade_log ORDER BY id"
    )
    assert rows[0][0] == pytest.approx(0.6)
    assert rows[0][1] is None
    assert rows[1][0] == pytest.approx(0.4)
    assert rows[1][1] is not None
    assert rows[1][2:4] == pytest.approx((4.0, 3.92))
    assert rows[1][4] == "exchange_confirmed_partial"


def test_actual_trade_lookup_requires_exact_order_id(tmp_path):
    class Client:
        @staticmethod
        def get_recent_trades(symbol, limit):
            return [
                {"order_id": "manual", "side": "SELL", "quantity": 1, "price": 1, "commission": 0, "realized_pnl": -99},
                {"order_id": "wanted", "side": "SELL", "quantity": 2, "price": 104, "commission": 0.2, "commission_asset": "USDT", "realized_pnl": 8},
            ]

    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"), log_path=str(tmp_path / "logs"),
        exchange="binance", binance_client=Client(),
    )
    assert recorder.get_actual_trade_info("BTCUSDT", datetime.now(), "LONG") is None
    actual = recorder.get_actual_trade_info(
        "BTCUSDT", datetime.now(), "LONG", exit_order_id="wanted",
    )
    assert actual["quantity"] == 2
    assert actual["exit_price"] == 104
    assert actual["gross_pnl"] == 8


def test_stock_history_sync_writes_execution_ledger_not_fake_closed_trade(tmp_path):
    recorder = _recorder(tmp_path, exchange="kiwoom")
    service = StockAnalysisService(object(), broker_name="kiwoom", recorder=recorder)
    inserted = service._sync_trade_history_to_recorder([{
        "execution_id": "stock-fill-1", "order_id": "stock-order-1", "symbol": "005930",
        "side": "BUY", "filled_price": 70000, "filled_quantity": 1,
        "fee": 10, "tax": 0, "filled_at": "2026-09-12T09:01:00+09:00",
    }])
    assert inserted == 1
    assert recorder.execute_query("SELECT COUNT(*) FROM trade_log")[0][0] == 0
    assert recorder.execute_query("SELECT exchange, symbol FROM exchange_execution_log")[0] == ("kiwoom", "005930")


def test_stock_fill_profit_field_is_not_treated_as_round_trip_realized_pnl(tmp_path):
    recorder = _recorder(tmp_path, exchange="kiwoom")
    service = StockAnalysisService(object(), broker_name="kiwoom", recorder=recorder)
    service._sync_trade_history_to_recorder([{
        "execution_id": "stock-fill-profit", "order_id": "stock-order-profit",
        "symbol": "005930", "side": "SELL", "filled_price": 70000,
        "filled_quantity": 1, "profit": 999999, "fee": 10, "tax": 20,
        "filled_at": "2026-09-12T09:01:00+09:00",
    }])
    assert recorder.execute_query(
        "SELECT realized_pnl, realized_pnl_present, side FROM exchange_execution_log"
    )[0] == (0.0, 0, "sell")


@pytest.mark.parametrize("broker", ["kiwoom", "shinhan", "mirae", "kis"])
def test_all_stock_brokers_share_fill_not_round_trip_contract(tmp_path, broker):
    recorder = Recorder(
        db_path=str(tmp_path / f"{broker}.db"), log_path=str(tmp_path / f"{broker}-logs"), exchange=broker,
    )
    service = StockAnalysisService(object(), broker_name=broker, recorder=recorder)
    assert service._sync_trade_history_to_recorder([{
        "execution_id": f"{broker}-fill", "order_id": f"{broker}-order",
        "symbol": "069500", "side": "SELL", "filled_price": 35000,
        "filled_quantity": 2, "fee": 10, "tax": 20,
        "filled_at": "2026-09-12T09:02:00+09:00",
    }]) == 1
    assert recorder.execute_query("SELECT COUNT(*) FROM trade_log")[0][0] == 0
    assert recorder.execute_query("SELECT fee, fee_currency FROM exchange_execution_log")[0] == (30.0, "KRW")


@pytest.mark.parametrize(
    ("venue", "symbol", "currency"),
    [
        ("binance", "BTCUSDT", "USDT"), ("bybit", "BTC/USDT:USDT", "USDT"),
        ("okx", "ETH-USDT-SWAP", "USDT"), ("bitget", "SOLUSDT", "USDT"),
        ("upbit", "KRW-BTC", "KRW"), ("bithumb", "BTC/KRW", "KRW"),
    ],
)
def test_all_crypto_venues_keep_their_settlement_currency(venue, symbol, currency):
    assert Recorder._settlement_currency(symbol, venue) == currency


def test_execution_counts_are_isolated_between_crypto_and_stock(tmp_path):
    recorder = _recorder(tmp_path)
    executed_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    recorder.save_exchange_execution_history("binance", [{
        "id": "crypto-fill", "order": "crypto-order", "symbol": "BTCUSDT",
        "side": "buy", "price": 100.0, "amount": 1.0, "status": "closed",
        "timestamp": executed_at_ms,
    }])
    recorder.save_exchange_execution_history("kiwoom", [{
        "id": "stock-fill", "order": "stock-order", "symbol": "005930",
        "side": "buy", "price": 70000.0, "amount": 1.0, "status": "closed",
        "timestamp": executed_at_ms + 1,
    }])
    service = AccountQueryService(str(tmp_path / "trading.db"))

    crypto_stats = service.trading_statistics(asset_class="crypto", period="all")
    stock_stats = service.trading_statistics(asset_class="stock", period="all")
    crypto_report = service.report_period_metrics(asset_class="crypto")["periods"]["today"]
    stock_report = service.report_period_metrics(asset_class="stock")["periods"]["today"]

    assert crypto_stats["execution_count"] == 1
    assert stock_stats["execution_count"] == 1
    assert {row["exchange"] for row in crypto_stats["execution_rows"]} == {"binance"}
    assert {row["exchange"] for row in stock_stats["execution_rows"]} == {"kiwoom"}
    assert crypto_report["execution_count"] == 1
    assert stock_report["execution_count"] == 1


def test_statistics_layout_has_stable_feedback_and_scroll_container():
    source = open("webui/src/components/TradingStatisticsWorkspace.tsx", encoding="utf-8").read()
    workspace_source = open("webui/src/components/LegacyFeatureWorkspaces.tsx", encoding="utf-8").read()
    operations_source = open("webui/src/components/Operations.tsx", encoding="utf-8").read()
    analyst_source = open("webui/src/components/AIAnalystWorkspace.tsx", encoding="utf-8").read()
    styles = open("webui/src/styles.css", encoding="utf-8").read()
    assert 'className={`legacy-stat-feedback' in source
    assert 'className="legacy-stat-table"' in source
    assert "화면 다시 계산" in source
    assert "거래소 체결 동기화" in source
    assert "for (const source of targets)" in source
    assert ".legacy-stat-table {" in styles
    assert "grid-template-rows: auto minmax(0, 1fr)" in styles
    assert "repeat(11" in styles
    assert 'className="legacy-coin-notices" role="status"' in workspace_source
    assert 'className="report-notification-status" role="status"' in workspace_source
    assert workspace_source.count("legacy-workspace-feedback") >= 2
    assert ".legacy-coin-notices" in styles
    assert ".report-notification-status:empty" in styles
    assert 'const confirmedMetricsAvailable = statisticsMode === "paper" || reconciledCount > 0' in operations_source
    assert 'const winRateLabel = confirmedMetricsAvailable' in operations_source
    assert 'return paper ? "청산 기록 없음" : "대조 전"' in analyst_source
    assert 'reconciledCount > 0 ?' in analyst_source


def test_assistant_explains_v39128_statistics_contract():
    from config.ai_custom_knowledge import build_ai_custom_knowledge

    answer = build_ai_custom_knowledge("거래 통계 가져오기와 누적 PnL 차이는 무엇인가요?")
    assert "화면 다시 계산" in answer
    assert "거래소 체결 동기화" in answer
    assert "대조 미확정" in answer
    assert "주식·ETF" in answer
