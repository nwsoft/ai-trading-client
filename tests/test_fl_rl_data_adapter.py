#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from trading.fl_rl_data_adapter import RLDataAdapter


def test_build_transitions_and_anonymize():
    adapter = RLDataAdapter(db_path="/tmp/not_used.db", user_scope="user-a")

    rows = [
        {
            "id": 1,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 100.0,
            "exit_price": 101.0,
            "quantity": 1.5,
            "leverage": 5,
            "pnl": 1.0,
            "pnl_percent": 0.01,
            "entry_time": "2026-05-21T10:00:00+00:00",
            "exit_time": "2026-05-21T10:05:00+00:00",
            "exchange": "binance",
        },
        {
            "id": 2,
            "symbol": "ETHUSDT",
            "side": "SELL",
            "entry_price": 200.0,
            "exit_price": 198.0,
            "quantity": 2.0,
            "leverage": 3,
            "pnl": -4.0,
            "pnl_percent": -0.01,
            "entry_time": "2026-05-21T10:10:00+00:00",
            "exit_time": "2026-05-21T10:12:00+00:00",
            "exchange": "binance",
        },
    ]

    transitions = adapter.build_transitions(rows)
    assert len(transitions) == 2
    assert transitions[0].action == 1
    assert transitions[1].action == 2
    assert transitions[1].done is True

    anon = adapter.anonymize(transitions, salt="salt-1")
    assert len(anon) == 2
    assert anon[0].user_hash == anon[1].user_hash
    assert anon[0].symbol_bucket == "BTC"
    assert anon[1].symbol_bucket == "ETH"
    assert len(anon[0].timestamp_date) == 10
