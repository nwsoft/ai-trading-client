#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_recover_broker_success_path():
    from scripts import stock_broker_recovery as recovery

    with patch.object(recovery, "_run_script", side_effect=[0, 0]), \
         patch.object(recovery, "_run_readiness", return_value=0):
        assert recovery.recover_broker("kiwoom", strict=False) is True


def test_recover_broker_strict_stops_on_preflight_fail():
    from scripts import stock_broker_recovery as recovery

    with patch.object(recovery, "_run_script", return_value=1), \
         patch.object(recovery, "_run_readiness", return_value=0):
        assert recovery.recover_broker("kiwoom", strict=True) is False


def test_recover_broker_non_strict_preflight_fail_returns_false():
    from scripts import stock_broker_recovery as recovery

    with patch.object(recovery, "_run_script", side_effect=[1, 0]), \
         patch.object(recovery, "_run_readiness", return_value=0):
        assert recovery.recover_broker("kiwoom", strict=False) is False


def test_recover_broker_strict_fails_on_readiness():
    from scripts import stock_broker_recovery as recovery

    with patch.object(recovery, "_run_script", side_effect=[0, 0]), \
         patch.object(recovery, "_run_readiness", return_value=1):
        assert recovery.recover_broker("kiwoom", strict=True) is False


def test_main_all_brokers_exit_zero_when_all_pass(monkeypatch):
    from scripts import stock_broker_recovery as recovery

    args = SimpleNamespace(broker="kiwoom", all=True, auto_mode=False, strict=False)

    with patch.object(recovery, "_parse_args", return_value=args), \
         patch.object(recovery, "_get_all_brokers", return_value=["kiwoom", "shinhan"]), \
         patch.object(recovery, "recover_broker", side_effect=[True, True]):
        with patch.object(recovery.sys, "exit") as exit_mock:
            recovery.main()
            exit_mock.assert_called_once_with(0)


def test_main_single_broker_exit_one_on_fail(monkeypatch):
    from scripts import stock_broker_recovery as recovery

    args = SimpleNamespace(broker="kiwoom", all=False, auto_mode=False, strict=True)

    with patch.object(recovery, "_parse_args", return_value=args), \
         patch.object(recovery, "recover_broker", return_value=False):
        with patch.object(recovery.sys, "exit") as exit_mock:
            recovery.main()
            exit_mock.assert_called_once_with(1)
