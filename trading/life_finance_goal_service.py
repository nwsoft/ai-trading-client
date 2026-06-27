#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생활금융 목표 관리 및 시뮬레이션 서비스.

목적:
- 여러 재정 목표를 통합 관리하고 달성 가능성을 분석한다.
- 월 저축 가능액을 우선순위별로 배분하고, 달성 시점을 예측한다.
- "만약 월 X만원씩 더 저축하면?" 같은 What-if 시나리오를 계산한다.

이 모듈은 순수 Python 로직으로, 파일 I/O 없이 동작한다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


PRIORITY_ORDER = {'높음': 0, '중간': 1, '낮음': 2}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────
# 1. 단일 목표 시뮬레이션
# ─────────────────────────────────────────────────────────────

def simulate_goal_progress(
    target_amount: float,
    current_amount: float,
    monthly_savings: float,
    months: int = 36,
) -> Dict[str, Any]:
    """단일 목표의 월별 저축 진행률을 시뮬레이션한다.

    Parameters
    ----------
    target_amount: 목표 금액
    current_amount: 현재 저축액
    monthly_savings: 매월 추가 저축액
    months: 시뮬레이션 기간 (개월)

    Returns
    -------
    {
      'monthly_balances': [float, ...],     # 월말 잔액 리스트 (길이=months)
      'achieved_at_month': int | None,       # 달성 예상 월 (인덱스 0-based)
      'final_balance': float,
      'progress_pct': float,                 # 최종 달성률 (%)
      'achievable': bool,
    }
    """
    target = max(0.0, _to_float(target_amount))
    current = max(0.0, _to_float(current_amount))
    monthly = _to_float(monthly_savings)
    periods = max(1, _to_int(months))

    balances = []
    achieved_at: Optional[int] = None
    bal = current

    for m in range(periods):
        bal = bal + monthly
        bal = max(0.0, bal)
        balances.append(round(bal, 2))
        if achieved_at is None and target > 0 and bal >= target:
            achieved_at = m

    final = balances[-1] if balances else current
    progress = (final / target * 100) if target > 0 else 0.0

    return {
        'monthly_balances': balances,
        'achieved_at_month': achieved_at,
        'final_balance': round(final, 2),
        'progress_pct': round(min(100.0, progress), 2),
        'achievable': achieved_at is not None,
    }


def months_to_achieve(
    target_amount: float,
    current_amount: float,
    monthly_savings: float,
    max_months: int = 600,
) -> Optional[int]:
    """목표 달성까지 필요한 개월 수를 반환한다.

    달성 불가능하거나 monthly_savings <= 0 이면 None 반환.
    """
    target = _to_float(target_amount)
    current = _to_float(current_amount)
    monthly = _to_float(monthly_savings)

    if monthly <= 0:
        return None
    remaining = target - current
    if remaining <= 0:
        return 0
    months = remaining / monthly
    result = int(months) if months == int(months) else int(months) + 1
    return result if result <= max_months else None


# ─────────────────────────────────────────────────────────────
# 2. 다목표 예산 배분
# ─────────────────────────────────────────────────────────────

def allocate_budget_across_goals(
    goals: List[Dict[str, Any]],
    monthly_budget: float,
    strategy: str = 'priority',
) -> List[Dict[str, Any]]:
    """월 예산을 여러 목표에 배분한다.

    Parameters
    ----------
    goals:
        각 목표 dict. 필수 키: 'id', 'name', 'target_amount', 'current_amount'.
        선택 키: 'priority' ('높음'|'중간'|'낮음'), 'monthly_request' (희망 배분액).
    monthly_budget:
        이번 달 배분 가능한 총액.
    strategy:
        'priority' — 높음 → 중간 → 낮음 순으로 순차 충당.
        'proportional' — 잔여 금액 비율로 배분.

    Returns
    -------
    goals에 'allocated', 'months_to_achieve' 필드를 추가한 리스트.
    """
    budget = max(0.0, _to_float(monthly_budget))
    if not goals:
        return []

    # 완료된 목표 제외
    active = [g for g in goals if _to_float(g.get('current_amount')) < _to_float(g.get('target_amount', 0))]
    completed = [g for g in goals if g not in active]

    result = []

    if strategy == 'priority':
        sorted_goals = sorted(
            active,
            key=lambda g: PRIORITY_ORDER.get(str(g.get('priority', '중간')), 1),
        )
        remaining = budget
        for g in sorted_goals:
            target = _to_float(g.get('target_amount', 0))
            current = _to_float(g.get('current_amount', 0))
            need = max(0.0, target - current)
            alloc = min(need, remaining)
            remaining -= alloc
            allocated = round(alloc, 2)
            mta = months_to_achieve(target, current, allocated) if allocated > 0 else None
            result.append({**g, 'allocated': allocated, 'months_to_achieve': mta})

    elif strategy == 'proportional':
        remainders = [
            max(0.0, _to_float(g.get('target_amount', 0)) - _to_float(g.get('current_amount', 0)))
            for g in active
        ]
        total_need = sum(remainders)
        for g, rem in zip(active, remainders):
            if total_need > 0:
                alloc = round(budget * rem / total_need, 2)
            else:
                alloc = 0.0
            target = _to_float(g.get('target_amount', 0))
            current = _to_float(g.get('current_amount', 0))
            mta = months_to_achieve(target, current, alloc) if alloc > 0 else None
            result.append({**g, 'allocated': alloc, 'months_to_achieve': mta})

    else:
        result = [{**g, 'allocated': 0.0, 'months_to_achieve': None} for g in active]

    for g in completed:
        result.append({**g, 'allocated': 0.0, 'months_to_achieve': 0})

    return result


# ─────────────────────────────────────────────────────────────
# 3. What-if 시나리오
# ─────────────────────────────────────────────────────────────

def goal_what_if(
    target_amount: float,
    current_amount: float,
    scenarios: Dict[str, float],
    simulation_months: int = 36,
) -> Dict[str, Dict[str, Any]]:
    """다양한 월 저축 시나리오별 달성 시점을 비교한다.

    Parameters
    ----------
    target_amount: 목표 금액
    current_amount: 현재 저축액
    scenarios:
        { '시나리오명': monthly_savings, ... }
    simulation_months: 최대 시뮬레이션 기간

    Returns
    -------
    {
      '시나리오명': {
        'monthly_savings': float,
        'achieved_at_month': int | None,
        'final_balance': float,
        'achievable': bool,
      }, ...
    }
    """
    results = {}
    for name, monthly in (scenarios or {}).items():
        sim = simulate_goal_progress(
            target_amount=target_amount,
            current_amount=current_amount,
            monthly_savings=monthly,
            months=simulation_months,
        )
        results[name] = {
            'monthly_savings': _to_float(monthly),
            'achieved_at_month': sim['achieved_at_month'],
            'final_balance': sim['final_balance'],
            'achievable': sim['achievable'],
        }
    return results


# ─────────────────────────────────────────────────────────────
# 4. 목표 요약
# ─────────────────────────────────────────────────────────────

def compute_goal_summary(
    goals: List[Dict[str, Any]],
    monthly_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """모든 목표의 통합 요약을 반환한다.

    Returns
    -------
    {
      'total_goals': int,
      'completed_count': int,
      'active_count': int,
      'total_target': float,
      'total_current': float,
      'overall_progress_pct': float,
      'items': [ { 'id', 'name', 'progress_pct', 'remaining', 'status' }, ... ]
    }
    """
    if not goals:
        return {
            'total_goals': 0,
            'completed_count': 0,
            'active_count': 0,
            'total_target': 0.0,
            'total_current': 0.0,
            'overall_progress_pct': 0.0,
            'items': [],
        }

    total_target = sum(_to_float(g.get('target_amount', 0)) for g in goals)
    total_current = sum(_to_float(g.get('current_amount', 0)) for g in goals)
    completed = [g for g in goals if _to_float(g.get('current_amount', 0)) >= _to_float(g.get('target_amount', 0))]
    active = [g for g in goals if g not in completed]

    items = []
    for g in goals:
        target = _to_float(g.get('target_amount', 0))
        current = _to_float(g.get('current_amount', 0))
        remaining = max(0.0, target - current)
        progress = (current / target * 100) if target > 0 else 0.0
        status = 'completed' if remaining == 0 else 'active'
        items.append({
            'id': g.get('id', ''),
            'name': g.get('name', ''),
            'progress_pct': round(min(100.0, progress), 2),
            'remaining': round(remaining, 2),
            'status': status,
            'priority': g.get('priority', '중간'),
        })

    overall = (total_current / total_target * 100) if total_target > 0 else 0.0

    return {
        'total_goals': len(goals),
        'completed_count': len(completed),
        'active_count': len(active),
        'total_target': round(total_target, 2),
        'total_current': round(total_current, 2),
        'overall_progress_pct': round(min(100.0, overall), 2),
        'items': items,
    }


# ─────────────────────────────────────────────────────────────
# 5. 우선순위 정렬 제안
# ─────────────────────────────────────────────────────────────

def suggest_priority_order(
    goals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """달성 용이성(잔여액 적은 것)과 우선순위를 결합해 집중 순서를 제안한다.

    Returns
    -------
    goals를 추천 집중 순서로 정렬한 리스트.
    각 항목에 'focus_rank' (1-based) 필드를 추가.
    """
    active = []
    completed = []
    for g in goals:
        target = _to_float(g.get('target_amount', 0))
        current = _to_float(g.get('current_amount', 0))
        if current >= target:
            completed.append({**g, 'focus_rank': None, 'remaining': 0.0})
        else:
            active.append(g)

    sorted_active = sorted(
        active,
        key=lambda g: (
            PRIORITY_ORDER.get(str(g.get('priority', '중간')), 1),
            max(0.0, _to_float(g.get('target_amount', 0)) - _to_float(g.get('current_amount', 0))),
        ),
    )

    result = []
    for rank, g in enumerate(sorted_active, start=1):
        remaining = max(0.0, _to_float(g.get('target_amount', 0)) - _to_float(g.get('current_amount', 0)))
        result.append({**g, 'focus_rank': rank, 'remaining': round(remaining, 2)})

    result.extend(completed)
    return result
