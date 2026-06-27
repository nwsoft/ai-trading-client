#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D1 증권 실행 경로 사전 점검 스크립트

목적:
- 현재 설정에서 브로커별 주문 경로(mock/live_api)를 한눈에 확인
- 실주문 차단/허용 플래그 상태를 점검
- macOS 개발환경에서 즉시 가능한 사전 판정(구성 검증) 제공
"""

import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchanges.exchange_factory import ExchangeFactory


def _load_settings() -> Tuple[Dict[str, Any], Path]:
    """사용자 계정별 설정을 우선 탐색해 가장 관련성 높은 settings.json을 로드한다."""
    data_dir = ROOT / "data"
    candidates: List[Path] = []

    # 1) 계정별 설정(data/*/config/settings.json) 우선
    if data_dir.exists():
        account_settings = sorted(data_dir.glob("*/config/settings.json"))
        # 공용/초기화 성격의 폴더는 후순위로 밀어 혼선을 줄인다.
        preferred = [p for p in account_settings if p.parent.parent.name.lower() not in {"nwsoft"}]
        fallback = [p for p in account_settings if p.parent.parent.name.lower() in {"nwsoft"}]
        candidates.extend(preferred)
        candidates.extend(fallback)

    # 2) 루트 data/settings.json, 3) 템플릿
    candidates.extend([
        ROOT / "data" / "settings.json",
        ROOT / "config" / "settings_template.json",
    ])

    # 관련성 점수: 활성 브로커/키움 인증값이 있는 파일을 우선
    scored: List[Tuple[int, float, Path, Dict[str, Any]]] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        score = 0
        brokers = settings.get("enabled_stock_brokers")
        if isinstance(brokers, list) and brokers:
            score += 4

        stock_cfg = settings.get("stock_broker_configs") if isinstance(settings.get("stock_broker_configs"), dict) else {}
        kiwoom_cfg = stock_cfg.get("kiwoom") if isinstance(stock_cfg.get("kiwoom"), dict) else {}
        if kiwoom_cfg:
            score += 2
            for key in ("id", "password", "cert_password", "account_no"):
                if str(kiwoom_cfg.get(key, "")).strip():
                    score += 1

        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = 0.0

        scored.append((score, mtime, path, settings))

    if scored:
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, best_path, best_settings = scored[0]
        return best_settings, best_path

    return {}, Path("(not found)")


def _bool(v: Any) -> bool:
    return bool(v)


def _get_enabled_brokers(settings: Dict[str, Any]) -> List[str]:
    brokers = settings.get("enabled_stock_brokers")
    if isinstance(brokers, list) and brokers:
        return [str(b).strip() for b in brokers if str(b).strip()]

    stock_configs = settings.get("stock_broker_configs")
    if isinstance(stock_configs, dict) and stock_configs:
        return [str(k).strip() for k in stock_configs.keys() if str(k).strip()]

    return ["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"]


def _resolve_broker_config(settings: Dict[str, Any], broker: str) -> Dict[str, Any]:
    stock_configs = settings.get("stock_broker_configs")
    if not isinstance(stock_configs, dict):
        return {}

    if broker in stock_configs and isinstance(stock_configs[broker], dict):
        return stock_configs[broker]

    lower_map = {str(k).lower(): v for k, v in stock_configs.items() if isinstance(v, dict)}
    return lower_map.get(str(broker).lower(), {})


def _is_non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _check_live_credentials(broker: str, api_type: str, cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """브로커/경로별 최소 인증정보 충족 여부를 점검한다."""
    if api_type == "mock":
        return True, []

    missing: List[str] = []

    broker_lower = str(broker).lower()
    api_type_norm = str(api_type).lower()
    api_version = str(cfg.get("api_version", "") or "").strip().lower()

    if broker_lower == "kiwoom":
        if api_type_norm == "openapi":
            if not _is_non_empty(cfg.get("id")):
                missing.append("id")
            if not _is_non_empty(cfg.get("password")):
                missing.append("password")
            if not _is_non_empty(cfg.get("cert_password")):
                missing.append("cert_password")
        if not _is_non_empty(cfg.get("account_no")):
            missing.append("account_no")

    elif broker_lower == "shinhan":
        # rest/openapi: app_key/app_secret 우선, 없으면 id/password 폴백 허용
        has_app = _is_non_empty(cfg.get("app_key")) and _is_non_empty(cfg.get("app_secret"))
        has_idpw = _is_non_empty(cfg.get("id")) and _is_non_empty(cfg.get("password"))
        if not (has_app or has_idpw):
            missing.append("app_key/app_secret(or id/password)")
        if not _is_non_empty(cfg.get("account_no")):
            missing.append("account_no")

    elif broker_lower in ("miraeasset", "mirae_asset"):
        # rest/openapi: app_key/app_secret 우선, 없으면 id/password 폴백 허용
        has_app = _is_non_empty(cfg.get("app_key")) and _is_non_empty(cfg.get("app_secret"))
        has_idpw = _is_non_empty(cfg.get("id")) and _is_non_empty(cfg.get("password"))
        if not (has_app or has_idpw):
            missing.append("app_key/app_secret(or id/password)")
        if not _is_non_empty(cfg.get("account_no")):
            missing.append("account_no")

    elif broker_lower in ("koreainvestment", "korea_investment", "kis"):
        has_app = _is_non_empty(cfg.get("app_key")) and _is_non_empty(cfg.get("app_secret"))
        has_idpw = _is_non_empty(cfg.get("id")) and _is_non_empty(cfg.get("password"))
        if not (has_app or has_idpw):
            missing.append("app_key/app_secret(or id/password)")
        if not _is_non_empty(cfg.get("account_no")):
            missing.append("account_no")

    else:
        missing.append("unknown_broker")

    # 명시적으로 모의 버전을 쓰는 경우는 live credential 검사 대상에서 제외
    if api_version == "mock":
        return True, []

    return len(missing) == 0, missing


def _check_core_files() -> Dict[str, bool]:
    targets = {
        "exchange_factory": ROOT / "trading" / "exchanges" / "exchange_factory.py",
        "stock_analysis_service": ROOT / "trading" / "stock_analysis_service.py",
        "stock_guardrails_test": ROOT / "tests" / "test_stock_order_guardrails.py",
        "stock_integration_test": ROOT / "tests" / "test_stock_integration.py",
    }
    return {k: p.exists() for k, p in targets.items()}


def _evaluate_stock_auto_trading_config(settings: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    raw = settings.get("stock_auto_trading", {})
    auto_cfg = raw if isinstance(raw, dict) else {}

    def _parse_int(key: str, default: int) -> int:
        try:
            return int(auto_cfg.get(key, default))
        except Exception:
            return default

    def _parse_float(key: str, default: float) -> float:
        try:
            return float(auto_cfg.get(key, default))
        except Exception:
            return default

    enabled = bool(auto_cfg.get("enabled", False))
    summary = {
        "enabled": enabled,
        "interval_sec": _parse_int("interval_sec", 60),
        "quantity": _parse_float("quantity", 1.0),
        "max_orders_per_cycle": _parse_int("max_orders_per_cycle", 1),
        "buy_threshold": _parse_float("buy_threshold", 70.0),
        "sell_threshold": _parse_float("sell_threshold", 30.0),
        "risk_guard_enabled": bool(auto_cfg.get("risk_guard_enabled", True)),
        "risk_governance_enabled": bool(auto_cfg.get("risk_governance_enabled", True)),
        "global_kill_switch": bool(auto_cfg.get("global_kill_switch", False)),
        "enable_exit_policy": bool(auto_cfg.get("enable_exit_policy", True)),
        "symbols": auto_cfg.get("symbols", []),
    }

    blocking: List[str] = []
    warning: List[str] = []

    if not enabled:
        return summary, blocking, warning

    if summary["interval_sec"] < 5:
        blocking.append("stock_auto_trading.interval_sec는 5초 이상이어야 합니다.")
    if summary["quantity"] <= 0:
        blocking.append("stock_auto_trading.quantity는 0보다 커야 합니다.")
    if summary["max_orders_per_cycle"] < 1:
        blocking.append("stock_auto_trading.max_orders_per_cycle는 1 이상이어야 합니다.")
    if summary["buy_threshold"] <= summary["sell_threshold"]:
        blocking.append("stock_auto_trading.buy_threshold는 sell_threshold보다 커야 합니다.")

    if summary["risk_guard_enabled"]:
        daily_max_loss = _parse_float("daily_max_loss", 500000.0)
        max_consecutive_losses = _parse_int("max_consecutive_losses", 3)
        cooldown_sec = _parse_int("cooldown_sec_per_symbol", 300)
        if daily_max_loss < 0:
            blocking.append("stock_auto_trading.daily_max_loss는 0 이상이어야 합니다.")
        if max_consecutive_losses < 1:
            blocking.append("stock_auto_trading.max_consecutive_losses는 1 이상이어야 합니다.")
        if cooldown_sec < 0:
            blocking.append("stock_auto_trading.cooldown_sec_per_symbol는 0 이상이어야 합니다.")

    if summary["risk_governance_enabled"]:
        weekly_max_loss = _parse_float("weekly_max_loss", 1500000.0)
        monthly_max_loss = _parse_float("monthly_max_loss", 4000000.0)
        max_symbol_weight_percent = _parse_float("max_symbol_weight_percent", 35.0)
        if weekly_max_loss < 0:
            blocking.append("stock_auto_trading.weekly_max_loss는 0 이상이어야 합니다.")
        if monthly_max_loss < 0:
            blocking.append("stock_auto_trading.monthly_max_loss는 0 이상이어야 합니다.")
        if max_symbol_weight_percent <= 0 or max_symbol_weight_percent > 100:
            blocking.append("stock_auto_trading.max_symbol_weight_percent는 0 초과 100 이하여야 합니다.")
        if summary.get("global_kill_switch"):
            warning.append("stock_auto_trading.global_kill_switch=ON 상태입니다. 자동주문은 모두 차단됩니다.")

        # 브로커별 거버넌스 오버라이드 유효성 검사
        broker_overrides = auto_cfg.get("broker_overrides", {})
        if broker_overrides not in (None, {}) and not isinstance(broker_overrides, dict):
            blocking.append("stock_auto_trading.broker_overrides는 객체(dict) 형태여야 합니다.")
        elif isinstance(broker_overrides, dict):
            for broker, override in broker_overrides.items():
                broker_name = str(broker or "").strip() or "(unknown)"
                if not isinstance(override, dict):
                    blocking.append(
                        f"stock_auto_trading.broker_overrides.{broker_name}는 객체(dict) 형태여야 합니다."
                    )
                    continue

                for key in ("daily_max_loss", "weekly_max_loss", "monthly_max_loss"):
                    if key in override:
                        try:
                            value = float(override.get(key, 0.0) or 0.0)
                        except Exception:
                            blocking.append(
                                f"stock_auto_trading.broker_overrides.{broker_name}.{key}는 숫자여야 합니다."
                            )
                            continue
                        if value < 0:
                            blocking.append(
                                f"stock_auto_trading.broker_overrides.{broker_name}.{key}는 0 이상이어야 합니다."
                            )

                if "max_symbol_weight_percent" in override:
                    try:
                        weight = float(override.get("max_symbol_weight_percent", 0.0) or 0.0)
                    except Exception:
                        blocking.append(
                            f"stock_auto_trading.broker_overrides.{broker_name}.max_symbol_weight_percent는 숫자여야 합니다."
                        )
                    else:
                        if weight <= 0 or weight > 100:
                            blocking.append(
                                f"stock_auto_trading.broker_overrides.{broker_name}.max_symbol_weight_percent는 0 초과 100 이하여야 합니다."
                            )

    if summary["enable_exit_policy"]:
        for key in (
            "take_profit_percent",
            "stop_loss_percent",
            "etf_take_profit_percent",
            "etf_stop_loss_percent",
        ):
            value = _parse_float(key, 0.0)
            if value <= 0:
                blocking.append(f"stock_auto_trading.{key}는 0보다 커야 합니다.")

    symbols = auto_cfg.get("symbols", [])
    if isinstance(symbols, list) and not [str(s).strip() for s in symbols if str(s).strip()]:
        warning.append("stock_auto_trading.symbols가 비어 있어 브로커 기본 유니버스를 사용합니다.")

    return summary, blocking, warning


def _print_auto_trading_summary(summary: Dict[str, Any]) -> None:
    print("\n[증권 자동매매 정책]")
    print(f"- enabled: {summary.get('enabled')}")
    print(f"- interval_sec: {summary.get('interval_sec')}")
    print(f"- quantity: {summary.get('quantity')}")
    print(f"- max_orders_per_cycle: {summary.get('max_orders_per_cycle')}")
    print(f"- thresholds: buy={summary.get('buy_threshold')} / sell={summary.get('sell_threshold')}")
    print(f"- risk_guard_enabled: {summary.get('risk_guard_enabled')}")
    print(f"- risk_governance_enabled: {summary.get('risk_governance_enabled')}")
    print(f"- global_kill_switch: {summary.get('global_kill_switch')}")
    print(f"- enable_exit_policy: {summary.get('enable_exit_policy')}")
    symbols = summary.get('symbols') or []
    if isinstance(symbols, list) and symbols:
        print(f"- symbols: {', '.join(str(s) for s in symbols[:8])}")
    else:
        print("- symbols: (broker default universe)")


def _build_rows(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    enabled_brokers = _get_enabled_brokers(settings)
    global_live_flag = _bool(settings.get("enable_stock_live_order", False))

    rows = []
    for broker in enabled_brokers:
        cfg = _resolve_broker_config(settings, broker)
        api_type = str(cfg.get("api_type", "openapi") or "openapi").strip().lower()
        api_version = str(cfg.get("api_version", "") or "").strip().lower()
        allow_live_order = _bool(cfg.get("allow_live_order", False))

        supported = ExchangeFactory.get_supported_api_versions(broker)
        supported_for_type = supported.get(api_type, {}) if isinstance(supported, dict) else {}
        valid_combo = bool(supported_for_type) and bool(api_version) and api_version in supported_for_type

        execution_mode = "mock" if api_type == "mock" else "live_api"
        live_order_enabled = execution_mode == "live_api" and global_live_flag and allow_live_order
        credentials_ready, missing_credentials = _check_live_credentials(broker, api_type, cfg)

        os_blocked = False
        if broker.lower() == "kiwoom" and execution_mode == "live_api" and platform.system() != "Windows":
            os_blocked = True

        rows.append(
            {
                "broker": broker,
                "api_type": api_type,
                "api_version": api_version,
                "allow_live_order": allow_live_order,
                "execution_mode": execution_mode,
                "live_order_enabled": live_order_enabled,
                "valid_combo": valid_combo,
                "credentials_ready": credentials_ready,
                "missing_credentials": missing_credentials,
                "os_blocked": os_blocked,
            }
        )

    return rows


def _print_table(rows: List[Dict[str, Any]], global_live_flag: bool) -> None:
    print("\n[증권 브로커 실행 경로]")
    print(f"global enable_stock_live_order = {global_live_flag}")
    print("-" * 150)
    print(f"{'broker':<12} {'api_type':<10} {'api_version':<14} {'combo':<8} {'cred':<8} {'os':<6} {'mode':<10} {'broker_live':<12} {'effective_live':<14}")
    print("-" * 150)
    for r in rows:
        print(
            f"{str(r.get('broker', '')):<12} {str(r.get('api_type', '')):<10} {str(r.get('api_version', '')):<14} {str(r.get('valid_combo')):<8} "
            f"{str(r.get('credentials_ready')):<8} {('BLOCK' if r.get('os_blocked') else 'OK'):<6} "
            f"{str(r.get('execution_mode', '')):<10} {str(r.get('allow_live_order')):<12} {str(r.get('live_order_enabled')):<14}"
        )
        if r["missing_credentials"]:
            print(f"  - missing_credentials: {', '.join(r['missing_credentials'])}")


def main() -> int:
    settings, settings_path = _load_settings()
    core = _check_core_files()
    os_name = platform.system()

    print("D1 증권 사전 점검 시작")
    print(f"- settings: {settings_path}")
    print(f"- os: {os_name}")

    print("\n[핵심 파일 체크]")
    for name, ok in core.items():
        print(f"- {name}: {'OK' if ok else 'MISSING'}")

    global_live_flag = _bool(settings.get("enable_stock_live_order", False))
    rows = _build_rows(settings)
    _print_table(rows, global_live_flag)
    auto_summary, auto_blocking, auto_warning = _evaluate_stock_auto_trading_config(settings)
    _print_auto_trading_summary(auto_summary)

    blocking: List[str] = []
    warning: List[str] = []

    if not rows:
        blocking.append("활성 증권 브로커가 없습니다. settings의 enabled_stock_brokers를 확인하세요.")

    invalid_combos = [r for r in rows if not r.get("valid_combo")]
    if invalid_combos:
        names = ", ".join(f"{r['broker']}({r['api_type']}/{r['api_version'] or 'missing'})" for r in invalid_combos)
        blocking.append(f"api_type/api_version 조합이 유효하지 않은 브로커: {names}")

    live_path_rows = [r for r in rows if r["execution_mode"] == "live_api"]
    invalid_credentials = [r for r in live_path_rows if not r.get("credentials_ready")]
    if invalid_credentials:
        details = ", ".join(
            f"{r['broker']}[{','.join(r.get('missing_credentials') or [])}]" for r in invalid_credentials
        )
        blocking.append(f"live_api 인증정보 누락 브로커: {details}")

    os_blocked_live = [r for r in live_path_rows if r.get("os_blocked")]
    if os_blocked_live:
        names = ", ".join(r["broker"] for r in os_blocked_live)
        warning.append(f"현재 OS에서 실연동 제한 브로커: {names}")

    if not all(core.values()):
        missing = [k for k, v in core.items() if not v]
        blocking.append(f"핵심 파일 누락: {', '.join(missing)}")

    if os_name != "Windows":
        warning.append("현재 OS에서는 키움 OpenAPI+ 실주문 검증이 제한됩니다(Windows+pykiwoom 필요).")

    live_candidates = [r for r in rows if r["execution_mode"] == "live_api"]
    effective_live = [r for r in rows if r["live_order_enabled"]]

    if live_candidates and not effective_live:
        warning.append(
            "live_api 후보 브로커는 있으나 실주문 플래그가 모두 OFF입니다. "
            "enable_stock_live_order + broker.allow_live_order를 확인하세요."
        )

    if not live_candidates:
        warning.append("모든 브로커가 mock 경로입니다. D1 실주문 경로 검증 대상이 없습니다.")

    blocking.extend(auto_blocking)
    warning.extend(auto_warning)

    print("\n[판정]")
    if blocking:
        print("- 결과: BLOCKED")
        for msg in blocking:
            print(f"  * {msg}")
    else:
        print("- 결과: READY_FOR_NEXT_STEP")

    if warning:
        print("- 경고:")
        for msg in warning:
            print(f"  * {msg}")

    print("\n[다음 실행 권장]")
    print("1) python -m pytest tests/test_stock_analysis_service.py -q")
    print("2) python -m pytest tests/test_stock_order_guardrails.py -q")
    print("3) python -m pytest tests/test_stock_integration.py -q")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
