from membership_policy import (
    is_exchange_allowed,
    normalize_user_grade,
    referral_allowed_exchanges,
    referral_exchange_entitlement,
    referral_program,
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
    entitlement = referral_exchange_entitlement(
        "referral",
        "binance",
        {"allowed_exchanges": ["binance"], "referral_programs": []},
    )
    assert entitlement["allowed"] is False


def test_referral_entitlement_requires_server_verified_uid_and_enabled_program() -> None:
    policy = {
        "allowed_exchanges": ["okx"],
        "referral_programs": [
            {
                "exchange": "okx",
                "enabled": True,
                "attribution_status": "verified",
                "uid_masked": "****1234",
                "referral_url": "https://www.okx.com/join/example",
                "can_configure_api": True,
                "can_select_exchange": True,
                "can_start_trading": True,
            }
        ],
    }
    entitlement = referral_exchange_entitlement("referral", "okx", policy)
    assert entitlement["allowed"] is True
    assert entitlement["status"] == "verified"
    assert "****1234" in entitlement["label"]

    policy["referral_programs"][0]["attribution_status"] = "pending"
    policy["referral_programs"][0]["can_configure_api"] = False
    pending = referral_exchange_entitlement("referral", "okx", policy)
    assert pending["allowed"] is False
    assert "확인 대기" in pending["label"]


def test_referral_program_rejects_non_https_join_url() -> None:
    program = referral_program(
        {
            "referral_programs": [
                {
                    "exchange": "bybit",
                    "attribution_status": "required",
                    "referral_url": "http://unsafe.example/join",
                }
            ]
        },
        "bybit",
    )
    assert program["referral_url"] == ""


def test_settings_and_dashboard_expose_referral_attribution_status_and_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    policy_source = (root / "membership_policy.py").read_text(encoding="utf-8")
    settings = (root / "ui" / "settings_modern.py").read_text(encoding="utf-8")
    dashboard = (root / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")

    assert "정상 레퍼럴 승인" in policy_source
    assert "가입·상태" in settings
    assert "_ensure_referral_api_allowed" in settings
    assert "_register_referral_selection_controls" in settings
    assert "레퍼럴 UID 확인 대기" in dashboard
    main_source = (root / "main.py").read_text(encoding="utf-8")
    start_gate = main_source.split("def _is_exchange_allowed_by_membership", 1)[1].split(
        "def _running_crypto_exchanges", 1
    )[0]
    assert "referral_exchange_entitlement" in start_gate


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
