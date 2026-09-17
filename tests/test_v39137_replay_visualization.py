"""Replay visual evidence is additive and cannot authorize trading or passport promotion."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from trading.custom_strategy_validator import run_historical_replay
from trading.replay_visualization import build_replay_visualization
from trading.strategy_validation_lab import run_validation_lab


def replay(side="LONG", scale=1.0, count=180, no_trades=False, step=900000):
    rows = []
    for i in range(count):
        price = (100 + i * .1) * scale
        rows.append([1735689600000 + i * step, price, price * 1.03,
                     price * .97, price, 1000, 1735689600000 + (i + 1) * step - 1])
    rules = {"signal_mode": "independent", "entry_signal": side,
             "executable_entry": {"all": [{"field": "price", "operator": "gt", "value": 1e20 if no_trades else 0}]},
             "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1}}
    return run_historical_replay(rules, rows)


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("scale", [1.0, 700.0, 0.0000001])
def test_chart_matches_exact_replay_trades_and_lab(side, scale):
    metrics = replay(side, scale)
    chart = metrics["replay_visualization"]
    assert chart["status"] == "available"
    assert len(chart["candles"]) == metrics["candles"] == 180
    assert len(chart["candles_sha256"]) == 64
    assert chart["simulation_only"] is True
    assert metrics["decisions"] > 0
    for i, trade in enumerate(metrics["trades"]):
        assert trade["side"] == side
        assert chart["candles"][trade["entry_index"]]["close"] == pytest.approx(trade["entry_price"], abs=1e-10)
        assert chart["equity"][i + 1]["time"] == chart["candles"][trade["exit_index"]]["time"]
        assert chart["equity"][i + 1]["value"] == metrics["equity_curve_percent"][i]
        assert trade["gross_pnl_percent"] - trade["cost_percent"] == pytest.approx(trade["net_pnl_percent"])
    lab = run_validation_lab([{"return_percent": t["net_pnl_percent"]} for t in metrics["trades"]])
    assert chart["equity"][-1]["value"] == pytest.approx(lab["performance"]["total_return_percent"], abs=1e-4)
    assert "promotion_ready" not in chart
    assert "active" not in chart


def test_zero_trades_preserves_real_candles_and_flat_curve():
    metrics = replay(no_trades=True)
    chart = metrics["replay_visualization"]
    assert metrics["decisions"] == 0
    assert chart["status"] == "available"
    assert len(chart["equity"]) == 2
    assert all(p["value"] == 0 for p in chart["equity"])


@pytest.mark.parametrize("bad", ["missing_time", "duplicate", "reversed", "invalid_price", "invalid_ohlc", "oversize"])
def test_bad_candles_are_never_invented_or_silently_repaired(bad):
    rows = [dict(timestamp=100 + i, open=100, high=101, low=99, close=100) for i in range(3)]
    if bad == "missing_time": rows[0]["timestamp"] = None
    if bad == "duplicate": rows[1]["timestamp"] = rows[0]["timestamp"]
    if bad == "reversed": rows.reverse()
    if bad == "invalid_price": rows[0]["close"] = float("nan")
    if bad == "invalid_ohlc": rows[0]["high"] = 90
    if bad == "oversize": rows *= 2000
    chart = build_replay_visualization(rows, [], [], [])
    assert chart["status"] == "unavailable"
    assert "candles" not in chart


def test_replay_snapshot_is_detached_deterministic_and_costs_do_not_change_candles():
    a, b = replay(), replay()
    assert a["replay_visualization"] == b["replay_visualization"]
    a["replay_visualization"]["candles"][0]["close"] = 999
    assert b["replay_visualization"]["candles"][0]["close"] == 100


def test_trade_index_mismatch_is_not_attached_to_a_different_candle():
    rows = [dict(timestamp=100 + i, open=100, high=101, low=99, close=100) for i in range(3)]
    for trade in [{"entry_index": 0, "exit_index": 9, "side": "LONG"},
                  {"entry_index": 1, "exit_index": 1, "side": "SHORT"}]:
        assert build_replay_visualization(rows, [trade], [1.0], [0.0])["status"] == "unavailable"


def test_frontend_replay_contract_against_real_python_output():
    import os
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "--test", "tests/replay-evidence.test.cjs"], cwd=root,
                            env={**os.environ, "NOAHAI_QA_PYTHON": sys.executable},
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    # Browser QA consumes actual engine output, never external accounts or APIs.
    etf = "--etf" in sys.argv
    stock = "--stock" in sys.argv or etf
    metrics = replay(count=360, scale=700 if stock else 1e-9 if "--low-price" in sys.argv else 1,
                     side="SHORT" if "--short" in sys.argv else "LONG", no_trades="--empty" in sys.argv,
                     step=86400000 if stock else 900000)
    metrics.update(validation_source="kiwoom" if stock else "binance", validation_interval="1d" if stock else "15m",
                   symbol="069500" if etf else "005930" if stock else "LOWPRICEUSDT" if "--low-price" in sys.argv else "BTCUSDT",
                   quote_currency="KRW" if stock else "USDT")
    metrics["replay_visualization"]["binding"] = {"version_id": "fixture_v1"}
    print(json.dumps(metrics))
