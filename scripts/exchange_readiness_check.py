#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래소 준비도 점검 스크립트

국내(업비트/빗썸) -> 해외(Bybit/OKX/Bitget/Binance) 순서로
연결/인증/잔고조회 상태를 점검해 운영자가 바로 판단할 수 있게 출력합니다.
"""

import json
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.exchange_manager import ExchangeManager


DOMESTIC_EXCHANGES = ["upbit", "bithumb"]
OVERSEAS_EXCHANGES = ["bybit", "okx", "bitget", "binance"]
DEFAULT_TIMEOUT_SEC = int(os.environ.get("EXCHANGE_READINESS_TIMEOUT_SEC", "25") or "25")
WORKER_RESULT_PREFIX = "__READINESS_RESULT__="


def resolve_settings_path(
    settings_file: str = "",
    account: str = "",
) -> Path:
    if settings_file:
        return Path(settings_file).expanduser().resolve()
    if account:
        normalized = str(account).strip()
        if not normalized or Path(normalized).name != normalized:
            raise ValueError("account는 경로가 아닌 계정 디렉터리명이어야 합니다.")
        return (ROOT / "data" / normalized / "config" / "settings.json").resolve()
    from path_utils import get_config_dir
    return (Path(get_config_dir()) / "settings.json").resolve()


def load_user_settings(
    settings_file: str = "",
    account: str = "",
) -> Dict[str, Any]:
    user_settings = resolve_settings_path(settings_file, account)
    if user_settings.exists():
        return json.loads(user_settings.read_text(encoding="utf-8"))
    return {}


def key_ready(settings: Dict[str, Any], exchange: str) -> bool:
    ex = exchange.lower()
    if ex == "binance":
        return bool(settings.get("binance_api_key") and settings.get("binance_secret_key"))
    if ex == "bybit":
        return bool(settings.get("bybit_api_key") and settings.get("bybit_secret_key"))
    if ex == "okx":
        return bool(settings.get("okx_api_key") and settings.get("okx_secret_key") and settings.get("okx_passphrase"))
    if ex == "bitget":
        return bool(settings.get("bitget_api_key") and settings.get("bitget_secret_key") and settings.get("bitget_password"))
    if ex == "upbit":
        return bool(settings.get("upbit_api_key") and settings.get("upbit_secret_key"))
    if ex == "bithumb":
        return bool(settings.get("bithumb_api_key") and settings.get("bithumb_secret_key"))
    return False


def classify_result(result: Dict[str, Any]) -> Dict[str, str]:
    """운영자가 바로 조치할 수 있도록 상태를 원인 중심으로 정규화."""
    exchange = str(result.get("exchange", "") or "")
    key_is_ready = bool(result.get("key_ready"))
    validate = bool(result.get("validate"))
    balance_status = str(result.get("balance_status", "unknown") or "unknown").lower()
    message = str(result.get("balance_message", "") or "")
    lowered = message.lower()

    if not key_is_ready:
        return {
            "root_cause": "missing_credentials",
            "action": f"{exchange} 필수 API 키/시크릿/추가필드를 설정하세요.",
        }

    if balance_status == "client_unavailable":
        return {
            "root_cause": "client_unavailable",
            "action": f"{exchange} 클라이언트/의존성 설치 상태를 확인하세요.",
        }

    if balance_status == "connection_failed":
        return {
            "root_cause": "connection_failed",
            "action": f"{exchange} 네트워크 연결 또는 거래소 서비스 상태를 점검하세요.",
        }

    if balance_status in {"invalid_api_keys", "auth_check_failed"}:
        return {
            "root_cause": "authentication_failed",
            "action": f"{exchange} API 권한, 만료 여부, 서명 정보, IP 화이트리스트를 확인하세요.",
        }

    if "permission" in lowered or "not authorized" in lowered:
        return {
            "root_cause": "permission_denied",
            "action": f"{exchange} API 권한(조회/주문)과 계정 접근 정책을 확인하세요.",
        }

    if "passphrase" in lowered:
        return {
            "root_cause": "passphrase_invalid",
            "action": f"{exchange} passphrase 설정값을 재확인하세요.",
        }

    if "ip" in lowered and ("white" in lowered or "restrict" in lowered):
        return {
            "root_cause": "ip_restricted",
            "action": f"{exchange} API 키의 IP 화이트리스트/접근 제한을 수정하세요.",
        }

    if validate and balance_status == "success":
        return {
            "root_cause": "ready",
            "action": "추가 조치 없이 운영 점검을 통과했습니다.",
        }

    if not validate:
        return {
            "root_cause": "validation_failed",
            "action": f"{exchange} 인증 검증 단계 로그와 키 설정을 다시 확인하세요.",
        }

    return {
        "root_cause": "unknown",
        "action": f"{exchange} 상세 로그를 확인해 원인을 분류하세요.",
    }


def check_one(base_settings: Dict[str, Any], exchange: str) -> Dict[str, Any]:
    settings = dict(base_settings)
    settings["selected_exchange"] = exchange
    settings["enabled_exchanges"] = [exchange]

    manager = ExchangeManager(settings)
    result: Dict[str, Any] = {
        "exchange": exchange,
        "enabled": exchange in settings.get("enabled_exchanges", []),
        "key_ready": key_ready(base_settings, exchange),
        "validate": False,
        "balance_status": "unknown",
        "balance_message": "",
    }

    try:
        result["validate"] = bool(manager.validate_exchange_connection(exchange))
    except Exception as e:
        result["validate"] = False
        result["balance_message"] = f"validate_error: {e}"

    try:
        balance = manager.get_exchange_balance(exchange, force_refresh=True)
        if isinstance(balance, dict):
            result["balance_status"] = str(balance.get("status", "unknown"))
            result["balance_message"] = str(balance.get("message", "") or balance.get("error", ""))
        else:
            result["balance_status"] = type(balance).__name__
    except Exception as e:
        result["balance_status"] = "error"
        result["balance_message"] = str(e)

    # 인증 검증 실패가 우선 원인이므로 상태를 명확히 표기
    if not result["validate"] and result["balance_status"] == "success":
        result["balance_status"] = "auth_check_failed"
        if not result["balance_message"]:
            result["balance_message"] = "validate 단계에서 인증 실패"

    result.update(classify_result(result))

    return result


def check_one_with_timeout(base_settings: Dict[str, Any], exchange: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> Dict[str, Any]:
    if timeout_sec <= 0:
        return check_one(base_settings, exchange)

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker-exchange",
                exchange,
            ],
            input=json.dumps(base_settings, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        timeout_result = {
            "exchange": exchange,
            "enabled": exchange in base_settings.get("enabled_exchanges", []),
            "key_ready": key_ready(base_settings, exchange),
            "validate": False,
            "balance_status": "connection_failed",
            "balance_message": f"timeout_after_{timeout_sec}s",
        }
        timeout_result.update(classify_result(timeout_result))
        return timeout_result

    for line in reversed((completed.stdout or "").splitlines()):
        if not line.startswith(WORKER_RESULT_PREFIX):
            continue
        try:
            result = json.loads(line[len(WORKER_RESULT_PREFIX):])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            break

    fallback = {
        "exchange": exchange,
        "enabled": exchange in base_settings.get("enabled_exchanges", []),
        "key_ready": key_ready(base_settings, exchange),
        "validate": False,
        "balance_status": "error",
        "balance_message": f"worker_exit_{completed.returncode}_without_result",
    }
    fallback.update(classify_result(fallback))
    return fallback


def print_group(title: str, exchanges: List[str], base_settings: Dict[str, Any], timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> List[Dict[str, Any]]:
    group_results: List[Dict[str, Any]] = []
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    for ex in exchanges:
        r = check_one_with_timeout(base_settings, ex, timeout_sec=timeout_sec)
        group_results.append(r)
        print(
            f"- {r['exchange']:<8} | key_ready={str(r['key_ready']):<5} | "
            f"validate={str(r['validate']):<5} | balance_status={r['balance_status']} | cause={r['root_cause']}"
        )
        if r["balance_message"]:
            print(f"  message: {r['balance_message']}")
        print(f"  action: {r['action']}")
    return group_results


def print_summary(results: List[Dict[str, Any]]) -> None:
    ready_count = sum(1 for item in results if item.get("root_cause") == "ready")
    blocked_count = len(results) - ready_count
    print("\n요약:")
    print(f"- ready: {ready_count}")
    print(f"- action_required: {blocked_count}")

    if blocked_count:
        print("- 우선 정리 권장:")
        for item in results:
            if item.get("root_cause") == "ready":
                continue
            print(f"  - {item.get('exchange')}: {item.get('root_cause')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="거래소별 인증·잔고 읽기 전용 준비도 점검")
    parser.add_argument("--account", default="", help="점검할 사용자 계정 디렉터리명")
    parser.add_argument("--settings-file", default="", help="점검할 settings.json 명시 경로")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--strict", action="store_true", help="하나라도 준비되지 않으면 실패 종료")
    parser.add_argument("--worker-exchange", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker_exchange:
        try:
            worker_settings = json.loads(sys.stdin.read() or "{}")
            worker_result = check_one(worker_settings, args.worker_exchange)
        except Exception as exc:
            worker_result = {
                "exchange": args.worker_exchange,
                "enabled": False,
                "key_ready": False,
                "validate": False,
                "balance_status": "error",
                "balance_message": f"worker_error: {exc}",
            }
            worker_result.update(classify_result(worker_result))
        print(WORKER_RESULT_PREFIX + json.dumps(worker_result, ensure_ascii=False))
        return 0

    try:
        settings_path = resolve_settings_path(args.settings_file, args.account)
        settings = load_user_settings(args.settings_file, args.account)
    except Exception as exc:
        print(f"설정 경로 해석 실패: {exc}")
        return 2
    if not settings:
        print(f"설정 파일을 찾을 수 없습니다: {settings_path}")
        return 2

    print("거래소 준비도 점검 시작")
    print(f"settings={settings_path}")
    print(f"selected_exchange={settings.get('selected_exchange')}")
    print(f"enabled_exchanges={settings.get('enabled_exchanges', [])}")

    domestic_results = print_group(
        "1) 국내 거래소 점검 (현물 전용)",
        DOMESTIC_EXCHANGES,
        settings,
        timeout_sec=args.timeout,
    )
    overseas_results = print_group(
        "2) 해외 거래소 점검 (선물 중심)",
        OVERSEAS_EXCHANGES,
        settings,
        timeout_sec=args.timeout,
    )
    results = domestic_results + overseas_results
    print_summary(results)

    print("\n점검 기준:")
    print("- key_ready=True: 필수 키/추가필드(예: okx_passphrase, bitget_password)까지 설정됨")
    print("- validate=True: 인증 포함 연결 검증 통과")
    print("- balance_status=success: 계정 정보 조회까지 성공")
    if args.strict and any(item.get("root_cause") != "ready" for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
