#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
설정 파일 로드 및 저장
"""

import json
import os
import sys
import copy
import shutil
import math
from typing import Dict, Any, List

from config.settings_contract import normalize_settings_contract

# 🔒 보호할 설정 항목 리스트 (템플릿 병합 시 덮어쓰지 않음)
PROTECTED_SETTINGS = [
    'analyzer_settings.user_signal_threshold',
    'ai_trading_preferences.risk_tolerance',
    'ai_trading_preferences.balance_utilization_limit',
    'ai_trading_preferences.risk_levels.conservative.balance_utilization',
    'ai_trading_preferences.risk_levels.moderate.balance_utilization',
    'ai_trading_preferences.risk_levels.aggressive.balance_utilization',
    'exchange_risk_overrides.binance.max_position_size',
    'exchange_risk_overrides.bybit.max_position_size',
    'exchange_risk_overrides.okx.max_position_size',
    'exchange_risk_overrides.bitget.max_position_size',
]

LEGACY_PROFITABILITY_POLICY = {
    'enabled': True,
    'min_trades': 20,
    'min_win_rate': 0.48,
    'min_sharpe': 0.60,
    'max_mdd': 0.25,
    'min_expectancy': 0.0,
    'min_walkforward_pass_rate': 0.50,
}


def _repair_trade_rate(value: Any, fallback: float, maximum: float) -> tuple[float, bool]:
    """TP/SL을 런타임 fraction으로 복구한다.

    0.18처럼 퍼센트 포인트로 저장된 값은 0.0018로 변환하고,
    가격값처럼 비정상적으로 큰 값은 안전한 기본값으로 되돌린다.
    """
    try:
        raw = float(value)
    except Exception:
        return float(fallback), True
    if not math.isfinite(raw) or raw <= 0 or raw > 5.0:
        return float(fallback), True
    normalized = raw / 100.0 if raw > maximum else raw
    normalized = max(0.0005, min(normalized, maximum))
    return normalized, not math.isclose(raw, normalized, rel_tol=0.0, abs_tol=1e-12)


def normalize_trade_rate(
    value: Any,
    *,
    kind: str = "tp",
    fallback: float | None = None,
) -> tuple[float, bool]:
    """외부/AI/사용자 입력 TP·SL을 런타임 fraction으로 정규화한다."""
    rate_kind = str(kind or "tp").strip().lower()
    if rate_kind == "sl":
        return _repair_trade_rate(value, 0.0020 if fallback is None else fallback, 0.03)
    return _repair_trade_rate(value, 0.0018 if fallback is None else fallback, 0.05)


def _repair_tp_sl_settings(settings: Dict[str, Any]) -> bool:
    changed = False
    for key, fallback, maximum in (
        ("default_tp", 0.0018, 0.05),
        ("default_sl", 0.0020, 0.03),
    ):
        normalized, was_changed = normalize_trade_rate(
            settings.get(key, fallback),
            kind="tp" if key == "default_tp" else "sl",
            fallback=fallback,
        )
        if was_changed:
            settings[key] = normalized
            changed = True
    return changed

RECOMMENDED_PROFITABILITY_POLICY = {
    'enabled': True,
    'min_trades': 10,
    'min_win_rate': 0.42,
    'min_sharpe': 0.20,
    'max_mdd': 0.30,
    'min_expectancy': 0.0,
    'min_walkforward_pass_rate': 0.40,
}


def load_settings_template() -> Dict[str, Any]:
    """settings_template.json 을 로드하여 반환 (프리셋 등 참조용)"""
    try:
        template_path = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'config', 'settings_template.json')
        if not os.path.exists(template_path):
            template_path = os.path.join(os.path.dirname(__file__), 'settings_template.json')
        with open(template_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def update_settings_from_template(settings: Dict[str, Any]) -> Dict[str, Any]:
    """템플릿에서 새로운 설정을 안전하게 병합 (사용자 설정 보존)"""
    try:
        # 템플릿 파일 경로 결정
        if getattr(sys, 'frozen', False):
            # 배포 환경: PyInstaller 내장 템플릿 사용
            template_path = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'config', 'settings_template.json')
        else:
            # 개발 환경: 프로젝트 내 config 폴더 사용
            template_path = os.path.join(os.path.dirname(__file__), 'settings_template.json')

        # 템플릿 파일이 없으면 현재 설정 반환
        if not os.path.exists(template_path):
            print(f"⚠️ 템플릿 파일 없음: {template_path}")
            return settings

        # 템플릿 로드
        with open(template_path, 'r', encoding='utf-8') as f:
            template_settings = json.load(f)

        print(f"✅ 템플릿 파일 로드: {template_path}")

        # 안전한 병합 수행
        updated_settings = deep_merge_settings(settings, template_settings)

        # 기존 저장값이 과거의 더 엄격한 수익성 기본값과 완전히 일치하면,
        # 최신 권장값으로 한 번만 완화한다. 사용자 커스텀 값은 건드리지 않는다.
        updated_settings = normalize_profitability_validation_policy(updated_settings)

        # UI 설정이 없으면 강제로 추가
        if 'ui_settings' not in updated_settings:
            updated_settings['ui_settings'] = {
                'always_on_top': False,
                'window_geometry': '1400x900',
                'remember_window_position': True,
                'auto_update_enabled': True,
                'auto_update_check_interval_hours': 6,
                'auto_update_auto_download': True,
                'auto_update_auto_apply_on_exit': True,
                'auto_update_open_position_action': 'defer',
                'auto_update_release_repo': 'nwsoft/ai-trading-client',
            }
            print("  ➕ UI 설정 강제 추가 (템플릿 병합 후)")

        # 업데이트된 설정이 있는지 확인
        changes = detect_settings_changes(settings, updated_settings)

        # 실제 변경사항이 있는지 확인 (추가/병합만 있는 경우 제외)
        has_real_changes = False
        for change in changes:
            # "새 설정 추가"나 "추가" 메시지만 있으면 실제 변경 없음
            if "설정 변경" in change or "병합" in change:
                has_real_changes = True
                break

        if has_real_changes:
            print("🔄 설정 업데이트 감지:")
            for change in changes:
                print(f"  • {change}")
            return updated_settings
        elif changes:
            # 새 항목만 추가된 경우 - 현재 설정 반환 (추가 로직은 deep_merge에서 처리됨)
            print("✅ 새 설정 항목 감지 (보존 정책으로 자동 처리)")
            return updated_settings
        else:
            print("✅ 설정 업데이트 없음")
            return settings

    except Exception as e:
        print(f"설정 업데이트 오류: {e}")
        return settings


def normalize_profitability_validation_policy(settings: Dict[str, Any]) -> Dict[str, Any]:
    """과거의 과도한 수익성 기본값을 최신 권장값으로 완화한다."""
    try:
        advanced_layers = settings.get('advanced_trading_layers')
        if not isinstance(advanced_layers, dict):
            return settings

        policy = advanced_layers.get('profitability_validation')
        if not isinstance(policy, dict):
            return settings

        if not all(policy.get(key) == value for key, value in LEGACY_PROFITABILITY_POLICY.items()):
            return settings

        policy.update(RECOMMENDED_PROFITABILITY_POLICY)
        advanced_layers['profitability_validation'] = policy
        settings['advanced_trading_layers'] = advanced_layers
        print("✅ 수익성 검증 기본값을 최신 권장값으로 완화했습니다")
    except Exception:
        pass

    return settings


def migrate_stock_broker_api_contracts(settings: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """v3.9.0.5 증권 API 이름을 공식 계약 기준으로 안전 이전한다.

    API 키/계좌 값은 그대로 보존한다. 다만 신한에 잘못 연결돼 있던 XingAPI는
    LS증권 계약이므로 신한으로 자동 전송하지 않도록 해당 증권사만 비활성화한다.
    """
    if not isinstance(settings, dict):
        return settings, False

    configs = settings.get('stock_broker_configs')
    if not isinstance(configs, dict):
        configs = {}
        settings['stock_broker_configs'] = configs

    canonical = {
        'kiwoom': ('openapi_plus', 'pykiwoom'),
        'shinhan': ('partner_rest', 'shinhan_openapi_v2'),
        'miraeAsset': ('partner_rest', 'mirae_partner_profile'),
        'koreaInvestment': ('rest', 'kis_openapi_v1'),
    }
    changed = False
    archive = settings.get('_legacy_stock_api_migrations')
    if not isinstance(archive, list):
        archive = []

    for broker, (target_type, target_version) in canonical.items():
        cfg = configs.get(broker)
        if not isinstance(cfg, dict):
            continue
        old_type = str(cfg.get('api_type') or '').strip().lower()
        old_version = str(cfg.get('api_version') or '').strip().lower()
        if old_type == 'mock':
            if old_version != 'mock':
                cfg['api_version'] = 'mock'
                changed = True
            continue
        if (old_type, old_version) == (target_type, target_version):
            continue

        archive.append({
            'broker': broker,
            'api_type': old_type,
            'api_version': old_version,
            'reason': (
                'xingapi_is_ls_securities_not_shinhan'
                if broker == 'shinhan' and old_version == 'xingapi'
                else 'v3905_official_contract_normalization'
            ),
        })
        cfg['api_type'] = target_type
        cfg['api_version'] = target_version
        if broker == 'shinhan' and old_version == 'xingapi':
            cfg['enabled'] = False
            cfg['allow_live_order'] = False
            cfg['migration_notice'] = (
                '기존 xingapi는 LS증권 API이므로 신한증권에서 분리했습니다. '
                '신한 제휴 API 프로필을 확인한 뒤 다시 활성화하세요.'
            )
        changed = True

    if archive:
        settings['_legacy_stock_api_migrations'] = archive[-50:]
    if settings.get('stock_api_contract_version') != 2:
        settings['stock_api_contract_version'] = 2
        changed = True
    return settings, changed


def deep_merge_settings(existing: Dict[str, Any], template: Dict[str, Any], parent_key: str = '') -> Dict[str, Any]:
    """깊은 병합으로 설정을 안전하게 업데이트 (사용자 설정 보존)"""
    result = existing.copy()

    for key, template_value in template.items():
        current_key_path = f"{parent_key}.{key}" if parent_key else key
        if key not in result:
            # 새로운 키는 추가
            result[key] = template_value
            print(f"  ➕ 새 설정 추가: {current_key_path}")
        elif isinstance(template_value, dict) and isinstance(result[key], dict):
            # 🔥 재귀적으로 병합 (2단계 이상 중첩도 처리)
            # 모든 딕셔너리는 사용자 설정 보존 (새로운 키만 추가)
            # 단, 보호된 설정 항목은 절대 덮어쓰지 않음
            merged_dict = deep_merge_settings(result[key], template_value, parent_key=current_key_path)
            result[key] = merged_dict
        elif key == 'ui_settings' and isinstance(template_value, dict):
            # UI 설정은 특별 처리: 기존 설정과 병합
            if key not in result:
                result[key] = template_value.copy()
                print(f"  ➕ UI 설정 추가: {template_value}")
            else:
                # 기존 UI 설정과 템플릿 UI 설정 병합
                merged_ui = result[key].copy()
                for ui_key, ui_value in template_value.items():
                    if ui_key not in merged_ui:
                        merged_ui[ui_key] = ui_value
                        print(f"    ➕ UI 설정 항목 추가: ui_settings.{ui_key}")
                result[key] = merged_ui
        elif isinstance(template_value, list) and isinstance(result[key], list):
            # 모든 리스트는 사용자 설정 보존 (템플릿으로 덮어쓰지 않음)
            if result[key] != template_value:
                print(f"  🔒 리스트 설정 보존: {current_key_path}")
            continue
        else:
            # 스칼라 값은 사용자 설정 보존 (API 키 등 개인정보 및 사용자 선호)
            # 🔒 보호된 설정 항목 확인
            if current_key_path in PROTECTED_SETTINGS:
                # 보호된 설정은 절대 덮어쓰지 않음
                if result[key] != template_value:
                    print(f"  🔒 보호된 설정 보존: {current_key_path}")
                continue
            
            if key in ['binance_api_key', 'binance_secret_key', 'upbit_api_key', 'upbit_secret_key',
                       'bithumb_api_key', 'bithumb_secret_key', 'bitget_api_key', 'bitget_secret_key', 'bitget_password',
                       'okx_api_key', 'okx_secret_key', 'okx_passphrase', 'bybit_api_key', 'bybit_secret_key',
                       'openai_api_key', 'backend_url', 'selected_exchange', 'enabled_exchanges',
                      'default_margin_type', 'paper_trading', 'demo_mode',
                      'broadcast_replay_enabled', 'broadcast_replay_source_account']:
                # 개인정보/중요 사용자 설정은 절대 덮어쓰지 않음
                continue
            elif result[key] != template_value:
                # 중요한 설정은 사용자 값 보존 (절대 덮어쓰지 않음)
                if key in ['min_trade_amount', 'log_level']:
                    print(f"  🔒 중요 설정 보존: {current_key_path}")
                    continue
                elif key == 'user_signal_threshold':
                    # user_signal_threshold는 AI가 자동 조절: 구버전 기본값(20)만 업데이트
                    if result[key] == 20:
                        result[key] = template_value
                        print(f"  🔄 user_signal_threshold 업데이트: 20 → {template_value} (AI 자동 조절 준비)")
                    else:
                        # AI가 조절한 값이면 보존
                        print(f"  🤖 user_signal_threshold 보존: {current_key_path}")
                    continue
                elif key == 'min_trade_amount':
                    # min_trade_amount는 사용자 설정 보존 (5는 정확한 최소값)
                    print(f"  🔒 min_trade_amount 보존: {current_key_path}")
                    continue
                elif key == 'symbol_min_notional_overrides':
                    # 심볼별 오버라이드는 기존 설정과 병합 (덮어쓰지 않음)
                    if key in result and isinstance(result[key], dict):
                        merged_overrides = result[key].copy()
                        merged_overrides.update(template_value)
                        result[key] = merged_overrides
                        print(f"  🔄 설정 병합: {current_key_path}")
                    else:
                        result[key] = template_value
                        print(f"  ➕ 설정 추가: {current_key_path}")
                    continue
                else:
                    # 기존 사용자 설정 보존 (템플릿으로 덮어쓰지 않음)
                    if result[key] != template_value:
                        print(f"  🔒 사용자 설정 보존: {current_key_path}")
                    # 변경하지 않음 (continue 생략 - 다음 키로 계속)

    return result


def detect_settings_changes(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """설정 변경사항 감지"""
    changes = []

    def compare_dicts(old_dict: Dict, new_dict: Dict, prefix: str = ""):
        for key in new_dict:
            full_key = f"{prefix}.{key}" if prefix else key

            if key not in old_dict:
                changes.append(f"새 설정 추가: {full_key}")
            elif isinstance(new_dict[key], dict) and isinstance(old_dict[key], dict):
                compare_dicts(old_dict[key], new_dict[key], full_key)
            elif new_dict[key] != old_dict[key]:
                changes.append(f"설정 변경: {full_key}")

    compare_dicts(old, new)
    return changes


def load_settings(*, persist_migrations: bool = True) -> Dict[str, Any]:
    """설정 파일 로드 (PyInstaller 배포 환경 대응).

    진단 도구는 ``persist_migrations=False``로 호출해 현재 파일을 변경하지
    않고 마이그레이션 결과만 메모리에서 검증할 수 있다.
    """
    try:
        # PyInstaller 환경 감지
        if getattr(sys, 'frozen', False):
            # 배포 환경: 사용자 Documents 폴더 사용
            from path_utils import get_config_dir
            config_dir = get_config_dir()
            config_path = os.path.join(config_dir, 'settings.json')
            template_path = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'config', 'settings_template.json')
        else:
            # 개발 환경: path_utils 사용
            from path_utils import get_config_dir
            config_dir = get_config_dir()
            config_path = os.path.join(config_dir, 'settings.json')
            template_path = os.path.join(os.path.dirname(__file__), 'settings_template.json')

        # 설정 파일이 존재하면 로드
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                print(f"✅ 설정 파일 로드: {config_path}")
            except Exception as e:
                print(f"⚠️ 설정 파일 읽기 오류: {e}")
                import traceback
                print(traceback.format_exc())
                # 빌드 환경에서도 확인 가능하도록
                if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                    print(f"[ERROR] 설정 파일 경로: {config_path}")
                # 기본 설정 반환
                return get_default_settings()

            loaded_settings_snapshot = copy.deepcopy(settings)
            needs_save = False

            # 🔄 템플릿에서 새로운 설정 업데이트
            settings = update_settings_from_template(settings)
            if settings != loaded_settings_snapshot:
                needs_save = True

            if _repair_tp_sl_settings(settings):
                print("🔧 비정상 TP/SL 설정을 fraction 단위로 복구했습니다.")
                needs_save = True

            # v3.9.0.0 안전 마이그레이션: 업데이트 전 설정에 마커가 없으면
            # AI 커스텀 실거래와 검증 미통과 제한운용을 최초 1회 명시적으로 OFF한다.
            # 이후 사용자가 직접 켜고 저장한 값은 다시 덮어쓰지 않는다.
            safety_marker = '_ai_custom_runtime_safe_default_v3900_applied'
            if not bool(loaded_settings_snapshot.get(safety_marker, False)):
                runtime_cfg = dict(settings.get('ai_custom_runtime', {}) or {})
                runtime_cfg['enabled'] = False
                runtime_cfg['allow_limited_live'] = False
                settings['ai_custom_runtime'] = runtime_cfg
                settings[safety_marker] = True
                print("🔒 AI 커스텀 실거래·미통과 제한운용 안전 기본값 OFF 적용")
                needs_save = True
            
            # 🔥 모델명 정규화: 잘못된 모델명 자동 수정
            if 'assistant_ai_model' in settings:
                model_name = settings['assistant_ai_model']
                model_fixes = {
                    'gpt4-4o': 'gpt-4o',
                    'gpt4o': 'gpt-4o',
                    'gpt-4-4o': 'gpt-4o',
                    'gpt4': 'gpt-4o',
                    'gpt-4': 'gpt-4o',
                }
                if model_name in model_fixes:
                    print(f"🔧 모델명 정규화: '{model_name}' → '{model_fixes[model_name]}'")
                    settings['assistant_ai_model'] = model_fixes[model_name]
                    needs_save = True

            # v3.9.0.3: 종료된 DeepSeek V3.1/deepseek-chat 별칭을 V4 Flash로 이전한다.
            deprecated_deepseek_models = {'deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat', 'deepseek-reasoner'}
            if 'api.deepseek.com' in str(settings.get('openai_base_url', '') or ''):
                for model_key in ('openai_model', 'assistant_ai_model'):
                    if str(settings.get(model_key) or '') in deprecated_deepseek_models:
                        settings[model_key] = 'deepseek-v4-flash'
                        needs_save = True
                roles = settings.get('ai_model_roles', {})
                if isinstance(roles, dict):
                    for role_key, role_model in list(roles.items()):
                        if isinstance(role_model, dict):
                            if (
                                str(role_model.get('provider') or '').lower() == 'deepseek'
                                and str(role_model.get('model') or '') in deprecated_deepseek_models
                            ):
                                role_model['model'] = 'deepseek-v4-flash'
                                needs_save = True
                        elif str(role_model or '') in deprecated_deepseek_models:
                            roles[role_key] = {
                                'provider': 'deepseek',
                                'model': 'deepseek-v4-flash',
                            }
                            needs_save = True
            arena_cfg = settings.get('alpha_arena', {})
            if isinstance(arena_cfg, dict) and str(arena_cfg.get('engine') or '') in deprecated_deepseek_models:
                arena_cfg['engine'] = 'deepseek-v4-flash'
                available = [
                    'deepseek-v4-flash' if str(item) in deprecated_deepseek_models else item
                    for item in list(arena_cfg.get('available_engines', []) or [])
                ]
                arena_cfg['available_engines'] = list(dict.fromkeys(available or ['deepseek-v4-flash']))
                needs_save = True
            if str(settings.get('alphaarena_ai_engine') or '') in deprecated_deepseek_models:
                settings['alphaarena_ai_engine'] = 'deepseek-v4-flash'
                needs_save = True

            # v3.9.0.3: 새 Router 스키마를 기존 OpenAI 모델 설정에서 무중단 생성한다.
            # 기존 키도 계속 유지하므로 이전 화면/모듈은 같은 값으로 동작한다.
            legacy_roles = dict(settings.get('ai_model_roles', {}) or {})
            models_cfg = dict(settings.get('ai_models', {}) or {})
            if not str(models_cfg.get('analyst') or ''):
                models_cfg['analyst'] = str(settings.get('openai_model') or 'gpt-4o-mini')
                needs_save = True
            if not str(models_cfg.get('assistant') or ''):
                models_cfg['assistant'] = str(
                    settings.get('assistant_ai_model') or models_cfg['analyst']
                )
                needs_save = True
            loaded_provider = str(
                loaded_settings_snapshot.get('ai_provider') or ''
            ).strip().lower()
            if not loaded_provider and 'api.deepseek.com' in str(
                loaded_settings_snapshot.get('openai_base_url', '') or ''
            ):
                loaded_provider = 'deepseek'
            active_provider = loaded_provider or str(
                settings.get('ai_provider') or 'openai'
            ).strip().lower()
            if settings.get('ai_provider') != active_provider:
                settings['ai_provider'] = active_provider
                needs_save = True
            role_defaults = {
                'frequent_cheap': str(models_cfg['analyst']),
                'standard': str(models_cfg['analyst']),
                'premium': str(models_cfg['assistant']),
            }
            normalized_roles = {}
            for role_key, fallback_model in role_defaults.items():
                raw_role = legacy_roles.get(role_key)
                if isinstance(raw_role, dict):
                    role_provider = str(raw_role.get('provider') or active_provider).strip().lower()
                    role_model = str(raw_role.get('model') or fallback_model).strip()
                else:
                    role_provider = active_provider
                    role_model = str(raw_role or fallback_model).strip()
                normalized_roles[role_key] = {
                    'provider': role_provider,
                    'model': role_model,
                }
            if legacy_roles != normalized_roles:
                settings['ai_model_roles'] = normalized_roles
                needs_save = True
            models_cfg['roles'] = copy.deepcopy(normalized_roles)
            settings['ai_models'] = models_cfg

            profiles_cfg = dict(settings.get('ai_provider_profiles', {}) or {})
            loaded_profiles = loaded_settings_snapshot.get('ai_provider_profiles', {})
            analyst_profile = dict(profiles_cfg.get('analyst', {}) or {})
            assistant_profile = dict(profiles_cfg.get('assistant', {}) or {})
            transcription_profile = dict(profiles_cfg.get('transcription', {}) or {})
            loaded_analyst = (
                loaded_profiles.get('analyst', {})
                if isinstance(loaded_profiles, dict)
                else {}
            )
            loaded_assistant = (
                loaded_profiles.get('assistant', {})
                if isinstance(loaded_profiles, dict)
                else {}
            )
            if not isinstance(loaded_analyst, dict) or not str(loaded_analyst.get('provider') or ''):
                analyst_profile['provider'] = active_provider
                needs_save = True
            if not isinstance(loaded_analyst, dict) or not str(loaded_analyst.get('model') or ''):
                analyst_profile['model'] = models_cfg['analyst']
                needs_save = True
            if not isinstance(loaded_assistant, dict) or not str(loaded_assistant.get('provider') or ''):
                assistant_profile['provider'] = active_provider
                needs_save = True
            if not isinstance(loaded_assistant, dict) or not str(loaded_assistant.get('model') or ''):
                assistant_profile['model'] = models_cfg['assistant']
                needs_save = True
            transcription_cfg = dict(settings.get('ai_custom_transcription', {}) or {})
            if not str(transcription_cfg.get('provider') or ''):
                transcription_cfg['provider'] = 'openai'
                needs_save = True
            if not str(transcription_cfg.get('model') or ''):
                transcription_cfg['model'] = 'gpt-4o-mini-transcribe'
                needs_save = True
            settings['ai_custom_transcription'] = transcription_cfg
            if not str(transcription_profile.get('provider') or ''):
                transcription_profile['provider'] = str(transcription_cfg['provider'])
                needs_save = True
            if not str(transcription_profile.get('model') or ''):
                transcription_profile['model'] = str(transcription_cfg['model'])
                needs_save = True
            profiles_cfg['analyst'] = analyst_profile
            profiles_cfg['assistant'] = assistant_profile
            profiles_cfg['transcription'] = transcription_profile
            settings['ai_provider_profiles'] = profiles_cfg
            
            # 🔥 frequency_thresholds 형식 자동 수정 (잘못된 리스트 형식을 딕셔너리로 변환)
            fixed_frequency = False
            try:
                trading_strategies = settings.get('trading_strategies', {})
                scalping = trading_strategies.get('scalping', {})
                criteria = scalping.get('criteria', {})
                freq_config = criteria.get('frequency_thresholds')
                
                # 잘못된 형식 감지 및 수정
                if freq_config is not None:
                    # 리스트 형식이면서 소수점 값이거나 길이가 4개인 경우
                    if isinstance(freq_config, list):
                        if len(freq_config) == 4 and all(isinstance(x, (int, float)) and 0 < x < 1 for x in freq_config):
                            # 잘못된 소수점 리스트 형식 → 올바른 딕셔너리 형식으로 변환
                            print(f"🔧 frequency_thresholds 형식 자동 수정: {freq_config} → 딕셔너리 형식")
                            criteria['frequency_thresholds'] = {
                                'major': [5000, 20000, 50000, 200000, 500000],
                                'altcoin': [1000, 5000, 10000, 50000, 100000]
                            }
                            fixed_frequency = True
                        elif len(freq_config) == 5 and all(isinstance(x, (int, float)) and x >= 1 for x in freq_config):
                            # 정수 리스트 형식 → 딕셔너리 형식으로 변환 (하위 호환성)
                            print(f"🔧 frequency_thresholds 형식 업그레이드: 리스트 → 딕셔너리")
                            criteria['frequency_thresholds'] = {
                                'major': freq_config,
                                'altcoin': freq_config
                            }
                            fixed_frequency = True
                    # 딕셔너리가 아닌 다른 타입인 경우
                    elif not isinstance(freq_config, dict):
                        print(f"🔧 frequency_thresholds 타입 오류 자동 수정: {type(freq_config)} → 딕셔너리 형식")
                        criteria['frequency_thresholds'] = {
                            'major': [5000, 20000, 50000, 200000, 500000],
                            'altcoin': [1000, 5000, 10000, 50000, 100000]
                        }
                        fixed_frequency = True
                    # 딕셔너리 형식이지만 'major' 또는 'altcoin' 키가 없는 경우
                    elif isinstance(freq_config, dict):
                        if 'major' not in freq_config or 'altcoin' not in freq_config:
                            print(f"🔧 frequency_thresholds 딕셔너리 키 누락 수정")
                            if 'major' not in freq_config:
                                freq_config['major'] = [5000, 20000, 50000, 200000, 500000]
                            if 'altcoin' not in freq_config:
                                freq_config['altcoin'] = [1000, 5000, 10000, 50000, 100000]
                            fixed_frequency = True
            except Exception as e:
                print(f"⚠️ frequency_thresholds 형식 검사 중 오류 (무시): {e}")
            
            # 수정된 경우 설정 파일 저장
            if fixed_frequency:
                print("✅ frequency_thresholds 형식 자동 수정 완료 및 저장")
                needs_save = True

            # UI 설정이 없으면 강제로 추가
            if 'ui_settings' not in settings:
                settings['ui_settings'] = {
                    'always_on_top': False,
                    'window_geometry': '1400x900',
                    'remember_window_position': True,
                    'auto_update_enabled': True,
                    'auto_update_check_interval_hours': 6,
                    'auto_update_auto_download': True,
                    'auto_update_auto_apply_on_exit': True,
                    'auto_update_open_position_action': 'defer',
                    'auto_update_release_repo': 'nwsoft/ai-trading-client',
                }
                print("  ➕ UI 설정 강제 추가")
                needs_save = True

            # v3.9.0.2 안전 마이그레이션: 과거 AI 자동적용 설정을 더 이상 허용하지 않는다.
            if str(settings.get('assistant_apply_mode', 'user_confirm') or 'user_confirm').lower() != 'user_confirm':
                settings['assistant_apply_mode'] = 'user_confirm'
                print("  🔒 AI 설정 적용 방식을 사용자 최종확인으로 고정")
                needs_save = True

            # adminjung 계정 최초 1회 방송 리플레이 기본값 자동 초기화
            settings, replay_init_changed = _apply_adminjung_broadcast_replay_defaults(settings)
            if replay_init_changed:
                needs_save = True

            # v3.9.0.4: 실행 설정을 하나의 정본으로 정리한다.
            settings, contract_report, contract_changed = normalize_settings_contract(settings)
            if contract_changed:
                print(
                    "🧭 설정 정본 v3.9.0.4 적용: "
                    f"{len(contract_report.get('normalized_keys', []))}개 항목 정리"
                )
                needs_save = True

            settings, stock_contract_changed = migrate_stock_broker_api_contracts(settings)
            if stock_contract_changed:
                print("📈 증권 API 계약명/레거시 선택지 v3.9.0.5 이전 완료")
                needs_save = True

            # 변경이 있을 때만 저장 (로그인/초기화 시 불필요한 디스크 I/O 방지)
            if needs_save and persist_migrations:
                save_settings(settings)
            elif needs_save:
                print("ℹ️ 읽기 전용 설정 점검: 마이그레이션 결과를 저장하지 않았습니다.")

            from trading.ai.credentials import hydrate_ai_credentials
            return hydrate_ai_credentials(settings)

        # 설정 파일이 없으면 템플릿에서 생성
        print(f"⚠️ 설정 파일 없음, 템플릿에서 생성: {config_path}")

        # 템플릿 파일 로드
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            print(f"✅ 템플릿에서 로드: {template_path}")
        else:
            # 템플릿도 없으면 기본 설정 사용
            settings = get_default_settings()
            print("⚠️ 템플릿 파일 없음, 기본 설정 사용")

        # adminjung 계정 최초 1회 방송 리플레이 기본값 자동 초기화
        settings, _ = _apply_adminjung_broadcast_replay_defaults(settings)
        settings, _, _ = normalize_settings_contract(settings)
        settings, _ = migrate_stock_broker_api_contracts(settings)

        # 사용자 설정 파일 생성
        if persist_migrations:
            save_settings(settings)
            print(f"✅ 사용자 설정 파일 생성: {config_path}")
        else:
            print("ℹ️ 읽기 전용 설정 점검: 사용자 설정 파일을 생성하지 않았습니다.")

        from trading.ai.credentials import hydrate_ai_credentials
        return hydrate_ai_credentials(settings)

    except Exception as e:
        print(f"설정 파일 로드 오류: {e}")
        return get_default_settings()


def _get_settings_paths() -> tuple[str, str]:
    """설정 파일 경로와 백업 디렉토리 경로를 반환한다."""
    from path_utils import get_config_dir
    config_dir = get_config_dir()
    config_path = os.path.join(config_dir, 'settings.json')
    backup_dir = os.path.join(config_dir, 'backups')
    return config_path, backup_dir


def _apply_adminjung_broadcast_replay_defaults(settings: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """adminjung 계정의 방송 리플레이 기본값을 최초 1회 자동 초기화한다."""
    changed = False
    try:
        from path_utils import get_current_user_account

        current_user = str(get_current_user_account() or settings.get('user_id') or settings.get('username') or '').strip().lower()
        if current_user != 'adminjung':
            return settings, False

        if bool(settings.get('broadcast_replay_auto_initialized', False)):
            return settings, False

        settings['broadcast_replay_enabled'] = True
        settings['broadcast_replay_source_account'] = str(settings.get('broadcast_replay_source_account') or 'nwsoft').strip() or 'nwsoft'
        settings['broadcast_replay_auto_initialized'] = True
        changed = True
        print("✅ adminjung 방송 리플레이 기본값 자동 초기화 완료")
    except Exception:
        return settings, False

    return settings, changed


def create_settings_backup(retention: int = 3) -> str:
    """현재 settings.json을 백업하고 최신 retention개만 유지한다.

    Returns:
        생성된 백업 파일 경로. 백업 대상이 없으면 빈 문자열 반환.
    """
    try:
        config_path, backup_dir = _get_settings_paths()
        if not os.path.exists(config_path):
            return ''

        os.makedirs(backup_dir, exist_ok=True)
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_path = os.path.join(backup_dir, f'settings_{timestamp}.json')
        shutil.copy2(config_path, backup_path)
        try:
            os.chmod(backup_path, 0o600)
        except OSError:
            pass

        # 최신 retention개만 유지
        backups = sorted(
            [
                os.path.join(backup_dir, name)
                for name in os.listdir(backup_dir)
                if name.startswith('settings_') and name.endswith('.json')
            ],
            # copy2는 원본 settings.json의 mtime도 복사하므로 연속 저장 시
            # mtime 정렬이 동률이 될 수 있다. 파일명의 마이크로초 타임스탬프가
            # 백업 생성 순서를 정확히 보존한다.
            key=lambda p: os.path.basename(p),
            reverse=True,
        )
        for stale in backups[retention:]:
            try:
                os.remove(stale)
            except Exception:
                pass

        return backup_path
    except Exception as e:
        print(f"설정 백업 생성 오류: {e}")
        return ''


def list_settings_backups(limit: int = 20) -> List[str]:
    """백업 파일 경로 목록을 최신순으로 반환한다."""
    try:
        _, backup_dir = _get_settings_paths()
        if not os.path.isdir(backup_dir):
            return []
        backups = [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.startswith('settings_') and name.endswith('.json')
        ]
        backups.sort(key=lambda p: os.path.basename(p), reverse=True)
        return backups[: max(0, int(limit))]
    except Exception as e:
        print(f"설정 백업 목록 조회 오류: {e}")
        return []


def restore_settings_from_backup(backup_path: str) -> bool:
    """지정한 백업 파일로 settings.json을 복구한다."""
    try:
        if not backup_path or not os.path.exists(backup_path):
            print("⚠️ 복구할 백업 파일이 없습니다.")
            return False

        # 복구 직전 현재 설정을 한번 더 백업해 롤백 여지 확보
        create_settings_backup(retention=3)

        config_path, _ = _get_settings_paths()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        shutil.copy2(backup_path, config_path)
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass
        print(f"✅ 설정 복구 완료: {backup_path} -> {config_path}")
        return True
    except Exception as e:
        print(f"설정 복구 오류: {e}")
        return False


def save_settings(settings: Dict[str, Any]) -> bool:
    """설정 파일 저장 (PyInstaller 배포 환경 대응)"""
    try:
        config_path, _ = _get_settings_paths()
        from trading.ai.credentials import prepare_ai_credentials_for_storage

        settings_to_save, _ = prepare_ai_credentials_for_storage(settings)
        settings_to_save, _, _ = normalize_settings_contract(settings_to_save)
        if _repair_tp_sl_settings(settings_to_save):
            print("🔧 저장 전 비정상 TP/SL 설정을 복구했습니다.")

        # 디렉토리 생성
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        # 기존 설정 파일이 있으면 자동 백업 (최신 3개 유지)
        if os.path.exists(config_path):
            create_settings_backup(retention=3)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass
        print(f"✅ 설정 파일 저장: {config_path}")
        return True

    except Exception as e:
        print(f"설정 파일 저장 오류: {e}")
        return False


def get_default_settings() -> Dict[str, Any]:
    """기본 설정 반환"""
    # v3.9.0.4부터 settings_template.json을 새 설치와 초기화의 단일 정본으로 사용한다.
    template = load_settings_template()
    if template:
        normalized, _, _ = normalize_settings_contract(template)
        return normalized

    # 패키지 손상 등으로 템플릿을 읽지 못할 때만 사용하는 최소 호환 폴백.
    return {
        # 거래 설정
        'default_leverage': 10,
        'default_margin_type': 'ISOLATED',
        'default_tp': 0.0018,
        'default_sl': 0.002,
        'rr_guardrail': {
            'enabled': True,
            'min_rr_ratio': 2.0,
            'strict': True,
            'adaptive': {
                'enabled': True,
                'rr_min': 1.8,
                'rr_max': 2.2,
                'volatility_low': 0.01,
                'volatility_high': 0.02,
                'update_interval_seconds': 21600,
                'hysteresis': 0.10,
                'rollback_mdd_delta': 20.0
            }
        },
        'entry_order_type': 'market',
        'tp_sl_settings': {
            'enabled': True,
            'trigger_price_source': 'mark',
            'tp_order_type': 'market',
            'sl_order_type': 'market'
        },
        'backup_tp_sl_settings': {
            'enabled': True,
            'description': '백업 TP/SL 설정 (동적 임계값보다 높게 설정하여 실시간 모니터링이 먼저 청산되도록 함)',
            'multipliers': {
                'high_volatility': 3.0,
                'medium_volatility': 2.5,
                'low_volatility': 2.0
            },
            'safety_limits': {
                'tp_min': 0.01,
                'tp_max': 0.05,
                'sl_min': 0.008,
                'sl_max': 0.03
            },
            'volatility_thresholds': {
                'high': 0.02,
                'medium': 0.01
            }
        },
        'exchange_tp_sl_overrides': {
            'binance': {},
            'bybit': {'trigger_price_source': 'mark'},
            'okx': {'trigger_price_source': 'mark', 'margin_mode': 'cross'},
            'bitget': {'trigger_price_source': 'mark'}
        },
        'ai_exit_settings': {
            'min_profit_for_exit': 0.0012,
            'max_profit_for_exit': 0.003,
            'min_loss_for_exit': -0.0015,
            'max_loss_for_exit': -0.001
        },
        'auto_trade_interval': 10,
        'execution_history_sync_interval_seconds': 300,
        'pending_order_poll_interval_seconds': 10,
        'paper_trading': False,
        'enable_stock_live_order': False,
        'asset_stop_position_policy': 'keep_with_tp_sl',
        # 하위 호환: 레거시 키 유지
        'stock_stop_position_policy': 'keep_with_tp_sl',
        'demo_mode': False,
        'broadcast_replay_enabled': False,
        'broadcast_replay_source_account': '',
        'broadcast_display_override_enabled': False,
        'broadcast_display_balance_usdt': None,
        'broadcast_display_total_trades': None,
        'broadcast_display_win_rate_percent': None,
        'broadcast_display_total_pnl_usdt': None,
        'broadcast_display_total_fees_usdt': None,
        'ai_enabled': True,
        'ai_cost_control': {
            'enabled': True,
            'stable_state_cache_sec': 1800,
            'exploration_interval_sec': 1800,
            'minimum_event_interval_sec': 300,
            'price_change_bps': 15.0,
            'rsi_event_low': 35.0,
            'rsi_event_high': 65.0,
            'max_daily_market_calls': 240,
            'max_daily_calls_per_exchange': 40,
            'max_monthly_market_calls': 6000,
            'hard_max_daily_market_calls': 240,
            'hard_max_daily_calls_per_exchange': 40,
            'hard_max_monthly_market_calls': 6000,
            'allow_high_cost_limits': False,
            'provider_budget_enabled': True,
            'max_daily_automatic_ai_calls': 360,
            'max_monthly_automatic_ai_calls': 9000,
            'max_daily_ai_calls_by_role': {
                'signal_analysis': 240,
                'pattern_similarity': 40,
                'pre_entry': 40,
                'position_sizing': 40,
                'loss_analysis': 50,
                'profit_analysis': 50,
                'daily_report': 5,
                'diagnosis': 10,
                'parameter_optimization': 10,
            },
            'max_cache_entries': 1000,
            # 진입 후보의 AI 포지션 크기 제안은 시장분석 호출과 별도이므로
            # 신선한 캐시를 우선하고 의미 있는 상태 변경에만 다시 호출한다.
            'position_sizing_cache_sec': 900,
            'position_sizing_retry_cooldown_sec': 120,
            'position_sizing_price_change_bps': 100.0,
            'position_sizing_confidence_delta': 0.10,
            'position_sizing_max_cache_entries': 100,
            'pattern_similarity_cache_sec': 900,
            'pattern_similarity_retry_cooldown_sec': 120,
            'pattern_similarity_max_cache_entries': 300,
        },
        # API 설정
        'binance_api_key': '',
        'binance_secret_key': '',
        'openai_api_key': '',
        'openai_base_url': '',
        'ai_provider': 'openai',
            'ai_credentials': {
                'openai': {'api_key': '', 'base_url': ''},
                'deepseek': {'api_key': '', 'base_url': 'https://api.deepseek.com'},
                'kimi': {'api_key': '', 'base_url': 'https://api.moonshot.ai/v1'},
                'anthropic': {'api_key': '', 'base_url': 'https://api.anthropic.com'},
                'gemini': {'api_key': '', 'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/'},
            },
        'ai_provider_profiles': {
            'analyst': {'provider': 'openai', 'model': ''},
            'assistant': {'provider': 'openai', 'model': ''},
            'transcription': {'provider': 'openai', 'model': 'gpt-4o-mini-transcribe'},
        },
        'ai_models': {
            'analyst': '',
            'assistant': '',
            'roles': {},
        },
        'upbit_api_key': '',
        'upbit_secret_key': '',
        'bithumb_api_key': '',
        'bithumb_secret_key': '',
        'bitget_api_key': '',
        'bitget_secret_key': '',
        'bitget_password': '',
        'okx_api_key': '',
        'okx_secret_key': '',
        'okx_passphrase': '',
        'bybit_api_key': '',
        'bybit_secret_key': '',
        'selected_exchange': 'binance',
        'enabled_exchanges': ['binance'],
        # 사용자가 명시적으로 고른 거래소만 LIVE 신규 주문을 허용한다.
        'trade_enabled_exchanges': [],
        # 비어 있으면 enabled_exchanges 전체를 학습한다.
        'learning_enabled_exchanges': [],
        'multi_venue_execution': {
            'enabled': True,
            # 사용자가 실제 주문 대상으로 고른 거래소마다 독립 실행한다.
            'mode': 'parallel',
            'opportunity_window_sec': 60,
            'duplicate_window_sec': 120,
            # 0은 실제 주문 대상으로 고른 거래소 수를 그대로 허용한다.
            'max_parallel_targets': 0,
            # 값이 0이면 통화별 별도 상한을 두지 않고 기존 계좌 가드레일을 사용한다.
            'max_loss_by_currency': {'USDT': 0.0, 'KRW': 0.0},
            'best_target': '',
            'target_cost_bps': {},
        },
        'enabled_stock_brokers': [],
        'stock_broker_configs': {
            'kiwoom': {
                'enabled': False,
                'api_type': 'openapi_plus',
                'api_version': 'pykiwoom',
                'allow_live_order': False,
                'account_no': '',
                'password': '',
                'asset_types': ['stock', 'etf'],
                'cert_password': '',
                'id': ''
            },
            'shinhan': {
                'enabled': False,
                'api_type': 'partner_rest',
                'api_version': 'shinhan_openapi_v2',
                'allow_live_order': False,
                'partner_profile': {},
                'app_key': '',
                'app_secret': '',
                'account_no': '',
                'password': '',
                'asset_types': ['stock', 'etf'],
                'cert_password': '',
                'id': ''
            },
            'miraeAsset': {
                'enabled': False,
                'api_type': 'partner_rest',
                'api_version': 'mirae_partner_profile',
                'allow_live_order': False,
                'partner_profile': {},
                'app_key': '',
                'app_secret': '',
                'account_no': '',
                'password': '',
                'asset_types': ['stock', 'etf'],
                'cert_password': '',
                'id': ''
            },
            'koreaInvestment': {
                'enabled': False,
                'api_type': 'rest',
                'api_version': 'kis_openapi_v1',
                'allow_live_order': False,
                'sandbox': False,
                'app_key': '',
                'app_secret': '',
                'account_no': '',
                'password': '',
                'asset_types': ['stock', 'etf'],
                'cert_password': '',
                'id': ''
            }
        },
        'stock_auto_trading': {
            'auto_start': False,
            'enabled': False,
            'interval_sec': 60,
            'buy_threshold': 70.0,
            'sell_threshold': 30.0,
            'order_type': 'MARKET',
            'quantity': 1.0,
            'max_orders_per_cycle': 1,
            'symbols': [],
            'risk_guard_enabled': True,
            'max_consecutive_losses': 3,
            'daily_max_loss': 500000.0,
            'cooldown_sec_per_symbol': 300,
            'risk_governance_enabled': True,
            'global_kill_switch': False,
            'weekly_max_loss': 1500000.0,
            'monthly_max_loss': 4000000.0,
            'max_symbol_weight_percent': 35.0,
            'broker_overrides': {},
            'enable_exit_policy': True,
            'take_profit_percent': 5.0,
            'stop_loss_percent': 8.0,
            'etf_take_profit_percent': 4.0,
            'etf_stop_loss_percent': 6.0,
            'use_signal_exit': True,
            'etf_alert_exit': True,
        },
        'stock_search_profile': {
            'recent_codes': [],
            'favorites': [],
        },
        'openai_model': 'gpt-5.6-luna',
        'assistant_ai_model': 'gpt-5.6-terra',
        'ai_model_roles': {
            'frequent_cheap': {'provider': 'openai', 'model': 'gpt-5.6-luna'},
            'standard': {'provider': 'openai', 'model': 'gpt-5.6-terra'},
            'premium': {'provider': 'openai', 'model': 'gpt-5.6-sol'},
        },
        'assistant_response_mode': 'standard',
        'assistant_token_budget': {
            'standard': {'max_input_chars': 12000, 'max_output_tokens': 1200},
            'saver': {'max_input_chars': 6000, 'max_output_tokens': 500},
            'premium': {'max_input_chars': 20000, 'max_output_tokens': 2200},
        },
        'assistant_context_policy': {
            'standard': {'include_recent_turns': 8, 'include_summary': True, 'include_market_snapshot': True},
            'saver': {'include_recent_turns': 4, 'include_summary': True, 'include_market_snapshot': True},
            'premium': {'include_recent_turns': 12, 'include_summary': True, 'include_market_snapshot': True},
        },
        'ai_custom_transcription': {
            'enabled': True,
            'provider': 'openai',
            'model': 'gpt-4o-mini-transcribe',
            'max_duration_minutes': 45,
            'max_file_mb': 24,
        },
        'ai_custom_runtime': {
            'enabled': False,
            'allow_limited_live': False,
            'limited_max_leverage': 1,
            'limited_max_position_size': 0.01,
        },
        'ai_custom_features': {
            'profile': 'standard',
            'overrides': {},
        },
        '_ai_custom_runtime_safe_default_v3900_applied': True,
        'assistant_apply_mode': 'user_confirm',
        'assistant_voice': {
            'enabled': False,
            'auto_tts': False,
            'lang': 'ko-KR',
            'rate': 180,
        },
        'backend_url': 'http://localhost:8000',
        'api_timeout': 10,

        # AI 설정
        'ai_signal_enabled': True,
        'rsi_period': 14,
        'ma_period': 20,
        'bb_period': 20,
        'optimization_interval': 6,
        'learning_period': 7,
        'ai_learning_min_samples': 20,
        'federated_learning': {
            'enabled': False,
            'batch_enabled': False,
            'upload_enabled': False,
            'batch_size': 128,
            'max_pending_batches': 100,
            'sync_interval_minutes': 60,
            'server_base_url': '',
            'api_key': '',
            'timeout_sec': 5,
            'anonymization_salt': ''
        },
        'saas_preparation': {
            'enabled': False,
            'tenant_mode': 'single',
            'telemetry_enabled': False,
            'subscription_tier': 'starter',
            'feature_flags': {
                'fl_beta': False,
                'api_metering': False,
                'model_marketplace': False
            }
        },

        # 로그 설정
        'log_level': 'DEBUG',
        'log_file_size_limit': 200,
        'log_retention_days': 30,
        'position_sizing_debug': False,
        'position_sizing_persist': False,
        'analytics_refresh_interval_minutes': 30,
        'clear_logs_on_restart': True,
        'db_backup_interval': 24,
        'db_backup_retention': 7,
        'cache_timeout': 30,
        'max_concurrent_requests': 10,

        # 포지션 설정
        'max_positions': 3,  # 기본값: 다중포지션 모드 (집중모드: 1, 다중포지션: 3)
        'position_mode': 'multi',  # 'focus' 또는 'multi'
        'min_trade_amount': 5,
        'slippage_tolerance': 0.08,
        'include_fees': True,
        'symbol_min_notional_overrides': {
            'ETHUSDT': 20.0
        },

        # 코인 선택 설정
        'num_alt_coins': 10,
        'num_major_coins': 5,
        'min_total_coins': 10,
        'max_total_coins': 20,

        'market_regime_coins': {
            'bear': {'min': 10, 'max': 10},
            'neutral': {'min': 15, 'max': 15},
            'bull': {'min': 20, 'max': 20},
            'volatile': {'min': 12, 'max': 12},
            'normal': {'min': 15, 'max': 15}
        },

        # 동적 코인 선택 비율 (v3.8.8.8)
        'coin_selection_ratios': {
            'bull': {
                'altcoin_ratio': 0.8,
                'major_ratio': 0.2,
                'description': '강세장 - 알트코인 비중 높임 (변동성 활용)'
            },
            'bear': {
                'altcoin_ratio': 0.4,
                'major_ratio': 0.6,
                'description': '약세장 - 메이저 코인 비중 높임 (안정성 중시)'
            },
            'volatile': {
                'altcoin_ratio': 0.6,
                'major_ratio': 0.4,
                'description': '고변동성 - 균형잡힌 포트폴리오'
            },
            'normal': {
                'altcoin_ratio': 0.7,
                'major_ratio': 0.3,
                'description': '정상장 - 기본 비율 유지'
            }
        },

        # 동적 시장 분석 임계값 (v3.8.8.8)
        'market_analysis_thresholds': {
            'bull': {
                'trend_slope_threshold': 0.03,
                'volume_ratio_threshold': 1.2,
                'volatility_threshold': 2.0,
                'rsi_overbought': 75,
                'rsi_oversold': 25
            },
            'bear': {
                'trend_slope_threshold': 0.08,
                'volume_ratio_threshold': 2.0,
                'volatility_threshold': 5.0,
                'rsi_overbought': 65,
                'rsi_oversold': 35
            },
            'volatile': {
                'trend_slope_threshold': 0.02,
                'volume_ratio_threshold': 1.8,
                'volatility_threshold': 4.0,
                'rsi_overbought': 80,
                'rsi_oversold': 20
            },
            'normal': {
                'trend_slope_threshold': 0.05,
                'volume_ratio_threshold': 1.5,
                'volatility_threshold': 3.0,
                'rsi_overbought': 70,
                'rsi_oversold': 30
            }
        },

        # 거래 전략
        'trading_strategies': {
            'scalping': {
                'weights': {
                    'volatility_weight': 0.30,
                    'volume_stability_weight': 0.25,
                    'trend_weight': 0.25,
                    'frequency_weight': 0.10,
                    'depth_weight': 0.05
                },
                'criteria': {
                    'volatility_thresholds': [0.8, 1.5, 3.0, 6.0, 10.0],
                    'volume_spike_thresholds': [1.2, 2.0, 3.0, 4.0],
                    'trend_thresholds': [15, 35, 60],
                    'frequency_thresholds': {
                        'major': [5000, 20000, 50000, 200000, 500000],
                        'altcoin': [1000, 5000, 10000, 50000, 100000]
                    },
                    'depth_thresholds': [1e5],
                    'volume_thresholds': {
                        'optimal_min': 1000000,
                        'optimal_max': 100000000,
                        'acceptable_min': 500000,
                        'acceptable_max': 1000000000
                    }
                },
                'base_scores': {
                    'volatility_initial': 50,
                    'volume_initial': 50,
                    'trend_base': 60,
                    'frequency_base': 70,
                    'technical_base': 60,
                    'risk_base': 70
                },
                'adjustment_factors': {
                    'default': 1.0,
                    'market_low': 0.7,
                    'market_normal': 0.85,
                    'market_high': 0.95,
                    'fallback_levels': [0.7, 0.5, 0.3, 0.1]
                }
            }
        },

        # 신호 임계값
        'signal_thresholds': {
            'rsi_extreme_oversold': 20,
            'rsi_oversold': 28,
            'rsi_overbought': 72,
            'rsi_extreme_overbought': 80,
            'momentum_threshold': 0.00045,
            'trend_momentum_threshold': 0.0016
        },
        'exchange_signal_thresholds': {
            'binance': {
                'rsi_extreme_oversold': 20,
                'rsi_oversold': 28,
                'rsi_overbought': 72,
                'rsi_extreme_overbought': 80,
                'momentum_threshold': 0.00045,
                'trend_momentum_threshold': 0.0016
            },
            'bybit': {
                'rsi_extreme_oversold': 20,
                'rsi_oversold': 28,
                'rsi_overbought': 72,
                'rsi_extreme_overbought': 80,
                'momentum_threshold': 0.00045,
                'trend_momentum_threshold': 0.0016
            },
            'okx': {
                'rsi_extreme_oversold': 20,
                'rsi_oversold': 28,
                'rsi_overbought': 72,
                'rsi_extreme_overbought': 80,
                'momentum_threshold': 0.00045,
                'trend_momentum_threshold': 0.0016
            },
            'bitget': {
                'rsi_extreme_oversold': 20,
                'rsi_oversold': 28,
                'rsi_overbought': 72,
                'rsi_extreme_overbought': 80,
                'momentum_threshold': 0.00045,
                'trend_momentum_threshold': 0.0016
            },
            'upbit': {
                'rsi_extreme_oversold': 15,
                'rsi_oversold': 20,
                'rsi_overbought': 80,
                'rsi_extreme_overbought': 85,
                'momentum_threshold': 0.002,
                'trend_momentum_threshold': 0.004
            },
            'bithumb': {
                'rsi_extreme_oversold': 22,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'rsi_extreme_overbought': 78,
                'momentum_threshold': 0.00035,
                'trend_momentum_threshold': 0.0012
            }
        },

        'analyzer_settings': {
            'user_signal_threshold': 68,
            'exchange_signal_thresholds': {},
            'coin_multipliers': {
                'major': 0.65,
                'altcoin': 0.8
            },
            'market_multipliers': {
                'low': 0.25,
                'normal': 0.85,
                'high': 1.0
            },
            'volatility_thresholds': {
                'major_min': 0.0002,
                'major_max': 0.015,
                'altcoin_min': 0.0006,
                'altcoin_max': 0.020
            },
            'base_trading_params': {
                'tp_percent': 0.0018,
                'sl_percent': 0.002,
                'leverage': 10,
                'position_size': 0.10
            }
        },

        'symbol_filters': {
            'excluded_symbols': [
                'ALPACAUSDT',
                'B3USDT',
                'WUSDT',
                'FUSDT',
                'SUSDT',
                'HUSDT',
                'BUSDT',
                'TUSDT',
                'AUSDT',
                'GUSDT',
                'DUSDT',
                'MUSDT'
            ],
            'excluded_patterns': [
                'USDCUSDT',
                'USDTBTC',
                'USDTUSDT',
                'BTCBTC',
                'ETHETH',
                'BNBBNB',
                'ADAADA',
                'FART',
                'PENGU',
                'PUMP',
                'HYPE',
                'SOON',
                'COIN',
                'TOKEN',
                'MOON',
                'SHIB',
                'DOGE',
                'PEPE',
                'BONK',
                'INU',
                'CAT',
                'FLOKI'
            ],
            'min_symbol_length': 3,
            'max_symbol_length': 12
        },

        'ai_trading_preferences': {
            'risk_tolerance': 'MODERATE',
            'balance_utilization_limit': 0.20,
            'max_position_size_factor': 5.0,
            'min_position_size_factor': 0.5,
            'risk_levels': {
                'conservative': {
                    'balance_utilization': 0.12,
                    'max_position_factor': 2.0,
                    'description': '보수적 접근 - 안전 우선'
                },
                'moderate': {
                    'balance_utilization': 0.25,
                    'max_position_factor': 5.0,
                    'description': '중간 접근 - 균형 잡힌 리스크'
                },
                'aggressive': {
                    'balance_utilization': 0.40,
                    'max_position_factor': 10.0,
                    'description': '적극적 접근 - 수익 극대화'
                }
            },
            'ai_decision_history': True,
            'user_feedback_enabled': True
        },
        'exchange_position_factors': {
            'binance': 1.0,
            'bybit': 0.9,
            'okx': 0.8,
            'bitget': 0.85,
            'upbit': 0.7,
            'bithumb': 0.7
        },
        'dynamic_thresholds_enabled': True,
        'dynamic_thresholds_profile': {
            'low': {
                'rsi_oversold_delta': -2,
                'rsi_overbought_delta': 2,
                'momentum_threshold_scale': 0.9
            },
            'high': {
                'rsi_oversold_delta': -4,
                'rsi_overbought_delta': 4,
                'momentum_threshold_scale': 1.25
            }
        },
        'dynamic_thresholds_high_multiplier': 1.5,
        'dynamic_thresholds_hysteresis_enabled': True,
        'dynamic_thresholds_hysteresis': {
            'high_enter_mult': 1.65,
            'high_exit_mult': 1.28,
            'low_enter_mult': 1.0,
            'low_exit_mult': 1.1
        },
        'dynamic_thresholds_mode': 'auto',
        'dynamic_thresholds_manual_regime': 'NORMAL',
        'operation_mode': 'guided',
        'tuning': {
            'slippage_abs_warn': 0.0010,
            'slippage_abs_high': 0.0020,
            'adjust_step_volume': 0.15,
            'adjust_step_volatility': 5.0,
            'min_min_quote_volume': 5000000,
            'max_min_quote_volume': 50000000,
            'min_volatility_max': 10.0,
            'max_volatility_max': 40.0
        },
        'exchange_risk_overrides': {
            'binance': {'max_positions': 3, 'max_position_size': 0.02, 'min_position_size': 0.001, 'max_leverage': 20},
            'bybit': {'max_positions': 3, 'max_position_size': 0.008, 'min_position_size': 0.001, 'max_leverage': 20},
            'okx': {'max_positions': 3, 'max_position_size': 0.006, 'min_position_size': 0.001, 'max_leverage': 20},
            'bitget': {'max_positions': 3, 'max_position_size': 0.007, 'min_position_size': 0.001, 'max_leverage': 20},
            'upbit': {'max_positions': 3, 'max_position_size': 0.005, 'min_position_size': 0.001},
            'bithumb': {'max_positions': 3, 'max_position_size': 0.005, 'min_position_size': 0.001}
        },
        'strategy_config': {
            'volatility_thresholds': [1.0, 3.0, 5.0, 7.0, 10.0],
            'volume_thresholds': {'optimal_min': 1000000, 'optimal_max': 100000000, 'acceptable_min': 500000, 'acceptable_max': 1000000000},
            'weights': {
                'volatility_weight': 0.30,
                'volume_stability_weight': 0.25,
                'trend_weight': 0.25,
                'frequency_weight': 0.10,
                'rsi_weight': 0.05,
                'depth_weight': 0.05
            },
            'base_scores': {
                'volatility_initial': 50,
                'volume_initial': 50,
                'trend_base': 60,
                'frequency_base': 70,
                'technical_base': 60,
                'risk_base': 70
            }
        },
        'futures_selection': {
            'bybit': {
                'max_candidates': 100,
                'min_quote_volume': 20000000,
                'volatility_max': 25.0,
                'sort_weights': {'volume': 0.9, 'volatility': 0.1}
            },
            'okx': {
                'max_candidates': 100,
                'min_quote_volume': 15000000,
                'volatility_max': 25.0,
                'sort_weights': {'volume': 0.9, 'volatility': 0.1}
            },
            'bitget': {
                'max_candidates': 100,
                'min_quote_volume': 12000000,
                'volatility_max': 25.0,
                'sort_weights': {'volume': 0.9, 'volatility': 0.1}
            }
        },
        'risk_winrate_window': 10,
        'risk_downshift_threshold': 40,
        'risk_upshift_threshold': 60,
        'risk_shift_factor_down': 0.85,
        'risk_shift_factor_up': 1.10,
        
        # Alpha Arena 설정
        'alpha_arena': {
            'enabled': False,
            'exchange': 'binance-futures',
            'engine': 'deepseek-v4-flash',
            'available_engines': ['deepseek-v4-flash', 'qwen3-max'],
            'initial_capital_benchmark': 10000,  # 초기 자금 기준 (10000=만불, 1000=천불, 100=백불)
            'deepseek_api_key': '',
            'qwen_api_key': '',
            'tick_interval_sec': 60,  # 기본 60초, 최소 30초 (내부 가드레일)
            'tick_trigger': 'interval',  # 'interval' 또는 'candle_close_3m' (기본 interval, UI 노출 X)
            'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT'],
            'leverage_min': 10,
            'leverage_max': 20,
            'require_trading_decisions': False,
            'echo_last_orders_to_llm': True,
            'auto_insurance_tp_sl': False,
            'max_concurrent_positions': 6,
            'cooldown_sec_per_symbol': 30,
            'max_risk_per_tick': 1500.0,
            'workingType': 'MARK_PRICE',
            'logging': {
                'level': 'INFO',
                'store_prompt_hash': True,
                'prompt_version': 'alphaarena-v1'
            },
            'help': {
                'on_unknown': '대시보드 사용자메뉴얼에서 AlphaArena 가서 설명을 읽어주세요.'
            }
        }
    }


def update_setting(key: str, value: Any) -> bool:
    """개별 설정 업데이트"""
    try:
        settings = load_settings()
        settings[key] = value
        return save_settings(settings)

    except Exception as e:
        print(f"설정 업데이트 오류: {e}")
        return False


def get_setting(key: str, default: Any = None) -> Any:
    """개별 설정 조회"""
    try:
        settings = load_settings()
        return settings.get(key, default)

    except Exception as e:
        print(f"설정 조회 오류: {e}")
        return default


def reset_settings() -> bool:
    """설정 초기화 (기본: 민감 설정 보존)"""
    try:
        return reset_settings_with_options(preserve_sensitive=True)

    except Exception as e:
        print(f"설정 초기화 오류: {e}")
        return False


def _is_sensitive_setting_key(key: str) -> bool:
    """민감 정보 키 여부 판별"""
    key_l = str(key or '').lower()
    sensitive_suffixes = (
        'api_key',
        'app_key',
        'app_secret',
        'secret_key',
        'passphrase',
        'password',
        'token',
        'account_no',
        'cert_password',
        'credential_ref',
        'user_id',
    )
    sensitive_exact = {
        'backend_url',
        'id',
        'selected_exchange',
        'enabled_exchanges',
        'enabled_stock_brokers',
    }
    return key_l.endswith(sensitive_suffixes) or key_l in sensitive_exact


def _preserve_sensitive_values(current: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """기본 설정 위에 민감 설정/미지 키를 보존 병합"""
    merged: Dict[str, Any] = copy.deepcopy(defaults)

    for key, cur_val in (current or {}).items():
        if key not in merged:
            # 템플릿에 아직 없는 사용자 키는 보존하여 재시작 불능 회귀를 방지
            merged[key] = copy.deepcopy(cur_val)
            continue

        default_val = merged.get(key)
        if isinstance(cur_val, dict) and isinstance(default_val, dict):
            merged[key] = _preserve_sensitive_values(cur_val, default_val)
            continue

        if _is_sensitive_setting_key(key):
            merged[key] = copy.deepcopy(cur_val)

    return merged


def reset_settings_with_options(preserve_sensitive: bool = True) -> bool:
    """설정 초기화 옵션.

    Args:
        preserve_sensitive: True면 API 키/인증 정보/백엔드 URL/브로커 계정 설정을 보존.
    """
    try:
        default_settings = get_default_settings()
        if preserve_sensitive:
            current_settings = load_settings()
            default_settings = _preserve_sensitive_values(current_settings, default_settings)
        return save_settings(default_settings)

    except Exception as e:
        print(f"설정 초기화 오류: {e}")
        return False
