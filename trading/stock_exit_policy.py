#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증권 자동매매용 익절/손절 정책 엔진."""

from __future__ import annotations

from typing import Any, Dict, Optional


DEFAULT_STOCK_EXIT_POLICY: Dict[str, Any] = {
    'enable_exit_policy': True,
    'take_profit_percent': 5.0,
    'stop_loss_percent': 8.0,
    'etf_take_profit_percent': 4.0,
    'etf_stop_loss_percent': 6.0,
    'use_signal_exit': True,
    'etf_alert_exit': True,
}

# 시장 레짐별 TP/SL 조정 배율
# bear: SL 좁혀서 손실 최소화, TP도 낮춰서 작은 이익도 확보
# volatile: SL 더 좁게(급락 대비), TP는 현행 유지
# bull: TP 넓혀서 추세 이익 극대화, SL은 현행
# range/normal: 기본값 그대로
_REGIME_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    'bear':     {'tp_mult': 0.7, 'sl_mult': 0.6},
    'volatile': {'tp_mult': 1.0, 'sl_mult': 0.7},
    'bull':     {'tp_mult': 1.3, 'sl_mult': 1.0},
    'trend':    {'tp_mult': 1.2, 'sl_mult': 1.0},
    'range':    {'tp_mult': 1.0, 'sl_mult': 1.0},
    'normal':   {'tp_mult': 1.0, 'sl_mult': 1.0},
}


def normalize_stock_exit_policy(policy: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(DEFAULT_STOCK_EXIT_POLICY)
    if isinstance(policy, dict):
        merged.update(policy)

    merged['enable_exit_policy'] = bool(merged.get('enable_exit_policy', True))
    merged['use_signal_exit'] = bool(merged.get('use_signal_exit', True))
    merged['etf_alert_exit'] = bool(merged.get('etf_alert_exit', True))

    for key, default in (
        ('take_profit_percent', 5.0),
        ('stop_loss_percent', 8.0),
        ('etf_take_profit_percent', 4.0),
        ('etf_stop_loss_percent', 6.0),
    ):
        try:
            merged[key] = float(merged.get(key, default) or default)
        except Exception:
            merged[key] = default
    return merged


def evaluate_stock_position_exit(
    *,
    position: Dict[str, Any],
    analysis_result: Dict[str, Any],
    policy: Dict[str, Any] | None = None,
    market_regime: Optional[str] = None,
) -> Dict[str, Any]:
    """보유 포지션의 자동 청산 여부를 판단한다.

    market_regime: 'bear' | 'volatile' | 'bull' | 'trend' | 'range' | 'normal'
        전달되면 TP/SL 기준을 레짐에 맞게 자동 조정한다.
        bear/volatile에서 SL을 좁혀 손실을 줄이고,
        bull/trend에서 TP를 넓혀 추세 이익을 극대화한다.
    """
    normalized = normalize_stock_exit_policy(policy)
    if not normalized.get('enable_exit_policy', True):
        return {'should_exit': False, 'reason': '', 'policy_snapshot': normalized}

    is_etf = bool(position.get('is_etf', analysis_result.get('is_etf', False)))
    pnl_rate = 0.0
    try:
        pnl_rate = float(position.get('pnl_rate', 0.0) or 0.0)
    except Exception:
        pnl_rate = 0.0

    tp_key = 'etf_take_profit_percent' if is_etf else 'take_profit_percent'
    sl_key = 'etf_stop_loss_percent' if is_etf else 'stop_loss_percent'
    take_profit = float(normalized.get(tp_key, 4.0 if is_etf else 5.0) or 0.0)
    stop_loss = float(normalized.get(sl_key, 6.0 if is_etf else 8.0) or 0.0)

    # 레짐 기반 동적 조정
    regime_key = str(market_regime or 'normal').lower().strip()
    mults = _REGIME_MULTIPLIERS.get(regime_key, _REGIME_MULTIPLIERS['normal'])
    effective_tp = take_profit * mults['tp_mult']
    effective_sl = stop_loss * mults['sl_mult']
    regime_adjusted = regime_key not in ('normal', 'range', '')

    if take_profit > 0 and pnl_rate >= effective_tp:
        return {
            'should_exit': True,
            'reason': (
                f'take_profit:{pnl_rate:.2f}% >= {effective_tp:.2f}%'
                + (f' (regime={regime_key}, base={take_profit:.2f}%)' if regime_adjusted else '')
            ),
            'policy_snapshot': normalized,
            'regime': regime_key,
        }

    if stop_loss > 0 and pnl_rate <= -effective_sl:
        return {
            'should_exit': True,
            'reason': (
                f'stop_loss:{pnl_rate:.2f}% <= -{effective_sl:.2f}%'
                + (f' (regime={regime_key}, base={stop_loss:.2f}%)' if regime_adjusted else '')
            ),
            'policy_snapshot': normalized,
            'regime': regime_key,
        }

    if is_etf and normalized.get('etf_alert_exit', True):
        etf_risk = str(analysis_result.get('etf_risk', 'ok')).lower()
        if etf_risk == 'alert':
            return {
                'should_exit': True,
                'reason': 'etf_alert_exit',
                'policy_snapshot': normalized,
                'regime': regime_key,
            }

    if normalized.get('use_signal_exit', True):
        signal = str(analysis_result.get('signal', '') or '').upper()
        score = float(analysis_result.get('score', 0.0) or 0.0)
        momentum = float(analysis_result.get('momentum', 0.0) or 0.0)
        if signal == 'SELL':
            return {
                'should_exit': True,
                'reason': f'signal_exit:SELL score={score:.1f} momentum={momentum:+.2f}',
                'policy_snapshot': normalized,
                'regime': regime_key,
            }

    return {
        'should_exit': False,
        'reason': '',
        'policy_snapshot': normalized,
        'regime': regime_key,
    }