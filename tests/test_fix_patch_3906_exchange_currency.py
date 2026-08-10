import logging
import json
import sqlite3
from datetime import datetime

import pytest

from trading.recorder import Recorder
from trading.unified_trader import UnifiedTrader
from scripts.generate_champion_challenger_7d_report import generate_report
from utils.report_formatting import format_champion_challenger_section


def _insert_closed_trade(db_path, *, exchange, symbol, pnl, reason="strategy_close"):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_log (
                symbol, side, entry_price, exit_price, quantity, leverage,
                pnl, pnl_percent, reason, entry_time, exit_time, exchange
            ) VALUES (?, 'LONG', 100, 110, 1, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                pnl,
                pnl,
                reason,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                exchange,
            ),
        )


def test_recent_trades_supports_krw_and_ccxt_derivative_symbols(tmp_path):
    db_path = tmp_path / "trading.db"
    recorder = Recorder(db_path=str(db_path), log_path=str(tmp_path / "logs"))
    _insert_closed_trade(db_path, exchange="bithumb", symbol="H/KRW", pnl=112.0228)
    _insert_closed_trade(db_path, exchange="bybit", symbol="AVAX/USDT:USDT", pnl=1.25)
    _insert_closed_trade(db_path, exchange="bithumb", symbol="BTC/KRW", pnl=-10.0)

    bithumb_h = recorder.get_recent_trades(
        symbol="H/KRW", exchange="BITHUMB", days=30
    )
    bybit_avax = recorder.get_recent_trades(
        symbol="AVAX/USDT:USDT", exchange="bybit", days=30
    )
    all_bithumb = recorder.get_recent_trades(
        coin="", exchange="bithumb", days=30
    )

    assert [row["symbol"] for row in bithumb_h] == ["H/KRW"]
    assert [row["symbol"] for row in bybit_avax] == ["AVAX/USDT:USDT"]
    assert {row["symbol"] for row in all_bithumb} == {"H/KRW", "BTC/KRW"}


def test_legacy_binance_fill_import_is_not_a_completed_strategy_trade(tmp_path):
    db_path = tmp_path / "trading.db"
    recorder = Recorder(db_path=str(db_path), log_path=str(tmp_path / "logs"))
    _insert_closed_trade(
        db_path,
        exchange="binance",
        symbol="ETHUSDT",
        pnl=5.0,
        reason="binance_import",
    )
    _insert_closed_trade(
        db_path,
        exchange="binance",
        symbol="ETHUSDT",
        pnl=1.5,
        reason="strategy_close",
    )

    rows = recorder.get_recent_trades(
        symbol="ETHUSDT", exchange="binance", days=30
    )

    assert [row["pnl"] for row in rows] == [1.5]
    assert recorder.count_closed_trades(exchange="binance") == 1


def _bare_trader():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = logging.getLogger("test.v3906")
    return trader


def test_learning_store_does_not_require_nonexistent_closed_history():
    trader = _bare_trader()
    trader._get_recent_learning_entries_unified = lambda **_kwargs: [
        {
            "confidence": 0.5,
            "recent_trade_count": 0,
            "recent_win_rate": 0.0,
        }
        for _ in range(40)
    ]

    thresholds = trader._get_ai_learned_thresholds_unified(
        "upbit", "BTC/KRW"
    )

    assert thresholds["min_trades_history"] == 0
    assert thresholds["min_ai_confidence"] == 0.45


def test_learned_minimum_never_exceeds_observed_completed_history():
    trader = _bare_trader()
    trader._get_recent_learning_entries_unified = lambda **_kwargs: [
        {
            "confidence": 0.55,
            "recent_trade_count": 2,
            "recent_win_rate": 0.5,
        }
        for _ in range(40)
    ]

    thresholds = trader._get_ai_learned_thresholds_unified(
        "bybit", "AVAX/USDT:USDT"
    )

    assert thresholds["min_trades_history"] == 2


def test_missing_history_is_not_scored_as_zero_percent_win_rate():
    trader = _bare_trader()
    result = trader._ai_validate_entry_conditions_unified(
        "bithumb",
        "H/KRW",
        {"confidence": 0.5},
        {
            "loss_rate": 0.0,
            "win_rate": 0.0,
            "recent_trades": 0,
            "data_insufficient": True,
            "used_defaults": True,
        },
        {"volatility_suitable": True},
    )

    assert result["confidence"] == 0.6
    assert "낮은 승률" not in result["reasoning"]
    assert "초기 검증" in result["reasoning"]


def test_market_thresholds_do_not_create_a_cold_start_deadlock():
    trader = _bare_trader()
    trader._get_ai_learned_thresholds_unified = lambda *_args, **_kwargs: None

    thresholds = trader._get_dynamic_entry_thresholds_unified(
        "okx", "BTC/USDT:USDT", {"volatility": 0.03}
    )

    assert thresholds["min_trades_history"] == 0
    assert thresholds["min_ai_confidence"] == pytest.approx(0.6)


def test_champion_report_marks_mixed_currency_money_as_incomparable(tmp_path):
    db_path = tmp_path / "trading.db"
    Recorder(db_path=str(db_path), log_path=str(tmp_path / "logs"))
    _insert_closed_trade(db_path, exchange="binance", symbol="ETHUSDT", pnl=12.306272)
    _insert_closed_trade(db_path, exchange="bithumb", symbol="H/KRW", pnl=112.0228)
    _insert_closed_trade(
        db_path,
        exchange="binance",
        symbol="BTCUSDT",
        pnl=999.0,
        reason="binance_import",
    )

    json_path, _ = generate_report(db_path, tmp_path / "reports")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["challenger"]["mixed_currency"] is True
    assert payload["challenger"]["total_pnl"] is None
    assert payload["challenger"]["pnl_by_currency"] == {
        "USDT": 12.3063,
        "KRW": 112.0228,
    }
    assert payload["comparison"]["total_pnl_delta"] is None
    assert payload["comparison"]["verdict"] == "inconclusive_currency_boundary"


def test_ai_report_renders_currency_breakdown_without_cross_currency_sum(tmp_path):
    """리포트 모듈 import와 통화별 문장 조립을 함께 회귀 검증한다."""
    payload = {
        "champion": {
            "win_rate": 50.0,
            "pnl_by_currency": {"KRW": 1000.0, "USDT": 2.5},
        },
        "challenger": {
            "win_rate": 60.0,
            "pnl_by_currency": {"KRW": 1200.0, "USDT": 3.0},
        },
        "comparison": {
            "verdict": "inconclusive_currency_boundary",
            "summary": "결제통화별 손익을 분리해 비교합니다.",
            "win_rate_delta": 10.0,
            "total_pnl_delta": None,
            "trades_delta": 2,
        },
    }
    section = format_champion_challenger_section(payload)

    assert "금액 우열: 결제통화 경계로 비교 보류" in section
    assert "- KRW: 챔피언 +1000.0000 → 챌린저 +1200.0000" in section
    assert "- USDT: 챔피언 +2.5000 → 챌린저 +3.0000" in section
    assert "거래 수 변화: +2건" in section


def test_binance_history_import_only_writes_the_execution_ledger():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )
    start = source.index("    def _import_trading_stats_from_api(self):")
    end = source.index("    def _get_trading_stats_exchange_options", start)
    import_path = source[start:end]

    assert "save_exchange_execution_history" in import_path
    assert "TradeLog(" not in import_path
    assert "reason='binance_import'" not in import_path
