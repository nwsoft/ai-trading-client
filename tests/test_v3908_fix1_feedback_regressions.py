import sqlite3
import threading
from pathlib import Path

from ui.asset_insight_data import (
    AssetSnapshotStore,
    load_closed_trade_records,
    load_trade_history_metrics,
    normalize_current_balances,
)
from ui.service_tab_policy import get_service_protected_tabs, get_service_tab_order


ROOT = Path(__file__).resolve().parents[1]


def test_current_asset_balance_uses_account_snapshot_not_trade_notional():
    metrics = normalize_current_balances(
        {"binance_futures": {"USDT": 198.8222, "BTC": 0.0}},
        {},
    )

    assert metrics["has_current_data"] is True
    assert metrics["comparable_currency"] == "USDT"
    assert metrics["total_assets"] == 198.8222
    assert metrics["asset_breakdown"]["암호화폐"] == 198.8222


def test_current_asset_balance_does_not_add_krw_and_usdt():
    metrics = normalize_current_balances(
        {"binance_futures": {"USDT": 200.0}},
        {"kiwoom": {"status": "ok", "total_assets": 5_000_000}},
    )

    assert metrics["currency_totals"] == {"USDT": 200.0, "KRW": 5_000_000.0}
    assert metrics["allocation_comparable"] is False
    assert metrics["total_assets"] == 0.0


def test_asset_snapshot_store_is_one_thread_safe_current_balance_source():
    store = AssetSnapshotStore()

    threads = [
        threading.Thread(target=store.update, args=(f"binance_{index}", {"USDT": index + 1}))
        for index in range(20)
    ]
    threads.append(threading.Thread(target=store.update, args=("kiwoom", {"total_assets": 1000})))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = store.snapshot()
    assert len(snapshot["crypto"]) == 20
    assert snapshot["stock"]["kiwoom"]["total_assets"] == 1000
    assert snapshot["updated_at"]


def test_legacy_trade_db_without_asset_type_or_entry_amount_is_readable(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_log (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                pnl REAL,
                reason TEXT,
                exchange TEXT,
                entry_time TEXT NOT NULL,
                exit_time TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO trade_log(symbol, pnl, reason, exchange, entry_time, exit_time) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("BTCUSDT", 3.5, "자동청산", None, "2026-08-01 00:00:00", "2026-08-01 01:00:00"),
                ("ETHUSDT", -1.0, "자동청산", "binance", "2026-08-02 00:00:00", "2026-08-02 01:00:00"),
            ],
        )

    metrics = load_trade_history_metrics(str(db_path))

    assert metrics["schema_compatible"] is True
    assert metrics["closed_count"] == 2
    assert metrics["pnl_by_currency"]["USDT"] == 2.5
    assert metrics["pnl_by_asset_currency"]["crypto"]["USDT"] == 2.5

    records = load_closed_trade_records(str(db_path), asset_class="crypto")
    assert records["schema_compatible"] is True
    assert len(records["records"]) == 2
    assert all(row["notional"] == 0.0 for row in records["records"])


def test_ai_analyst_policy_keeps_assistant_owned_tab_alive():
    protected = get_service_protected_tabs("ai_analyst")
    order = get_service_tab_order("ai_analyst")

    assert "AI 어시스턴트" in protected
    assert order[:2] == ["AI 애널리스트", "AI 어시스턴트"]


def test_live_assistant_resolver_recreates_stale_cached_widget():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    body = source[source.index("    def _get_live_ai_assistant"):source.index("    def _ensure_custom_strategy_tab")]

    assert "self._widget_alive(assistant) and self._widget_alive(chat_input)" in body
    assert '_invalidate_tab_widget_reference("AI 어시스턴트")' in body
    assert "self._ensure_ai_assistant_tab()" in body


def test_quick_question_refuses_destroyed_tcl_input():
    source = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")
    body = source[source.index("    def send_quick_question"):source.index("    def update_model_caption")]

    assert "not self.winfo_exists() or not self.chat_input.winfo_exists()" in body
    assert "return False" in body
    assert "return True" in body


def test_assistant_request_is_written_to_bottom_history_contract():
    dashboard = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    assistant = (ROOT / "ui" / "widgets" / "ai_assistant_widget.py").read_text(encoding="utf-8")

    record_body = dashboard[
        dashboard.index("    def _record_ai_assistant_request"):
        dashboard.index("    def _refresh_ai_execute_summary_card")
    ]
    send_body = assistant[
        assistant.index("    def send_ai_message"):
        assistant.index("    def _current_strategy_engine_policy")
    ]
    support_body = assistant[
        assistant.index("    def _build_fix1_feedback_support"):
        assistant.index("    def _build_multi_venue_support")
    ]

    assert "AI 애널리스트 심층분석" in record_body
    assert "result='응답 생성 중'" in record_body
    assert "status='running'" in record_body
    assert "def _finish_ai_assistant_request" in record_body
    assert "_record_ai_assistant_request" in send_body
    assert "_active_ai_activity_id" in send_body
    assert "현재 잔고" in support_body
    assert "AI 실행 기록" in support_body


def test_ai_activity_keeps_request_and_completion_in_one_event():
    from ui.ai_activity import AIActivityLedger

    ledger = AIActivityLedger(max_size=30)
    event_id = ledger.record(
        action="ai_analysis_request",
        title="AI 애널리스트 심층분석",
        plan_lines=["현재 위험을 분석해줘"],
        risk_level="normal",
        risk_reasons=[],
        result="응답 생성 중",
        status="running",
    )

    assert len(ledger.events) == 1
    assert ledger.events[0]["id"] == event_id
    assert ledger.events[0]["status"] == "running"
    assert ledger.finish(event_id, result="응답 완료") is True
    assert len(ledger.events) == 1
    assert ledger.events[0]["status"] == "completed"
