from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from log_system.log_stream import get_log_stream
from web_platform.application_services import ApplicationServices, DetachedRuntimeBridge
from web_platform.headless_runtime import HeadlessTradingRuntime


def test_source_log_uses_live_exchange_stream_when_source_file_is_stale(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    source_path = log_dir / "trading_bitget.log"
    source_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "web_platform.application_services.get_exchange_log_file_path",
        lambda source: str(log_dir / f"trading_{source}.log"),
    )
    marker = f"web-source-stream-{time.time_ns()}"
    stream = get_log_stream()
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    event = stream.add_event("bitget", "INFO", "analysis", marker)
    try:
        snapshot = services.log_snapshot(service="blockchain", source="bitget", lines=50)

        assert any(marker in row["message"] for row in snapshot["lines"])
        assert all("(ex=bitget)" in row["message"] for row in snapshot["lines"] if marker in row["message"])
    finally:
        with stream._lock:
            try:
                stream._buf.remove(event)
            except ValueError:
                pass


class _ConcurrentRuntimeBridge:
    def __init__(self):
        self.started: list[str] = []

    def execute(self, command, payload):
        assert command == "trading.start"
        time.sleep(0.2)
        source = str(payload["source"])
        self.started.append(source)
        return {"source": source, "command": command, "running_sources": []}

    def snapshot(self):
        return {"running_sources": []}


def test_unrelated_exchange_commands_are_not_serialized_by_application_lock(tmp_path, monkeypatch):
    bridge = _ConcurrentRuntimeBridge()
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    services.audit_path = Path(tmp_path) / "audit.jsonl"
    monkeypatch.setattr(services, "_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("web_platform.application_services.load_settings", lambda **_kwargs: {"paper_trading": True})

    def start(source: str):
        return services.execute_runtime_command(
            command_id=f"command-{source}-1234567890",
            command="trading.start",
            payload={"source": source, "close_all": False},
        )

    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(start, ["upbit", "bybit"]))
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.35
    assert set(bridge.started) == {"upbit", "bybit"}
    assert all(result["accepted"] is True for result in results)


def test_runtime_excludes_dead_unified_workers_even_when_old_flag_remains_true():
    class _Thread:
        def __init__(self, alive: bool):
            self.alive = alive

        def is_alive(self):
            return self.alive

    class _Unified:
        monitoring_flags = {"upbit": True, "bybit": True}
        monitoring_threads = {"upbit": _Thread(False), "bybit": _Thread(True)}

    runtime = HeadlessTradingRuntime.__new__(HeadlessTradingRuntime)
    runtime.trading_worker = None
    runtime.trading_thread = None
    runtime.unified_trader = _Unified()

    assert runtime.running_crypto_exchanges() == ["bybit"]


def test_web_source_workspace_polls_logs_and_separates_account_and_command_busy_state():
    source = Path("webui/src/components/LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    app = Path("webui/src/App.tsx").read_text(encoding="utf-8")

    assert "const [accountBusy, setAccountBusy]" in source
    assert "const [commandBusy, setCommandBusy]" in source
    assert "client.logs(service, source, 200)" in source
    assert "startSequentialPoll(loadLogs, 1_000)" in source
    assert "startSequentialPoll(loadWorkspace, 5_000)" in source
    assert "startSequentialPoll(refresh, 2_000" in app
    assert "onRuntimeChanged={refreshRuntimeFromSettings}" in app
    operations = Path("webui/src/components/Operations.tsx").read_text(encoding="utf-8")
    assert "Promise.allSettled" in operations
    assert "설정 대상 전체 시작" in operations
