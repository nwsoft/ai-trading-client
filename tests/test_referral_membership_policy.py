from membership_policy import (
    is_exchange_allowed,
    membership_denial_code,
    membership_position_cap,
    membership_source_access,
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


def test_referral_exchange_policy_keeps_domestic_open_and_foreign_verified_set() -> None:
    policy = {
        "allowed_exchanges": ["binance", "bybit", "upbit", "bithumb", "unknown"],
    }

    assert referral_allowed_exchanges(policy) == {"binance", "bybit", "upbit", "bithumb", "coinone"}
    assert is_exchange_allowed("referral", "binance", policy)
    assert is_exchange_allowed("referral", "upbit", policy)
    assert is_exchange_allowed("referral", "bithumb", policy)
    assert is_exchange_allowed("referral", "coinone", policy)
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


def test_referral_denial_codes_distinguish_each_operator_action() -> None:
    base = {
        "allowed_exchanges": ["bybit"],
        "referral_programs": [
            {
                "exchange": "bybit",
                "enabled": True,
                "attribution_status": "pending",
                "uid_masked": "****8484",
                "can_configure_api": False,
            }
        ],
    }

    assert membership_denial_code("referral", "bybit", base) == (
        "membership_exchange_approval_pending"
    )
    for status, expected in {
        "rejected": "membership_exchange_approval_rejected",
        "expired": "membership_exchange_approval_expired",
    }.items():
        base["referral_programs"][0]["attribution_status"] = status
        assert membership_denial_code("referral", "bybit", base) == expected

    base["referral_programs"][0].update(
        attribution_status="verified", can_configure_api=True
    )
    base["allowed_exchanges"] = []
    assert membership_denial_code("referral", "bybit", base) == (
        "membership_exchange_activation_pending"
    )


def test_referral_start_requires_complete_signed_approval_contract() -> None:
    missing_program = {"allowed_exchanges": ["bybit"], "referral_programs": []}
    access = membership_source_access("referral", "bybit", missing_program)
    assert access["allowed"] is False
    assert membership_denial_code("referral", "bybit", missing_program) == (
        "membership_exchange_approval_required"
    )

    approved = {
        "allowed_exchanges": ["bybit"],
        "referral_programs": [
            {
                "exchange": "bybit",
                "enabled": True,
                "attribution_status": "verified",
                "can_configure_api": True,
                "can_start_trading": True,
            }
        ],
    }
    assert membership_source_access("referral", "bybit", approved)["allowed"] is True
    assert membership_denial_code("referral", "bybit", approved) == ""


def test_membership_source_access_keeps_crypto_and_stock_plans_separate() -> None:
    assert membership_denial_code("pro_stock", "bybit", {}) == (
        "membership_crypto_plan_required"
    )
    assert membership_denial_code("pro_coin", "kis", {}) == (
        "membership_stock_plan_required"
    )
    assert membership_source_access("premium", "kis", {})["allowed"] is True


def test_web_gateway_maps_membership_conflicts_to_actionable_korean() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "webui" / "src" / "api.ts").read_text(encoding="utf-8")
    for code in (
        "membership_exchange_approval_required",
        "membership_exchange_approval_pending",
        "membership_exchange_approval_rejected",
        "membership_exchange_approval_expired",
        "membership_exchange_activation_pending",
        "membership_crypto_plan_required",
        "membership_stock_plan_required",
    ):
        assert code in source
    assert "API 키 인증 완료와 거래 권한은 별개" in source


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


def test_position_capacity_is_separate_from_strategy_validation_rights() -> None:
    assert membership_position_cap("referral") == 3
    assert membership_position_cap("pro_coin") == 5
    assert membership_position_cap("premium") == 5
    assert membership_position_cap("pro_stock") == 0
    assert membership_position_cap("referral", strategy_validation=True) == 5
    assert membership_position_cap("premium", strategy_validation=True) == 5
    assert membership_position_cap(
        "premium", {"max_managed_positions_per_venue": 4}
    ) == 4
    assert membership_position_cap(
        "referral", {"max_managed_positions_per_venue": 9}
    ) == 3


def test_domestic_referral_entitlement_does_not_require_referral_uid() -> None:
    entitlement = referral_exchange_entitlement("referral", "coinone", {})
    assert entitlement["allowed"] is True
    assert entitlement["status"] == "domestic_free"
    assert entitlement["verification_method"] == "not_required_domestic"


def test_status_check_refresh_emits_exchange_runtime_heartbeat() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    section = source.split("def apply_server_membership_policy", 1)[1].split(
        "def create_user_files_in_account_folder", 1
    )[0]

    assert '_emit_exchange_runtime_snapshot(trigger="heartbeat:status_check")' in section
