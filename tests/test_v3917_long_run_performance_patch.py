import json
import sqlite3
import threading
import time
from pathlib import Path

from web_platform.application_services import ApplicationServices
from web_platform.query_services import AccountQueryService


ROOT = Path(__file__).resolve().parents[1]


class BlockingAccountBridge:
    def __init__(self):
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def account_snapshot(self, *, sources, force_refresh=False):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=2)
        return {
            "schema_version": "1.0.0",
            "sources": {source: {"source": source, "status": "success"} for source in sources},
            "requested_sources": list(sources),
            "fresh": True,
        }


def test_slow_account_refresh_does_not_hold_settings_lock(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    bridge = BlockingAccountBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **_kwargs: {})
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    worker = threading.Thread(
        target=lambda: services.refresh_account_snapshot(sources=["binance"]), daemon=True,
    )
    worker.start()
    assert bridge.entered.wait(timeout=1)
    started = time.perf_counter()
    snapshot = services.settings_snapshot()
    catalog = services.strategy_catalog()
    elapsed = time.perf_counter() - started
    bridge.release.set()
    worker.join(timeout=1)

    assert snapshot["account_scope"] == "tester"
    assert "strategies" in catalog
    assert elapsed < 0.25


def test_duplicate_account_refreshes_join_one_provider_call(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    bridge = BlockingAccountBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    services = ApplicationServices(account="tester", runtime_bridge=bridge)
    results = []
    workers = [
        threading.Thread(
            target=lambda: results.append(services.refresh_account_snapshot(sources=["binance"])),
            daemon=True,
        )
        for _ in range(2)
    ]
    workers[0].start()
    assert bridge.entered.wait(timeout=1)
    workers[1].start()
    time.sleep(0.05)
    bridge.release.set()
    for worker in workers:
        worker.join(timeout=1)

    assert bridge.calls == 1
    assert len(results) == 2
    assert all(result["sources"]["binance"]["status"] == "success" for result in results)


def test_duplicate_membership_polls_use_one_server_request(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    entered = threading.Event()
    release = threading.Event()
    calls = 0

    class Response:
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {"is_active": True, "force_quit": False}

    def blocking_post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return Response()

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(service_module.requests, "post", blocking_post)
    (tmp_path / "token.json").write_text(json.dumps({"access_token": "test-token"}), encoding="utf-8")
    services = ApplicationServices(account="tester", runtime_bridge=BlockingAccountBridge())
    services.session_user = {"session_id": "session-1", "membership_policy": {}}

    owner = threading.Thread(target=services.refresh_membership_status, daemon=True)
    owner.start()
    assert entered.wait(timeout=1)
    started = time.perf_counter()
    cached = services.refresh_membership_status()
    elapsed = time.perf_counter() - started
    release.set()
    owner.join(timeout=1)

    assert calls == 1
    assert elapsed < 0.25
    assert cached["status"] == "not_checked"


def test_operational_kpi_is_not_capped_at_two_hundred(tmp_path):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE trade_log (
                symbol TEXT, exchange TEXT, pnl REAL, net_pnl REAL, entry_time TEXT,
                exit_time TEXT, reason TEXT, reconciliation_status TEXT
            )"""
        )
        connection.executemany(
            "INSERT INTO trade_log VALUES ('BTCUSDT', 'binance', ?, ?, '2026-08-23 10:00:00', ?, 'close', 'exchange_confirmed')",
            [(value, value, f"2026-08-23 10:{index % 60:02d}:{index % 60:02d}") for index in range(250) for value in [1 if index < 150 else -1]],
        )
        connection.execute(
            "CREATE TABLE exchange_trade_stats (exchange TEXT, total_trades INTEGER, winning_trades INTEGER, total_pnl REAL)"
        )
        connection.execute("INSERT INTO exchange_trade_stats VALUES ('binance', 250, 150, 50)")

    overview = AccountQueryService(str(db_path)).trading_overview(asset_class="crypto")

    assert overview["closed_count"] == 250
    assert overview["win_rate"] == 60.0
    assert overview["pnl_by_currency"] == {"USDT": 50.0}
    assert len(overview["recent_trades"]) == 50


def test_read_only_query_connection_is_explicitly_closed(tmp_path, monkeypatch):
    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE trade_log (id INTEGER, symbol TEXT)")
        connection.execute("INSERT INTO trade_log VALUES (1, 'BTCUSDT')")

    service = AccountQueryService(str(db_path))
    real_connection = service._connect()

    class TrackedConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def close(self):
            self.closed = True
            self.connection.close()

    tracked = TrackedConnection(real_connection)
    monkeypatch.setattr(service, "_connect", lambda: tracked)

    assert service.table_rows("trade_log", limit=1)[0]["symbol"] == "BTCUSDT"
    assert tracked.closed is True


def test_trade_history_helper_connection_is_explicitly_closed(tmp_path, monkeypatch):
    import web_platform.asset_insight_data as insight_module

    db_path = tmp_path / "trading.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_log (symbol TEXT, pnl REAL, entry_time TEXT, exit_time TEXT)"
        )
        connection.execute(
            "INSERT INTO trade_log VALUES ('BTCUSDT', 1, '2026-08-24', '2026-08-25')"
        )

    real_connection = sqlite3.connect(db_path)

    class TrackedConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def close(self):
            self.closed = True
            self.connection.close()

    tracked = TrackedConnection(real_connection)
    monkeypatch.setattr(insight_module.sqlite3, "connect", lambda _path: tracked)

    loaded = insight_module.load_closed_trade_records(str(db_path), limit=1)

    assert loaded["schema_compatible"] is True
    assert tracked.closed is True


def test_all_web_read_only_sqlite_contexts_close_connections():
    query_source = (ROOT / "web_platform" / "query_services.py").read_text(encoding="utf-8")
    insight_source = (ROOT / "web_platform" / "asset_insight_data.py").read_text(encoding="utf-8")

    assert "with self._connect() as connection" not in query_source
    # v3.9.1.13 adds one bounded read for the newest source-scoped coin
    # selection session; it must follow the same explicit-close contract.
    # Broker learning now has its own explicitly closed, read-only DB query.
    assert query_source.count("with closing(self._connect()) as connection") == 8
    assert "with sqlite3.connect(db_path) as connection" not in insight_source
    assert "with closing(sqlite3.connect(db_path)) as connection" in insight_source


def test_web_network_pollers_are_completion_based():
    sources = [
        ROOT / "webui" / "src" / "App.tsx",
        ROOT / "webui" / "src" / "components" / "Operations.tsx",
        ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx",
        ROOT / "webui" / "src" / "components" / "AlphaArenaWorkspace.tsx",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    scheduler = (ROOT / "webui" / "src" / "sequentialPoll.ts").read_text(encoding="utf-8")

    assert combined.count("setInterval(") == 1  # display clock only
    assert combined.count("startSequentialPoll(") >= 6
    assert "await task()" in scheduler
    assert scheduler.index("await task()") < scheduler.index("schedule();", scheduler.index("await task()"))


def test_current_release_is_pending_windows_and_soak_gates():
    from config.app_version import RELEASE_VERSION

    manifest = json.loads((ROOT / "deploy" / "release-manifest.json").read_text(encoding="utf-8"))
    assert tuple(map(int, manifest["version"].split("."))) <= tuple(map(int, RELEASE_VERSION.split(".")))
    major, minor, patch, revision = (int(part) for part in manifest["version"].split("."))
    assert manifest["update_contract"]["updater_semver"] == f"{major}.{minor}.{patch * 100 + revision}"
    assert manifest["build_status"] in {
        "pending_windows_rebuild", "built_windows_unverified", "windows_external_gates_pending", "windows_stable_external_gates_pending", "windows_verified_release_candidate",
    }
    if manifest["build_status"] == "pending_windows_rebuild":
        assert manifest["publish_ready"] is False
        assert not manifest["assets"]["installer"]["sha256"]
    else:
        assert len(manifest.get("source_fingerprint") or "") == 64
        assert len(manifest["assets"]["installer"]["sha256"]) == 64
