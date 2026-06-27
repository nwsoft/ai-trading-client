#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 주문 가드레일 유틸.

수동/자동 주문 진입 전에 공통 제약을 평가하기 위한 순수 함수 모음.
"""

from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional

from trading.stock_analysis_service import asset_mode_matches


DEFAULT_STOCK_ORDER_GUARDRAILS: Dict[str, Any] = {
    'enabled': True,
    'enforce_market_hours': True,
    'max_order_value': 50_000_000.0,
    'max_quantity': 10_000,
    'daily_order_limit': 20,
    'allow_market_order': True,
    'allow_limit_order': True,
    # 브로커별 최소수량/수량단위(기본: 1주 단위)
    'broker_min_quantity': {
        'kiwoom': 1,
        'shinhan': 1,
        'miraeasset': 1,
    },
    'broker_quantity_step': {
        'kiwoom': 1,
        'shinhan': 1,
        'miraeasset': 1,
    },
}


def _normalize_stock_broker_key(broker: str) -> str:
    """브로커 키 별칭을 내부 표준 키로 정규화한다."""
    broker_norm = str(broker or '').strip().lower()
    alias_map = {
        'mirae_asset': 'miraeasset',
        'mirae-asset': 'miraeasset',
        'miraeasset': 'miraeasset',
    }
    return alias_map.get(broker_norm, broker_norm)


def _resolve_broker_quantity_rule(policy: Dict[str, Any], broker: str) -> Dict[str, float]:
    """브로커별 최소수량/수량단위를 계산한다."""
    broker_norm = _normalize_stock_broker_key(broker)

    min_qty = 1.0
    step_qty = 1.0

    min_map = policy.get('broker_min_quantity', {})
    if broker_norm and isinstance(min_map, dict):
        try:
            normalized_min_map = {
                _normalize_stock_broker_key(str(k)): v for k, v in min_map.items()
            }
            min_qty = float(normalized_min_map.get(broker_norm, 1) or 1)
        except Exception:
            min_qty = 1.0

    step_map = policy.get('broker_quantity_step', {})
    if broker_norm and isinstance(step_map, dict):
        try:
            normalized_step_map = {
                _normalize_stock_broker_key(str(k)): v for k, v in step_map.items()
            }
            step_qty = float(normalized_step_map.get(broker_norm, 1) or 1)
        except Exception:
            step_qty = 1.0

    if min_qty <= 0:
        min_qty = 1.0
    if step_qty <= 0:
        step_qty = 1.0

    return {
        'min_quantity': min_qty,
        'quantity_step': step_qty,
    }


def is_krx_market_open(now: Optional[datetime] = None) -> bool:
    """한국 정규장 시간 여부(간단 규칙)."""
    current = now or datetime.now()
    if current.weekday() >= 5:
        return False
    t = current.time()
    return dtime(9, 0) <= t <= dtime(15, 30)


def normalize_stock_order_guardrails(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """가드레일 설정 병합/정규화."""
    merged = dict(DEFAULT_STOCK_ORDER_GUARDRAILS)
    if isinstance(config, dict):
        merged.update(config)

    merged['enabled'] = bool(merged.get('enabled', True))
    merged['enforce_market_hours'] = bool(merged.get('enforce_market_hours', True))
    merged['allow_market_order'] = bool(merged.get('allow_market_order', True))
    merged['allow_limit_order'] = bool(merged.get('allow_limit_order', True))

    try:
        merged['max_order_value'] = float(merged.get('max_order_value', 50_000_000.0) or 0)
    except Exception:
        merged['max_order_value'] = 50_000_000.0

    try:
        merged['max_quantity'] = int(float(merged.get('max_quantity', 10_000) or 0))
    except Exception:
        merged['max_quantity'] = 10_000

    try:
        merged['daily_order_limit'] = int(float(merged.get('daily_order_limit', 20) or 0))
    except Exception:
        merged['daily_order_limit'] = 20

    return merged


def evaluate_stock_order_guardrails(
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: Optional[float],
    order_type: str,
    broker: str,
    asset_mode: str,
    is_etf: bool,
    daily_order_count: int,
    guardrails: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """주문 입력과 정책 제약을 평가한다.

    Returns:
        {
            'allowed': bool,
            'reasons': List[str],
            'normalized': {...}
        }
    """
    policy = normalize_stock_order_guardrails(guardrails)
    reasons: List[str] = []

    side_norm = str(side or '').strip().upper()
    order_type_norm = str(order_type or '').strip().upper()
    symbol_norm = str(symbol or '').strip()
    broker_norm = _normalize_stock_broker_key(broker)

    qty = 0.0
    try:
        qty = float(quantity)
    except Exception:
        qty = 0.0

    px: Optional[float]
    try:
        px = None if price is None else float(price)
    except Exception:
        px = None

    if not symbol_norm or len(symbol_norm) != 6 or not symbol_norm.isdigit():
        reasons.append('종목코드는 6자리 숫자여야 합니다.')

    if side_norm not in {'BUY', 'SELL'}:
        reasons.append('주문 방향은 BUY 또는 SELL이어야 합니다.')

    if order_type_norm not in {'MARKET', 'LIMIT'}:
        reasons.append('주문 타입은 MARKET 또는 LIMIT이어야 합니다.')

    if qty <= 0:
        reasons.append('주문 수량은 0보다 커야 합니다.')

    if qty > 0 and broker_norm:
        rule = _resolve_broker_quantity_rule(policy, broker_norm)
        min_qty = rule['min_quantity']
        step_qty = rule['quantity_step']

        if qty < min_qty:
            reasons.append(f'{broker_norm.upper()} 최소 주문수량 미달: {qty:g} < {min_qty:g}')

        units = qty / step_qty if step_qty > 0 else qty
        if abs(units - round(units)) > 1e-9:
            reasons.append(f'{broker_norm.upper()} 수량 단위 불일치: {qty:g} (단위 {step_qty:g})')

    max_qty = int(policy.get('max_quantity', 0) or 0)
    if max_qty > 0 and qty > max_qty:
        reasons.append(f'수량 한도 초과: {qty:g} > {max_qty:g}')

    if order_type_norm == 'MARKET' and not policy.get('allow_market_order', True):
        reasons.append('시장가 주문이 비활성화되어 있습니다.')

    if order_type_norm == 'LIMIT' and not policy.get('allow_limit_order', True):
        reasons.append('지정가 주문이 비활성화되어 있습니다.')

    if order_type_norm == 'LIMIT' and (px is None or px <= 0):
        reasons.append('지정가 주문은 가격이 필요합니다.')

    if not asset_mode_matches(asset_mode, is_etf):
        mode_label = {'all': '통합', 'stock': '주식만', 'etf': 'ETF만'}.get(asset_mode, asset_mode)
        type_label = 'ETF' if is_etf else '주식'
        reasons.append(f'현재 보기 모드({mode_label})에서는 {type_label} 주문이 차단됩니다.')

    limit_count = int(policy.get('daily_order_limit', 0) or 0)
    if limit_count > 0 and int(daily_order_count) >= limit_count:
        reasons.append(f'일일 주문 한도 초과: {daily_order_count} >= {limit_count}')

    if policy.get('enforce_market_hours', True) and not is_krx_market_open(now=now):
        reasons.append('한국 정규장(평일 09:00~15:30) 외 시간에는 주문이 차단됩니다.')

    if px is not None and px > 0 and qty > 0:
        notional = px * qty
        max_notional = float(policy.get('max_order_value', 0.0) or 0.0)
        if max_notional > 0 and notional > max_notional:
            reasons.append(f'주문 금액 한도 초과: {notional:,.0f}원 > {max_notional:,.0f}원')

    if not policy.get('enabled', True):
        reasons = []

    return {
        'allowed': len(reasons) == 0,
        'reasons': reasons,
        'normalized': {
            'symbol': symbol_norm,
            'side': side_norm,
            'order_type': order_type_norm,
            'broker': broker_norm,
            'quantity': qty,
            'price': px,
            'asset_mode': asset_mode,
            'is_etf': bool(is_etf),
        },
    }


def validate_stock_order_quantity_rule(
    *,
    quantity: float,
    broker: str,
    guardrails: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """브로커별 최소수량/수량단위만 빠르게 검증한다.

    UI 입력 단계의 실시간 경고/버튼 비활성화 용도로 사용한다.
    """
    policy = normalize_stock_order_guardrails(guardrails)
    broker_norm = _normalize_stock_broker_key(broker)

    try:
        qty = float(quantity)
    except Exception:
        qty = 0.0

    reasons: List[str] = []
    if qty <= 0:
        reasons.append('주문 수량은 0보다 커야 합니다.')

    rule = _resolve_broker_quantity_rule(policy, broker_norm)
    min_qty = float(rule.get('min_quantity', 1.0) or 1.0)
    step_qty = float(rule.get('quantity_step', 1.0) or 1.0)

    if qty > 0:

        if qty + 1e-9 < min_qty:
            reasons.append(f'{broker_norm.upper()} 최소 주문수량 미달: {qty:g} < {min_qty:g}')

        units = qty / step_qty if step_qty > 0 else qty
        if abs(units - round(units)) > 1e-9:
            reasons.append(f'{broker_norm.upper()} 수량 단위 불일치: {qty:g} (단위 {step_qty:g})')

    return {
        'allowed': len(reasons) == 0,
        'reasons': reasons,
        'normalized': {
            'broker': broker_norm,
            'quantity': qty,
            'min_quantity': min_qty,
            'quantity_step': step_qty,
        },
    }


def get_stock_order_quantity_rule(
    *,
    broker: str,
    guardrails: Optional[Dict[str, Any]] = None,
) -> Dict[str, float | str]:
    """브로커별 수량 규칙(min/step)을 UI에서 표시하기 쉽게 반환한다."""
    policy = normalize_stock_order_guardrails(guardrails)
    broker_norm = _normalize_stock_broker_key(broker)
    rule = _resolve_broker_quantity_rule(policy, broker_norm)
    return {
        'broker': broker_norm,
        'min_quantity': float(rule.get('min_quantity', 1.0) or 1.0),
        'quantity_step': float(rule.get('quantity_step', 1.0) or 1.0),
    }
