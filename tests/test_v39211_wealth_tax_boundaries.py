"""Customer questions must not manufacture income, eligibility or tax savings."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from trading.life_finance import LifeFinanceManager
from trading.life_finance_assistant import LifeFinanceAssistant
from trading.tax_calculation_service import compare_tax_saving_accounts, calc_card_income_deduction
from web_platform import companion as c
from web_platform.gateway import create_gateway_app


@pytest.fixture
def assistant(tmp_path):
    return LifeFinanceAssistant(LifeFinanceManager(
        data_dir=str(tmp_path/'data'), backup_dir=str(tmp_path/'backup'),
        external_sync_dir=str(tmp_path/'sync')))


@pytest.mark.parametrize('question', ['ISA와 IRP 중 내게 뭐가 유리해?', '연말정산 계산해줘',
    '금융소득 종합과세 확인', '이자 1500만원 종합과세 확인', '배당 800만원 종합과세 확인'])
def test_missing_tax_basis_never_becomes_income_or_zero(assistant, question):
    result = asyncio.run(assistant.process_command(question))
    assert result['data']['status'] == 'needs_input'
    assert result['action_taken'] is None
    assert '5000만원' not in result['response'] and '추천:' not in result['response']


@pytest.mark.parametrize('question,total,subject', [
    ('이자 1500만원 배당 800만원 종합과세 확인', 23_000_000, True),
    ('이자 0원 배당 800만원 종합과세 확인', 8_000_000, False),
    ('이자 1500만원 배당 500만원 종합과세 확인', 20_000_000, False),
    ('이자 15,000,000원 배당 8,000,000원 종합과세 확인', 23_000_000, True)])
def test_both_named_income_fields_and_actual_result_key(assistant, question, total, subject):
    result = asyncio.run(assistant.process_command(question))
    assert result['data']['total_financial_income'] == total
    assert result['data']['subject_to_comprehensive_tax'] is subject
    assert '납세 완료' not in result['response'].replace('납세 완료를 뜻하지 않습니다', '')


def test_year_end_does_not_report_decision_tax_as_refund_or_payment(assistant):
    result = asyncio.run(assistant.process_command('연봉 6000만원 연말정산 계산'))
    assert result['data']['annual_salary'] == 60_000_000
    assert '납부 예상' not in result['response'] and '환급 예상' not in result['response']
    assert '기납부세액' in result['response']


def test_isa_uses_separate_tax_after_exemption():
    result = compare_tax_saving_accounts(50_000_000, 10_000_000, 3, .1)
    isa = result['scenarios']['ISA']
    assert isa['estimated_total_interest'] == 3_100_000
    assert isa['tax_on_interest'] == 108_900  # (3,100,000 - 2,000,000) * 9.9%
    assert isa['tax_saving_vs_normal'] == 368_500
    assert result['best_scenario'] is None
    assert result['scenarios']['IRP']['tax_on_interest'] is None


def test_isa_minimum_term_and_total_contribution_limit():
    short = compare_tax_saving_accounts(50_000_000, 10_000_000, 2, .1)['scenarios']['ISA']
    assert short['tax_on_interest'] is None and short['total_benefit'] is None
    long = compare_tax_saving_accounts(50_000_000, 20_000_000, 6, .1)['scenarios']['ISA']
    balance = 0
    for _ in range(5):
        balance = balance * 1.1 + 20_000_000
    assert long['estimated_total_interest'] == round(balance * 1.1 - 100_000_000)


def test_mixed_card_threshold_is_deducted_from_credit_first():
    assert calc_card_income_deduction(40_000_000, 10_000_000, 5_000_000)['deduction_amount'] == 1_500_000
    assert calc_card_income_deduction(40_000_000, 5_000_000, 10_000_000)['deduction_amount'] == 1_500_000


@pytest.mark.parametrize('question,action', [
    ('ISA와 IRP 중 내게 뭐가 유리해?', 'tax'), ('5년 예금하면 비과세야?', 'tax'),
    ('매달 나가는 돈을 줄이고 절세해서 목돈을 모으고 싶어', 'tax'),
    ('구독료와 보험료 줄여서 월30만원 더 모으고 싶어', 'life')])
def test_companion_preserves_tax_and_expense_intent(question, action):
    briefing = c.build_briefing(operations={}, account={}, finance=None, catalog={}, market={},
        plans={}, now=datetime.now(timezone.utc))
    result = c.query(question, briefing, {})
    assert result['status'] == 'clarification'
    assert action in [a['id'] for a in result['actions']]
    assert not result['orders_submitted'] and not result['provider_called'] and not result['saved']
    if action == 'tax':
        target = next(a for a in result['actions'] if a['id'] == action)
        assert target['feature'] == 'personal_finance.tax'


def test_gateway_rejects_missing_basis_instead_of_default_zero():
    calls = []
    services = SimpleNamespace(account='synthetic', runtime_snapshot=lambda: {},
        calculate_life_tax=lambda **kw: calls.append(kw) or {'result': {}})
    token = 'synthetic-tax-boundary-token-long-enough'
    client = TestClient(create_gateway_app(token=token, application_services=services))
    headers = {'Authorization': 'Bearer '+token, 'X-NoahAI-Intent': 'confirmed'}
    for kind in ('year_end', 'financial_income', 'saving_accounts', 'optimization'):
        assert client.post('/api/v1/life-finance/tax', json={'calculation': kind}, headers=headers).status_code == 422
    assert not calls
    response = client.post('/api/v1/life-finance/tax', json={'calculation': 'financial_income',
        'interest_income': 0, 'dividend_income': 0}, headers=headers)
    assert response.status_code == 200 and len(calls) == 1


@pytest.mark.parametrize('service', ['blockchain', 'stock', 'portfolio', 'ai_analyst', 'personal_finance'])
@pytest.mark.parametrize('question,action', [('ISA와 IRP 중 내게 뭐가 유리해?', 'tax'),
    ('구독료와 매달 나가는 돈을 아끼고 싶어', 'life')])
def test_general_assistant_uses_same_local_finance_guidance(monkeypatch, service, question, action):
    import web_platform.application_services as module
    obj = module.ApplicationServices.__new__(module.ApplicationServices)
    obj.account = 'synthetic'
    briefing = c.build_briefing(operations={}, account={}, finance=None, catalog={}, market={},
        plans={}, now=datetime.now(timezone.utc))
    obj.companion_query = lambda **kw: c.query(kw['question'], briefing, {}, service=kw['service'])
    def forbidden(*args, **kwargs):
        raise AssertionError('local guide must not construct AI configuration or provider')
    monkeypatch.setattr(module, 'load_settings', forbidden)
    result = obj.ask_assistant(question=question, service=service, explanation_level='beginner')
    assert action in [a['id'] for a in result['actions']]
    assert result['source'] == 'local_companion_evidence' and not result['provider_called']
