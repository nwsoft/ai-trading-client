from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.trade_candidate import evaluate_trade_candidate
from web_platform.query_services import AccountQueryService


def _paper_strategy(*, operation_mode: str = "paper_validation") -> dict:
    return {
        "id": "paper-v1",
        "strategy_key": "paper-strategy",
        "version_id": "paper-v1",
        "name": "구조화 전 독립 전략",
        "target_scope": "asset:crypto",
        "market_regimes": ["all"],
        "signal_mode": "independent",
        "entry_signal": "",
        "operation_mode": operation_mode,
        "rules": {
            "signal_mode": "independent",
            "entry_signal": "",
            "executable_entry": {"all": [], "any": []},
        },
    }


@pytest.mark.parametrize(
    "target", ["binance", "upbit", "bithumb", "bybit", "bitget", "okx"]
)
def test_paper_validation_nonmatch_delegates_to_noah_without_blocking_base_trade(target):
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "LONG", "confidence": 0.8},
        strategy_pool=[_paper_strategy()],
        asset_class="crypto",
        target=target,
        market_regime="range",
    )

    assert candidate.allowed is True
    assert candidate.final_signal == "LONG"
    assert candidate.signal_source == "noah_base"
    assert candidate.reason == "paper_validation_not_matched_delegate_to_noah"


def test_active_strategy_nonmatch_remains_fail_closed():
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "LONG", "confidence": 0.8},
        strategy_pool=[_paper_strategy(operation_mode="standard")],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )

    assert candidate.allowed is False
    assert candidate.final_signal == "HOLD"
    assert candidate.reason == "no_strategy_matched_current_scope_regime_and_entry"


def test_paper_observation_rejects_independent_strategy_without_executable_direction(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    submitted = pipeline.submit(
        name="동적 양방향 원문",
        rules={
            "entry": "LONG_SCORE 또는 SHORT_SCORE",
            "exit": "반대 신호",
            "stop_loss": "1%",
            "take_profit": "2%",
            "position_size": "5%",
            "market_conditions": ["all"],
            "signal_mode": "independent",
            "entry_signal": "",
            "executable_entry": {"all": [], "any": []},
            "engine_settings": {
                "_unit": "percent_points",
                "tp_percent": 2.0,
                "sl_percent": 1.0,
            },
        },
        source_kind="text",
        source_reference="pasted",
    )
    readiness = pipeline.paper_execution_readiness(submitted)
    assert readiness["ready"] is False
    assert readiness["reasons"] == [
        "independent_entry_signal_missing",
        "independent_executable_entry_missing",
    ]
    with pytest.raises(ValueError, match="실행 규칙"):
        pipeline.approve(
            submitted["strategy_key"], submitted["version_id"], approved_by="tester"
        )
    with pytest.raises(ValueError, match="실행 규칙"):
        pipeline.start_paper_observation(
            submitted["strategy_key"], submitted["version_id"]
        )


def test_confirm_strategy_without_custom_exit_rates_explicitly_inherits_noah_exit(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    submitted = pipeline.submit(
        name="Noah 후보 확인",
        rules={
            "entry": "NoahAI LONG 신호 확인",
            "exit": "NoahAI 스마트 청산",
            "stop_loss": "NoahAI 동적 정책",
            "take_profit": "NoahAI 동적 정책",
            "position_size": "5%",
            "market_conditions": ["all"],
            "signal_mode": "confirm",
            "executable_entry": {"all": [{"field": "signal", "operator": "eq", "value": "LONG"}]},
            "engine_settings": {"_unit": "percent_points", "position_size": 0.05},
        },
    )
    assert submitted["rules"]["exit_policy"] == {"mode": "inherit_noah_base"}
    assert submitted["execution_readiness"]["ready"] is True
    pipeline.approve(submitted["strategy_key"], submitted["version_id"], approved_by="tester")

    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "LONG", "confidence": 0.8},
        strategy_pool=[{
            "id": submitted["version_id"],
            "name": submitted["name"],
            "target_scope": "asset:crypto",
            "market_regimes": ["all"],
            "signal_mode": "confirm",
            "rules": submitted["rules"],
            "engine_settings": {"_unit": "fraction", "position_size": 0.05},
        }],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )
    assert candidate.allowed is True
    assert candidate.exit_plan.source == "noah_dynamic"
    assert candidate.exit_plan.strategy_owned is False
    assert candidate.exit_plan.allow_noah_dynamic_adjustment is True


def test_strategy_owned_exit_rejects_out_of_range_rates_before_approval(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=str(tmp_path / "strategies.json"))
    submitted = pipeline.submit(
        name="위험한 고정 청산값",
        rules={
            "entry": "RSI 30 이하 LONG",
            "exit": "고정 TP/SL",
            "stop_loss": "1%",
            "take_profit": "60%",
            "position_size": "5%",
            "market_conditions": ["all"],
            "signal_mode": "independent",
            "entry_signal": "LONG",
            "executable_entry": {
                "all": [{"field": "rsi", "operator": "lte", "value": 30}]
            },
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points",
                "tp_percent": 60.0,
                "sl_percent": 1.0,
            },
        },
    )
    assert submitted["execution_readiness"]["ready"] is False
    assert "exit_rate_contract_missing_or_invalid" in submitted["execution_readiness"]["reasons"]
    with pytest.raises(ValueError, match="실행 규칙"):
        pipeline.approve(
            submitted["strategy_key"], submitted["version_id"], approved_by="tester"
        )


@pytest.mark.parametrize(
    ("rsi", "expected"),
    [(25, "LONG"), (75, "SHORT")],
)
def test_independent_dual_direction_branches_select_exactly_one_direction(rsi, expected):
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "HOLD", "rsi": rsi},
        strategy_pool=[{
            "id": "dual-v1",
            "name": "RSI 양방향",
            "target_scope": "asset:crypto",
            "market_regimes": ["all"],
            "signal_mode": "independent",
            "operation_mode": "standard",
            "rules": {
                "signal_mode": "independent",
                "independent_entries": {
                    "LONG": {"all": [{"field": "rsi", "operator": "lte", "value": 30}]},
                    "SHORT": {"all": [{"field": "rsi", "operator": "gte", "value": 70}]},
                },
                "exit_policy": {"mode": "strategy_owned"},
                "engine_settings": {"_unit": "percent_points", "tp_percent": 2, "sl_percent": 1},
            },
            "engine_settings": {"_unit": "fraction", "tp_percent": 0.02, "sl_percent": 0.01},
        }],
        asset_class="crypto",
        target="binance",
        market_regime="range",
    )
    assert candidate.allowed is True
    assert candidate.final_signal == expected
    assert candidate.signal_source == "custom_independent"
    assert candidate.exit_plan.strategy_owned is True


def test_ai_report_detail_uses_same_closed_trade_ledger_as_period_summary(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, asset_type TEXT,
            side TEXT, entry_price REAL, exit_price REAL, quantity REAL,
            pnl REAL, pnl_percent REAL, fees REAL,
            entry_time DATETIME, exit_time DATETIME, reason TEXT
        );
        """
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        "INSERT INTO trade_log VALUES (1, 'BTCUSDT', 'binance', 'crypto', "
        "'LONG', 100, 102, 1, 1.8, 1.8, .2, ?, ?, 'take_profit')",
        (now, now),
    )
    connection.commit()
    connection.close()

    snapshot = AccountQueryService(str(db_path)).workspace(
        "blockchain", "blockchain.ai_reports"
    )

    today = snapshot["report_periods"]["periods"]["today"]
    assert today["closed_count"] == 1
    assert today["detail_total_count"] == 1
    assert today["detail_rows"][0]["symbol"] == "BTCUSDT"
    assert today["ledger_reconciled"] is True
    assert len(snapshot["trading"]["recent_trades"]) == 1
    detail = snapshot["trading"]["recent_trades"][0]
    assert detail["symbol"] == "BTCUSDT"
    assert detail["pnl"] == pytest.approx(1.8)
    assert detail["exit_price"] == pytest.approx(102.0)

    ui_source = (
        Path(__file__).resolve().parents[1]
        / "webui/src/components/LegacyFeatureWorkspaces.tsx"
    ).read_text(encoding="utf-8")
    assert "detail_rows" in ui_source
    assert "ledger_reconciled" in ui_source
    assert "실현손익" in ui_source
    assert "요약에는 청산 ${periodClosed}건" in ui_source


def test_report_excludes_future_rows_from_every_period(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, "
        "asset_type TEXT, pnl REAL, net_pnl REAL, fees REAL, exit_time DATETIME, "
        "reason TEXT, reconciliation_status TEXT)"
    )
    now = datetime.now().astimezone()
    rows = [
        (1, "BTCUSDT", "binance", "crypto", 2.0, 2.0, 0.1, now.isoformat(), "take_profit", "exchange_confirmed"),
        (2, "ETHUSDT", "binance", "crypto", 999.0, 999.0, 1.0, (now + timedelta(days=1)).isoformat(), "future_bad_row", "exchange_confirmed"),
    ]
    connection.executemany("INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()

    periods = AccountQueryService(str(db_path)).report_period_metrics(asset_class="crypto")["periods"]
    for key in ("today", "week", "month", "realtime"):
        assert periods[key]["closed_count"] == 1
        assert periods[key]["pnl_by_currency"] == {"USDT": pytest.approx(2.0)}


def test_report_detail_pages_reconcile_to_full_period_ledger(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, "
        "asset_type TEXT, side TEXT, pnl REAL, net_pnl REAL, pnl_percent REAL, fees REAL, "
        "entry_price REAL, exit_price REAL, quantity REAL, entry_time DATETIME, "
        "exit_time DATETIME, reason TEXT, reconciliation_status TEXT)"
    )
    now = datetime.now().astimezone().isoformat()
    connection.executemany(
        "INSERT INTO trade_log VALUES (?, 'BTCUSDT', 'binance', 'crypto', 'LONG', 1, 1, 1, .1, 100, 101, 1, ?, ?, 'take_profit', 'exchange_confirmed')",
        [(row_id, now, now) for row_id in range(1, 122)],
    )
    connection.commit()
    connection.close()

    service = AccountQueryService(str(db_path))
    first = service.report_period_metrics(
        asset_class="crypto", detail_period="today", detail_offset=0, detail_limit=100
    )["periods"]["today"]
    second = service.report_period_metrics(
        asset_class="crypto", detail_period="today", detail_offset=100, detail_limit=100
    )["periods"]["today"]
    assert first["closed_count"] == 121
    assert first["detail_total_count"] == 121
    assert len(first["detail_rows"]) == 100
    assert first["detail_has_more"] is True
    assert first["detail_checksum"]["pnl_by_currency"] == {"USDT": pytest.approx(121.0)}
    assert first["ledger_reconciled"] is True
    assert len(second["detail_rows"]) == 21
    assert second["detail_has_more"] is False


def test_report_treats_local_naive_and_explicit_utc_as_same_local_period(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, "
        "asset_type TEXT, pnl REAL, fees REAL, exit_time DATETIME, reason TEXT)"
    )
    local_now = datetime.now().astimezone().replace(microsecond=0)
    utc_same_instant = local_now.astimezone(timezone.utc)
    connection.executemany(
        "INSERT INTO trade_log VALUES (?, 'BTCUSDT', 'binance', 'crypto', 1, .1, ?, 'take_profit')",
        [(1, local_now.replace(tzinfo=None).isoformat(sep=" ")), (2, utc_same_instant.isoformat())],
    )
    connection.commit()
    connection.close()

    today = AccountQueryService(str(db_path)).report_period_metrics(asset_class="crypto")["periods"]["today"]
    assert today["closed_count"] == 2
    assert today["ledger_reconciled"] is True
