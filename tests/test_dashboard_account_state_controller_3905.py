from ui.controllers.account_state_controller import (
    account_panel_error,
    build_account_panel_result,
    get_exchange_account_contract,
    normalize_spot_holdings,
    select_paper_position_store,
    summarize_paper_positions,
)


def test_spot_exchange_uses_holdings_contract_not_futures_positions():
    contract = get_exchange_account_contract("bithumb")
    assert contract.title == "보유자산"
    assert contract.source == "balance"
    assert contract.holding_mode is True
    assert contract.empty_text == "보유자산 없음"


def test_futures_exchange_keeps_position_contract():
    contract = get_exchange_account_contract("binance")
    assert contract.title == "포지션"
    assert contract.source == "positions"
    assert contract.holding_mode is False


def test_spot_holdings_exclude_quote_and_summary_values():
    holdings = normalize_spot_holdings({
        "KRW": 120000.0,
        "BTC": 0.01,
        "ETH": {"total": 0.4},
        "TOTAL": 999999.0,
        "XRP": 0.0,
    })
    assert set(holdings) == {"BTC", "ETH"}
    assert holdings["BTC"]["quantity"] == 0.01
    assert holdings["ETH"]["side"] == "HOLD"


def test_empty_and_error_are_different_states():
    empty = build_account_panel_result({}, empty_message="보유자산 없음")
    error = account_panel_error("인증 실패", "authentication_failed")
    assert empty.state == "empty"
    assert empty.message == "보유자산 없음"
    assert error.state == "error"
    assert error.error_code == "authentication_failed"


def test_stale_rows_are_explicit_not_reported_as_live_success():
    stale = build_account_panel_result(
        {"BTCUSDT": {"quantity": 0.1}},
        empty_message="활성 포지션 없음",
        stale=True,
        message="실시간 조회 실패 · 로컬 캐시",
    )
    assert stale.state == "stale"
    assert stale.rows
    assert "캐시" in stale.message


def test_paper_position_summary_uses_only_count_and_unrealized_pnl():
    summary = summarize_paper_positions({
        "BTCUSDT": {"unrealized_pnl": 1.25},
        "ETHUSDT": {"unrealizedPnl": -0.4},
    })

    assert summary == {"position_count": 2.0, "unrealized_pnl": 0.85}


def test_paper_store_selector_reads_binance_without_live_store_mix():
    paper_position = {"unrealized_pnl": 0.3}
    snapshot = select_paper_position_store(
        execution_mode="paper",
        exchange="binance",
        binance_store={"BTCUSDT": paper_position},
        unified_stores={"binance": {"LIVEUSDT": object()}},
    )

    assert snapshot == {"BTCUSDT": paper_position}
    assert "LIVEUSDT" not in snapshot


def test_paper_store_selector_reads_unified_store_by_exchange():
    bybit_position = {"unrealized_pnl": -0.2}
    snapshot = select_paper_position_store(
        execution_mode="paper",
        exchange="bybit",
        unified_stores={
            "bybit": {"ETHUSDT": bybit_position},
            "okx": {"OTHER": object()},
        },
    )

    assert snapshot == {"ETHUSDT": bybit_position}


def test_non_paper_mode_does_not_expose_paper_store():
    snapshot = select_paper_position_store(
        execution_mode="learning",
        exchange="binance",
        binance_store={"BTCUSDT": object()},
    )
    assert snapshot is None
