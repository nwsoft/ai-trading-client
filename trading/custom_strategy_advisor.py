#!/usr/bin/env python3
"""AI 커스텀 전략의 누락 조건, 위험 설계, 개선 방향을 설명한다."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List


FIELD_GUIDANCE: Dict[str, Dict[str, str]] = {
    "entry": {
        "label": "진입 조건",
        "question": "어떤 지표가 어떤 값일 때 LONG 또는 SHORT에 진입할까요?",
        "example": "15분봉 RSI 35 이하이고 종가가 EMA50 위로 복귀하면 LONG",
    },
    "exit": {
        "label": "일반 청산 조건",
        "question": "익절·손절 외에 추세 약화나 반대 신호가 나오면 언제 청산할까요?",
        "example": "15분봉 종가가 EMA20 아래에서 마감하면 청산",
    },
    "stop_loss": {
        "label": "손절 조건",
        "question": "고정 비율, ATR, 구조적 지지·저항 중 무엇으로 손절거리를 정할까요?",
        "example": "진입가 대비 1% 또는 ATR 2배 중 더 넓은 값",
    },
    "take_profit": {
        "label": "수익 실현",
        "question": "고정 익절, 분할 익절, 트레일링 중 어떤 방식으로 수익을 실현할까요?",
        "example": "1차 1.5%에서 절반, 나머지는 ATR 1배 트레일링",
    },
    "position_size": {
        "label": "거래 위험예산",
        "question": "거래 한 번에서 계좌의 최대 몇 %까지 손실을 허용할까요?",
        "example": "거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%",
    },
    "market_conditions": {
        "label": "사용 시장상황",
        "question": "상승·하락·횡보·고변동·돌파 중 어느 시장상황에서 사용할까요?",
        "example": "상승 추세와 상승 돌파에서만 사용",
    },
}

TRANSITION_POLICIES = {
    "delegate_to_noah": "해당 전략의 시장상황이 아니면 기본 노아AI에 맡깁니다.",
    "pause": "해당 전략의 시장상황이 아니면 커스텀 신규 진입을 일시정지합니다.",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("%", "").strip()
        return float(value)
    except Exception:
        return float(default)


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def build_strategy_guidance(
    rules: Dict[str, Any] | None,
    required_fields: Iterable[str],
) -> Dict[str, Any]:
    """누락을 추정으로 채우지 않고 사용자에게 답할 질문과 예시를 돌려준다."""
    current = dict(rules or {})
    missing = [field for field in required_fields if _missing(current.get(field))]
    questions: List[Dict[str, str]] = []
    for field in missing:
        guide = FIELD_GUIDANCE.get(field, {
            "label": field,
            "question": f"{field} 조건을 어떻게 사용할까요?",
            "example": "사용자가 원하는 조건을 구체적으로 입력",
        })
        questions.append({"field": field, **guide})

    risk_model = dict(current.get("risk_model", {}) or {})
    risk_missing = []
    if _number(risk_model.get("risk_per_trade_percent")) <= 0:
        risk_missing.append("risk_per_trade_percent")
    if _number(risk_model.get("max_margin_usage_percent")) <= 0:
        risk_missing.append("max_margin_usage_percent")
    if _number(risk_model.get("max_leverage")) <= 0:
        risk_missing.append("max_leverage")

    transition = str(current.get("regime_transition", "") or "").strip().lower()
    if transition not in TRANSITION_POLICIES:
        transition = "delegate_to_noah"

    return {
        "complete": not missing,
        "missing_conditions": missing,
        "questions": questions,
        "risk_model_status": "complete" if not risk_missing else "recommended_inputs_missing",
        "risk_model_missing": risk_missing,
        "risk_model_help": (
            "레버리지는 직접 목표값으로 쓰기보다 거래당 위험예산, 손절거리, "
            "최대 증거금 사용률과 사용자 최대 레버리지에서 거래별로 계산합니다."
        ),
        "regime_transition": transition,
        "regime_transition_help": TRANSITION_POLICIES[transition],
        "approval_note": "AI 권장값은 자동 적용하지 않으며 사용자가 확인한 새 버전에만 반영됩니다.",
    }


def build_improvement_advice(metrics: Dict[str, Any] | None) -> Dict[str, Any]:
    """비용 포함 성과를 읽고 기존 버전을 변경하지 않는 개선 제안을 만든다."""
    values = dict(metrics or {})
    trades = int(_number(values.get("decisions", values.get("trades", 0))))
    net_pnl = _number(values.get("net_pnl_percent", values.get("net_pnl", 0.0)))
    mdd = _number(values.get("max_drawdown_percent", values.get("max_drawdown", 0.0)))
    win_rate = _number(values.get("win_rate", 0.0))
    if win_rate > 1.0:
        win_rate /= 100.0
    profit_factor = _number(values.get("profit_factor", 0.0))
    fee_verified = _number(values.get("fee_verification_rate", 0.0))

    actions: List[Dict[str, str]] = []
    if trades < 10:
        actions.append({
            "priority": "표본 확보",
            "reason": f"판단 표본이 {trades}회로 적습니다.",
            "suggestion": "실거래 확대 전에 과거 재생 또는 제한 관찰 표본을 더 확보하세요.",
        })
    if net_pnl <= 0:
        actions.append({
            "priority": "순기대값 개선",
            "reason": f"비용 반영 PnL이 {net_pnl:.2f}%입니다.",
            "suggestion": "진입조건, 손절거리, 수익 실현을 각각 분리해 새 버전으로 검증하세요.",
        })
    if profit_factor and profit_factor < 1.0:
        actions.append({
            "priority": "손익비 개선",
            "reason": f"Profit Factor가 {profit_factor:.2f}로 1 미만입니다.",
            "suggestion": "승률을 억지로 높이기보다 평균 손실 축소와 이익 보유시간을 재검토하세요.",
        })
    if mdd > 10.0:
        actions.append({
            "priority": "낙폭 축소",
            "reason": f"최대 낙폭이 {mdd:.2f}%입니다.",
            "suggestion": "거래당 위험예산과 동시 포지션 수를 낮춘 새 버전을 검증하세요.",
        })
    if fee_verified and fee_verified < 0.8:
        actions.append({
            "priority": "수수료 근거 보완",
            "reason": f"실제 수수료 확인률이 {fee_verified:.0%}입니다.",
            "suggestion": "체결 수수료가 확인되기 전에는 전략 승격 판단을 보류하세요.",
        })
    if not actions and trades >= 10 and net_pnl > 0 and (not profit_factor or profit_factor >= 1.0):
        actions.append({
            "priority": "현 버전 유지",
            "reason": f"현재 표본의 승률은 {win_rate:.1%}, 비용 반영 PnL은 {net_pnl:.2f}%입니다.",
            "suggestion": "설정을 자동 변경하지 말고 다음 검토 구간까지 동일 버전을 관찰하세요.",
        })
    return {
        "metrics_snapshot": deepcopy(values),
        "actions": actions,
        "auto_applied": False,
        "note": "개선안은 제안일 뿐이며 사용자 승인 없이 현재 전략을 변경하지 않습니다.",
    }
