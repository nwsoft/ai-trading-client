from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_financial_intelligence_does_not_idle_poll_hidden_tab():
    source = (ROOT / "ui" / "widgets" / "financial_intelligence_widget.py").read_text(encoding="utf-8")
    assert "if self._cleaned_up or self._async_poll_id is not None or not self._is_visible_now()" in source
    assert "if workers_active or not self._async_results.empty()" in source
    assert "self._async_poll_id = self.after(50, self._poll_async_results)" not in source


def test_dashboard_recursively_cleans_owned_widget_jobs():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    cleanup = source.split("def cleanup_all_widgets", 1)[1].split("def update_status_info", 1)[0]
    assert "cleanup_widget_tree(self)" in cleanup
    assert '("cleanup_after_jobs", "_cancel_after_jobs", "cleanup")' in cleanup
    assert "self.tk.call('after', 'cancel', 'all')" not in source


def test_exchange_and_broker_sections_refresh_only_while_visible():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    lifecycle = (ROOT / "ui" / "refresh_lifecycle.py").read_text(encoding="utf-8")
    assert "def _schedule_visible_refresh" in source
    assert "def _run_visible_refresh_async" in source
    assert 'owner_widget.bind("<Map>", _on_map, add="+")' in lifecycle
    assert 'owner_widget.bind("<Unmap>", _on_unmap, add="+")' in lifecycle
    assert "not owner_widget.winfo_viewable()" in lifecycle
    assert '"hidden_retry_ms": 2000' in lifecycle
    assert 'f"exchange_balance:{exchange}"' in source
    assert 'f"exchange_positions:{exchange}"' in source
    assert 'f"broker_positions:{broker}"' in source
    assert 'name=f"dashboard_refresh_{key}"' in source
    assert "queue.Queue(maxsize=1024)" in source
    assert "self._global_async_refresh_registry" in source
    assert 'coalesce_key=f"async_refresh_apply:{key}"' in source
    timeout_block = source.split("def _timeout():", 1)[1].split("def _worker():", 1)[0]
    assert 'state["running"] = False' in timeout_block
    assert 'state["generation"] = generation + 1' in timeout_block
    assert "thread_safe_after(7000, refresh_once)" not in source
    assert "thread_safe_after(5000, refresh_once)" not in source
    assert "thread_safe_after(3000, refresh_once)" not in source


def test_safe_report_fallback_owns_and_cancels_callbacks():
    source = (ROOT / "ui" / "widgets" / "ai_report_widget_safe.py").read_text(encoding="utf-8")
    assert "def cleanup_after_jobs" in source
    assert 'self.bind("<Unmap>", self._on_unmap_hidden, add="+")' in source
    assert "self._safe_after(100, self._generate_reports_async)" in source
    assert "self.after(100, self._generate_reports_async)" not in source


def test_recurring_widgets_remove_completed_job_ids_and_cleanup_on_destroy():
    for relative in (
        "ui/widgets/ai_learning_widget.py",
        "ui/widgets/ai_report_widget.py",
        "ui/widgets/market_trend_widget.py",
        "ui/widgets/realtime_log_widget.py",
        "ui/widgets/life_finance_widget.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "after_cancel" in source
        assert "def destroy" in source or "<Destroy>" in source
