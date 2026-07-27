"""서버 회원등급 응답을 공식 클라이언트 실행 권한으로 정규화한다."""

from __future__ import annotations

from typing import Any, Dict, Set


ALLOWED_USER_GRADES = {"referral", "pro_coin", "pro_stock", "premium"}
REFERRAL_SAFE_EXCHANGES = {"binance", "bybit", "okx", "bitget"}
SUPPORTED_CRYPTO_EXCHANGES = REFERRAL_SAFE_EXCHANGES | {"upbit", "bithumb"}


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
        return set()
    return {
        str(exchange or "").strip().lower()
        for exchange in raw_allowed
        if str(exchange or "").strip().lower() in REFERRAL_SAFE_EXCHANGES
    }


def is_exchange_allowed(user_grade: Any, exchange: Any, policy: Dict[str, Any]) -> bool:
    grade = normalize_user_grade(user_grade)
    normalized_exchange = str(exchange or "").strip().lower()
    if grade == "pro_stock":
        return False
    if grade == "referral":
        return normalized_exchange in referral_allowed_exchanges(policy)
    return normalized_exchange in SUPPORTED_CRYPTO_EXCHANGES
