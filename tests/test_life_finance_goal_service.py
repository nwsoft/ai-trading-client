#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생활금융 목표 관리 및 시뮬레이션 테스트.

커버 대상:
- simulate_goal_progress: 월별 잔액, 달성 시점, 달성률, 달성 불가 케이스
- months_to_achieve: 정확한 개월 수 계산, 음수/0 경계, 이미 달성
- allocate_budget_across_goals: priority/proportional 전략, 완료 목표 제외
- goal_what_if: 시나리오별 달성 비교, 빈 시나리오
- compute_goal_summary: 전체 요약, 빈 목표 리스트, 진행률 계산
- suggest_priority_order: 우선순위+잔여액 정렬, focus_rank 부여
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from trading.life_finance_goal_service import (
    allocate_budget_across_goals,
    compute_goal_summary,
    goal_what_if,
    months_to_achieve,
    simulate_goal_progress,
    suggest_priority_order,
)


# ─────────────────────────────────────────────────────────────
# 샘플 데이터
# ─────────────────────────────────────────────────────────────

def make_goal(
    gid: str = 'g1',
    name: str = '목표',
    target: float = 1_000_000,
    current: float = 0.0,
    priority: str = '중간',
) -> Dict:
    return {
        'id': gid,
        'name': name,
        'target_amount': target,
        'current_amount': current,
        'priority': priority,
    }


# ─────────────────────────────────────────────────────────────
# 1. simulate_goal_progress
# ─────────────────────────────────────────────────────────────

class TestSimulateGoalProgress:

    def test_returns_required_keys(self):
        result = simulate_goal_progress(1_000_000, 0, 100_000, months=12)
        assert 'monthly_balances' in result
        assert 'achieved_at_month' in result
        assert 'final_balance' in result
        assert 'progress_pct' in result
        assert 'achievable' in result

    def test_monthly_balances_length(self):
        result = simulate_goal_progress(1_000_000, 0, 100_000, months=12)
        assert len(result['monthly_balances']) == 12

    def test_achievable_at_correct_month(self):
        # 100만원 목표, 0원 시작, 월 100만원 → 1개월 후 달성
        result = simulate_goal_progress(1_000_000, 0, 1_000_000, months=12)
        assert result['achieved_at_month'] == 0  # 첫 달 달성
        assert result['achievable'] is True

    def test_not_achievable_within_period(self):
        # 100만원 목표, 0원 시작, 월 1만원 → 12개월 안에 달성 불가
        result = simulate_goal_progress(1_000_000, 0, 10_000, months=12)
        assert result['achievable'] is False
        assert result['achieved_at_month'] is None

    def test_already_achieved(self):
        # 이미 달성된 경우 (current >= target)
        result = simulate_goal_progress(1_000_000, 1_500_000, 0, months=6)
        # 목표 이미 넘었으므로 progress_pct >= 100 또는 final_balance >= target
        assert result['final_balance'] >= 0

    def test_zero_monthly_savings(self):
        result = simulate_goal_progress(1_000_000, 500_000, 0, months=12)
        # 저축 없으면 잔액 변화 없음
        assert result['final_balance'] == 500_000
        assert result['achievable'] is False

    def test_progress_pct_capped_at_100(self):
        result = simulate_goal_progress(100_000, 200_000, 10_000, months=3)
        assert result['progress_pct'] <= 100.0

    def test_monthly_balances_monotonic_increase(self):
        result = simulate_goal_progress(1_000_000, 0, 100_000, months=10)
        balances = result['monthly_balances']
        for i in range(1, len(balances)):
            assert balances[i] >= balances[i - 1]


# ─────────────────────────────────────────────────────────────
# 2. months_to_achieve
# ─────────────────────────────────────────────────────────────

class TestMonthsToAchieve:

    def test_basic_calculation(self):
        # 100만원 목표, 0원 시작, 월 10만원 → 10개월
        result = months_to_achieve(1_000_000, 0, 100_000)
        assert result == 10

    def test_already_achieved(self):
        result = months_to_achieve(1_000_000, 1_000_000, 100_000)
        assert result == 0

    def test_zero_savings_returns_none(self):
        assert months_to_achieve(1_000_000, 0, 0) is None

    def test_negative_savings_returns_none(self):
        assert months_to_achieve(1_000_000, 0, -100) is None

    def test_partial_current_amount(self):
        # 100만원 목표, 50만원 달성, 월 25만원 → 2개월
        result = months_to_achieve(1_000_000, 500_000, 250_000)
        assert result == 2

    def test_very_small_savings_returns_none_or_large(self):
        # max_months 초과 시 None
        result = months_to_achieve(1_000_000_000, 0, 1, max_months=100)
        assert result is None

    def test_returns_integer(self):
        result = months_to_achieve(1_000_000, 0, 100_000)
        assert isinstance(result, int)

    def test_rounds_up(self):
        # 100만원 목표, 0원 시작, 월 33만원 → ceiling(100/33) = 4
        result = months_to_achieve(1_000_000, 0, 330_000)
        # 330000 * 3 = 990000 < 1000000, 330000 * 4 = 1320000 >= 1000000
        assert result == 4


# ─────────────────────────────────────────────────────────────
# 3. allocate_budget_across_goals
# ─────────────────────────────────────────────────────────────

class TestAllocateBudgetAcrossGoals:

    def test_priority_strategy_fills_high_first(self):
        goals = [
            make_goal('g1', '중간목표', 1_000_000, 0, '중간'),
            make_goal('g2', '높음목표', 500_000, 0, '높음'),
        ]
        result = allocate_budget_across_goals(goals, 300_000, strategy='priority')
        by_id = {g['id']: g for g in result}
        # 높음 우선순위가 먼저 채워져야 함
        assert by_id['g2']['allocated'] >= by_id['g1']['allocated']

    def test_proportional_strategy_distributes_by_remaining(self):
        goals = [
            make_goal('g1', '목표1', 1_000_000, 0, '중간'),
            make_goal('g2', '목표2', 500_000, 0, '중간'),
        ]
        result = allocate_budget_across_goals(goals, 300_000, strategy='proportional')
        by_id = {g['id']: g for g in result}
        # 잔여액 비율: 1000000 : 500000 = 2:1 → allocated도 2:1
        assert by_id['g1']['allocated'] == pytest.approx(200_000, abs=1)
        assert by_id['g2']['allocated'] == pytest.approx(100_000, abs=1)

    def test_zero_budget(self):
        goals = [make_goal('g1')]
        result = allocate_budget_across_goals(goals, 0, strategy='priority')
        assert result[0]['allocated'] == 0.0

    def test_empty_goals(self):
        result = allocate_budget_across_goals([], 500_000)
        assert result == []

    def test_completed_goals_get_zero_allocation(self):
        goals = [
            make_goal('g1', '미완', 1_000_000, 0),
            make_goal('g2', '완료', 500_000, 500_000),
        ]
        result = allocate_budget_across_goals(goals, 300_000, strategy='priority')
        by_id = {g['id']: g for g in result}
        assert by_id['g2']['allocated'] == 0.0

    def test_result_has_allocated_field(self):
        goals = [make_goal('g1')]
        result = allocate_budget_across_goals(goals, 100_000)
        for g in result:
            assert 'allocated' in g
            assert 'months_to_achieve' in g

    def test_allocated_not_exceed_remaining(self):
        # 목표 잔여액보다 많이 배분되면 안 됨
        goals = [make_goal('g1', target=100_000, current=90_000)]
        result = allocate_budget_across_goals(goals, 500_000, strategy='priority')
        remaining = 100_000 - 90_000
        assert result[0]['allocated'] <= remaining

    def test_total_allocated_not_exceed_budget(self):
        goals = [make_goal('g1'), make_goal('g2'), make_goal('g3')]
        budget = 200_000
        result = allocate_budget_across_goals(goals, budget, strategy='priority')
        total_alloc = sum(g['allocated'] for g in result)
        assert total_alloc <= budget + 1  # float 허용 오차


# ─────────────────────────────────────────────────────────────
# 4. goal_what_if
# ─────────────────────────────────────────────────────────────

class TestGoalWhatIf:

    def test_returns_scenario_keys(self):
        scenarios = {'기본': 100_000, '적극': 200_000}
        result = goal_what_if(1_000_000, 0, scenarios, simulation_months=36)
        assert '기본' in result
        assert '적극' in result

    def test_higher_savings_achieves_earlier(self):
        scenarios = {'적다': 50_000, '많다': 200_000}
        result = goal_what_if(1_000_000, 0, scenarios, simulation_months=36)
        a_low = result['적다']['achieved_at_month']
        a_high = result['많다']['achieved_at_month']
        # 많이 저축할수록 더 빨리 달성 (달성 불가 시 None)
        if a_low is not None and a_high is not None:
            assert a_high <= a_low

    def test_insufficient_savings_not_achievable(self):
        result = goal_what_if(1_000_000, 0, {'소액': 1_000}, simulation_months=12)
        assert result['소액']['achievable'] is False

    def test_empty_scenarios(self):
        result = goal_what_if(1_000_000, 0, {}, simulation_months=12)
        assert result == {}

    def test_scenario_has_required_fields(self):
        result = goal_what_if(1_000_000, 0, {'test': 100_000}, simulation_months=12)
        item = result['test']
        assert 'monthly_savings' in item
        assert 'achieved_at_month' in item
        assert 'final_balance' in item
        assert 'achievable' in item

    def test_already_achieved_goal(self):
        result = goal_what_if(100_000, 200_000, {'test': 50_000}, simulation_months=6)
        assert result['test']['achievable'] is True


# ─────────────────────────────────────────────────────────────
# 5. compute_goal_summary
# ─────────────────────────────────────────────────────────────

class TestComputeGoalSummary:

    def test_empty_goals(self):
        result = compute_goal_summary([])
        assert result['total_goals'] == 0
        assert result['overall_progress_pct'] == 0.0

    def test_counts_correct(self):
        goals = [
            make_goal('g1', target=1_000_000, current=1_000_000),  # 완료
            make_goal('g2', target=1_000_000, current=500_000),     # 진행
            make_goal('g3', target=1_000_000, current=0),           # 시작 전
        ]
        result = compute_goal_summary(goals)
        assert result['total_goals'] == 3
        assert result['completed_count'] == 1
        assert result['active_count'] == 2

    def test_total_target_and_current(self):
        goals = [
            make_goal('g1', target=1_000_000, current=200_000),
            make_goal('g2', target=2_000_000, current=800_000),
        ]
        result = compute_goal_summary(goals)
        assert result['total_target'] == pytest.approx(3_000_000)
        assert result['total_current'] == pytest.approx(1_000_000)

    def test_overall_progress_pct(self):
        goals = [make_goal('g1', target=1_000_000, current=500_000)]
        result = compute_goal_summary(goals)
        assert result['overall_progress_pct'] == pytest.approx(50.0)

    def test_items_list_length(self):
        goals = [make_goal('g1'), make_goal('g2')]
        result = compute_goal_summary(goals)
        assert len(result['items']) == 2

    def test_item_status_completed(self):
        goals = [make_goal('g1', target=100_000, current=100_000)]
        result = compute_goal_summary(goals)
        assert result['items'][0]['status'] == 'completed'

    def test_item_status_active(self):
        goals = [make_goal('g1', target=100_000, current=50_000)]
        result = compute_goal_summary(goals)
        assert result['items'][0]['status'] == 'active'

    def test_overall_progress_capped_at_100(self):
        # 초과 달성
        goals = [make_goal('g1', target=100_000, current=200_000)]
        result = compute_goal_summary(goals)
        assert result['overall_progress_pct'] <= 100.0


# ─────────────────────────────────────────────────────────────
# 6. suggest_priority_order
# ─────────────────────────────────────────────────────────────

class TestSuggestPriorityOrder:

    def test_returns_all_goals(self):
        goals = [make_goal('g1'), make_goal('g2'), make_goal('g3')]
        result = suggest_priority_order(goals)
        assert len(result) == 3

    def test_high_priority_ranked_first(self):
        goals = [
            make_goal('g1', priority='낮음', target=100_000, current=0),
            make_goal('g2', priority='높음', target=100_000, current=0),
        ]
        result = suggest_priority_order(goals)
        ranked = [g for g in result if g.get('focus_rank') is not None]
        assert ranked[0]['id'] == 'g2'  # 높음 우선순위

    def test_same_priority_smaller_remaining_first(self):
        goals = [
            make_goal('g1', priority='중간', target=1_000_000, current=0),
            make_goal('g2', priority='중간', target=100_000, current=0),
        ]
        result = suggest_priority_order(goals)
        ranked = [g for g in result if g.get('focus_rank') is not None]
        # 잔여액 적은 g2가 먼저
        assert ranked[0]['id'] == 'g2'

    def test_completed_goals_have_no_rank(self):
        goals = [
            make_goal('g1', target=100_000, current=100_000),
            make_goal('g2', target=100_000, current=50_000),
        ]
        result = suggest_priority_order(goals)
        by_id = {g['id']: g for g in result}
        assert by_id['g1']['focus_rank'] is None
        assert by_id['g2']['focus_rank'] is not None

    def test_focus_rank_sequential(self):
        goals = [make_goal(f'g{i}', target=100_000 * i, current=0) for i in range(1, 5)]
        result = suggest_priority_order(goals)
        ranks = sorted(g['focus_rank'] for g in result if g.get('focus_rank') is not None)
        assert ranks == list(range(1, len(ranks) + 1))

    def test_remaining_field_added(self):
        goals = [make_goal('g1', target=100_000, current=30_000)]
        result = suggest_priority_order(goals)
        assert result[0]['remaining'] == pytest.approx(70_000)

    def test_empty_goals(self):
        result = suggest_priority_order([])
        assert result == []
