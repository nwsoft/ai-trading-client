#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime

from trading.stock_order_guardrails import (
    evaluate_stock_order_guardrails,
    get_stock_order_quantity_rule,
    is_krx_market_open,
    normalize_stock_order_guardrails,
    validate_stock_order_quantity_rule,
)


def test_market_open_time_weekday():
    dt = datetime(2026, 4, 27, 10, 0, 0)  # Monday
    assert is_krx_market_open(dt) is True


def test_market_closed_weekend():
    dt = datetime(2026, 4, 26, 10, 0, 0)  # Sunday
    assert is_krx_market_open(dt) is False


def test_normalize_guardrail_defaults():
    cfg = normalize_stock_order_guardrails(None)
    assert cfg['enabled'] is True
    assert cfg['max_order_value'] > 0
    assert cfg['daily_order_limit'] > 0


def test_guardrail_rejects_mode_mismatch():
    result = evaluate_stock_order_guardrails(
        symbol='069500',
        side='BUY',
        quantity=1,
        price=30000,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='stock',
        is_etf=True,
        daily_order_count=0,
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is False
    assert any('주문이 차단' in reason for reason in result['reasons'])


def test_guardrail_rejects_daily_limit_and_notional():
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=200,
        price=800000,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='all',
        is_etf=False,
        daily_order_count=20,
        guardrails={'daily_order_limit': 20, 'max_order_value': 50_000_000},
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is False
    assert any('일일 주문 한도 초과' in reason for reason in result['reasons'])
    assert any('주문 금액 한도 초과' in reason for reason in result['reasons'])


def test_guardrail_allows_valid_input():
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=10,
        price=70000,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='all',
        is_etf=False,
        daily_order_count=0,
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is True
    assert result['reasons'] == []


def test_guardrail_rejects_fractional_qty_for_broker_step():
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=1.5,
        price=70000,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='all',
        is_etf=False,
        daily_order_count=0,
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is False
    assert any('수량 단위 불일치' in reason for reason in result['reasons'])


def test_guardrail_rejects_broker_min_qty_from_policy():
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=5,
        price=70000,
        order_type='LIMIT',
        broker='miraeAsset',
        asset_mode='all',
        is_etf=False,
        daily_order_count=0,
        guardrails={
            'broker_min_quantity': {
                'miraeAsset': 10,
            }
        },
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is False
    assert any('최소 주문수량 미달' in reason for reason in result['reasons'])


def test_validate_quantity_rule_rejects_step_violation():
    result = validate_stock_order_quantity_rule(
        quantity=1.5,
        broker='kiwoom',
    )
    assert result['allowed'] is False
    assert any('수량 단위 불일치' in reason for reason in result['reasons'])


def test_validate_quantity_rule_handles_broker_alias_min_qty():
    result = validate_stock_order_quantity_rule(
        quantity=5,
        broker='mirae_asset',
        guardrails={
            'broker_min_quantity': {
                'miraeAsset': 10,
            }
        },
    )
    assert result['allowed'] is False
    assert any('최소 주문수량 미달' in reason for reason in result['reasons'])


def test_validate_quantity_rule_includes_min_and_step_in_normalized():
    result = validate_stock_order_quantity_rule(
        quantity=1,
        broker='kiwoom',
    )
    normalized = result['normalized']
    assert normalized['min_quantity'] == 1.0
    assert normalized['quantity_step'] == 1.0


def test_get_stock_order_quantity_rule_with_alias_key():
    rule = get_stock_order_quantity_rule(
        broker='mirae_asset',
        guardrails={
            'broker_min_quantity': {
                'miraeAsset': 3,
            },
            'broker_quantity_step': {
                'miraeAsset': 2,
            },
        },
    )
    assert rule['broker'] == 'miraeasset'
    assert rule['min_quantity'] == 3.0


def test_guardrail_rejects_max_quantity_exceeded():
    """max_quantity 한도 초과 시 주문이 차단된다."""
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=15000,  # 기본 max_quantity=10000 초과
        price=10,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='all',
        is_etf=False,
        daily_order_count=0,
        now=datetime(2026, 4, 27, 10, 0, 0),
    )
    assert result['allowed'] is False
    assert any('수량 한도 초과' in reason for reason in result['reasons'])


def test_guardrail_rejects_outside_market_hours():
    """장외 시간(야간)에는 enforce_market_hours 정책으로 주문이 차단된다."""
    result = evaluate_stock_order_guardrails(
        symbol='005930',
        side='BUY',
        quantity=1,
        price=70000,
        order_type='LIMIT',
        broker='kiwoom',
        asset_mode='all',
        is_etf=False,
        daily_order_count=0,
        now=datetime(2026, 4, 28, 20, 0, 0),  # 평일 오후 8시 — 장외
    )
    assert result['allowed'] is False
    assert any('정규장' in reason for reason in result['reasons'])
