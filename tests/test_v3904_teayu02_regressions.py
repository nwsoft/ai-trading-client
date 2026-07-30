import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from config import settings as settings_module
from trading.ai.credentials import (
    prepare_ai_credentials_for_storage,
    unresolved_credential_references,
)
from trading.market_data_utils import kline_number
from trading.optimizer import Optimizer
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


ROOT = Path(__file__).resolve().parents[1]


def test_delayed_balance_refresh_no_longer_captures_unbound_time():
    refreshed = threading.Event()

    class Dashboard:
        @staticmethod
        def winfo_exists():
            return True

        @staticmethod
        def thread_safe_after(_delay, callback):
            callback()

        @staticmethod
        def update_balance_on_trade_completion():
            refreshed.set()

    trader = object.__new__(Trader)
    trader.dashboard = Dashboard()
    trader.log_event = lambda *_args, **_kwargs: None

    with patch("trading.trader.time.sleep", return_value=None):
        trader._schedule_delayed_balance_update(0)

    assert refreshed.wait(timeout=1)


def test_local_ai_key_storage_has_no_keyring_runtime_dependency():
    stored, warnings = prepare_ai_credentials_for_storage(
        {
            "ai_provider": "openai",
            "openai_api_key": "local-key",
            "ai_credentials": {
                "openai": {
                    "api_key": "local-key",
                    "credential_ref": "keyring://NoahAI/old.openai",
                }
            },
        }
    )
    assert warnings == []
    assert stored["openai_api_key"] == "local-key"
    assert stored["ai_credentials"]["openai"]["api_key"] == "local-key"
    assert "credential_ref" not in stored["ai_credentials"]["openai"]
    ui_source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    assert "store_credential" not in ui_source
    assert 'provider_cfg["api_key"] = buffered_key' in ui_source
    assert "v3.9.0.3 키 재입력 필요" in ui_source
    assert "binance_key[:10]" not in ui_source
    assert "masked_key" not in (ROOT / "ui" / "dashboard_modern.py").read_text(
        encoding="utf-8"
    )


def test_unresolved_v3903_reference_does_not_block_unrelated_settings_save(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    original = {
        "version": "before",
        "ai_credentials": {
            "openai": {
                "credential_ref": "keyring://NoahAI/old.openai",
                "base_url": "",
            }
        },
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(
        settings_module,
        "_get_settings_paths",
        lambda: (str(config_path), str(backup_dir)),
    )
    updated = dict(original)
    updated["version"] = "after"
    assert unresolved_credential_references(updated) == ["openai"]
    assert settings_module.save_settings(updated) is True
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["version"] == "after"
    assert persisted["ai_credentials"]["openai"]["credential_ref"].startswith(
        "keyring://NoahAI/"
    )


def test_settings_template_merge_never_prints_secret_values(capsys):
    secret = "do-not-print-this-api-key"
    merged = settings_module.deep_merge_settings(
        {
            "ai_credentials": {
                "openai": {
                    "api_key": secret,
                    "model": "user-model",
                }
            },
            "log_level": "INFO",
        },
        {
            "ai_credentials": {
                "openai": {
                    "api_key": "",
                    "model": "template-model",
                }
            },
            "log_level": "DEBUG",
        },
    )

    output = capsys.readouterr().out
    assert secret not in output
    assert "user-model" not in output
    assert "template-model" not in output
    assert merged["ai_credentials"]["openai"]["api_key"] == secret


def test_read_only_settings_load_does_not_persist_migrations(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "settings.json"
    original = {
        "version": "3.9.0.3",
        "default_tp": 0.18,
        "default_sl": 0.2,
        "_ai_custom_runtime_safe_default_v3900_applied": True,
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    loaded = settings_module.load_settings(persist_migrations=False)

    assert loaded["default_tp"] == 0.0018
    assert loaded["default_sl"] == 0.002
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_safe_windows_builder_has_no_mandatory_keyring_contract():
    source = (ROOT / "build_safe.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements_windows.txt").read_text(encoding="utf-8")
    assert "keyring" not in source.lower()
    assert "keyring" not in requirements.lower()
    assert "if not ensure_build_dependencies(target_platform):" in source


def test_static_spec_has_no_os_credential_store_dependency():
    source = (ROOT / "aiautotrade.spec").read_text(encoding="utf-8")
    assert "keyring" not in source.lower()


def test_exchange_cards_share_runtime_manager_wake_hidden_tabs_and_show_terminal_states():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    manager_source = (ROOT / "trading" / "exchange_manager.py").read_text(
        encoding="utf-8"
    )
    assert 'manager = getattr(self, "exchange_manager", None)' in source
    assert "exchange_name=exchange" in source
    assert "def _kick_visible_refreshes_for_tab" in source
    assert "self._kick_visible_refreshes_for_tab(current)" in source
    assert 'self._set_balance_metric_state(widgets, "탭 열면 조회")' in source
    assert '"no_api_keys": "API 키 없음"' in source
    assert '"invalid_api_keys": "API 키 오류"' in source
    assert "if not self._has_valid_api_keys(normalized_name):" in manager_source
    assert "'status': 'no_api_keys'" in manager_source
    assert "timeout_ms: int = 12000" in source
    assert 'TimeoutError("거래소 응답 시간이 12초를 초과했습니다")' in source
    assert 'state["timed_out"] = True' in source
    assert 'f"broker_balance:{broker}"' in source


def test_ai_preflight_results_do_not_touch_destroyed_settings_widgets():
    source = (ROOT / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    assert "def _window_alive" in source
    assert "def _read_live_widget" in source
    assert "def _dispatch_window_result" in source
    assert "if not self._window_alive():" in source
    assert "self._dispatch_window_result(" in source


def test_kline_normalizer_accepts_binance_arrays_and_exchange_dicts():
    array_row = [123, "1", "3", "0.5", "2.5", "99"]
    dict_row = {"close": "2.5", "volume": "99"}
    assert kline_number(array_row, "close") == 2.5
    assert kline_number(array_row, "volume") == 99.0
    assert kline_number(dict_row, "close") == 2.5
    assert kline_number(dict_row, "volume") == 99.0


def test_market_regime_paths_accept_array_ohlcv_and_legacy_threshold_shape():
    klines = [
        [index, 100, 102, 99, 100 + index, 10 + index]
        for index in range(24)
    ]

    trader = object.__new__(Trader)
    trader.binance_client = type(
        "Binance",
        (),
        {"get_klines": staticmethod(lambda *_args, **_kwargs: klines)},
    )()
    trader.settings = {"market_analysis_thresholds": []}
    trader.log_event = lambda *_args, **_kwargs: None
    trader.logger = logging.getLogger("test-binance-regime-array")
    assert trader._analyze_market_regime_binance_fast() in {
        "normal",
        "bull",
        "bear",
        "volatile",
    }

    unified = object.__new__(UnifiedTrader)
    unified.exchange_manager = type(
        "Manager",
        (),
        {"get_klines": staticmethod(lambda *_args, **_kwargs: klines)},
    )()
    unified.logger = logging.getLogger("test-unified-regime-array")
    assert unified._evaluate_current_market_conditions_unified_fast(
        "okx",
        "BTC/USDT:USDT",
    ) in {"normal", "bull", "bear", "volatile"}


def test_unified_cycle_normalizes_string_coins_and_non_dict_analysis():
    source = (ROOT / "trading" / "unified_trader.py").read_text(encoding="utf-8")
    assert 'else {"symbol": str(item or "").strip()}' in source
    assert 'if not isinstance(signal_data, dict):' in source
    assert '"reason": "분석기 응답 형식 오류"' in source


def test_optimizer_serializes_datetime_values_in_result_payload():
    captured = {}

    class Recorder:
        @staticmethod
        def execute_query(_query, params):
            captured["params"] = params

    optimizer = object.__new__(Optimizer)
    optimizer.recorder = Recorder()
    optimizer.logger = logging.getLogger("test-optimizer-json")
    optimizer.save_symbol_optimization(
        "BTCUSDT",
        {"checked_at": datetime(2026, 7, 29, 12, 0, 0)},
    )
    payload = json.loads(captured["params"][2])
    assert payload["checked_at"] == "2026-07-29T12:00:00"


def test_binance_protective_orders_wait_for_a_real_open_position():
    source = (ROOT / "api" / "binance_client.py").read_text(encoding="utf-8")
    method = source.split("def place_tp_sl_orders(", 1)[1].split(
        "def get_order_status(",
        1,
    )[0]
    assert "futures_position_information(symbol=symbol)" in method
    assert '"code": "position_not_open"' in method
    assert "time.sleep(0.25 + (verify_attempt * 0.25))" in method
    assert "import time" not in method
