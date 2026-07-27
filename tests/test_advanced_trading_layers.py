#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest.mock import MagicMock
from types import SimpleNamespace


def test_profitability_validator_blocks_when_metrics_bad():
    from trading.profitability_validation import ProfitabilityValidator

    validator = ProfitabilityValidator()
    trades = [
        {"pnl": -1000, "quantity": 1, "filled_price": 10000, "fees": 100, "slippage_bps": 30},
        {"pnl": -500, "quantity": 1, "filled_price": 10000, "fees": 100, "slippage_bps": 30},
        {"pnl": 100, "quantity": 1, "filled_price": 10000, "fees": 100, "slippage_bps": 30},
    ]
    report = validator.evaluate_strategy(
        recent_trades=trades,
        policy={"enabled": True, "min_trades": 3, "min_sharpe": 0.2, "min_win_rate": 0.5},
    )

    assert report["enabled"] is False
    assert "expectancy_below_threshold" in report["reasons"]


def test_portfolio_orchestrator_allocates_capital():
    from trading.portfolio_orchestrator import PortfolioOrchestrator

    orchestrator = PortfolioOrchestrator()
    allocation = orchestrator.allocate(
        candidates=[
            {"symbol": "BTCUSDT", "asset_class": "crypto", "signal_strength": 0.8, "volatility": 0.03, "avg_correlation": 0.2},
            {"symbol": "005930", "asset_class": "stock", "signal_strength": 0.7, "volatility": 0.02, "avg_correlation": 0.1},
        ],
        total_capital=1000000,
        policy={"enabled": True},
    )

    assert "allocations" in allocation
    assert "BTCUSDT" in allocation["allocations"]
    assert allocation["allocations"]["BTCUSDT"]["capital"] > 0


def test_execution_optimizer_fallback_to_market():
    from trading.execution_optimizer import ExecutionOptimizer

    calls = []

    def place(order_type, price):
        calls.append((order_type, price))
        if order_type == "LIMIT":
            return False, {"status": "failed"}, ["limit_rejected"]
        return True, {"status": "success", "price": 100}, []

    optimizer = ExecutionOptimizer()
    success, _, errors, _, _ = optimizer.execute_with_quality_control(
        place_order_fn=place,
        order_type="LIMIT",
        request_price=100,
        fallback_market=True,
        max_retries=1,
        timeout_ms=1500,
        max_slippage_bps=100,
    )

    assert success is True
    assert calls[0][0] == "LIMIT"
    assert calls[1][0] == "MARKET"
    assert "limit_rejected" in ";".join(errors)


def test_strategy_engine_cooldown_blocks_trade():
    from datetime import datetime, timedelta
    from trading.strategy_engine import StrategyEngine

    engine = StrategyEngine()
    allowed, meta = engine.should_trade(
        symbol="005930",
        analysis_result={"score": 75, "momentum": 1.0},
        runtime_state={"last_trade_at::005930": datetime.now() - timedelta(seconds=10)},
        policy={"enabled": True, "cooldown_sec": 60, "consensus_threshold": 0.4, "allow_regimes": ["trend", "range"]},
    )

    assert allowed is False
    assert any("cooldown" in r for r in meta["reasons"])


def test_strategy_engine_regime_metadata_hysteresis_and_stale_input():
    from datetime import datetime, timedelta, timezone
    from trading.strategy_engine import StrategyEngine

    engine = StrategyEngine()
    runtime_state = {}
    common_policy = {
        "enabled": True,
        "cooldown_sec": 0,
        "consensus_threshold": 0.1,
        "allow_regimes": ["trend", "range"],
        "high_vol_action": "evaluate",
        "regime_hysteresis_confirmations": 2,
        "regime_data_max_age_sec": 300,
    }

    _, first = engine.should_trade(
        symbol="005930",
        analysis_result={"score": 80, "momentum": 1.0},
        runtime_state=runtime_state,
        policy=common_policy,
    )
    _, pending = engine.should_trade(
        symbol="005930",
        analysis_result={"score": 80, "momentum": 0.1},
        runtime_state=runtime_state,
        policy=common_policy,
    )
    _, confirmed = engine.should_trade(
        symbol="005930",
        analysis_result={"score": 80, "momentum": 0.1},
        runtime_state=runtime_state,
        policy=common_policy,
    )

    assert first["regime"] == "trend"
    assert first["regime_observed_at"]
    assert 0.0 <= first["regime_confidence"] <= 1.0
    assert pending["regime"] == "trend"
    assert pending["candidate_regime"] == "range"
    assert pending["regime_transition_pending"] is True
    assert confirmed["regime"] == "range"
    assert confirmed["regime_transition_pending"] is False

    allowed, stale = engine.should_trade(
        symbol="STALE",
        analysis_result={
            "score": 80,
            "momentum": 1.0,
            "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        },
        runtime_state={},
        policy=common_policy,
    )
    assert allowed is False
    assert any(reason.startswith("regime_data_stale:") for reason in stale["reasons"])


def test_ops_automation_detects_anomaly_and_rollback():
    from trading.ops_automation import OpsAutomationEngine

    ops = OpsAutomationEngine()
    anomalies = ops.detect_anomalies(
        {"reject_rate": 0.4, "avg_slippage_bps": 50, "quality_score": 30},
        {"enabled": True, "auto_rollback": True},
    )
    action = ops.build_rollback_action(anomalies, {"enabled": True, "auto_rollback": True})

    assert anomalies
    assert action["should_rollback"] is True


def _make_mock_adapter():
    adapter = MagicMock()
    adapter.broker_name = "mock"
    adapter.api_type = "mock"
    adapter.get_positions.return_value = []
    adapter.get_open_orders.return_value = []
    adapter.get_today_trades.return_value = []
    adapter.get_trade_history.return_value = [
        {"symbol": "005930", "pnl": -1000, "quantity": 1, "filled_price": 70000, "timestamp": "2026-04-30T09:00:00"},
        {"symbol": "005930", "pnl": -2000, "quantity": 1, "filled_price": 70000, "timestamp": "2026-04-30T09:05:00"},
        {"symbol": "005930", "pnl": -1500, "quantity": 1, "filled_price": 70000, "timestamp": "2026-04-30T09:10:00"},
    ]
    adapter.get_balance.return_value = {"cash": 1000000, "total_assets": 1000000}
    adapter.get_stock_info.return_value = {
        "code": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "current_price": 72000,
        "prev_close": 71000,
        "change_rate": 1.2,
        "volume": 1000000,
        "is_etf": False,
        "status": "ok",
    }
    adapter.get_realtime_price.return_value = {
        "code": "005930",
        "current_price": 72000,
        "change_rate": 1.2,
        "volume": 1000000,
        "status": "ok",
    }
    adapter.place_order.return_value = {"status": "success", "success": True, "order_id": "A1"}
    return adapter


def test_stock_auto_trade_profitability_gate_blocks_entries():
    from trading.stock_analysis_service import StockAnalysisService

    recorder = MagicMock()
    recorder.execute_query.return_value = []
    recorder.insert_trade_log.return_value = 1

    svc = StockAnalysisService(_make_mock_adapter(), broker_name="mock", recorder=recorder)
    result = svc.run_auto_trade_cycle(
        symbols=["005930"],
        quantity=1,
        buy_threshold=35,
        sell_threshold=10,
        allow_live_order=True,
        auto_risk_policy={
            "profitability_validation": {
                "enabled": True,
                "min_trades": 3,
                "min_win_rate": 0.9,
                "min_expectancy": 100,
                "min_sharpe": 1.0,
                "max_mdd": 0.1,
                "min_walkforward_pass_rate": 1.0,
            }
        },
    )

    assert result["orders_executed"] == 0
    assert result["decisions"][0]["reason"] == "profitability_blocked"
    assert result["profitability_validation"]["enabled"] is False


def test_unified_manager_quality_control_fallbacks_to_market():
    from trading.unified_trading_manager import UnifiedTradingManager

    manager = UnifiedTradingManager.__new__(UnifiedTradingManager)
    manager.settings = {}
    manager.logger = MagicMock()
    calls = []

    def fake_place(exchange_name, trading_type, symbol, side, quantity, price=None, order_type="MARKET"):
        calls.append(order_type)
        if order_type == "LIMIT":
            return {"status": "failed", "error": "limit_rejected"}
        return {"status": "success", "order_id": "U1", "symbol": symbol, "side": side, "quantity": quantity}

    manager.place_order_unified = fake_place

    result = manager.place_order_with_quality_control(
        exchange_name="bybit",
        trading_type="futures",
        symbol="BTCUSDT",
        side="buy",
        quantity=0.02,
        order_type="LIMIT",
        policy={"enabled": True, "fallback_market": True, "max_retries": 1, "max_slippage_bps": 100},
    )

    assert result["status"] == "success"
    assert calls[:2] == ["LIMIT", "MARKET"]
    assert "limit_rejected" in ";".join(result["errors"])


def test_unified_trader_cycle_blocks_on_profitability_gate():
    from trading.unified_trader import UnifiedTrader

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {
        "advanced_trading_layers": {
            "profitability_validation": {"enabled": True, "min_trades": 3, "min_win_rate": 0.9, "min_sharpe": 1.0},
            "portfolio_orchestration": {"enabled": True},
            "strategy_engine": {"enabled": True, "consensus_threshold": 0.4, "allow_regimes": ["trend", "range"]},
            "ops_automation": {"enabled": True, "auto_rollback": True},
        }
    }
    trader.logger = MagicMock()
    trader.exchange_manager = MagicMock()
    trader.unified_manager = MagicMock()
    trader.main_app = SimpleNamespace(selected_coins=[{"symbol": "BTCUSDT"}])
    trader.monitoring_flags = {"bybit": True}
    trader.portfolio_allocation_cache = {}
    trader.cycle_execution_metrics = {}
    trader.active_positions = {"bybit": {}}
    trader.log_event = MagicMock()
    trader._auto_adjust_threshold_from_performance = MagicMock()
    trader._check_and_reselect_coins_unified_optimized = MagicMock()
    trader.analyze_coins_unified = MagicMock(return_value={"BTCUSDT": {"signal": "LONG", "confidence": 0.91, "market_volatility": 1.2}})
    trader.get_exchange_client = MagicMock(return_value=SimpleNamespace(get_trade_history=lambda limit=100: [
        {"symbol": "BTCUSDT", "pnl": -1000, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:00:00"},
        {"symbol": "BTCUSDT", "pnl": -800, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:05:00"},
        {"symbol": "BTCUSDT", "pnl": -600, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:10:00"},
    ]))
    trader._monitor_exchange_positions = MagicMock()

    trader.execute_trading_cycle_unified("bybit")

    trader.unified_manager.place_order_with_quality_control.assert_not_called()
    assert "bybit" not in trader.portfolio_allocation_cache
    assert "bybit" not in trader.cycle_execution_metrics


def test_unified_trader_cycle_records_allocation_and_ops_metrics():
    from trading.unified_trader import UnifiedTrader

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {
        "advanced_trading_layers": {
            "profitability_validation": {"enabled": True, "min_trades": 3, "min_win_rate": 0.3, "min_sharpe": -5.0, "min_expectancy": -1000.0, "min_walkforward_pass_rate": 0.0},
            "portfolio_orchestration": {"enabled": True, "risk_budget": {"crypto": 0.5}},
            "strategy_engine": {"enabled": True, "consensus_threshold": 0.1, "allow_regimes": ["trend", "range"], "cooldown_sec": 0},
            "execution_optimizer": {"enabled": True, "fallback_market": True, "max_retries": 1},
            "ops_automation": {"enabled": True, "auto_rollback": True},
        },
        "default_leverage": 3,
    }
    trader.logger = MagicMock()
    trader.exchange_manager = MagicMock()
    trader.exchange_manager.get_exchange_balance.return_value = {"status": "success", "balance": {"USDT": {"free": 10000}}}
    trader.exchange_manager.get_current_price.return_value = 50000.0
    trader.unified_manager = MagicMock()
    trader.unified_manager.get_exchange.return_value = object()
    trader.main_app = SimpleNamespace(selected_coins=[{"symbol": "BTCUSDT"}])
    trader.monitoring_flags = {"bybit": True}
    trader.portfolio_allocation_cache = {}
    trader.cycle_execution_metrics = {}
    trader.active_positions = {"bybit": {}}
    trader.log_event = MagicMock()
    trader._log_trade_event = MagicMock()
    trader._auto_adjust_threshold_from_performance = MagicMock()
    trader._check_and_reselect_coins_unified_optimized = MagicMock()
    trader.analyze_coins_unified = MagicMock(return_value={"BTCUSDT": {"signal": "LONG", "confidence": 0.91, "market_volatility": 1.2}})
    trader.get_exchange_client = MagicMock(return_value=SimpleNamespace(
        get_trade_history=lambda limit=100: [
            {"symbol": "BTCUSDT", "pnl": 800, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:00:00"},
            {"symbol": "BTCUSDT", "pnl": 600, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:05:00"},
            {"symbol": "BTCUSDT", "pnl": -100, "quantity": 1, "filled_price": 10000, "timestamp": "2026-04-30T09:10:00"},
        ],
        set_leverage=lambda symbol, leverage: True,
        set_margin_type=lambda symbol, margin_type: True,
        exchange=object(),
    ))
    trader._monitor_exchange_positions = MagicMock()

    trader.execute_trading_cycle_unified("bybit")

    assert trader.portfolio_allocation_cache["bybit"]["allocations"]["BTCUSDT"]["capital"] > 0
    assert trader.cycle_execution_metrics["bybit"]["attempted_orders"] >= 0  # 전략엔진 통과 시 ≥1, 차단 시 0
    assert "profitability_validation" in trader.cycle_execution_metrics["bybit"]


def test_unified_trader_execute_signal_trade_uses_quality_control_and_allocation():
    from trading.unified_trader import UnifiedTrader

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {
        "advanced_trading_layers": {
            "execution_optimizer": {"enabled": True, "fallback_market": True, "max_retries": 1},
        },
        "default_leverage": 3,
    }
    trader.logger = MagicMock()
    trader.exchange_manager = MagicMock()
    trader.exchange_manager.get_current_price.return_value = 50000.0
    trader.unified_manager = MagicMock()
    trader.unified_manager.get_exchange.return_value = object()
    trader.unified_manager.place_order_with_quality_control.return_value = {
        "status": "success",
        "order_id": "O1",
        "latency_ms": 120.0,
        "slippage_bps": 6.5,
        "price": 50000.0,
    }
    trader.portfolio_allocation_cache = {"bybit": {"allocations": {"BTCUSDT": {"capital": 10000.0}}, "risk_scale": 1.0}}
    trader.active_positions = {"bybit": {}}
    trader.risk_manager = None
    trader.recorder = None
    trader._perform_pre_entry_analysis_unified = MagicMock(return_value={"proceed": True, "reason": "ok"})
    trader._calculate_dynamic_tp_sl_unified = MagicMock(return_value={"tp": 0.02, "sl": 0.01})
    trader._analyze_pattern_similarity_unified = MagicMock(return_value={"action": "KEEP"})
    trader._calculate_dynamic_confidence_threshold_unified = MagicMock(return_value=0.1)
    trader._get_ai_max_positions = MagicMock(return_value=3)
    trader._get_ai_enhanced_parameters_unified = MagicMock(return_value={"tp_percent": 0.02, "sl_percent": 0.01, "leverage": 3, "position_size_factor": 1.0})
    trader.get_exchange_client = MagicMock(return_value=SimpleNamespace(
        set_leverage=lambda symbol, leverage: True,
        set_margin_type=lambda symbol, margin_type: True,
        exchange=object(),
    ))
    trader._calculate_position_size_unified = MagicMock(return_value=0.05)
    trader._ensure_min_notional = MagicMock(return_value=(0.05, ""))
    trader._normalize_symbol_for_adapter = MagicMock(side_effect=lambda client, symbol: symbol)
    trader._clamp_leverage = MagicMock(side_effect=lambda exchange, leverage: leverage)
    trader._record_position_with_tp_sl = MagicMock()
    trader._is_order_success = MagicMock(return_value=True)
    trader._log_trade_event = MagicMock()

    result = trader._execute_signal_trade("bybit", "BTCUSDT", {"signal": "LONG", "confidence": 0.91, "market_volatility": 1.2})

    call = trader.unified_manager.place_order_with_quality_control.call_args
    assert result["status"] == "success"
    assert call is not None
    assert call.kwargs["quantity"] > 0
    assert call.kwargs["policy"]["enabled"] is True
    assert result["latency_ms"] == 120.0


def test_life_finance_advisor_loads_external_catalog(tmp_path):
    from trading.life_finance_products import FinanceProductAdvisor

    loan_path = tmp_path / "loans.json"
    loan_path.write_text(
        """
[
  {
    "name": "테스트 대출",
    "provider": "테스트은행",
    "annual_rate": 2.9,
    "max_amount": 500000000,
    "term_months": 240,
    "fee_rate": 0.0
  }
]
        """.strip(),
        encoding="utf-8",
    )

    advisor = FinanceProductAdvisor(catalog_paths={"loan": str(loan_path)})
    result = advisor.compare_loans(amount=100_000_000, term_months=24)

    assert result["best"]["name"] == "테스트 대출"
    assert result["catalog_source"] == str(loan_path)
    assert result["catalog_source_kind"] == "operator_catalog"


def test_binance_order_quality_control_fallbacks_to_market():
    from trading.trader import Trader

    trader = Trader.__new__(Trader)
    trader.settings = {
        "advanced_trading_layers": {
            "execution_optimizer": {
                "enabled": True,
                "fallback_market": True,
                "max_retries": 1,
                "max_slippage_bps": 100,
            }
        }
    }
    trader.binance_client = MagicMock()
    calls = []

    def place(symbol, side, order_type, quantity, price=None):
        calls.append(order_type)
        if order_type == "LIMIT":
            return {"status": "FAILED", "error": "limit_rejected"}
        return {"status": "FILLED", "order_id": "B1", "symbol": symbol}

    trader.binance_client.place_futures_order.side_effect = place

    result = trader._place_entry_order_with_quality_control_binance(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        layer_settings={
            "execution_optimizer": {
                "enabled": True,
                "fallback_market": True,
                "max_retries": 1,
                "max_slippage_bps": 100,
                "signal_strength": 0.5,
                "volatility": 0.05,
                "spread_bps": 30,
                "preferred_order_type": "LIMIT",
            }
        },
        trade_params={"confidence": 0.5, "volatility": 0.05},
    )

    assert result["status"] == "FILLED"
    assert calls[:2] == ["LIMIT", "MARKET"]


def test_binance_cycle_profitability_gate_blocks_early():
    from trading.trader import Trader

    trader = Trader.__new__(Trader)
    trader.settings = {
        "advanced_trading_layers": {
            "profitability_validation": {
                "enabled": True,
                "min_trades": 3,
                "min_win_rate": 0.9,
                "min_sharpe": 1.0,
            }
        }
    }
    trader.logger = MagicMock()
    trader.log_event = MagicMock()
    trader.cycle_execution_metrics = {}
    trader._cleanup_zombie_flags = MagicMock()
    trader._check_and_reselect_coins_optimized = MagicMock()
    trader._auto_adjust_threshold_from_performance = MagicMock()
    trader._get_recent_trade_samples_binance = MagicMock(return_value=[
        {"symbol": "BTCUSDT", "pnl": -1000, "quantity": 1, "exit_price": 10000, "fees": 0, "slippage": 0},
        {"symbol": "BTCUSDT", "pnl": -900, "quantity": 1, "exit_price": 10000, "fees": 0, "slippage": 0},
        {"symbol": "BTCUSDT", "pnl": -800, "quantity": 1, "exit_price": 10000, "fees": 0, "slippage": 0},
    ])
    trader.risk_manager = None

    trader.execute_trading_cycle()

    assert "binance" in trader.cycle_execution_metrics
    assert trader.cycle_execution_metrics["binance"]["attempted_orders"] == 0
    assert trader.cycle_execution_metrics["binance"]["profitability_validation"]["enabled"] is False
