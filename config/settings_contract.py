#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NoahAI v3.9.0.4 설정 정본, 마이그레이션과 비밀값 없는 진단."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, Tuple


SETTINGS_SCHEMA_VERSION = "3.9.0.4"
LEGACY_ARCHIVE_KEY = "_legacy_settings_v3904"
TRADE_SCOPE_CONFIRMATION_KEY = "_trade_scope_user_confirmed_v3904"

# 실행 코드가 더 이상 소비하지 않는 과거 최상위 설정이다.
# 기존 사용자 값은 삭제하지 않고 LEGACY_ARCHIVE_KEY 아래로 1회 이동한다.
RETIRED_TOP_LEVEL_KEYS = {
    "ai_enabled": "AI 실행은 Provider·역할·운용 모드에서 결정",
    "ai_signal_enabled": "신호 파이프라인은 자동 관리",
    "analytics_refresh_interval_minutes": "화면별 가시성 스케줄러로 통합",
    "api_timeout": "연결 어댑터별 timeout으로 통합",
    "auto_coin_selection": "선택 파이프라인이 항상 운용 범위 안에서 결정",
    "backend_url": "로그인·서비스별 보안 엔드포인트로 분리",
    "cache_timeout": "서비스별 캐시 정책으로 분리",
    "clear_logs_on_restart": "회전·보존 로그 정책으로 대체",
    "db_backup_interval": "DB 소유 서비스의 백업 정책으로 이동",
    "db_backup_retention": "DB 소유 서비스의 백업 정책으로 이동",
    "dynamic_thresholds_hysteresis": "전략 엔진 내부 국면 전환 정책으로 이동",
    "dynamic_thresholds_hysteresis_enabled": "전략 엔진 내부 국면 전환 정책으로 이동",
    "entry_order_type": "실행 최적화·거래소 어댑터 정책으로 이동",
    "learning_period": "학습기별 표본 정책으로 분리",
    "log_file_size_limit": "공통 회전 로그 정책으로 이동",
    "log_retention_days": "공통 회전 로그 정책으로 이동",
    "ma_period": "전략·분석기별 지표 설정으로 이동",
    "max_concurrent_requests": "Provider·거래소별 제한기로 이동",
    "optimization_interval": "최적화기별 주기로 분리",
    "strategy_config": "trading_strategies 정본으로 통합",
}

ALPHA_LEGACY_VALUE_KEYS = {
    "alphaarena_enabled": "enabled",
    "alphaarena_ai_engine": "engine",
    "alphaarena_capital": "initial_capital_benchmark",
}
ALPHA_LEGACY_SECRET_KEYS = {
    "alphaarena_deepseek_api_key",
    "alphaarena_openai_api_key",
    "alphaarena_anthropic_api_key",
    "alphaarena_google_api_key",
    "alphaarena_xai_api_key",
    "alphaarena_alibaba_api_key",
}


def _stable_unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    source = [values] if isinstance(values, (str, bytes)) else (values or [])
    for value in source:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _archive_value(settings: Dict[str, Any], key: str, value: Any, reason: str) -> None:
    archive = settings.get(LEGACY_ARCHIVE_KEY)
    if not isinstance(archive, dict):
        archive = {}
        settings[LEGACY_ARCHIVE_KEY] = archive
    values = archive.get("values")
    if not isinstance(values, dict):
        values = {}
        archive["values"] = values
    reasons = archive.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
        archive["reasons"] = reasons
    values.setdefault(key, copy.deepcopy(value))
    reasons.setdefault(key, reason)
    archive["schema_version"] = SETTINGS_SCHEMA_VERSION


def normalize_settings_contract(settings: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """설정을 v3.9.0.4 정본으로 맞추고 비밀값 없는 변경 보고서를 반환한다."""
    normalized = copy.deepcopy(settings or {})
    changed_keys: list[str] = []

    for key, reason in RETIRED_TOP_LEVEL_KEYS.items():
        if key not in normalized:
            continue
        _archive_value(normalized, key, normalized.pop(key), reason)
        changed_keys.append(key)

    alpha = normalized.get("alpha_arena")
    if not isinstance(alpha, dict):
        alpha = {}
        normalized["alpha_arena"] = alpha
        changed_keys.append("alpha_arena")

    for legacy_key, canonical_key in ALPHA_LEGACY_VALUE_KEYS.items():
        if legacy_key not in normalized:
            continue
        legacy_value = normalized.pop(legacy_key)
        current = alpha.get(canonical_key)
        should_migrate = canonical_key not in alpha
        if canonical_key == "enabled":
            should_migrate = should_migrate or (not bool(current) and bool(legacy_value))
        elif canonical_key == "engine":
            should_migrate = should_migrate or (
                str(current or "") in ("", "deepseek-v4-flash")
                and str(legacy_value or "") not in ("", "deepseek-v4-flash")
            )
        elif canonical_key == "initial_capital_benchmark":
            try:
                current_capital = int(float(current or 10000))
                legacy_capital = int(float(legacy_value or 10000))
                should_migrate = should_migrate or (
                    current_capital == 10000 and legacy_capital != 10000
                )
                legacy_value = legacy_capital
            except (TypeError, ValueError):
                should_migrate = False
        if should_migrate:
            alpha[canonical_key] = legacy_value
        _archive_value(
            normalized,
            legacy_key,
            legacy_value,
            f"alpha_arena.{canonical_key} 정본으로 통합",
        )
        changed_keys.append(legacy_key)

    legacy_leverage = normalized.pop("alphaarena_leverage_range", None)
    if legacy_leverage is not None:
        text = str(legacy_leverage or "").lower().replace("x", "")
        parts = [part.strip() for part in text.split("-", 1)]
        if len(parts) == 2:
            try:
                alpha.setdefault("leverage_min", int(float(parts[0])))
                alpha.setdefault("leverage_max", int(float(parts[1])))
            except (TypeError, ValueError):
                pass
        _archive_value(
            normalized,
            "alphaarena_leverage_range",
            legacy_leverage,
            "alpha_arena.leverage_min/max 정본으로 통합",
        )
        changed_keys.append("alphaarena_leverage_range")

    # 평문 비밀값은 여기서 보관하지 않는다. 보안 저장 처리 후 빈 레거시 껍데기만 제거한다.
    for secret_key in ALPHA_LEGACY_SECRET_KEYS:
        if secret_key in normalized and not str(normalized.get(secret_key) or "").strip():
            normalized.pop(secret_key, None)
            changed_keys.append(secret_key)

    enabled = _stable_unique(normalized.get("enabled_exchanges", []))
    if normalized.get("enabled_exchanges") != enabled:
        normalized["enabled_exchanges"] = enabled
        changed_keys.append("enabled_exchanges")
    if normalized.get("learning_enabled_exchanges") != enabled:
        normalized["learning_enabled_exchanges"] = list(enabled)
        changed_keys.append("learning_enabled_exchanges")

    configured_trade_enabled = _stable_unique(normalized.get("trade_enabled_exchanges", []))
    trade_scope_confirmed = bool(normalized.get(TRADE_SCOPE_CONFIRMATION_KEY, False))
    if configured_trade_enabled and not trade_scope_confirmed:
        _archive_value(
            normalized,
            "trade_enabled_exchanges_unconfirmed_v3903",
            configured_trade_enabled,
            "과도기 자동복사 여부를 확인할 수 없어 v3.9.0.4에서 사용자 재확인 필요",
        )
        configured_trade_enabled = []
        changed_keys.append("trade_enabled_exchanges")
    if TRADE_SCOPE_CONFIRMATION_KEY not in normalized:
        normalized[TRADE_SCOPE_CONFIRMATION_KEY] = False
        changed_keys.append(TRADE_SCOPE_CONFIRMATION_KEY)

    trade_enabled = [
        item
        for item in configured_trade_enabled
        if item in enabled
    ]
    if normalized.get("trade_enabled_exchanges") != trade_enabled:
        normalized["trade_enabled_exchanges"] = trade_enabled
        changed_keys.append("trade_enabled_exchanges")

    from trading.opportunity_coordinator import normalize_multi_venue_policy

    multi_venue = normalize_multi_venue_policy(
        normalized.get("multi_venue_execution", {})
    )
    # authorized_targets는 현재 설정·실행 시점에서 주입하는 런타임 값이므로
    # settings.json 정본에는 저장하지 않는다.
    multi_venue.pop("authorized_targets", None)
    if normalized.get("multi_venue_execution") != multi_venue:
        normalized["multi_venue_execution"] = multi_venue
        changed_keys.append("multi_venue_execution")

    stock_auto = normalized.get("stock_auto_trading")
    if isinstance(stock_auto, dict):
        canonical_auto_start = bool(stock_auto.get("auto_start", stock_auto.get("enabled", False)))
        if stock_auto.get("auto_start") is not canonical_auto_start:
            stock_auto["auto_start"] = canonical_auto_start
            changed_keys.append("stock_auto_trading.auto_start")
        if stock_auto.get("enabled") is not canonical_auto_start:
            stock_auto["enabled"] = canonical_auto_start
            changed_keys.append("stock_auto_trading.enabled")

    if normalized.get("_settings_schema_version") != SETTINGS_SCHEMA_VERSION:
        normalized["_settings_schema_version"] = SETTINGS_SCHEMA_VERSION
        changed_keys.append("_settings_schema_version")

    report = audit_settings_contract(normalized)
    report["normalized_keys"] = sorted(set(changed_keys))
    return normalized, report, bool(changed_keys)


def audit_settings_contract(settings: Dict[str, Any]) -> Dict[str, Any]:
    """설정 모순과 레거시 상태를 값·비밀 노출 없이 진단한다."""
    current = settings or {}
    enabled = _stable_unique(current.get("enabled_exchanges", []))
    trade_enabled = _stable_unique(current.get("trade_enabled_exchanges", []))
    trade_scope_confirmed = bool(current.get(TRADE_SCOPE_CONFIRMATION_KEY, False))
    invalid_trade = [item for item in trade_enabled if item not in enabled]
    retired = sorted(key for key in RETIRED_TOP_LEVEL_KEYS if key in current)
    alpha_legacy = sorted(
        key
        for key in (*ALPHA_LEGACY_VALUE_KEYS, "alphaarena_leverage_range", *ALPHA_LEGACY_SECRET_KEYS)
        if key in current
    )
    archive = current.get(LEGACY_ARCHIVE_KEY)
    archived_count = 0
    if isinstance(archive, dict) and isinstance(archive.get("values"), dict):
        archived_count = len(archive["values"])

    issues: list[Dict[str, str]] = []
    if invalid_trade:
        issues.append({
            "level": "error",
            "code": "trade_scope_outside_enabled_scope",
            "message": "실제 주문 범위가 분석·학습 범위를 벗어났습니다.",
        })
    if trade_enabled and not trade_scope_confirmed:
        issues.append({
            "level": "error",
            "code": "unconfirmed_trade_scope",
            "message": "실제 주문 범위의 사용자 확인 표식이 없어 LEARNING으로 잠가야 합니다.",
        })
    if retired:
        issues.append({
            "level": "warning",
            "code": "retired_top_level_keys",
            "message": f"실행에서 사용하지 않는 과거 설정 {len(retired)}개가 남아 있습니다.",
        })
    if alpha_legacy:
        issues.append({
            "level": "warning",
            "code": "duplicate_alpha_arena_schema",
            "message": f"AlphaArena 이중 설정 {len(alpha_legacy)}개가 남아 있습니다.",
        })
    if bool(current.get("paper_trading", False)):
        mode = "PAPER"
        mode_message = "실시간 데이터·분석은 유지하고 주문·포지션은 가상 체결합니다."
    elif trade_enabled and trade_scope_confirmed:
        mode = "LIVE"
        mode_message = "선택된 실제 주문 거래소에만 신규 실주문을 허용합니다."
    else:
        mode = "LEARNING"
        mode_message = (
            "시세·AI 커스텀·수익성·위험·수량·청산·주문 규격까지 판단하고 "
            "외부 상태 변경과 신규 주문은 차단합니다."
        )

    return {
        "schema_version": str(current.get("_settings_schema_version") or "legacy"),
        "mode": mode,
        "mode_message": mode_message,
        "enabled_exchanges_count": len(enabled),
        "trade_enabled_exchanges_count": len(trade_enabled),
        "trade_scope_confirmed": trade_scope_confirmed,
        "retired_key_names": retired,
        "alpha_legacy_key_names": alpha_legacy,
        "archived_legacy_count": archived_count,
        "issues": issues,
    }
