#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""키움 OpenAPI+ 런타임 루트 원인 진단 스크립트.

목적:
- "연결 안됨"을 반복 패치로 대응하지 않고, 환경 원인을 1회 진단으로 확정한다.

사용 예시:
  python scripts/diagnose_kiwoom_runtime.py
  python scripts/diagnose_kiwoom_runtime.py --output_dir data/reports

출력:
- 콘솔 요약
- JSON 리포트: data/reports/kiwoom_runtime_diag_<timestamp>.json

종료코드:
- 0: 런타임 준비 OK (ActiveX 로딩/이벤트 바인딩 가능)
- 1: 런타임 준비 FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import struct
import sys
from datetime import datetime
from typing import Any, Dict, Optional


def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _python_bits() -> int:
    return 64 if (8 * struct.calcsize("P")) == 64 else 32


def _safe_bool(value: Any) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def _check_registry() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "progid_exists": False,
        "clsid": "",
        "inproc_server32": "",
        "inproc_server32_exists": False,
        "error": "",
    }

    if platform.system() != "Windows":
        result["error"] = "non_windows"
        return result

    try:
        import winreg  # type: ignore

        # ProgID -> CLSID
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"KHOPENAPI.KHOpenAPICtrl.1\\CLSID") as key:
                clsid_value, _ = winreg.QueryValueEx(key, None)
                result["progid_exists"] = True
                result["clsid"] = str(clsid_value or "")
        except Exception as exc:
            result["error"] = f"progid_lookup_failed:{exc}"
            return result

        clsid = result.get("clsid", "")
        if not clsid:
            result["error"] = "empty_clsid"
            return result

        # CLSID -> InprocServer32(OCX 경로)
        try:
            reg_path = rf"CLSID\\{clsid}\\InprocServer32"
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, reg_path) as key:
                server_path, _ = winreg.QueryValueEx(key, None)
                path_text = str(server_path or "").strip().strip('"')
                result["inproc_server32"] = path_text
                result["inproc_server32_exists"] = os.path.exists(path_text) if path_text else False
        except Exception as exc:
            result["error"] = f"inproc_lookup_failed:{exc}"
            return result

        result["ok"] = bool(result["progid_exists"] and result["inproc_server32_exists"])
        return result

    except Exception as exc:
        result["error"] = f"registry_probe_exception:{exc}"
        return result


def _check_qax_runtime() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "pyqt_import_ok": False,
        "qax_import_ok": False,
        "qapp_ready": False,
        "setControl": False,
        "has_OnReceiveTrData": False,
        "error": "",
    }

    try:
        from PyQt5.QtWidgets import QApplication  # type: ignore
        result["pyqt_import_ok"] = True
    except Exception as exc:
        result["error"] = f"pyqt_import_failed:{exc}"
        return result

    try:
        from PyQt5.QAxContainer import QAxWidget  # type: ignore
        result["qax_import_ok"] = True
    except Exception as exc:
        result["error"] = f"qax_import_failed:{exc}"
        return result

    try:
        app = QApplication.instance() or QApplication(sys.argv)
        _ = app
        result["qapp_ready"] = True

        probe = QAxWidget()
        control_ok = _safe_bool(probe.setControl("KHOPENAPI.KHOpenAPICtrl.1"))
        has_event = hasattr(probe, "OnReceiveTrData")

        result["setControl"] = control_ok
        result["has_OnReceiveTrData"] = bool(has_event)
        result["ok"] = bool(control_ok and has_event)
        if not result["ok"]:
            result["error"] = "activex_binding_failed"
        return result
    except Exception as exc:
        result["error"] = f"qax_probe_exception:{exc}"
        return result


def run_diagnosis() -> Dict[str, Any]:
    os_name = platform.system()
    py_bits = _python_bits()

    report: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "environment": {
            "os": os_name,
            "python_version": platform.python_version(),
            "python_bits": py_bits,
            "executable": sys.executable,
        },
        "checks": {
            "registry": {},
            "qax_runtime": {},
        },
        "overall": "FAIL",
        "root_cause": "",
        "actions": [],
    }

    if os_name != "Windows":
        report["root_cause"] = "non_windows"
        report["actions"] = [
            "키움 OpenAPI+는 Windows 전용입니다.",
            "Windows PC에서 실행하거나 키움 대신 REST 기반 증권사(신한/미래에셋)를 사용하세요.",
        ]
        return report

    registry_result = _check_registry()
    qax_result = _check_qax_runtime()
    report["checks"]["registry"] = registry_result
    report["checks"]["qax_runtime"] = qax_result

    if qax_result.get("ok"):
        report["overall"] = "OK"
        report["root_cause"] = "runtime_ready"
        report["actions"] = [
            "키움 ActiveX 런타임 준비 완료.",
            "다음 단계로 verify_stock_broker_connection.py에서 실제 계정 연결을 점검하세요.",
        ]
        return report

    # 원인 분류
    if not registry_result.get("progid_exists"):
        report["root_cause"] = "openapi_not_installed_or_not_registered"
        report["actions"] = [
            "키움 OpenAPI+를 관리자 권한으로 재설치하세요.",
            "설치 후 KOA Studio 로그인 성공을 먼저 확인하세요.",
        ]
    elif registry_result.get("progid_exists") and not registry_result.get("inproc_server32_exists"):
        report["root_cause"] = "ocx_path_invalid"
        report["actions"] = [
            "레지스트리의 InprocServer32 경로가 유효하지 않습니다.",
            "OpenAPI+ 재설치로 OCX 등록 경로를 복구하세요.",
        ]
    elif not qax_result.get("qax_import_ok"):
        report["root_cause"] = "pyqt_qax_missing"
        report["actions"] = [
            "PyQt5 QAxContainer가 누락되었습니다.",
            "pip install PyQt5 후 다시 진단하세요.",
        ]
    elif py_bits == 64 and (not qax_result.get("setControl") or not qax_result.get("has_OnReceiveTrData")):
        report["root_cause"] = "likely_python_openapi_bitness_mismatch"
        report["actions"] = [
            "64비트 Python 환경에서 ActiveX 바인딩 실패가 발생했습니다.",
            "Windows 32비트 Python 환경 + OpenAPI+ 재설치 조합에서 KOA Studio 성공 여부를 먼저 확인하세요.",
        ]
    else:
        report["root_cause"] = "unknown_qax_runtime_failure"
        report["actions"] = [
            "QAxWidget 생성 또는 이벤트 바인딩 실패입니다.",
            "OpenAPI+ 재설치 후 KOA Studio 연결, 보안 프로그램 예외 등록, 재부팅을 순서대로 점검하세요.",
        ]

    return report


def save_report(report: Dict[str, Any], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"kiwoom_runtime_diag_{_now_ts()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="키움 OpenAPI+ 런타임 루트 원인 진단 도구")
    p.add_argument("--output_dir", default="data/reports", help="JSON 리포트 저장 디렉토리")
    p.add_argument("--no_save", action="store_true", help="리포트 파일 저장 생략")
    return p


def main() -> None:
    args = build_parser().parse_args()
    report = run_diagnosis()

    print("=" * 60)
    print("키움 런타임 진단 결과")
    print("=" * 60)
    print(f"overall    : {report.get('overall')}")
    print(f"root_cause : {report.get('root_cause')}")
    for action in report.get("actions", []):
        print(f"- {action}")

    if not args.no_save:
        saved = save_report(report, args.output_dir)
        print(f"report     : {saved}")

    if report.get("overall") == "OK":
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
