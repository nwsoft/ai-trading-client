#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
설정 변경 Diff Engine (최소판)
- 변경된 키를 기반으로 어떤 서브시스템을 갱신할지 판정합니다.
"""
from __future__ import annotations
from typing import Dict, Any, Set


def _changed_keys(old: Dict[str, Any], new: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    all_keys = set(old.keys()) | set(new.keys())
    for k in all_keys:
        if old.get(k) != new.get(k):
            keys.add(k)
    return keys


def compute_settings_diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """설정 변경점을 분석하여 적용 계획을 반환합니다.

    Returns: {
      'changed_keys': set[str],
      'logging_changed': bool,
      'ai_changed': bool,
      'exchanges_changed': bool,
      'enabled_exchanges_changed': bool,
      'trading_changed': bool,
    }
    """
    changed = _changed_keys(old or {}, new or {})
    # 그룹 판정
    logging_changed = any(k in changed for k in {'log_level'})
    ai_changed = any(
        k in changed
        for k in {
            'openai_api_key', 'openai_model', 'assistant_ai_model', 'ai_model_roles',
            'ai_provider', 'ai_credentials', 'ai_provider_profiles', 'ai_models',
            'assistant_response_mode', 'assistant_token_budget', 'assistant_context_policy',
        }
    )
    enabled_exchanges_changed = 'enabled_exchanges' in changed
    # 넓게: 각 거래소의 key/secret/passphrase 변경
    exchange_key_prefixes = ['binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb']
    exchange_key_suffixes = ['api_key', 'secret_key', 'passphrase', 'password']
    exchanges_changed = enabled_exchanges_changed or any(
        f"{p}_{s}" in changed for p in exchange_key_prefixes for s in exchange_key_suffixes
    )
    # 트레이딩 파라미터 변경 (최소 범위)
    trading_changed = any(
        k in changed
        for k in {
            'default_leverage', 'default_tp', 'default_sl', 'default_margin_type',
            'paper_trading', 'trade_enabled_exchanges', 'learning_enabled_exchanges',
            'max_positions', 'position_mode', 'min_trade_amount',
            'exchange_position_factors', 'exchange_risk_overrides',
            'multi_venue_execution', 'stock_auto_trading', 'enable_stock_live_order',
        }
    )

    return {
        'changed_keys': changed,
        'logging_changed': logging_changed,
        'ai_changed': ai_changed,
        'exchanges_changed': exchanges_changed,
        'enabled_exchanges_changed': enabled_exchanges_changed,
        'trading_changed': trading_changed,
    }
