from __future__ import annotations

import json
from pathlib import Path

from config.diff_engine import compute_settings_diff
from utils import runtime_stability


def test_settings_diff_does_not_restart_trading_for_ui_only_change() -> None:
    old = {
        "enabled_exchanges": ["binance", "upbit"],
        "paper_trading": True,
        "ui_settings": {"always_on_top": False},
    }
    new = {
        **old,
        "ui_settings": {"always_on_top": True},
    }

    plan = compute_settings_diff(old, new)

    assert plan["changed_keys"] == {"ui_settings"}
    assert plan["trading_changed"] is False
    assert plan["exchanges_changed"] is False


def test_settings_module_installs_windows_menu_guard_before_customtkinter() -> None:
    path = Path(__file__).resolve().parents[1] / "ui" / "settings_modern.py"
    source = path.read_text(encoding="utf-8")

    assert source.index("install_windows_menu_guard()") < source.index(
        "import customtkinter as ctk"
    )


def test_dashboard_keeps_only_selected_source_tree_active() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "ui" / "dashboard_modern.py"
    ).read_text(encoding="utf-8")
    ensure_source = source[
        source.index("    def _ensure_active_source_tab("):
        source.index("    def _build_source_tab_content(")
    ]
    build_source = source[
        source.index("    def _build_source_tab_content("):
        source.index("    def _get_service_split_layout(")
    ]

    assert "self._clear_tab_children(previous_frame)" in ensure_source
    assert "self._active_source_tab_by_service[service_name] = tab_label" in ensure_source
    assert "service_tab_partial_render:" in ensure_source
    assert "create_exchange_logs_section" in build_source
    assert "create_broker_logs_section" in build_source


def test_parallel_runtime_lock_is_atomic_and_released(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime_stability, "_runtime_dir", lambda: tmp_path)
    runtime_stability._SESSION_MARKER = None
    runtime_stability._INSTANCE_MARKER = None
    runtime_stability._CRASH_LOG = None
    runtime_stability._FATAL_EXCEPTION_SEEN = False

    lock = tmp_path / "runtime_instance.lock"
    lock.write_text(
        json.dumps({"pid": 98765, "started_at": "2026-08-12T00:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_stability,
        "_process_is_running",
        lambda pid: int(pid) == 98765,
    )

    result = runtime_stability.begin_runtime_session()

    assert result["parallel_session"] is True
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == 98765


def test_binance_subscription_entrypoints_are_singleflight() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "api" / "binance_client.py"
    ).read_text(encoding="utf-8")
    sender = source[
        source.index("    def _send_ws_message("):
        source.index("    def start_ticker_socket(")
    ]
    ticker = source[
        source.index("    def start_ticker_socket("):
        source.index("    def _start_ticker_socket_singleflight(")
    ]
    orderbook = source[
        source.index("    def start_orderbook_socket("):
        source.index("    def _start_orderbook_socket_singleflight(")
    ]

    assert "with self._subscription_lock_for(symbol)" in ticker
    assert "with self._subscription_lock_for(symbol)" in orderbook
    assert "with self.lock" in sender
    assert "ws.send" in sender
