#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 실계좌 연결 검증 스크립트 (테스트/진단용)

이 스크립트는 실제 증권사 API에 연결하여 기본 계좌 조회까지 성공하는지
단계별로 검증하고, 결과를 reports/ 에 JSON으로 저장한다.

사용법:
    python3 scripts/verify_stock_broker_connection.py \
        --broker kiwoom \
        --api_type openapi_plus \
        --api_version pykiwoom \
        --id YOUR_USER_ID \
        --password YOUR_PASSWORD \
        --cert_password YOUR_CERT_PASS \
        --account_no YOUR_ACCOUNT_NO

    또는 드라이런(Mock) 모드:
    python3 scripts/verify_stock_broker_connection.py --broker kiwoom --mock

지원 증권사:
    - kiwoom         (openapi_plus/pykiwoom, mock)
    - shinhan        (partner_rest/shinhan_openapi_v2, mock)
    - miraeAsset     (partner_rest/mirae_partner_profile, mock)
    - koreaInvestment (rest/kis_openapi_v1, mock)

검증 단계:
    1. API 조합 검증  (ExchangeFactory.validate_stock_broker_api_combo)
    2. 구현 성숙도 확인(문자열 등록과 실제 구현/검증 상태 분리)
    3. 어댑터 생성    (ExchangeFactory.create_stock_exchange)
    4. 연결           (adapter.connect())
    5. 계좌 잔고 조회 (adapter.get_balance())
    6. 포지션 조회    (adapter.get_positions() / get_account_info())

결과 저장:
    data/reports/stock_broker_verify_<broker>_<timestamp>.json

보안 주의:
    - API 키/비밀번호는 환경 변수로도 제공 가능 (--id 대신 BROKER_USER_ID 등)
    - 결과 파일에 민감 정보는 마스킹 처리됨
"""

import argparse
import json
import logging
import os
import platform
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("stock_broker_verify")


# ══════════════════════════════════════════════════════════════════════════════
#  결과 리포트 구조
# ══════════════════════════════════════════════════════════════════════════════

class VerifyResult:
    def __init__(self, broker: str, api_type: str, api_version: str):
        self.broker = broker
        self.api_type = api_type
        self.api_version = api_version
        self.timestamp = datetime.now().isoformat()
        self.steps: List[Dict[str, Any]] = []
        self.overall: str = "PENDING"  # OK / FAIL / PARTIAL

    def add_step(self, name: str, status: str, detail: str = "", data: Any = None):
        self.steps.append({
            "step": name,
            "status": status,       # OK / FAIL / SKIP
            "detail": detail,
            "data": data,
        })
        logger.info(f"  [{status}] {name}: {detail}")

    def finalize(self):
        statuses = [s["status"] for s in self.steps]
        if all(s == "OK" for s in statuses):
            self.overall = "OK"
        elif "OK" in statuses:
            self.overall = "PARTIAL"
        else:
            self.overall = "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "broker": self.broker,
            "api_type": self.api_type,
            "api_version": self.api_version,
            "timestamp": self.timestamp,
            "overall": self.overall,
            "steps": self.steps,
        }

    def save(self, output_dir: str = "data/reports") -> str:
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"stock_broker_verify_{self.broker}_{ts}.json"
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"결과 저장: {fpath}")
        return fpath


# ══════════════════════════════════════════════════════════════════════════════
#  검증 로직
# ══════════════════════════════════════════════════════════════════════════════

def _mask(value: str, keep: int = 4) -> str:
    """민감 정보 마스킹."""
    if not value:
        return "(없음)"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)


def run_verification(
    broker: str,
    api_type: str,
    api_version: str,
    user_id: str = "",
    password: str = "",
    cert_password: str = "",
    account_no: str = "",
    app_key: str = "",
    app_secret: str = "",
    sandbox: bool = False,
    partner_profile: Optional[Dict[str, Any]] = None,
    mock_mode: bool = False,
    runtime_only: bool = False,
) -> VerifyResult:
    """단계별 증권사 연결 검증을 실행한다."""
    if mock_mode:
        api_type = "mock"
        api_version = "mock"

    result = VerifyResult(broker, api_type, api_version)
    logger.info(f"\n{'='*60}")
    logger.info(f"증권사 연결 검증: {broker} / {api_type} / {api_version}")
    logger.info(f"계정: {_mask(user_id)}, 계좌: {_mask(account_no)}")
    logger.info(f"{'='*60}")

    # ── Step 0: 키움 OpenAPI 런타임 진단 (Windows/OCX/이벤트) ───────────────
    if broker == "kiwoom" and api_type == "openapi_plus":
        try:
            os_name = platform.system()
            py_bits = 64 if (8 * __import__('struct').calcsize('P')) == 64 else 32
            if os_name != "Windows":
                result.add_step(
                    "키움 런타임 진단",
                    "FAIL",
                    f"현재 OS={os_name} (키움 OpenAPI+는 Windows 전용)",
                    data={"os": os_name, "python_bits": py_bits},
                )
                result.finalize()
                return result

            try:
                from PyQt5.QtWidgets import QApplication
                from PyQt5.QAxContainer import QAxWidget
            except Exception as imp_exc:
                result.add_step(
                    "키움 런타임 진단",
                    "FAIL",
                    f"PyQt5/QAxContainer import 실패: {imp_exc}",
                    data={"os": os_name, "python_bits": py_bits},
                )
                result.finalize()
                return result

            app = QApplication.instance() or QApplication(sys.argv)
            _ = app  # linter-friendly placeholder
            probe = QAxWidget()
            control_ok = bool(probe.setControl("KHOPENAPI.KHOpenAPICtrl.1"))
            has_tr_event = hasattr(probe, "OnReceiveTrData")

            if not control_ok or not has_tr_event:
                result.add_step(
                    "키움 런타임 진단",
                    "FAIL",
                    "KHOpenAPI ActiveX 로딩/이벤트 바인딩 실패",
                    data={
                        "os": os_name,
                        "python_bits": py_bits,
                        "control_ok": control_ok,
                        "has_OnReceiveTrData": has_tr_event,
                    },
                )
                result.finalize()
                return result

            result.add_step(
                "키움 런타임 진단",
                "OK",
                "KHOpenAPI ActiveX 로딩 및 이벤트 바인딩 가능",
                data={
                    "os": os_name,
                    "python_bits": py_bits,
                    "control_ok": control_ok,
                    "has_OnReceiveTrData": has_tr_event,
                },
            )
            if runtime_only:
                result.add_step("런타임 전용 모드", "SKIP", "요청에 따라 실제 계정 연결 단계는 생략")
                result.finalize()
                return result
        except Exception as diag_exc:
            result.add_step("키움 런타임 진단", "FAIL", f"예외: {diag_exc}")
            result.finalize()
            return result

    # ── Step 1: API 조합 검증 ────────────────────────────────────────────────
    try:
        from trading.exchanges.exchange_factory import ExchangeFactory
        ok, err = ExchangeFactory.validate_stock_broker_api_combo(broker, api_type, api_version)
        if ok:
            result.add_step("API 조합 검증", "OK",
                            f"{broker} / {api_type} / {api_version} 조합 유효")
        else:
            result.add_step("API 조합 검증", "FAIL", err)
            result.finalize()
            return result
    except Exception as exc:
        result.add_step("API 조합 검증", "FAIL", f"예외: {exc}")
        result.finalize()
        return result

    # 문자열 조합 등록만으로 실제 구현/실주문 가능 상태라고 판단하지 않는다.
    maturity = ExchangeFactory.get_stock_broker_api_maturity(broker, api_type, api_version)
    if not maturity.get("implemented", False):
        result.add_step("API 구현 성숙도", "FAIL", maturity.get("message", "미구현 경로"), data=maturity)
        result.finalize()
        return result
    maturity_status = "OK" if api_type == "mock" else "SKIP"
    result.add_step(
        "API 구현 성숙도",
        maturity_status,
        maturity.get("message", maturity.get("status", "상태 미상")),
        data=maturity,
    )

    # ── Step 2: 어댑터 생성 ──────────────────────────────────────────────────
    adapter = None
    try:
        settings = {
            "stock_broker_configs": {
                broker: {
                    "api_type": api_type,
                    "api_version": api_version,
                    "id": user_id,
                    "password": password,
                    "cert_password": cert_password,
                    "account_no": account_no,
                    "app_key": app_key or user_id,
                    "app_secret": app_secret or password,
                    "sandbox": bool(sandbox),
                    "partner_profile": dict(partner_profile or {}),
                }
            }
        }
        adapter = ExchangeFactory.create_stock_exchange(broker, settings)
        result.add_step("어댑터 생성", "OK",
                        f"{adapter.__class__.__name__} 생성 완료")
    except Exception as exc:
        result.add_step("어댑터 생성", "FAIL", f"예외: {exc}")
        result.finalize()
        return result

    # ── Step 3: 연결 ─────────────────────────────────────────────────────────
    try:
        connected = adapter.connect()
        if connected:
            result.add_step("API 연결", "OK", "연결 성공")
        else:
            result.add_step("API 연결", "FAIL", "connect() 반환값 False")
            result.finalize()
            return result
    except Exception as exc:
        result.add_step("API 연결", "FAIL", f"예외: {exc}")
        result.finalize()
        return result

    # ── Step 4: 계좌 잔고 조회 ───────────────────────────────────────────────
    try:
        balance = adapter.get_balance()
        if isinstance(balance, dict):
            result.add_step("잔고 조회", "OK",
                            f"{len(balance)}개 항목",
                            data={k: v for k, v in list(balance.items())[:5]})
        else:
            result.add_step("잔고 조회", "FAIL", f"예상치 못한 반환 형식: {type(balance)}")
    except Exception as exc:
        result.add_step("잔고 조회", "FAIL", f"예외: {exc}")

    # ── Step 5: 계좌 정보 조회 ───────────────────────────────────────────────
    try:
        info = adapter.get_account_info()
        if isinstance(info, dict):
            result.add_step("계좌 정보 조회", "OK",
                            f"계좌번호: {_mask(str(info.get('account_no', '')))}")
        else:
            result.add_step("계좌 정보 조회", "FAIL", f"예상치 못한 반환 형식: {type(info)}")
    except Exception as exc:
        result.add_step("계좌 정보 조회", "FAIL", f"예외: {exc}")

    # ── Step 6: 현재 포지션/보유 종목 조회 ─────────────────────────────────────
    try:
        positions_fn = getattr(adapter, "get_positions", None) or getattr(adapter, "get_holdings", None)
        if callable(positions_fn):
            positions = positions_fn()
            count = len(positions) if isinstance(positions, (list, dict)) else 0
            result.add_step("포지션 조회", "OK", f"{count}개 종목/포지션")
        else:
            result.add_step("포지션 조회", "SKIP", "get_positions/get_holdings 미구현")
    except Exception as exc:
        result.add_step("포지션 조회", "FAIL", f"예외: {exc}")

    result.finalize()
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  CLI 엔트리포인트
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="NoahAI 증권 실계좌 연결 검증 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("검증 단계:")[0].strip(),
    )
    p.add_argument("--broker", default="kiwoom",
                   choices=["kiwoom", "shinhan", "miraeAsset", "koreaInvestment"],
                   help="검증할 증권사 (기본: kiwoom)")
    p.add_argument("--api_type", default="mock",
                   help="API 타입 (openapi/rest/mock, 기본: mock)")
    p.add_argument("--api_version", default="mock",
                   help="API 버전 (pykiwoom/shinhan_openapi_v2/mirae_partner_profile/kis_openapi_v1/mock)")
    p.add_argument("--mock", action="store_true",
                   help="Mock 모드로 실행 (API 없이 동작 검증)")
    p.add_argument("--id", dest="user_id",
                   default=os.environ.get("BROKER_USER_ID", ""),
                   help="증권사 로그인 ID (또는 env BROKER_USER_ID)")
    p.add_argument("--password",
                   default=os.environ.get("BROKER_PASSWORD", ""),
                   help="증권사 비밀번호 (또는 env BROKER_PASSWORD)")
    p.add_argument("--cert_password",
                   default=os.environ.get("BROKER_CERT_PASSWORD", ""),
                   help="공동인증서 비밀번호 (또는 env BROKER_CERT_PASSWORD)")
    p.add_argument("--account_no",
                   default=os.environ.get("BROKER_ACCOUNT_NO", ""),
                   help="계좌번호 (또는 env BROKER_ACCOUNT_NO)")
    p.add_argument("--app_key",
                   default=os.environ.get("BROKER_APP_KEY", ""),
                   help="앱키 (REST 기반 증권사, 또는 env BROKER_APP_KEY)")
    p.add_argument("--app_secret",
                   default=os.environ.get("BROKER_APP_SECRET", ""),
                   help="앱시크릿 (REST 기반 증권사, 또는 env BROKER_APP_SECRET)")
    p.add_argument("--sandbox", action="store_true",
                   help="증권사가 제공하는 모의투자 서버 사용 (지원 경로만 적용)")
    p.add_argument("--partner_profile_file", default="",
                   help="신한/미래에셋 제휴 계약 partner_profile JSON 파일")
    p.add_argument("--output_dir", default="data/reports",
                   help="결과 JSON 저장 디렉토리 (기본: data/reports)")
    p.add_argument("--no_save", action="store_true",
                   help="결과 파일 저장 생략")
    p.add_argument("--all_brokers", action="store_true",
                   help="지원하는 모든 증권사 Mock 모드로 순차 검증")
    p.add_argument("--runtime_only", action="store_true",
                   help="키움 런타임(ActiveX/QAx) 진단까지만 수행하고 실제 계정 연결 단계는 생략")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    results: List[VerifyResult] = []
    partner_profile: Dict[str, Any] = {}
    if args.partner_profile_file:
        try:
            with open(args.partner_profile_file, "r", encoding="utf-8") as profile_file:
                loaded_profile = json.load(profile_file)
            if not isinstance(loaded_profile, dict):
                parser.error("--partner_profile_file의 최상위 값은 JSON 객체여야 합니다.")
            partner_profile = loaded_profile
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"partner_profile JSON을 읽을 수 없습니다: {exc}")

    if args.all_brokers:
        # 지원 모든 증권사 × Mock 모드 순차 검증
        brokers = [
            ("kiwoom",    "mock", "mock"),
            ("shinhan",   "mock", "mock"),
            ("miraeAsset","mock", "mock"),
            ("koreaInvestment","mock", "mock"),
        ]
        for broker, api_type, api_version in brokers:
            res = run_verification(broker, api_type, api_version, mock_mode=True)
            results.append(res)
    else:
        res = run_verification(
            broker=args.broker,
            api_type=args.api_type,
            api_version=args.api_version,
            user_id=args.user_id,
            password=args.password,
            cert_password=args.cert_password,
            account_no=args.account_no,
            app_key=args.app_key,
            app_secret=args.app_secret,
            sandbox=args.sandbox,
            partner_profile=partner_profile,
            mock_mode=args.mock,
            runtime_only=args.runtime_only,
        )
        results.append(res)

    # ── 요약 출력 ──
    print("\n" + "="*60)
    print("검증 결과 요약")
    print("="*60)
    for r in results:
        ok_cnt  = sum(1 for s in r.steps if s["status"] == "OK")
        fail_cnt = sum(1 for s in r.steps if s["status"] == "FAIL")
        skip_cnt = sum(1 for s in r.steps if s["status"] == "SKIP")
        icon = "✅" if r.overall == "OK" else ("⚠️" if r.overall == "PARTIAL" else "❌")
        print(f"{icon} [{r.overall}] {r.broker}/{r.api_type}/{r.api_version} "
              f"— {ok_cnt}OK / {fail_cnt}FAIL / {skip_cnt}SKIP")
        for step in r.steps:
            s_icon = "✓" if step["status"] == "OK" else ("⚠" if step["status"] == "SKIP" else "✗")
            print(f"     {s_icon} {step['step']}: {step['detail']}")

    if not args.no_save:
        for r in results:
            r.save(args.output_dir)

    # 하나라도 FAIL이면 종료코드 1
    if any(r.overall == "FAIL" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
