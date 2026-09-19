from types import SimpleNamespace

import scripts.runtime_soak_monitor as soak_monitor
from scripts.runtime_soak_monitor import (
    Sample,
    _percentile,
    evaluate_thresholds,
    poll_gateway,
    summarize_gateway,
)


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, *, headers, timeout):
        self.calls.append((url, headers, timeout))
        if url.endswith("/api/v1/runtime/snapshot"):
            return _Response({
                "running_sources": ["binance", "bybit"],
                "execution_modes": {"binance": "PAPER", "bybit": "PAPER"},
            })
        if url.endswith("/api/v1/settings"):
            return _Response({"fields": [{"path": "paper_trading"}]})
        if url.endswith("/api/v1/strategies"):
            return _Response({
                "strategies": [{"strategy_key": "trend", "versions": [{"version_id": "v1"}]}],
                "paper_outcomes": [{"event_id": "closed-1"}],
            })
        source = url.split("source=", 1)[1].split("&", 1)[0]
        return _Response({
            "execution_mode": "PAPER",
            "paper_positions_status": "success",
            "paper_positions": [{"symbol": f"{source.upper()}USDT", "custom_strategy_version_id": "v1"}],
            "paper_position_policy": {"mode": "multi", "limit": 3},
            "paper_statistics": {"closed_count": 7},
            "paper_trades": [{"event_id": "recent", "version_id": "v1"}],
            "active_custom_strategies": [{"name": "추세 따라가기 V1", "version_id": "v1"}],
        })


def test_process_metrics_aggregate_multiple_roots_and_children(monkeypatch):
    class Process:
        def __init__(self, pid, rss, threads, descriptors):
            self.pid = pid
            self._rss = rss
            self._threads = threads
            self._descriptors = descriptors

        def memory_info(self):
            return SimpleNamespace(rss=self._rss)

        def num_threads(self):
            return self._threads

        def num_fds(self):
            return self._descriptors

    processes = [
        Process(10, 100 * 1024 * 1024, 3, 5),
        Process(11, 50 * 1024 * 1024, 2, 7),
    ]
    monkeypatch.setattr(soak_monitor, "_processes_for_roots", lambda roots: processes)

    assert soak_monitor._read_rss_mb(10, (20,)) == 150.0
    assert soak_monitor._read_threads(10, (20,)) == 5
    assert soak_monitor._read_open_fds(10, (20,)) == 12


def test_gateway_soak_poll_collects_runtime_and_source_paper_contract_without_secret():
    session = _Session()
    token = "t" * 36

    result = poll_gateway(
        session,
        base_url="http://127.0.0.1:3910/",
        token=token,
        sources=("binance", "bybit"),
        timeout_sec=12,
    )

    assert result["runtime"]["execution_modes"] == {"binance": "PAPER", "bybit": "PAPER"}
    assert result["workspaces"]["binance"]["paper_position_count"] == 1
    assert result["workspaces"]["bybit"]["paper_position_limit"] == 3
    assert result["control_surfaces"]["settings"]["field_count"] == 1
    assert result["control_surfaces"]["ai_custom"]["version_count"] == 1
    assert result["workspaces"]["binance"]["active_custom_strategy_versions"] == ["v1"]
    assert result["workspaces"]["binance"]["paper_position_strategy_versions"] == ["v1"]
    assert all(call[1]["Authorization"] == f"Bearer {token}" for call in session.calls)
    assert token not in str(result)


def test_gateway_soak_summary_and_thresholds_fail_closed_for_latency_mode_and_limit():
    samples = [
        Sample(
            ts="2026-08-24T00:00:00", elapsed_sec=index, rss_mb=100 + index,
            threads=10, open_fds=20,
            gateway={
                "runtime": {
                    "ok": True, "latency_ms": 25 + index,
                    "running_sources": ["binance"],
                    "execution_modes": {"binance": "PAPER"},
                },
                "control_surfaces": {
                    "settings": {"ok": True, "latency_ms": 350 + index * 100},
                    "ai_custom": {"ok": index == 0, "latency_ms": 100},
                },
                "workspaces": {
                    "binance": {
                        "ok": True,
                        "latency_ms": 250 + index * 100,
                        "execution_mode": "LIVE" if index else "PAPER",
                        "paper_position_limit": 1,
                        "paper_position_count": 2,
                        "paper_positions_status": "success",
                    },
                },
            },
        )
        for index in range(2)
    ]
    summary = summarize_gateway(samples, ("binance",))
    failures = evaluate_thresholds(
        rss_growth=1,
        thread_growth=0,
        fd_growth=0,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=True,
    )

    assert summary["runtime"]["success_count"] == 2
    assert "binance" in summary["paper_mode_mismatches"]
    assert any(row.startswith("workspace_p95_exceeded:binance") for row in failures)
    assert any(row.startswith("control_surface_p95_exceeded:settings") for row in failures)
    assert "control_surface_failures:ai_custom:1" in failures
    assert "workspace_paper_mode_mismatch:binance:1_samples" in failures
    assert "paper_position_limit_exceeded:binance:2>1" in failures


def test_gateway_soak_thresholds_pass_for_bounded_paper_run():
    sample = Sample(
        ts="2026-08-24T00:00:00", elapsed_sec=0, rss_mb=100,
        threads=10, open_fds=20,
        gateway={
            "runtime": {
                "ok": True, "latency_ms": 40,
                "running_sources": ["binance"],
                "execution_modes": {"binance": "PAPER"},
            },
            "workspaces": {
                "binance": {
                    "ok": True, "latency_ms": 80, "execution_mode": "PAPER",
                    "paper_position_limit": 3, "paper_position_count": 2,
                    "paper_positions_status": "success",
                },
            },
        },
    )
    summary = summarize_gateway([sample], ("binance",))
    assert evaluate_thresholds(
        rss_growth=12,
        thread_growth=1,
        fd_growth=2,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=True,
    ) == []
    assert _percentile([10, 20, 30, 40], 95) == 38.5


def test_gateway_soak_does_not_force_fail_legacy_positions_above_new_cap():
    sample = Sample(
        ts="2026-08-24T00:00:00", elapsed_sec=0, rss_mb=100,
        threads=10, open_fds=20,
        gateway={
            "runtime": {
                "ok": True, "latency_ms": 40,
                "running_sources": ["binance"],
                "execution_modes": {"binance": "PAPER"},
            },
            "workspaces": {
                "binance": {
                    "ok": True, "latency_ms": 80, "execution_mode": "PAPER",
                    "paper_position_limit": 3, "paper_position_count": 6,
                    "paper_positions_status": "success",
                },
            },
        },
    )
    summary = summarize_gateway([sample], ("binance",))
    failures = evaluate_thresholds(
        rss_growth=0,
        thread_growth=0,
        fd_growth=0,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=False,
    )

    assert failures == []


def test_gateway_soak_requires_running_paper_source_and_available_position_state():
    sample = Sample(
        ts="2026-08-24T00:00:00", elapsed_sec=0, rss_mb=100,
        threads=10, open_fds=20,
        gateway={
            "runtime": {
                "ok": True, "latency_ms": 40,
                "running_sources": [],
                "execution_modes": {"binance": "LIVE"},
            },
            "workspaces": {
                "binance": {
                    "ok": True, "latency_ms": 80, "execution_mode": "PAPER",
                    "paper_position_limit": 3, "paper_position_count": 0,
                    "paper_positions_status": "unavailable",
                },
            },
        },
    )
    summary = summarize_gateway([sample], ("binance",))
    failures = evaluate_thresholds(
        rss_growth=0,
        thread_growth=0,
        fd_growth=0,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=False,
    )

    assert "paper_source_not_running:binance:1_samples" in failures
    assert "runtime_paper_mode_mismatch:binance:1_samples" in failures
    assert "paper_position_status_failure:binance:1_samples" in failures


def test_gateway_soak_checks_expected_policy_instead_of_trusting_reported_cap():
    sample = Sample(
        ts="2026-08-24T00:00:00", elapsed_sec=0, rss_mb=100,
        threads=10, open_fds=20,
        gateway={
            "runtime": {
                "ok": True, "latency_ms": 40,
                "running_sources": ["binance"],
                "execution_modes": {"binance": "PAPER"},
            },
            "workspaces": {
                "binance": {
                    "ok": True, "latency_ms": 80, "execution_mode": "PAPER",
                    "paper_position_mode": "multi",
                    "paper_position_limit": 6, "paper_position_count": 4,
                    "paper_positions_status": "success",
                },
            },
        },
    )
    summary = summarize_gateway([sample], ("binance",))
    failures = evaluate_thresholds(
        rss_growth=0,
        thread_growth=0,
        fd_growth=0,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=True,
        expected_position_mode="multi",
        expected_position_limit=3,
    )

    assert "paper_position_limit_mismatch:binance:6!=3" in failures
    assert "paper_position_limit_exceeded:binance:4>3" in failures


def test_gateway_soak_requires_expected_active_version_and_paper_attribution():
    sample = Sample(
        ts="2026-08-24T00:00:00", elapsed_sec=0, rss_mb=100,
        threads=10, open_fds=20,
        gateway={
            "runtime": {
                "ok": True, "latency_ms": 40,
                "running_sources": ["binance"],
                "execution_modes": {"binance": "PAPER"},
            },
            "workspaces": {
                "binance": {
                    "ok": True, "latency_ms": 80, "execution_mode": "PAPER",
                    "paper_position_mode": "multi", "paper_position_limit": 3,
                    "paper_position_count": 1, "paper_positions_status": "success",
                    "active_custom_strategy_count": 1,
                    "active_custom_strategy_versions": ["v1"],
                    "active_custom_strategy_names": ["추세 따라가기 V1"],
                    "paper_position_strategy_versions": ["v1"],
                    "paper_trade_strategy_versions": [],
                },
            },
        },
    )
    summary = summarize_gateway([sample], ("binance",))
    common = dict(
        rss_growth=0,
        thread_growth=0,
        fd_growth=0,
        gateway_summary=summary,
        sources=("binance",),
        max_rss_growth_mb=512,
        max_thread_growth=32,
        max_fd_growth=64,
        runtime_p95_ms=150,
        workspace_p95_ms=300,
        require_paper=True,
        enforce_position_limit=True,
        require_active_custom_strategy=True,
        require_paper_attribution=True,
    )

    assert evaluate_thresholds(**common, expected_strategy_version="v1") == []
    failures = evaluate_thresholds(**common, expected_strategy_version="v2")
    assert "expected_strategy_version_missing:binance:v2:1_samples" in failures
    assert "expected_strategy_paper_attribution_missing:binance:v2" in failures
