from membership_policy import (
    is_exchange_allowed,
    normalize_user_grade,
    referral_allowed_exchanges,
)
from pathlib import Path


def test_referral_grade_aliases_are_distinct_from_paid_coin() -> None:
    assert normalize_user_grade("free") == "referral"
    assert normalize_user_grade("레퍼럴") == "referral"
    assert normalize_user_grade("pro_coin") == "pro_coin"


def test_referral_exchange_policy_allows_only_server_list_and_foreign_safe_set() -> None:
    policy = {
        "allowed_exchanges": ["binance", "bybit", "upbit", "bithumb", "unknown"],
    }

    assert referral_allowed_exchanges(policy) == {"binance", "bybit"}
    assert is_exchange_allowed("referral", "binance", policy)
    assert not is_exchange_allowed("referral", "upbit", policy)
    assert not is_exchange_allowed("referral", "bithumb", policy)
    assert not is_exchange_allowed("referral", "okx", policy)


def test_missing_or_tampered_referral_policy_fails_closed() -> None:
    assert not is_exchange_allowed("referral", "binance", {})
    assert not is_exchange_allowed(
        "referral",
        "binance",
        {"allowed_exchanges": "binance"},
    )


def test_paid_asset_grades_keep_their_asset_boundary() -> None:
    assert is_exchange_allowed("pro_coin", "upbit", {})
    assert is_exchange_allowed("premium", "bitget", {})
    assert not is_exchange_allowed("pro_stock", "binance", {})


def test_status_check_refresh_emits_exchange_runtime_heartbeat() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    section = source.split("def apply_server_membership_policy", 1)[1].split(
        "def create_user_files_in_account_folder", 1
    )[0]

    assert '_emit_exchange_runtime_snapshot(trigger="heartbeat:status_check")' in section
