#!/usr/bin/env python3
"""Audit the complete Settings and AI Assistant source contract.

This gate proves source-level ownership, validation and Web/legacy wiring.  It
does not certify a rebuilt Windows installer, an external account, microphone
permission or provider network health.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web_platform.application_services import (  # noqa: E402
    ALL_EDITABLE_SETTINGS,
    EXCLUDED_WEB_SETTINGS,
    MANAGED_NESTED_SETTINGS,
    SETTINGS_SECTION_IDS,
    _is_sensitive,
    _read_path,
    _settings_section,
    _validate_setting,
)


LEGACY_VISIBLE_PATHS = {
    "paper_trading", "verbose_trade_logging", "ui_settings.always_on_top",
    "position_mode", "default_margin_type", "broadcast_replay_enabled",
    "broadcast_replay_source_account", "enabled_exchanges",
    "trade_enabled_exchanges", "multi_venue_execution.mode",
    "enabled_stock_brokers", "stock_asset_mode",
    "stock_order_guardrails.enabled", "stock_order_guardrails.enforce_market_hours",
    "stock_order_guardrails.allow_market_order", "stock_order_guardrails.max_quantity",
    "stock_order_guardrails.max_order_value", "stock_order_guardrails.daily_order_limit",
    "stock_auto_trading.auto_start", "enable_stock_live_order",
    "asset_stop_position_policy", "life_finance_sync_dir", "life_finance_backup_dir",
    "ai_provider", "ai_provider_profiles.analyst.provider",
    "ai_provider_profiles.analyst.model", "ai_provider_profiles.assistant.provider",
    "ai_provider_profiles.assistant.model", "ai_model_roles.frequent_cheap.provider",
    "ai_model_roles.frequent_cheap.model", "ai_model_roles.standard.provider",
    "ai_model_roles.standard.model", "ai_model_roles.premium.provider",
    "ai_model_roles.premium.model", "assistant_response_mode",
    "ai_custom_transcription.enabled", "ai_custom_transcription.model",
    "ai_custom_transcription.max_duration_minutes", "ai_custom_transcription.max_file_mb",
    "ai_custom_runtime.enabled", "ai_custom_runtime.allow_limited_live",
    "ai_custom_features.profile", "assistant_voice.enabled", "assistant_voice.auto_tts",
    "assistant_voice.lang", "assistant_voice.rate", "dynamic_thresholds_enabled",
    "dynamic_thresholds_high_multiplier", "dynamic_thresholds_mode",
    "dynamic_thresholds_manual_regime", "ui_settings.auto_update_enabled",
    "ui_settings.auto_update_check_interval_hours", "ui_settings.auto_update_auto_download",
    "ui_settings.auto_update_auto_apply_on_exit", "ui_settings.auto_update_open_position_action",
}


def _leaves(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            return [(prefix, value)]
        rows: list[tuple[str, Any]] = []
        for key, item in value.items():
            rows.extend(_leaves(item, f"{prefix}.{key}" if prefix else str(key)))
        return rows
    return [(prefix, value)]


def audit() -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    template = json.loads((ROOT / "config" / "settings_template.json").read_text(encoding="utf-8"))
    descriptors = {item.path: item for item in ALL_EDITABLE_SETTINGS}
    if len(descriptors) != len(ALL_EDITABLE_SETTINGS):
        errors.append("설정 descriptor 경로가 중복됩니다.")

    for item in ALL_EDITABLE_SETTINGS:
        value = _read_path(template, item.path)
        try:
            _validate_setting(item, value)
        except (TypeError, ValueError) as exc:
            errors.append(f"정본 기본값 검증 실패: {item.path}: {exc}")

    missing_legacy = sorted(LEGACY_VISIBLE_PATHS.difference(descriptors))
    if missing_legacy:
        errors.append(f"원본 사용자 설정이 Web 계약에서 누락됨: {missing_legacy}")

    response = descriptors.get("assistant_response_mode")
    if not response or response.options != ("saver", "standard", "premium"):
        errors.append("어시스턴트 저장 프리셋이 saver/standard/premium 정본과 다릅니다.")
    profile = descriptors.get("ai_custom_features.profile")
    if not profile or profile.options != ("beginner", "standard", "advanced", "lab", "research"):
        errors.append("AI 커스텀 프로필이 beginner/standard/advanced/lab/research 정본과 다릅니다.")

    sections = {_settings_section(item) for item in ALL_EDITABLE_SETTINGS}
    if sections != SETTINGS_SECTION_IDS:
        errors.append(f"비어 있거나 알 수 없는 설정 탭: expected={sorted(SETTINGS_SECTION_IDS)} actual={sorted(sections)}")

    sensitive_json_roots = []
    for item in ALL_EDITABLE_SETTINGS:
        if item.kind != "json" or "." in item.path:
            continue
        value = template.get(item.path)
        if any(_is_sensitive(path.rsplit(".", 1)[-1]) for path, _ in _leaves(value, item.path)):
            sensitive_json_roots.append(item.path)
    if sensitive_json_roots:
        errors.append(f"비밀 하위값을 포함한 raw JSON 편집 경로: {sorted(sensitive_json_roots)}")

    leaf_ownership = {"exact": 0, "json_parent": 0, "managed": 0, "protected": 0, "unowned": 0}
    unowned = []
    json_paths = {item.path for item in ALL_EDITABLE_SETTINGS if item.kind == "json"}
    for path, _value in _leaves(template):
        root = path.split(".", 1)[0]
        if path in descriptors:
            leaf_ownership["exact"] += 1
        elif any(path.startswith(parent + ".") for parent in json_paths):
            leaf_ownership["json_parent"] += 1
        elif _is_sensitive(path.rsplit(".", 1)[-1]):
            leaf_ownership["protected"] += 1
        elif root in MANAGED_NESTED_SETTINGS:
            leaf_ownership["managed"] += 1
        elif root in EXCLUDED_WEB_SETTINGS:
            leaf_ownership["protected"] += 1
        else:
            leaf_ownership["unowned"] += 1
            unowned.append(path)
    if unowned:
        errors.append(f"소유 분류가 없는 settings.json leaf {len(unowned)}개: {unowned[:20]}")

    settings_ui = (ROOT / "webui" / "src" / "components" / "SettingsCenter.tsx").read_text(encoding="utf-8")
    assistant_ui = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    strategy_ui = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    gateway = (ROOT / "web_platform" / "gateway.py").read_text(encoding="utf-8")
    services = (ROOT / "web_platform" / "application_services.py").read_text(encoding="utf-8")
    required_source_tokens = {
        "설정 탭 기본값": (settings_ui, 'stageDefaults("section")'),
        "전체 기본값": (settings_ui, 'stageDefaults("all")'),
        "저장 검증 receipt": (settings_ui, "save_receipt?.verified"),
        "어시스턴트 최근 문맥 UI": (assistant_ui, "recentMessages"),
        "어시스턴트 최근 문맥 API": (gateway, "body.recent_messages"),
        "어시스턴트 저장 프리셋 적용": (services, "assistant_token_budget"),
        "Level 3 프로필 게이트": (strategy_ui, "featureViewLevel < 3"),
        "12단계 로컬 비용 없음": (strategy_ui, "12단계 자세히 · API 비용 없음"),
        "전략 입력 초기화": (strategy_ui, "새로 시작 · 입력 초기화"),
        "차트 분석 초기화": (assistant_ui, '>{t("초기화")}</button>'),
    }
    for label, (source, token) in required_source_tokens.items():
        if token not in source:
            errors.append(f"AI/설정 화면 계약 누락: {label}")

    active_runtime_files = [
        *sorted((ROOT / "trading").rglob("*.py")),
        *sorted((ROOT / "web_platform").rglob("*.py")),
    ]
    full_writer_calls = []
    restore_calls = []
    for path in active_runtime_files:
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?<!def )\bsave_settings\s*\(", source):
            line = source.count("\n", 0, match.start()) + 1
            full_writer_calls.append(f"{path.relative_to(ROOT)}:{line}")
        for match in re.finditer(r"\brestore_settings_from_backup\s*\(", source):
            line = source.count("\n", 0, match.start()) + 1
            restore_calls.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    if full_writer_calls:
        errors.append(f"Web 활성 runtime의 전체 settings writer: {full_writer_calls}")
    expected_restore_prefix = "web_platform/application_services.py:"
    unexpected_restore = [item for item in restore_calls if not item.startswith(expected_restore_prefix)]
    if unexpected_restore or len(restore_calls) != 1:
        errors.append(f"사용자 명시 endpoint 밖의 설정 복구 경로: {restore_calls}")

    summary = {
        "template_top_level": len(template),
        "template_leaf_values": len(_leaves(template)),
        "editable_fields": len(ALL_EDITABLE_SETTINGS),
        "legacy_visible_fields": len(LEGACY_VISIBLE_PATHS),
        "sections": len(sections),
        "leaf_ownership": leaf_ownership,
        "protected_top_level": len(EXCLUDED_WEB_SETTINGS),
        "active_runtime_full_writers": len(full_writer_calls),
        "explicit_restore_calls": len(restore_calls),
    }
    return errors, summary


def main() -> int:
    errors, summary = audit()
    print(json.dumps({"status": "FAIL" if errors else "PASS", "summary": summary, "errors": errors}, ensure_ascii=False, indent=2))
    if not errors:
        print("SETTINGS+ASSISTANT SOURCE CONTRACT PASS — Windows 설치본·외부계정 E2E는 별도 게이트입니다.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
