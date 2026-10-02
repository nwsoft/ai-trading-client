from copy import deepcopy
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from trading.life_finance import LifeFinanceManager, TransactionType as Kind
from trading.personal_finance_review import build_finance_review, explain_finance_review
from trading.tax_calculation_service import calc_earned_income_deduction, calc_financial_investment_tax
from web_platform.contracts import LifeTransactionCreateContract


def test_empty_is_not_zero_or_investable():
    result = build_finance_review([], [], today=date(2026, 10, 2))
    assert result["status"] == "no_records"
    assert result["recorded_difference"] is None
    assert "기록 없음" in explain_finance_review(result)


def test_transfer_roundtrip_and_same_millisecond_ids(tmp_path):
    manager = LifeFinanceManager(str(tmp_path))
    today = date.today()
    rows = [manager.add_transaction(today, amount, kind, "qa") for amount, kind in
            [(300, Kind.INCOME), (100, Kind.EXPENSE), (500, Kind.TRANSFER)]]
    assert len({row.id for row in rows}) == 3
    before = manager.transactions_file.read_bytes()
    transfer_before = manager.transfers_file.read_bytes()
    assert [t["type"] for t in json.loads(before)] == ["수입", "지출"]
    manager = LifeFinanceManager(str(tmp_path))
    result = manager.get_finance_review()
    assert result["recorded_difference"] == 200
    assert result["transfer_count"] == 1
    assert result["transfer_amount"] == 500
    assert manager.get_monthly_report(today.year, today.month).total_expense == 100
    assert manager.transactions_file.read_bytes() == before
    assert manager.transfers_file.read_bytes() == transfer_before
    assert list(manager.backup_dir.glob("*_life_finance_transfers.json"))


def test_transfer_separate_sync_and_delete(tmp_path):
    manager = LifeFinanceManager(str(tmp_path), external_sync_dir=str(tmp_path / "sync"))
    row = manager.add_transaction(date.today(), 500, Kind.TRANSFER, "own accounts")
    assert (tmp_path / "sync" / manager.transfers_file.name).read_bytes() == manager.transfers_file.read_bytes()
    assert manager.delete_transaction(row.id)
    assert LifeFinanceManager(str(tmp_path)).transactions == []


def test_corrupt_transfer_file_is_not_silently_discarded(tmp_path):
    path = tmp_path / "life_finance_transfers.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="원본을 보존"):
        LifeFinanceManager(str(tmp_path))
    assert path.read_text(encoding="utf-8") == "{broken"


def test_future_invalid_records_and_goal_no_balance_merge():
    today = date(2026, 10, 2)
    rows = [SimpleNamespace(date=today, amount=100, type=Kind.EXPENSE, category="식비"),
            SimpleNamespace(date=today + timedelta(days=1), amount=1000, type=Kind.INCOME),
            SimpleNamespace(date=today, amount=float("nan"), type=Kind.EXPENSE)]
    goals = [SimpleNamespace(is_completed=False, current_amount=99999, deadline=date(2026, 10, 1))]
    result = build_finance_review(rows, goals, today=today)
    assert result["recorded_difference"] == -100
    assert result["future_count"] == 1 and result["invalid_count"] == 1
    assert result["overdue_goal_count"] == 1
    assert result["income_count"] == 0
    assert any("누락된 수입" in text for text in result["actions"])


@pytest.mark.parametrize("amount", [0, -1, float("inf"), float("nan"), True])
def test_bad_amount_never_saved(tmp_path, amount):
    manager = LifeFinanceManager(str(tmp_path))
    with pytest.raises(ValueError):
        manager.add_transaction(date.today(), amount, Kind.INCOME, "invalid")
    assert manager.transactions == []


def test_transfer_api_contract():
    item = LifeTransactionCreateContract(date="2026-10-02", amount=10, type="내 계좌 이체", description="내 계좌 이동")
    assert item.type == "내 계좌 이체"
    with pytest.raises(ValueError):
        LifeTransactionCreateContract(date="2026-10-02", amount=10, type="typo", description="qa")


@pytest.mark.parametrize("salary,deduction", [(0, 0), (5e6, 3.5e6), (15e6, 7.5e6), (45e6, 12e6), (100e6, 14.75e6), (1e9, 20e6)])
def test_income_deduction_official_boundaries(salary, deduction):
    assert calc_earned_income_deduction(salary) == deduction


@pytest.mark.parametrize("amount", [0, 5e6, 15e6, 355e6])
def test_abolished_tax_is_unknown_not_tax_free(amount):
    result = calc_financial_investment_tax(domestic_stock_profit=amount, overseas_stock_profit=amount)
    assert result["status"] == "abolished_regime"
    assert result["total_tax"] is None
    assert "비과세라는 뜻은 아닙니다" in result["message"]


@pytest.fixture
def services(tmp_path, monkeypatch):
    import web_platform.application_services as module
    monkeypatch.setattr(module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(module, "load_settings", lambda **kw: deepcopy({"paper_trading": True}))
    obj = module.ApplicationServices(account="qa-finance")
    monkeypatch.setattr(obj, "_audit", lambda *a, **kw: None)
    def forbidden(*a, **kw):
        raise AssertionError("No external provider call")
    monkeypatch.setattr(obj.interactive_ai, "ask", forbidden)
    return obj


def test_assistant_explains_local_records_without_json_or_external_calls(services):
    services.add_life_transaction(transaction_date=date.today().isoformat(), amount=100,
                                  transaction_type="내 계좌 이체", description="qa")
    answer = services.ask_assistant(question="이번 달 내 돈 점검해줘", service="personal_finance", explanation_level="standard")
    assert not answer["provider_called"]
    assert "내 계좌 이체 1건" in answer["answer"]
    assert "기록 없음" in answer["answer"]
    answer = services.ask_assistant(question="금투세 얼마 내야 해?", service="personal_finance", explanation_level="standard")
    assert "폐지" in answer["answer"]
    assert "예상 세액: 0" not in answer["answer"]


def test_portfolio_context_does_not_change_allocation_and_isolates_failure(services, monkeypatch):
    fake = {"allocation_by_currency": {"USDT": {"total_value": 123}}, "performance_by_currency": {}}
    monkeypatch.setattr(services.advanced, "portfolio_analysis", lambda **kw: deepcopy(fake))
    monkeypatch.setattr(services.queries, "portfolio_snapshot", lambda: {})
    result = services.portfolio_analysis()
    assert result["allocation_by_currency"] == fake["allocation_by_currency"]
    assert result["finance_review"]["recorded_difference"] is None
    monkeypatch.setattr(services, "_life_finance", lambda: (_ for _ in ()).throw(OSError("private path")))
    result = services.portfolio_analysis()
    assert result["allocation_by_currency"] == fake["allocation_by_currency"]
    assert result["finance_review"]["status"] == "unavailable"
    assert "private path" not in str(result)
