#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeAdapter:
    def connect(self):
        return True

    def get_balance(self):
        return {"status": "ok", "cash": 1000000}

    def get_positions(self):
        return [{"code": "005930"}]

    def get_open_orders(self):
        return []

    def get_realtime_price(self, symbol):
        return {"code": symbol, "current_price": 70000}

    def place_order(self, **kwargs):
        return {"status": "success", "order_id": "OID001", **kwargs}

    def cancel_order(self, order_id, symbol=None):
        return True


def _live_row(**overrides):
    row = {
        "broker": "shinhan",
        "api_type": "rest",
        "api_version": "v1",
        "allow_live_order": True,
        "valid_combo": True,
        "execution_mode": "live_api",
        "credentials_ready": True,
        "missing_credentials": [],
        "os_blocked": False,
        "live_order_enabled": True,
    }
    row.update(overrides)
    return row


def test_smoke_check_returns_zero_without_targets_by_default():
    from scripts import stock_live_smoke_check as smoke

    with patch.object(smoke, "_parse_args", return_value=SimpleNamespace(strict=False)), \
         patch.object(smoke, "_load_settings", return_value=({}, Path("settings.json"))), \
         patch.object(smoke, "_build_rows", return_value=[_live_row(credentials_ready=False, missing_credentials=["id"])]):
        assert smoke.main() == 0


def test_preflight_auto_trading_validation_blocks_invalid_thresholds():
    from scripts import stock_d1_preflight as preflight

    summary, blocking, warning = preflight._evaluate_stock_auto_trading_config({
        "stock_auto_trading": {
            "enabled": True,
            "interval_sec": 3,
            "quantity": 0,
            "max_orders_per_cycle": 0,
            "buy_threshold": 20,
            "sell_threshold": 30,
            "enable_exit_policy": True,
            "take_profit_percent": 0,
            "stop_loss_percent": -1,
            "etf_take_profit_percent": 4,
            "etf_stop_loss_percent": 6,
        }
    })

    assert summary["enabled"] is True
    assert blocking
    assert any("buy_threshold" in msg for msg in blocking)
    assert any("quantity" in msg for msg in blocking)


def test_preflight_auto_trading_validation_blocks_invalid_broker_overrides():
    from scripts import stock_d1_preflight as preflight

    summary, blocking, warning = preflight._evaluate_stock_auto_trading_config({
        "stock_auto_trading": {
            "enabled": True,
            "interval_sec": 10,
            "quantity": 1,
            "max_orders_per_cycle": 1,
            "buy_threshold": 70,
            "sell_threshold": 30,
            "risk_governance_enabled": True,
            "broker_overrides": {
                "kiwoom": {
                    "daily_max_loss": -1,
                    "max_symbol_weight_percent": 120,
                },
                "shinhan": "invalid",
            },
            "enable_exit_policy": True,
            "take_profit_percent": 5,
            "stop_loss_percent": 8,
            "etf_take_profit_percent": 4,
            "etf_stop_loss_percent": 6,
        }
    })

    assert summary["enabled"] is True
    assert blocking
    assert any("broker_overrides.kiwoom.daily_max_loss" in msg for msg in blocking)
    assert any("broker_overrides.kiwoom.max_symbol_weight_percent" in msg for msg in blocking)
    assert any("broker_overrides.shinhan" in msg for msg in blocking)


def test_preflight_main_returns_one_when_auto_policy_invalid():
    from scripts import stock_d1_preflight as preflight

    settings = {
        "enable_stock_live_order": False,
        "enabled_stock_brokers": ["shinhan"],
        "stock_auto_trading": {
            "enabled": True,
            "interval_sec": 3,
            "buy_threshold": 20,
            "sell_threshold": 30,
            "quantity": 1,
            "max_orders_per_cycle": 1,
            "enable_exit_policy": True,
            "take_profit_percent": 5,
            "stop_loss_percent": 8,
            "etf_take_profit_percent": 4,
            "etf_stop_loss_percent": 6,
        },
    }

    with patch.object(preflight, "_load_settings", return_value=(settings, Path("settings.json"))), \
         patch.object(preflight, "_check_core_files", return_value={
             "exchange_factory": True,
             "stock_analysis_service": True,
             "stock_guardrails_test": True,
             "stock_integration_test": True,
         }), \
         patch.object(preflight, "_build_rows", return_value=[_live_row(live_order_enabled=False)]):
        assert preflight.main() == 1


def test_smoke_check_runs_adapter_when_target_ready():
    from scripts import stock_live_smoke_check as smoke

    with patch.object(smoke, "_parse_args", return_value=SimpleNamespace(strict=True)), \
         patch.object(smoke, "_load_settings", return_value=({}, Path("settings.json"))), \
         patch.object(smoke, "_build_rows", return_value=[_live_row()]), \
         patch.object(smoke.ExchangeFactory, "create_stock_exchange", return_value=FakeAdapter()):
        assert smoke.main() == 0


def test_order_drill_dry_run_ready_path():
    from scripts import stock_live_order_drill as drill

    args = SimpleNamespace(
        broker="shinhan",
        symbol="005930",
        side="BUY",
        quantity=1.0,
        order_type="LIMIT",
        price=70000.0,
        execute=False,
        cancel_after=False,
        strict=True,
    )
    with patch.object(drill, "_parse_args", return_value=args), \
         patch.object(drill, "_load_settings", return_value=({}, Path("settings.json"))), \
         patch.object(drill, "_build_rows", return_value=[_live_row()]), \
         patch.object(drill.ExchangeFactory, "create_stock_exchange", return_value=FakeAdapter()):
        assert drill.main() == 0


def test_order_drill_execute_and_cancel_path():
    from scripts import stock_live_order_drill as drill

    args = SimpleNamespace(
        broker="shinhan",
        symbol="005930",
        side="BUY",
        quantity=1.0,
        order_type="LIMIT",
        price=70000.0,
        execute=True,
        cancel_after=True,
        strict=True,
    )
    with patch.object(drill, "_parse_args", return_value=args), \
         patch.object(drill, "_load_settings", return_value=({}, Path("settings.json"))), \
         patch.object(drill, "_build_rows", return_value=[_live_row()]), \
         patch.object(drill.ExchangeFactory, "create_stock_exchange", return_value=FakeAdapter()):
        assert drill.main() == 0


def test_readiness_runner_respects_non_strict_failures():
    from scripts import stock_live_readiness_run as runner

    results = [
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="blocked", stderr=""),
        SimpleNamespace(returncode=0, stdout="smoke ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="drill ok", stderr=""),
    ]

    with patch.object(runner, "_parse_args", return_value=SimpleNamespace(broker="kiwoom", strict=False, all_brokers=False, skip_mock_check=True)), \
         patch.object(runner.subprocess, "run", side_effect=results):
        assert runner.main() == 1


def test_readiness_runner_strict_propagates_failures():
    from scripts import stock_live_readiness_run as runner

    results = [
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="ready", stderr=""),
        SimpleNamespace(returncode=1, stdout="no target", stderr=""),
        SimpleNamespace(returncode=0, stdout="drill skipped", stderr=""),
    ]

    with patch.object(runner, "_parse_args", return_value=SimpleNamespace(broker="kiwoom", strict=True, all_brokers=False, skip_mock_check=True)), \
         patch.object(runner.subprocess, "run", side_effect=results):
        assert runner.main() == 1


def test_readiness_runner_all_brokers_adds_drill_steps():
    from scripts import stock_live_readiness_run as runner

    calls = []

    def _fake_run(command, cwd=None, capture_output=None, text=None):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    args = SimpleNamespace(broker="kiwoom", strict=False, all_brokers=True, skip_mock_check=False)
    with patch.object(runner, "_parse_args", return_value=args), \
         patch.object(runner, "_load_settings", return_value=({"enabled_stock_brokers": ["kiwoom", "shinhan", "miraeAsset"]}, Path("settings.json"))), \
         patch.object(runner, "subprocess") as subproc:
        subproc.run.side_effect = _fake_run
        assert runner.main() == 0

    joined = [" ".join(c) for c in calls]
    assert any("stock_d1_preflight.py" in c for c in joined)
    assert any("stock_nonkey_hardening_check.py" in c for c in joined)
    assert any("stock_live_smoke_check.py" in c for c in joined)
    assert any("stock_live_order_drill.py --broker kiwoom" in c for c in joined)
    assert any("stock_live_order_drill.py --broker shinhan" in c for c in joined)
    assert any("stock_live_order_drill.py --broker miraeAsset" in c for c in joined)


def test_readiness_runner_all_supported_brokers_uses_factory_list():
    from scripts import stock_live_readiness_run as runner

    calls = []

    def _fake_run(command, cwd=None, capture_output=None, text=None):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    args = SimpleNamespace(
        broker="kiwoom",
        strict=False,
        all_brokers=False,
        all_supported_brokers=True,
        skip_mock_check=False,
    )
    with patch.object(runner, "_parse_args", return_value=args), \
         patch.object(runner.ExchangeFactory, "get_supported_exchanges", return_value={"stock": ["kiwoom", "shinhan", "miraeAsset"]}), \
         patch.object(runner, "subprocess") as subproc:
        subproc.run.side_effect = _fake_run
        assert runner.main() == 0

    joined = [" ".join(c) for c in calls]
    assert any("stock_live_order_drill.py --broker kiwoom" in c for c in joined)
    assert any("stock_live_order_drill.py --broker shinhan" in c for c in joined)
    assert any("stock_live_order_drill.py --broker miraeAsset" in c for c in joined)


def test_readiness_runner_all_supported_non_strict_allows_precheck_blocked():
    from scripts import stock_live_readiness_run as runner

    results = [
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="precheck blocked", stderr=""),
        SimpleNamespace(returncode=0, stdout="mock ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="smoke skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="drill kiwoom skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="drill shinhan skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="drill mirae skip", stderr=""),
    ]

    args = SimpleNamespace(
        broker="kiwoom",
        strict=False,
        all_brokers=False,
        all_supported_brokers=True,
        skip_mock_check=False,
    )
    with patch.object(runner, "_parse_args", return_value=args), \
         patch.object(runner.ExchangeFactory, "get_supported_exchanges", return_value={"stock": ["kiwoom", "shinhan", "miraeAsset"]}), \
         patch.object(runner, "subprocess") as subproc:
        subproc.run.side_effect = results
        assert runner.main() == 0