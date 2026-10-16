#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초보자용 AI 커스텀 시작 프리셋.

프리셋은 검토용 초안이며 저장·승인·자동검증·최종 적용 전에는 실행되지 않는다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


PRESET_CATALOG: Dict[str, Dict[str, Any]] = {
    "auto_regime": {
        "name": "AI가 시장에 맞춰 자동 대응",
        "short_name": "AI 자동 대응",
        "risk": "상대적 위험도: 국면별 변동",
        "regimes": ["all"],
        "executable_template": False,
        "summary": (
            "NoahAI 기본 판단이 시장 국면을 먼저 확인하고 추세·눌림목·횡보·돌파 중 "
            "조건이 맞는 방식만 후보로 검토합니다. 맞는 전략이 없거나 신호가 충돌하면 HOLD합니다."
        ),
    },
    "trend_follow": {
        "name": "추세 따라가기",
        "short_name": "이평선 추세",
        "risk": "상대적 위험도: 낮음~중간",
        "regimes": ["bull", "bear", "trend"],
        "executable_template": True,
        "summary": "EMA 20·50·200 정렬과 가격·RSI·거래량을 확인해 명확한 추세 방향만 따릅니다.",
        "rules_template": {
            "entry": "EMA 20·50·200 정렬, 가격 위치, RSI, 거래량 비율을 모두 확인",
            "exit": "고정 TP/SL 또는 사용자 승인 후 선언한 실행 청산 조건",
            "stop_loss": "1%",
            "take_profit": "2%",
            "position_size": "계좌 위험예산 기반, 증거금 최대 10%",
            "market_conditions": ["상승장", "하락장", "추세장"],
            "market_regimes": ["bull", "bear"],
            "signal_mode": "independent",
            "entry_signal": "",
            "independent_entries": {
                "LONG": {"all": [
                    {"field": "ema20", "operator": "gt_field", "value_field": "ema50"},
                    {"field": "ema50", "operator": "gt_field", "value_field": "ema200"},
                    {"field": "current_price", "operator": "gt_field", "value_field": "ema20"},
                    {"field": "rsi", "operator": "gte", "value": 50},
                    {"field": "rsi", "operator": "lte", "value": 75},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.0},
                ], "any": []},
                "SHORT": {"all": [
                    {"field": "ema20", "operator": "lt_field", "value_field": "ema50"},
                    {"field": "ema50", "operator": "lt_field", "value_field": "ema200"},
                    {"field": "current_price", "operator": "lt_field", "value_field": "ema20"},
                    {"field": "rsi", "operator": "gte", "value": 25},
                    {"field": "rsi", "operator": "lte", "value": 50},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.0},
                ], "any": []},
            },
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 2.0,
                "sl_percent": 1.0, "position_size": 0.1, "leverage": 1,
            },
        },
    },
    "trend_pullback": {
        "name": "눌림목 진입",
        "short_name": "추세 눌림목",
        "risk": "상대적 위험도: 중간",
        "regimes": ["bull", "bear", "trend"],
        "executable_template": True,
        "summary": "EMA50·EMA200으로 큰 추세를 확인한 뒤 EMA20·EMA50 부근 조정이 끝날 때만 재진입합니다.",
        "rules_template": {
            "entry": "큰 추세 정렬 후 EMA20 재돌파·재이탈과 RSI·거래량 회복을 확인",
            "exit": "고정 TP/SL 또는 사용자 승인 후 선언한 실행 청산 조건",
            "stop_loss": "1%", "take_profit": "1.8%",
            "position_size": "계좌 위험예산 기반, 증거금 최대 10%",
            "market_conditions": ["상승장", "하락장", "추세장"],
            "market_regimes": ["bull", "bear"],
            "signal_mode": "independent", "entry_signal": "",
            "independent_entries": {
                "LONG": {"all": [
                    {"field": "ema50", "operator": "gt_field", "value_field": "ema200"},
                    {"field": "current_price", "operator": "crosses_above", "value_field": "ema20"},
                    {"field": "rsi", "operator": "gte", "value": 40},
                    {"field": "rsi", "operator": "lte", "value": 60},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.0},
                ], "any": []},
                "SHORT": {"all": [
                    {"field": "ema50", "operator": "lt_field", "value_field": "ema200"},
                    {"field": "current_price", "operator": "crosses_below", "value_field": "ema20"},
                    {"field": "rsi", "operator": "gte", "value": 40},
                    {"field": "rsi", "operator": "lte", "value": 60},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.0},
                ], "any": []},
            },
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 1.8,
                "sl_percent": 1.0, "position_size": 0.1, "leverage": 1,
            },
        },
    },
    "range_rsi": {
        "name": "횡보장 저점·고점 대응",
        "short_name": "박스권 RSI",
        "risk": "상대적 위험도: 중간",
        "regimes": ["range", "calm"],
        "executable_template": True,
        "summary": "평평한 추세와 박스권이 확인된 경우에만 RSI 반전을 사용하고 돌파가 시작되면 중지합니다.",
        "rules_template": {
            "entry": "ADX 25 이하 횡보장에서 RSI 과매도·과매수 반전 후보를 확인",
            "exit": "고정 TP/SL 또는 사용자 승인 후 선언한 실행 청산 조건",
            "stop_loss": "0.8%", "take_profit": "1.2%",
            "position_size": "계좌 위험예산 기반, 증거금 최대 10%",
            "market_conditions": ["횡보장", "저변동성"],
            "market_regimes": ["range", "calm"],
            "signal_mode": "independent", "entry_signal": "",
            "independent_entries": {
                "LONG": {"all": [
                    {"field": "adx", "operator": "lte", "value": 25},
                    {"field": "rsi", "operator": "lte", "value": 30},
                ], "any": []},
                "SHORT": {"all": [
                    {"field": "adx", "operator": "lte", "value": 25},
                    {"field": "rsi", "operator": "gte", "value": 70},
                ], "any": []},
            },
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 1.2,
                "sl_percent": 0.8, "position_size": 0.1, "leverage": 1,
            },
        },
    },
    "volume_breakout": {
        "name": "강한 거래량 돌파",
        "short_name": "거래량 돌파",
        "risk": "상대적 위험도: 중간~높음",
        "regimes": ["trend", "volatile"],
        "executable_template": True,
        "summary": "거래량 확장과 ADX 추세 강도를 동반한 EMA20 모멘텀 돌파만 검토합니다.",
        "rules_template": {
            "entry": "거래량 1.5배·ADX 25 이상에서 EMA20 방향 돌파와 RSI 범위를 확인",
            "exit": "고정 TP/SL 또는 사용자 승인 후 선언한 실행 청산 조건",
            "stop_loss": "1%", "take_profit": "2%",
            "position_size": "계좌 위험예산 기반, 증거금 최대 8%",
            "market_conditions": ["추세장", "고변동성 진입 전환"],
            "market_regimes": ["bull", "bear", "volatile"],
            "signal_mode": "independent", "entry_signal": "",
            "independent_entries": {
                "LONG": {"all": [
                    {"field": "current_price", "operator": "crosses_above", "value_field": "ema20"},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.5},
                    {"field": "adx", "operator": "gte", "value": 25},
                    {"field": "rsi", "operator": "gte", "value": 55},
                    {"field": "rsi", "operator": "lte", "value": 75},
                ], "any": []},
                "SHORT": {"all": [
                    {"field": "current_price", "operator": "crosses_below", "value_field": "ema20"},
                    {"field": "volume_ratio", "operator": "gte", "value": 1.5},
                    {"field": "adx", "operator": "gte", "value": 25},
                    {"field": "rsi", "operator": "gte", "value": 25},
                    {"field": "rsi", "operator": "lte", "value": 45},
                ], "any": []},
            },
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "exit_policy": {"mode": "strategy_owned"},
            "engine_settings": {
                "_unit": "percent_points", "tp_percent": 2.0,
                "sl_percent": 1.0, "position_size": 0.08, "leverage": 1,
            },
        },
    },
}


def render_preset_source(name: str, rules: Dict[str, Any]) -> str:
    """Render the actual template contract; never revive the former vague prose."""
    engine = rules.get('engine_settings') or {}
    risk = rules.get('risk_model') or {}
    timeframe = rules.get('decision_timeframe') or '15m'
    labels = rules.get('market_conditions') or []
    lines = [f'전략명: {name}',
             '학습용 실행 프로토타입입니다. ATR·스윙 동적 손절 전략과 다릅니다.',
             '성과를 보장하지 않으며 사용자 검토·자동검증 전에는 실행하지 않습니다.',
             '시장상황: '+', '.join(labels), '국면 기준: 종목별', '우선순위: 5',
             f'판단 시간봉: {timeframe} (완성된 봉 기준)',
             f"손절: {engine['sl_percent']:g}%", f"익절: {engine['tp_percent']:g}%",
             f"포지션 크기: {engine.get('position_size', 0.1)*100:g}%",
             f"거래당 계좌 손실 위험: {risk.get('risk_per_trade_percent', 0.5):g}%",
             f"레버리지 상한: {risk.get('max_leverage', engine.get('leverage', 1)):g}배"]
    branches = rules.get('independent_entries') or {rules.get('entry_signal') or 'LONG':rules['executable_entry']}
    operators = {'gt':'>','gte':'>=','lt':'<','lte':'<=','eq':'==','ne':'!='}
    for direction, spec in branches.items():
        clauses = []
        for condition in spec.get('all') or []:
            field, operator = condition['field'], condition['operator']
            target = condition.get('value_field', condition.get('value'))
            if operator in {'crosses_above','crosses_below'}:
                clauses.append(f"{operator}({field}, {target})")
            else:
                clauses.append(f"{field} {operators[operator.removesuffix('_field')]} {target}")
        lines.append(f"{direction} 진입: "+' AND '.join(clauses))
    lines.append('청산: 전략 자체 고정 익절·손절')
    return '\n'.join(lines)


def list_beginner_presets() -> List[Dict[str, Any]]:
    return [{'key':key, **get_beginner_preset(key)} for key in PRESET_CATALOG]


def get_beginner_preset(key: str) -> Optional[Dict[str, Any]]:
    item = PRESET_CATALOG.get(str(key or '').strip().lower())
    if not item: return None
    result = deepcopy(item)
    if result.get('executable_template'):
        result['source_text'] = render_preset_source(result['name'], result['rules_template'])
    return result


def preset_key_from_text(message: str) -> Optional[str]:
    normalized = str(message or "").lower().replace(" ", "")
    aliases = (
        ("auto_regime", ("ai자동대응", "시장에맞춰자동", "자동대응")),
        ("trend_pullback", ("눌림목", "되돌림진입")),
        ("range_rsi", ("박스권", "횡보장", "rsi반전", "저점고점")),
        ("volume_breakout", ("거래량돌파", "돌파매매")),
        ("trend_follow", ("이평선", "이동평균", "추세따라가기", "추세추종", "골든크로스")),
    )
    for key, tokens in aliases:
        if any(token in normalized for token in tokens):
            return key
    return None


def recommend_preset_for_regime(
    regime: str,
    *,
    signal_conflict: bool = False,
    volume_expansion: bool = False,
) -> str:
    """초보자 설명용 추천. 실제 주문은 기존 가드레일과 활성 전략만 사용한다."""
    if signal_conflict:
        return "hold"
    normalized = str(regime or "").strip().lower()
    if normalized in {"range", "sideways", "calm", "low"}:
        return "range_rsi"
    if normalized in {"bull", "bear", "trend", "normal"}:
        return "trend_pullback"
    if normalized in {"volatile", "high"} and volume_expansion:
        return "volume_breakout"
    return "hold"
