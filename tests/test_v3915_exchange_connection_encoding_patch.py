import json
from copy import deepcopy
from pathlib import Path

import pytest

from web_platform.application_services import ApplicationServices


ROOT = Path(__file__).resolve().parents[1]


CRYPTO_CREDENTIALS = {
    "binance": ({"api_key": "binance-key", "secret_key": "binance-secret"}, ("binance_api_key", "binance_secret_key")),
    "upbit": ({"api_key": "upbit-key", "secret_key": "upbit-secret"}, ("upbit_api_key", "upbit_secret_key")),
    "bithumb": ({"api_key": "bithumb-key", "secret_key": "bithumb-secret"}, ("bithumb_api_key", "bithumb_secret_key")),
    "bybit": ({"api_key": "bybit-key", "secret_key": "bybit-secret"}, ("bybit_api_key", "bybit_secret_key")),
    "okx": ({"api_key": "okx-key", "secret_key": "okx-secret", "passphrase": "okx-pass"}, ("okx_api_key", "okx_secret_key", "okx_passphrase")),
    "bitget": ({"api_key": "bitget-key", "secret_key": "bitget-secret", "password": "bitget-pass"}, ("bitget_api_key", "bitget_secret_key", "bitget_password")),
}


def _write_path(target, path, value):
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = deepcopy(value)


class RecordingBridge:
    def __init__(self):
        self.settings = {}
        self.queried = []

    def refresh_settings(self, settings):
        self.settings = deepcopy(settings)

    def account_snapshot(self, *, sources, force_refresh=False):
        self.queried.extend(sources)
        results = {}
        for source in sources:
            _, stored_fields = CRYPTO_CREDENTIALS[source]
            assert all(self.settings.get(field) for field in stored_fields)
            results[source] = {"source": source, "status": "success", "balance": {}}
        return {
            "schema_version": "1.0.0",
            "sources": results,
            "requested_sources": list(sources),
            "fresh": True,
        }


def test_all_crypto_credentials_save_reread_refresh_and_connection_check(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))
    bridge = RecordingBridge()
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: deepcopy(stored))

    def patch_paths(changes):
        for path, value in changes.items():
            _write_path(stored, path, value)
        return True

    monkeypatch.setattr(service_module, "patch_settings_paths", patch_paths)
    services = ApplicationServices(account="tester", runtime_bridge=bridge)

    for source, (values, stored_fields) in CRYPTO_CREDENTIALS.items():
        before = services.settings_snapshot()
        after = services.update_credentials(
            expected_revision=before["revision"],
            provider=source,
            values=values,
        )
        assert after["save_receipt"]["verified"] is True
        assert after["credential_status"][source] is True
        assert all(stored.get(field) for field in stored_fields)

    result = services.refresh_account_snapshot(sources=list(CRYPTO_CREDENTIALS), force_refresh=True)
    assert result["fresh"] is True
    assert bridge.queried == list(CRYPTO_CREDENTIALS)
    assert all(result["sources"][source]["status"] == "success" for source in CRYPTO_CREDENTIALS)


def test_connection_check_classifies_cp949_as_local_runtime_failure(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    class EncodingFailureBridge:
        def account_snapshot(self, **_kwargs):
            raise UnicodeEncodeError("cp949", "🔧", 0, 1, "illegal multibyte sequence")

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    services = ApplicationServices(account="tester", runtime_bridge=EncodingFailureBridge())

    with pytest.raises(RuntimeError, match="^local_runtime_encoding_error$"):
        services.refresh_account_snapshot(sources=["binance"], force_refresh=True)


def test_windows_sidecar_forces_utf8_before_exchange_modules_are_imported():
    launcher = (ROOT / "web_platform" / "launcher.py").read_text(encoding="utf-8")
    electron = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    settings_center = (ROOT / "webui" / "src" / "components" / "SettingsCenter.tsx").read_text(encoding="utf-8")
    exchange_workspace = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    connection_helper = (ROOT / "webui" / "src" / "accountConnection.ts").read_text(encoding="utf-8")
    api = (ROOT / "webui" / "src" / "api.ts").read_text(encoding="utf-8")

    assert launcher.index("configure_utf8_runtime()") < launcher.index("import uvicorn")
    assert 'PYTHONUTF8: "1"' in electron
    assert 'PYTHONIOENCODING: "utf-8"' in electron
    assert "accountConnectionFailure(result, source)" in settings_center
    assert "status === \"success\"" in connection_helper
    assert "API 키나 거래소 권한 오류가 아닙니다." in connection_helper
    assert "API 키 오류 · 연결 실패" not in exchange_workspace
    assert "accountConnectionView(account, source)" in exchange_workspace
    assert "local_runtime_encoding_error" in api
    assert "settings_file_unreadable" in api
    assert "storage_status" in settings_center
