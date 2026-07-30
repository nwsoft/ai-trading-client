from datetime import datetime, timedelta, timezone

from trading.trader import _as_utc, _elapsed_milliseconds, _elapsed_minutes
from utils import perf_metrics_logger


def test_elapsed_time_accepts_legacy_naive_datetime():
    legacy_timestamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=3)
    elapsed = _elapsed_minutes(legacy_timestamp)
    assert 2.9 <= elapsed <= 3.1


def test_elapsed_time_accepts_timezone_aware_datetime():
    aware_timestamp = datetime.now(timezone(timedelta(hours=9))) - timedelta(seconds=2)
    assert 0.0 <= _elapsed_minutes(aware_timestamp) < 1.0
    assert 1000 <= _elapsed_milliseconds(aware_timestamp) < 10_000
    assert _as_utc(aware_timestamp).tzinfo == timezone.utc


def test_ui_perf_log_rotates_before_unbounded_growth(tmp_path, monkeypatch):
    log_path = tmp_path / "ui_perf_metrics.jsonl"
    log_path.write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(perf_metrics_logger, "_MAX_LOG_BYTES", 110)

    perf_metrics_logger._rotate_if_needed(str(log_path), incoming_bytes=20)

    assert not log_path.exists()
    assert (tmp_path / "ui_perf_metrics.jsonl.1").exists()
