"""서버 회원등급 응답을 공식 클라이언트 실행 권한으로 정규화한다."""

from __future__ import annotations

from typing import Any, Dict, Set


ALLOWED_USER_GRADES = {"referral", "pro_coin", "pro_stock", "premium"}
REFERRAL_SAFE_EXCHANGES = {"binance", "bybit", "okx", "bitget"}
DOMESTIC_OPEN_EXCHANGES = {"upbit", "bithumb", "coinone"}
SUPPORTED_CRYPTO_EXCHANGES = REFERRAL_SAFE_EXCHANGES | DOMESTIC_OPEN_EXCHANGES
REFERRAL_ATTRIBUTION_STATUSES = {"required", "pending", "verified", "rejected", "expired"}
FREE_MANAGED_POSITION_LIMIT = 3
PAID_MANAGED_POSITION_LIMIT = 5
STRATEGY_VALIDATION_POSITION_LIMIT = 5


def normalize_user_grade(raw_grade: Any) -> str:
    grade = str(raw_grade or "").strip().lower()
    aliases = {
        "free": "referral",
        "free_referral": "referral",
        "referral_free": "referral",
        "referral": "referral",
        "레퍼럴": "referral",
        "normal": "pro_coin",
        "general": "pro_coin",
        "basic": "pro_coin",
        "coin_start": "pro_coin",
        "coin-start": "pro_coin",
        "pro_coin": "pro_coin",
        "pro-coin": "pro_coin",
        "stock": "pro_stock",
        "stocks": "pro_stock",
        "etf": "pro_stock",
        "pro_stock": "pro_stock",
        "pro-stock": "pro_stock",
        "alltrading": "premium",
        "all_trading": "premium",
        "all-trading": "premium",
        "middle": "premium",
        "pro": "premium",
        "signature": "premium",
        "signature_federated": "premium",
        "premium_all": "premium",
        "premium-all": "premium",
    }
    normalized = aliases.get(grade, grade)
    return normalized if normalized in ALLOWED_USER_GRADES else "pro_coin"


def referral_allowed_exchanges(policy: Dict[str, Any]) -> Set[str]:
    raw_allowed = policy.get("allowed_exchanges", []) if isinstance(policy, dict) else []
    if not isinstance(raw_allowed, list):
        return set(DOMESTIC_OPEN_EXCHANGES)
    referred = {
        str(exchange or "").strip().lower()
        for exchange in raw_allowed
        if str(exchange or "").strip().lower() in REFERRAL_SAFE_EXCHANGES
    }
    # 국내 현물은 제휴 UID 귀속이 없는 공개 무료 경로다. 해외 거래소의
    # enabled+verified 레퍼럴 계약과 섞지 않는다.
    return set(DOMESTIC_OPEN_EXCHANGES) | referred


def membership_position_cap(
    user_grade: Any,
    policy: Dict[str, Any] | None = None,
    *,
    strategy_validation: bool = False,
) -> int:
    """Return the signed-plan ceiling for one crypto venue.

    Strategy creation and isolated PAPER validation are product commons: every
    member gets the same validation ceiling.  Account LIVE/PAPER operation uses
    the membership ceiling.  A server policy may reduce, but never silently
    raise, the product default.
    """
    if strategy_validation:
        return STRATEGY_VALIDATION_POSITION_LIMIT
    grade = normalize_user_grade(user_grade)
    default = (
        PAID_MANAGED_POSITION_LIMIT
        if grade in {"pro_coin", "premium"}
        else FREE_MANAGED_POSITION_LIMIT
        if grade == "referral"
        else 0
    )
    if default <= 0:
        return 0
    raw = (policy or {}).get("max_managed_positions_per_venue") if isinstance(policy, dict) else None
    if raw in (None, ""):
        return default
    try:
        return max(1, min(default, int(raw)))
    except (TypeError, ValueError):
        return default


def referral_program(policy: Dict[str, Any], exchange: Any) -> Dict[str, Any]:
    """서버가 서명해 전달한 거래소별 레퍼럴 귀속 상태를 안전하게 찾는다."""
    normalized_exchange = str(exchange or "").strip().lower()
    if normalized_exchange not in REFERRAL_SAFE_EXCHANGES or not isinstance(policy, dict):
        return {}
    raw_programs = policy.get("referral_programs", [])
    if not isinstance(raw_programs, list):
        return {}
    for raw_program in raw_programs:
        if not isinstance(raw_program, dict):
            continue
        if str(raw_program.get("exchange") or "").strip().lower() != normalized_exchange:
            continue
        status = str(raw_program.get("attribution_status") or "required").strip().lower()
        if status not in REFERRAL_ATTRIBUTION_STATUSES:
            status = "required"
        referral_url = str(raw_program.get("referral_url") or "").strip()
        if referral_url and not referral_url.lower().startswith("https://"):
            referral_url = ""
        return {
            "exchange": normalized_exchange,
            "display_name": str(raw_program.get("display_name") or normalized_exchange.upper()),
            "enabled": bool(raw_program.get("enabled", False)),
            "attribution_status": status,
            "uid_masked": str(raw_program.get("uid_masked") or ""),
            "referral_url": referral_url,
            "referral_code": str(raw_program.get("referral_code") or ""),
            "rejection_reason": str(raw_program.get("rejection_reason") or ""),
            "verification_method": str(raw_program.get("verification_method") or ""),
            "verification_error": str(raw_program.get("verification_error") or ""),
            "auto_verification_available": bool(raw_program.get("auto_verification_available", False)),
            "can_configure_api": bool(raw_program.get("can_configure_api", False)),
            "can_verify_affiliation": bool(raw_program.get("can_verify_affiliation", False)),
            "can_select_exchange": bool(raw_program.get("can_select_exchange", False)),
            "can_start_trading": bool(raw_program.get("can_start_trading", False)),
        }
    return {}


def referral_exchange_entitlement(user_grade: Any, exchange: Any, policy: Dict[str, Any]) -> Dict[str, Any]:
    """설정·API·실행 화면이 공유하는 사용자별 거래소 권한 설명을 만든다."""
    grade = normalize_user_grade(user_grade)
    normalized_exchange = str(exchange or "").strip().lower()
    if grade == "referral" and normalized_exchange in DOMESTIC_OPEN_EXCHANGES:
        return {
            "exchange": normalized_exchange,
            "status": "domestic_free",
            "label": "국내 현물 무료 이용 · 레퍼럴 확인 불필요",
            "allowed": True,
            "referral_url": "",
            "uid_masked": "",
            "reason": "",
            "can_verify_affiliation": False,
            "auto_verification_available": False,
            "verification_method": "not_required_domestic",
        }
    if grade != "referral":
        return {
            "exchange": normalized_exchange,
            "status": "paid_exempt",
            "label": "라이선스 회원 · 레퍼럴 확인 불필요",
            "allowed": is_exchange_allowed(grade, normalized_exchange, policy),
            "referral_url": "",
            "uid_masked": "",
            "reason": "",
            "can_verify_affiliation": True,
        }

    program = referral_program(policy, normalized_exchange)
    status = str(program.get("attribution_status") or "required")
    enabled = bool(program.get("enabled", False))
    allowed = bool(
        status == "verified"
        and enabled
        and program.get("can_configure_api")
        and is_exchange_allowed(grade, normalized_exchange, policy)
    )
    uid_masked = str(program.get("uid_masked") or "")
    reason = str(program.get("rejection_reason") or "")
    verification_method = str(program.get("verification_method") or "")
    if allowed:
        prefix = "레퍼럴 자동 승인" if verification_method == "auto_verified" else "정상 레퍼럴 승인"
        label = f"{prefix} · {uid_masked}" if uid_masked else prefix
    elif status == "verified":
        label = "귀속 승인 완료 · 거래소 운영 활성화 대기"
    elif status == "pending":
        label = f"UID 귀속 확인 대기 · {uid_masked}" if uid_masked else "UID 귀속 확인 대기"
    elif status == "rejected":
        label = "레퍼럴 귀속 불일치"
    elif status == "expired":
        label = "레퍼럴 승인 만료"
    elif program.get("referral_url"):
        label = "레퍼럴 가입·UID 확인 필요"
    else:
        label = "제휴 준비 중"
    return {
        "exchange": normalized_exchange,
        "status": status,
        "label": label,
        "allowed": allowed,
        "referral_url": str(program.get("referral_url") or ""),
        "uid_masked": uid_masked,
        "reason": reason,
        "can_verify_affiliation": bool(program.get("can_verify_affiliation", False)),
        "auto_verification_available": bool(program.get("auto_verification_available", False)),
        "verification_method": verification_method,
    }


def is_exchange_allowed(user_grade: Any, exchange: Any, policy: Dict[str, Any]) -> bool:
    grade = normalize_user_grade(user_grade)
    normalized_exchange = str(exchange or "").strip().lower()
    if grade == "pro_stock":
        return False
    if grade == "referral":
        return normalized_exchange in referral_allowed_exchanges(policy)
    return normalized_exchange in SUPPORTED_CRYPTO_EXCHANGES


def membership_source_access(user_grade: Any, source: Any, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Return one user-facing, secret-free membership decision for a venue.

    API credential validity and membership permission are deliberately separate:
    a valid exchange key must never make a pending referral look executable.
    """
    grade = normalize_user_grade(user_grade)
    normalized = str(source or "").strip().lower()
    if normalized in SUPPORTED_CRYPTO_EXCHANGES:
        if grade == "referral":
            return referral_exchange_entitlement(grade, normalized, policy)
        allowed = is_exchange_allowed(grade, normalized, policy)
        return {
            "exchange": normalized,
            "status": "paid_exempt" if allowed else "crypto_plan_required",
            "label": "라이선스 회원 · 거래소 이용 가능" if allowed else "현재 회원등급은 코인 거래를 지원하지 않음",
            "allowed": allowed,
            "reason": "",
            "referral_url": "",
            "uid_masked": "",
        }
    if normalized in {"kiwoom", "shinhan", "mirae", "kis"}:
        allowed = grade in {"pro_stock", "premium"}
        return {
            "exchange": normalized,
            "status": "paid_exempt" if allowed else "stock_plan_required",
            "label": "주식·ETF 이용 가능" if allowed else "현재 회원등급은 주식·ETF 거래를 지원하지 않음",
            "allowed": allowed,
            "reason": "",
            "referral_url": "",
            "uid_masked": "",
        }
    return {
        "exchange": normalized,
        "status": "unsupported_source",
        "label": "지원하지 않는 거래 기관",
        "allowed": False,
        "reason": "",
        "referral_url": "",
        "uid_masked": "",
    }


def membership_denial_code(user_grade: Any, source: Any, policy: Dict[str, Any]) -> str:
    """Return a stable gateway code that tells the UI what the user can do next."""
    access = membership_source_access(user_grade, source, policy)
    if access.get("allowed"):
        return ""
    status = str(access.get("status") or "")
    return {
        "pending": "membership_exchange_approval_pending",
        "rejected": "membership_exchange_approval_rejected",
        "expired": "membership_exchange_approval_expired",
        "verified": "membership_exchange_activation_pending",
        "required": "membership_exchange_approval_required",
        "crypto_plan_required": "membership_crypto_plan_required",
        "stock_plan_required": "membership_stock_plan_required",
        "unsupported_source": "membership_source_unsupported",
    }.get(status, "membership_exchange_not_approved")
