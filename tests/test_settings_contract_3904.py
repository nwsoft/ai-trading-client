import json
from pathlib import Path

from config.settings_contract import (
    ALPHA_LEGACY_SECRET_KEYS,
    RETIRED_TOP_LEVEL_KEYS,
    SETTINGS_SCHEMA_VERSION,
    audit_settings_contract,
    normalize_settings_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def test_template_is_clean_v3904_contract():
    template = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))

    assert template["_settings_schema_version"] == SETTINGS_SCHEMA_VERSION
    assert not (set(template) & set(RETIRED_TOP_LEVEL_KEYS))
    assert not (set(template) & ALPHA_LEGACY_SECRET_KEYS)
    assert not any(key.startswith("alphaarena_") for key in template)
    assert audit_settings_contract(template)["issues"] == []


def test_normalizer_archives_retired_values_and_migrates_alpha_without_loss():
    legacy = {
        "enabled_exchanges": ["binance", "binance", "upbit"],
        "learning_enabled_exchanges": ["bybit"],
        "trade_enabled_exchanges": ["binance", "bybit"],
        "_trade_scope_user_confirmed_v3904": True,
        "backend_url": "http://legacy.invalid",
        "ai_enabled": False,
        "alphaarena_enabled": True,
        "alphaarena_capital": 1000,
        "alphaarena_leverage_range": "3-5x",
        "alpha_arena": {
            "enabled": False,
            "initial_capital_benchmark": 10000,
        },
        "stock_auto_trading": {"enabled": True, "auto_start": False},
    }

    normalized, report, changed = normalize_settings_contract(legacy)

    assert changed is True
    assert normalized["_settings_schema_version"] == SETTINGS_SCHEMA_VERSION
    assert normalized["enabled_exchanges"] == ["binance", "upbit"]
    assert normalized["learning_enabled_exchanges"] == ["binance", "upbit"]
    assert normalized["trade_enabled_exchanges"] == ["binance"]
    assert normalized["alpha_arena"]["enabled"] is True
    assert normalized["alpha_arena"]["initial_capital_benchmark"] == 1000
    assert normalized["alpha_arena"]["leverage_min"] == 3
    assert normalized["alpha_arena"]["leverage_max"] == 5
    assert normalized["stock_auto_trading"] == {"enabled": False, "auto_start": False}
    assert normalized["_legacy_settings_v3904"]["values"]["backend_url"] == "http://legacy.invalid"
    assert normalized["_legacy_settings_v3904"]["values"]["ai_enabled"] is False
    assert report["issues"] == []


def test_nonempty_legacy_secret_is_not_archived_or_dropped_before_secure_storage():
    settings = {
        "enabled_exchanges": [],
        "trade_enabled_exchanges": [],
        "alpha_arena": {},
        "alphaarena_deepseek_api_key": "secret-value",
    }

    normalized, _, _ = normalize_settings_contract(settings)

    assert normalized["alphaarena_deepseek_api_key"] == "secret-value"
    archive_values = normalized.get("_legacy_settings_v3904", {}).get("values", {})
    assert "alphaarena_deepseek_api_key" not in archive_values


def test_unconfirmed_v3903_live_scope_is_archived_and_reset_to_learning():
    settings = {
        "enabled_exchanges": ["binance", "bybit"],
        "trade_enabled_exchanges": ["binance", "bybit"],
        "paper_trading": False,
        "alpha_arena": {},
    }

    normalized, report, changed = normalize_settings_contract(settings)

    assert changed is True
    assert normalized["trade_enabled_exchanges"] == []
    assert normalized["_trade_scope_user_confirmed_v3904"] is False
    assert normalized["_legacy_settings_v3904"]["values"][
        "trade_enabled_exchanges_unconfirmed_v3903"
    ] == ["binance", "bybit"]
    assert report["mode"] == "LEARNING"
    assert report["issues"] == []


def test_audit_reports_mode_without_exposing_values():
    learning = audit_settings_contract({
        "enabled_exchanges": ["binance"],
        "trade_enabled_exchanges": [],
        "paper_trading": False,
    })
    paper = audit_settings_contract({
        "enabled_exchanges": ["binance"],
        "trade_enabled_exchanges": ["binance"],
        "paper_trading": True,
    })

    assert learning["mode"] == "LEARNING"
    assert paper["mode"] == "PAPER"
    assert "enabled_exchanges" not in learning


def test_malformed_legacy_values_are_normalized_without_crashing():
    normalized, _, changed = normalize_settings_contract({
        "enabled_exchanges": "binance",
        "trade_enabled_exchanges": ["binance", "bybit"],
        "_trade_scope_user_confirmed_v3904": True,
        "alpha_arena": {"initial_capital_benchmark": 10000},
        "alphaarena_capital": "not-a-number",
    })

    assert changed is True
    assert normalized["enabled_exchanges"] == ["binance"]
    assert normalized["trade_enabled_exchanges"] == ["binance"]
    assert normalized["alpha_arena"]["initial_capital_benchmark"] == 10000


def test_multi_venue_policy_is_canonical_and_runtime_targets_are_not_saved():
    normalized, report, changed = normalize_settings_contract({
        "enabled_exchanges": ["binance", "okx"],
        "trade_enabled_exchanges": ["binance", "okx"],
        "_trade_scope_user_confirmed_v3904": True,
        "alpha_arena": {},
        "multi_venue_execution": {
            "mode": "risk_split",
            "authorized_targets": ["binance", "okx"],
            "opportunity_window_sec": 1,
            "duplicate_window_sec": 99999,
        },
    })

    assert changed is True
    assert normalized["multi_venue_execution"]["mode"] == "split"
    assert normalized["multi_venue_execution"]["opportunity_window_sec"] == 5
    assert normalized["multi_venue_execution"]["duplicate_window_sec"] == 3600
    assert "authorized_targets" not in normalized["multi_venue_execution"]
    assert report["issues"] == []
