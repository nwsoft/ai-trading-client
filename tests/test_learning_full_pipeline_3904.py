import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading.execution_mode import ExecutionMode
from trading.trader import Trader
from trading.stock_analysis_service import StockAnalysisService
from trading.unified_trader import UnifiedTrader


def test_binance_learning_dry_run_runs_final_gate_without_order_submission():
    trader = object.__new__(Trader)
    trader.settings = {
        "max_positions": 3,
        "default_leverage": 1,
        "min_trade_amount": 5.0,
    }
    trader.active_positions = {}
    trader.logger = MagicMock()
    trader.log_event = MagicMock()
    trader._log_trade_event = MagicMock()
    trader.should_execute_trade = MagicMock(return_value=True)
    trader.execute_single_trade = MagicMock()

    result = trader.execute_trades(
        [{"symbol": "BTCUSDT"}],
        {
            "BTCUSDT": {
                "side": "BUY",
                "qty": 0.01,
                "price": 100_000.0,
                "leverage": 1,
                "tp": 0.0018,
                "sl": 0.0020,
            }
        },
        dry_run=True,
    )

    assert result[0]["status"] == "learning_planned"
    trader.should_execute_trade.assert_called_once()
    trader.execute_single_trade.assert_not_called()


def test_unified_learning_builds_complete_plan_before_mutating_exchange_state():
    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "paper_trading": False,
        "demo_mode": False,
        "verbose_trade_logging": False,
        "default_leverage": 3,
    }
    trader.logger = MagicMock()
    trader.risk_manager = None
    trader.portfolio_allocation_cache = {}
    trader._execution_mode = MagicMock(return_value=ExecutionMode.LEARNING)
    trader._perform_pre_entry_analysis_unified = MagicMock(
        return_value={"proceed": True, "reason": "ok"}
    )
    trader._calculate_dynamic_tp_sl_unified = MagicMock(
        return_value={
            "tp": 0.003,
            "sl": 0.002,
            "rr_guardrail_enabled": True,
            "rr_guardrail_passed": True,
            "rr_after": 1.5,
            "rr_min": 1.2,
        }
    )
    trader._analyze_pattern_similarity_unified = MagicMock(
        return_value={"action": "PROCEED"}
    )
    trader._calculate_dynamic_confidence_threshold_unified = MagicMock(return_value=0.5)
    trader._log_trade_event = MagicMock()
    trader._position_store = MagicMock(return_value={})
    trader._get_ai_max_positions = MagicMock(return_value=3)
    trader._get_ai_enhanced_parameters_unified = MagicMock(
        return_value={"tp_percent": 0.003, "sl_percent": 0.002, "leverage": 3}
    )
    exchange_client = SimpleNamespace(
        set_leverage=MagicMock(),
        set_margin_type=MagicMock(),
        place_order=MagicMock(),
    )
    trader.get_exchange_client = MagicMock(return_value=exchange_client)
    trader._calculate_position_size_unified = MagicMock(return_value=0.02)
    trader._ensure_min_notional = MagicMock(return_value=(0.02, ""))
    trader._clamp_leverage = MagicMock(return_value=3)
    trader.exchange_manager = SimpleNamespace(get_current_price=MagicMock(return_value=100.0))

    result = trader._execute_signal_trade(
        "bybit",
        "BTC/USDT:USDT",
        {
            "signal": "LONG",
            "confidence": 0.9,
            "_learning_only": True,
            "_candidate_source": "base_ai",
        },
    )

    assert result["status"] == "learning_planned"
    assert result["trade_plan"]["quantity"] == 0.02
    assert result["trade_plan"]["tp_percent"] == 0.003
    assert result["trade_plan"]["sl_percent"] == 0.002
    trader._perform_pre_entry_analysis_unified.assert_called_once()
    trader._calculate_dynamic_tp_sl_unified.assert_called_once()
    trader._ensure_min_notional.assert_called_once()
    exchange_client.set_leverage.assert_not_called()
    exchange_client.set_margin_type.assert_not_called()
    exchange_client.place_order.assert_not_called()


def test_unified_trade_fails_closed_when_min_notional_validation_raises():
    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "paper_trading": False,
        "demo_mode": False,
        "verbose_trade_logging": False,
        "default_leverage": 3,
    }
    trader.logger = MagicMock()
    trader.risk_manager = None
    trader.portfolio_allocation_cache = {}
    trader._execution_mode = MagicMock(return_value=ExecutionMode.LEARNING)
    trader._perform_pre_entry_analysis_unified = MagicMock(
        return_value={"proceed": True, "reason": "ok"}
    )
    trader._calculate_dynamic_tp_sl_unified = MagicMock(
        return_value={
            "tp": 0.003,
            "sl": 0.002,
            "rr_guardrail_enabled": True,
            "rr_guardrail_passed": True,
        }
    )
    trader._analyze_pattern_similarity_unified = MagicMock(
        return_value={"action": "PROCEED"}
    )
    trader._calculate_dynamic_confidence_threshold_unified = MagicMock(return_value=0.5)
    trader._log_trade_event = MagicMock()
    trader._position_store = MagicMock(return_value={})
    trader._get_ai_max_positions = MagicMock(return_value=3)
    trader._get_ai_enhanced_parameters_unified = MagicMock(
        return_value={"tp_percent": 0.003, "sl_percent": 0.002, "leverage": 3}
    )
    exchange_client = SimpleNamespace(
        set_leverage=MagicMock(),
        set_margin_type=MagicMock(),
        place_order=MagicMock(),
    )
    trader.get_exchange_client = MagicMock(return_value=exchange_client)
    trader._calculate_position_size_unified = MagicMock(return_value=0.02)
    trader._ensure_min_notional = MagicMock(side_effect=RuntimeError("market limits unavailable"))
    trader._clamp_leverage = MagicMock(return_value=3)
    trader.exchange_manager = SimpleNamespace(get_current_price=MagicMock(return_value=100.0))

    result = trader._execute_signal_trade(
        "bybit",
        "BTC/USDT:USDT",
        {
            "signal": "LONG",
            "confidence": 0.9,
            "_learning_only": True,
            "_candidate_source": "base_ai",
        },
    )

    assert result["status"] == "skipped"
    assert "최소 주문 규격 검증 실패" in result["reason"]
    exchange_client.set_leverage.assert_not_called()
    exchange_client.set_margin_type.assert_not_called()
    exchange_client.place_order.assert_not_called()


def test_learning_order_barrier_is_after_full_decision_pipeline_in_both_paths():
    binance_source = inspect.getsource(Trader.execute_trading_cycle)
    assert binance_source.index("candidate = evaluate_trade_candidate") < binance_source.index(
        "self._perform_pre_entry_analysis(symbol, signal_data)"
    )
    assert binance_source.index(
        "self._perform_pre_entry_analysis(symbol, signal_data)"
    ) < binance_source.index("dry_run=True")
    assert binance_source.index("dry_run=True") < binance_source.index(
        "self.execute_trades(candidates, optimized_params_wrapped)"
    )

    unified_source = inspect.getsource(UnifiedTrader.execute_trading_cycle_unified)
    assert unified_source.index("candidate = evaluate_trade_candidate") < unified_source.index(
        "analysis['_learning_only'] = True"
    )
    assert unified_source.index("analysis['_learning_only'] = True") < unified_source.index(
        "trade_result = self._execute_signal_trade"
    )

    stock_source = inspect.getsource(StockAnalysisService.run_auto_trade_cycle)
    assert stock_source.index("evaluate_stock_order_guardrails") < stock_source.index(
        "'learning_order_blocked_after_full_pipeline'"
    )
    assert stock_source.index(
        "'learning_order_blocked_after_full_pipeline'"
    ) < stock_source.index("self._place_paper_stock_order")
