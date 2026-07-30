from trading.opportunity_coordinator import OpportunityCoordinator


def _authorize(coordinator, target, *, policy=None, quantity=1.0):
    return coordinator.authorize(
        policy=policy or {
            "mode": "parallel",
            "authorized_targets": ["bitget", "okx"],
            "opportunity_window_sec": 60,
            "duplicate_window_sec": 120,
        },
        asset_class="crypto",
        target=target,
        symbol="BTCUSDT",
        direction="LONG",
        quantity=quantity,
        price=100.0,
        stop_fraction=0.01,
        strategy_version="v1",
        signal_time=1_800.0,
    )


def test_parallel_mode_allows_same_opportunity_on_two_selected_venues():
    coordinator = OpportunityCoordinator()
    bitget = _authorize(coordinator, "bitget")
    okx = _authorize(coordinator, "okx")

    assert bitget.allowed is True
    assert okx.allowed is True
    assert bitget.opportunity_id == okx.opportunity_id
    assert bitget.idempotency_key != okx.idempotency_key
    assert okx.aggregate_targets == 2
    assert okx.aggregate_notional == 200.0


def test_duplicate_same_target_account_signal_is_blocked():
    coordinator = OpportunityCoordinator()
    first = _authorize(coordinator, "bitget")
    duplicate = _authorize(coordinator, "bitget")

    assert first.allowed is True
    assert duplicate.allowed is False
    assert duplicate.reason == "duplicate_order_same_target_account_signal"


def test_split_mode_divides_quantity_across_authorized_targets():
    coordinator = OpportunityCoordinator()
    policy = {
        "mode": "split",
        "authorized_targets": ["bitget", "okx"],
    }
    bitget = _authorize(coordinator, "bitget", policy=policy, quantity=2.0)
    okx = _authorize(coordinator, "okx", policy=policy, quantity=2.0)

    assert bitget.authorized_quantity == 1.0
    assert okx.authorized_quantity == 1.0
    assert bitget.quantity_factor == 0.5


def test_best_mode_selects_explicit_or_lowest_cost_target_only():
    coordinator = OpportunityCoordinator()
    policy = {
        "mode": "best",
        "authorized_targets": ["bitget", "okx"],
        "target_cost_bps": {"bitget": 9, "okx": 4},
    }
    bitget = _authorize(coordinator, "bitget", policy=policy)
    okx = _authorize(coordinator, "okx", policy=policy)

    assert bitget.allowed is False
    assert bitget.reason == "best_target_selected:okx"
    assert okx.allowed is True


def test_aggregate_loss_cap_blocks_only_excess_leg():
    coordinator = OpportunityCoordinator()
    policy = {
        "mode": "parallel",
        "authorized_targets": ["bitget", "okx"],
        "max_loss_by_currency": {"USDT": 1.5},
    }
    bitget = _authorize(coordinator, "bitget", policy=policy)
    okx = _authorize(coordinator, "okx", policy=policy)

    assert bitget.allowed is True
    assert bitget.estimated_loss == 1.0
    assert okx.allowed is False
    assert okx.reason == "aggregate_loss_cap_exceeded:USDT"


def test_failed_reservation_can_be_released_and_retried():
    coordinator = OpportunityCoordinator()
    first = _authorize(coordinator, "bitget")
    coordinator.release(first)
    retry = _authorize(coordinator, "bitget")

    assert retry.allowed is True
