"""Declared strategy candle contract shared by replay and execution clients."""
from __future__ import annotations

import re
from typing import Any



def normalize_timeframe(value: Any) -> str:
    raw = str(value or "").strip()
    if raw == "1M":
        raise ValueError("월봉은 고정 길이 봉으로 재생할 수 없습니다. 지원 시간봉을 선택하세요.")
    raw = raw.lower()
    if not re.fullmatch(r"[1-9][0-9]*(m|h|d|w)", raw):
        raise ValueError(f"전략 시간봉이 없거나 올바르지 않습니다: {raw or '미지정'}. 시간봉을 명시한 새 버전을 저장하세요.")
    return raw


def timeframe_ms(value: str) -> int:
    value = normalize_timeframe(value)
    return int(value[:-1]) * {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}[value[-1]]


def strategy_timeframe_contract(rules: dict[str, Any]) -> dict[str, Any]:
    """Never infer a strategy's decision interval from a venue or prose."""
    from trading.custom_strategy_validator import collect_advanced_indicator_references
    decision = normalize_timeframe(rules.get("decision_timeframe") or rules.get("timeframe"))
    execution = normalize_timeframe(rules.get("execution_timeframe") or decision)
    if execution != decision:
        raise ValueError("판단봉과 주문봉이 다른 전략의 과거 재생은 아직 지원하지 않습니다. 다른 시간봉으로 대체하지 않습니다.")
    required = {decision}
    required.update(normalize_timeframe(ref.get("timeframe") or "5m") for ref in collect_advanced_indicator_references(rules))
    required.update(normalize_timeframe(tf) for tf in rules.get("required_timeframes", []))
    return {"decision_timeframe": decision, "execution_timeframe": execution,
            "required_timeframes": sorted(required, key=timeframe_ms), "basis": "strategy_declared"}
