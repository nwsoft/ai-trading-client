import sqlite3
from pathlib import Path
from types import SimpleNamespace

from trading.recorder import Recorder
from trading.execution_views import format_execution_detail, load_execution_data
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from ui.refresh_lifecycle import schedule_visible_refresh


ROOT = Path(__file__).resolve().parents[1]


class _FakeOwner:
    def __init__(self, viewable=False):
        self.viewable = viewable
        self.bindings = {}

    def winfo_exists(self):
        return True

    def winfo_viewable(self):
        return self.viewable

    def bind(self, event, callback, add=None):
        self.bindings[event] = callback


class _FakeDashboard:
    def __init__(self):
        self._is_destroying = False
        self.after_jobs = []
        self.jobs = {}
        self._next_job = 0

    def winfo_exists(self):
        return True

    def safe_after(self, delay, callback):
        self._next_job += 1
        job_id = f"after-{self._next_job}"
        self.jobs[job_id] = (delay, callback)
        self.after_jobs.append(job_id)
        return job_id

    def after_cancel(self, job_id):
        self.jobs.pop(job_id, None)

    def run_job(self, job_id):
        _, callback = self.jobs.pop(job_id)
        if job_id in self.after_jobs:
            self.after_jobs.remove(job_id)
        callback()


def test_hidden_visible_refresh_keeps_a_liveness_retry_without_map_event():
    dashboard = _FakeDashboard()
    owner = _FakeOwner(viewable=False)
    calls = []

    schedule_visible_refresh(dashboard, owner, 100, lambda: calls.append("run"))
    first_job = next(iter(dashboard.jobs))
    dashboard.run_job(first_job)

    assert calls == []
    assert len(dashboard.jobs) == 1
    retry_job = next(iter(dashboard.jobs))
    assert dashboard.jobs[retry_job][0] == 2000

    # Windows/CTk에서 Map 이벤트가 누락되어도 자체 재확인으로 복구한다.
    owner.viewable = True
    dashboard.run_job(retry_job)
    assert calls == ["run"]


def test_startup_schema_migration_preserves_open_rows_and_exchange_identity(tmp_path):
    """Teayu DB 회귀: 시작 마이그레이션이 미청산 행을 삭제하면 안 된다."""
    db_path = tmp_path / "legacy-trading.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity REAL NOT NULL,
                leverage INTEGER NOT NULL,
                pnl REAL,
                pnl_percent REAL,
                reason TEXT,
                entry_time DATETIME NOT NULL,
                exit_time DATETIME,
                tp_price REAL,
                sl_price REAL,
                fees REAL DEFAULT 0,
                slippage REAL DEFAULT 0,
                exchange TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO trade_log (
                symbol, side, entry_price, exit_price, quantity, leverage,
                pnl, pnl_percent, reason, entry_time, exit_time, exchange
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RLC/KRW", "LONG", 400.0, None, 2.0, 1,
                    None, None, "entry", "2026-07-31 12:21:20", None, "bithumb",
                ),
                (
                    "ETHUSDT", "SHORT", 1882.0, 1880.0, 0.59, 50,
                    1.18, 0.1, "exit", "2026-07-31 12:20:00",
                    "2026-07-31 12:25:00", "binance",
                ),
            ],
        )

    recorder = Recorder(
        db_path=str(db_path),
        log_path=str(tmp_path / "logs"),
        exchange="binance",
    )
    rows_before = recorder.execute_query(
        "SELECT id, symbol, exit_time, exchange FROM trade_log ORDER BY id"
    )

    recorder.migrate_database_schema()
    recorder.migrate_database_schema()

    assert recorder.execute_query(
        "SELECT id, symbol, exit_time, exchange FROM trade_log ORDER BY id"
    ) == rows_before
    columns = {
        row[1] for row in recorder.execute_query("PRAGMA table_info(trade_log)")
    }
    assert {
        "exchange", "order_id", "exit_order_id", "model_version",
        "strategy_variant", "fee_asset", "fee_source",
    } <= columns


def test_startup_schema_failure_blocks_trading_initialization():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    block = source.split("# 데이터베이스 스키마 마이그레이션 실행", 1)[1].split(
        "# Analyzer 초기화", 1
    )[0]
    assert "거래 초기화 차단" in block
    assert "raise RuntimeError" in block
    assert "계속 진행" not in block


def test_unified_live_entry_creates_idempotent_trade_lifecycle_row(tmp_path, monkeypatch):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="bithumb",
    )
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.recorder = recorder
    trader.settings = {"default_leverage": 1, "default_tp": 0.01, "default_sl": 0.01}
    trader.logger = SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None)
    positions = {}
    trader._position_store = lambda exchange: positions
    monkeypatch.setattr(
        "trading.unified_trader.emit_position_opened",
        lambda **kwargs: (True, "position-1"),
    )

    order = {
        "order_id": "bithumb-entry-1",
        "price": 400.0,
        "filled": 2.0,
        "status": "closed",
    }
    trader._record_position_with_tp_sl(
        "bithumb", "RLC/KRW", "LONG", 2.0, order, {}, execution_mode="live"
    )
    trader._record_position_with_tp_sl(
        "bithumb", "RLC/KRW", "LONG", 2.0, order, {}, execution_mode="live"
    )

    assert recorder.execute_query(
        "SELECT exchange, order_id, symbol, exit_time FROM trade_log"
    ) == [("bithumb", "bithumb-entry-1", "RLC/KRW", None)]
    assert recorder.log_trade_exit(
        positions["RLC/KRW"],
        "test_exit",
        410.0,
        actual_trade_info={
            "exit_price": 410.0,
            "fees": 1.0,
            "slippage": 0.0,
            "quantity": 2.0,
        },
        exchange="bithumb",
        exit_order_id="bithumb-exit-1",
    )
    assert recorder.execute_query(
        "SELECT exit_time IS NOT NULL, exit_order_id, pnl FROM trade_log"
    ) == [(1, "bithumb-exit-1", 19.0)]


def test_native_binance_fill_is_written_to_common_execution_ledger(tmp_path):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="binance",
    )
    trader = Trader.__new__(Trader)
    trader.recorder = recorder
    trader.log_event = lambda *args, **kwargs: None

    assert trader._record_binance_execution(
        "ETHUSDT",
        "BUY",
        {
            "status": "FILLED",
            "order_id": "binance-fill-1",
            "avg_price": 2000.0,
            "executed_qty": 0.1,
            "cum_quote": 200.0,
        },
        source="test_entry",
    )
    assert recorder.execute_query(
        "SELECT exchange, order_id, symbol, side, cost FROM exchange_execution_log"
    ) == [("binance", "binance-fill-1", "ETHUSDT", "buy", 200.0)]


def test_ai_today_report_can_read_actual_fills_without_closed_pnl(tmp_path):
    recorder = Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "trading.log"),
        exchange="bithumb",
    )
    recorder.save_exchange_execution_history(
        "bithumb",
        [{
            "id": "fill-today-1",
            "order": "order-today-1",
            "symbol": "RLC/KRW",
            "side": "buy",
            "price": 400.0,
            "amount": 2.0,
            "cost": 800.0,
            "timestamp": 1785596400000,
            "status": "closed",
        }],
    )
    # 테스트 데이터 날짜를 실행일로 맞춘다.
    recorder.execute_query(
        "UPDATE exchange_execution_log SET executed_at = datetime('now', 'localtime')"
    )
    rows = load_execution_data(recorder.db_path, days=1, exchange="bithumb")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RLC/KRW"
    assert "실제 체결 내역" in format_execution_detail(rows)
