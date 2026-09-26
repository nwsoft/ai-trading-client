#!/usr/bin/env python3
"""AI 커스텀 전략의 누락 조건, 위험 설계, 개선 방향을 설명한다."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Mapping


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


VALIDATION_ISSUE_GUIDANCE: Dict[str, Dict[str, str]] = {
    "independent_entry_signal_missing": {
        "title": "독립 전략의 진입 방향이 없습니다",
        "explanation": "독립 전략은 NoahAI 기본 방향을 상속하지 않으므로 LONG 또는 SHORT를 명확히 알아야 합니다.",
        "action": "각 진입 조건에 LONG 또는 SHORT 방향을 적어 주세요.",
        "example": "RSI 30 이하이면 LONG 진입",
    },
    "independent_executable_entry_missing": {
        "title": "독립 전략의 실행 가능한 진입 조건이 없습니다",
        "explanation": "방향만으로는 언제 주문할지 알 수 없어 거래를 시작할 수 없습니다.",
        "action": "시간봉·지표·비교값을 포함한 진입 조건을 작성하세요.",
        "example": "15분봉 RSI(14)가 30 이하이면 LONG 진입",
    },
    "independent_exit_policy_cannot_inherit_noah": {
        "title": "독립 전략은 NoahAI 청산을 그대로 상속할 수 없습니다",
        "explanation": "독립 진입과 청산 중 한쪽만 다른 엔진에 맡기면 원문 전략의 손익 의미가 달라집니다.",
        "action": "독립 전략의 손절·익절과 일반 청산 조건을 직접 명시하세요.",
        "example": "손절 1%, 익절 2%, RSI 55 이상이면 청산",
    },
    "inherited_exit_policy_conflicts_with_strategy_rates": {
        "title": "두 가지 청산 방식이 동시에 선택됐습니다",
        "explanation": "NoahAI 스마트 청산 상속과 전략 고정 TP/SL을 동시에 실행할 수 없습니다.",
        "action": "NoahAI 청산 상속 또는 전략 자체 TP/SL 중 하나만 선택하세요.",
        "example": "확인 전략 + NoahAI 스마트 청산 상속",
    },
    "strategy_exit_rates_missing": {
        "title": "전략 자체 청산의 손절·익절 값이 부족합니다",
        "explanation": "전략 자체 청산을 선택했지만 TP와 SL 한 쌍이 모두 확인되지 않았습니다.",
        "action": "손절과 익절을 단위와 함께 모두 적어 주세요.",
        "example": "손절 1%, 익절 2%",
    },
    "exit_rate_contract_missing_or_invalid": {
        "title": "손절·익절 값 또는 단위가 올바르지 않습니다",
        "explanation": "저장·PAPER·실주문에서 같은 의미를 보장할 수 없는 값입니다.",
        "action": "손절 0.05~3%, 익절 0.05~5% 범위에서 % 단위를 명시하세요.",
        "example": "손절 1%, 익절 2%",
    },
    "engine_settings_contract_invalid": {
        "title": "위험 또는 운용 설정값이 허용 범위를 벗어났습니다",
        "explanation": "레버리지·포지션 비중·신호 임계값을 조용히 보정하지 않고 저장을 차단했습니다.",
        "action": "화면의 Level 4 허용 범위와 계좌 정책 상한 안에서 값을 다시 지정하세요.",
        "example": "거래당 위험 0.5%, 증거금 최대 10%, 레버리지 최대 3배",
    },
    "unsupported_executable_conditions": {
        "title": "현재 실행 엔진이 지원하지 않는 조건이 있습니다",
        "explanation": "지원하지 않는 조건을 삭제하거나 비슷한 조건으로 바꾸지 않고 안전하게 차단했습니다.",
        "action": "기술 코드를 확인해 지원 규칙으로 다시 작성하거나 원문 보관본으로 유지하세요.",
        "example": "지표·시간봉·비교 연산을 명시적인 선언 규칙으로 작성",
    },
    "stop_loss_unit_missing": {
        "title": "손절 값의 단위가 없습니다",
        "explanation": "숫자만 있으면 1%인지 1원인지 판단할 수 없어 임의로 실행하지 않습니다.",
        "action": "원문에 손절 기준과 단위를 함께 적어 주세요.",
        "example": "진입가 대비 손절 1%",
    },
    "take_profit_unit_missing": {
        "title": "익절 값의 단위가 없습니다",
        "explanation": "숫자만 있으면 비율인지 가격인지 판단할 수 없어 임의로 실행하지 않습니다.",
        "action": "원문에 익절 기준과 단위를 함께 적어 주세요.",
        "example": "진입가 대비 익절 2%",
    },
    "dual_direction_conditions_not_separated": {
        "title": "LONG과 SHORT 진입 조건을 분리할 수 없습니다",
        "explanation": "양방향 전략이 한쪽 조건으로 축소 실행되는 것을 막기 위한 차단입니다.",
        "action": "LONG 진입 조건과 SHORT 진입 조건을 각각 완전한 문장으로 적어 주세요.",
        "example": "RSI 30 이하이면 LONG, RSI 70 이상이면 SHORT",
    },
    "pine_dynamic_input_requires_user_confirmation": {
        "title": "Pine 입력값을 확정해야 합니다",
        "explanation": "input() 값은 TradingView 설정에 따라 달라지므로 현재 값만으로 실행값을 확정할 수 없습니다.",
        "action": "사용할 지표 기간과 임계값을 원문에 숫자로 명시한 뒤 다시 분석하세요.",
        "example": "RSI 기간 14, LONG 기준 30",
    },
    "pine_multitimeframe_request_not_supported": {
        "title": "다중 시간봉 request.security 조건은 아직 직접 실행할 수 없습니다",
        "explanation": "다른 시간봉 데이터를 불러오는 Pine 동작을 단일 조건으로 축소하면 원문 의미가 달라질 수 있습니다.",
        "action": "각 시간봉과 조건을 명시적인 Noah 규칙으로 다시 작성하거나 지원 확장 전까지 원문 보관본으로 유지하세요.",
        "example": "1시간봉 EMA50 상승이고 15분봉 RSI가 30 이하일 때 LONG",
    },
    "pine_collection_not_supported": {
        "title": "Pine 배열·행렬·맵 조건은 아직 지원하지 않습니다",
        "explanation": "컬렉션의 상태 변화까지 동일하게 재현할 수 없어 축소 실행하지 않습니다.",
        "action": "배열 계산의 최종 진입·청산 조건을 명시적인 지표 조건으로 작성하세요.",
        "example": "최근 5개 고점의 최댓값 돌파 시 LONG",
    },
    "pine_custom_function_not_supported": {
        "title": "Pine 사용자 함수의 실행 의미를 확인할 수 없습니다",
        "explanation": "사용자 함수 내부 조건을 누락한 채 실행되는 것을 막고 있습니다.",
        "action": "함수 내부의 진입·청산 계산을 원문에 풀어서 적어 주세요.",
        "example": "함수가 true가 되는 지표·연산·임계값을 모두 명시",
    },
    "pine_rolling_state_not_supported": {
        "title": "Pine 누적 상태 함수는 아직 직접 실행할 수 없습니다",
        "explanation": "highest·lowest·valuewhen·barssince의 과거 상태를 단순 현재값으로 바꾸면 결과가 달라집니다.",
        "action": "사용 기간과 비교 조건을 명시적인 지원 규칙으로 바꾸거나 원문 보관본으로 유지하세요.",
        "example": "최근 20봉 최고가를 현재 종가가 상향 돌파하면 LONG",
    },
    "pine_position_price_exit_not_supported": {
        "title": "포지션 평균가 기반 Pine 청산식을 직접 변환할 수 없습니다",
        "explanation": "실제 체결 평균가와 Pine의 가상 평균가가 달라질 수 있어 자동 변환하지 않습니다.",
        "action": "진입가 대비 손절·익절 비율을 명시적으로 적어 주세요.",
        "example": "실제 평균 진입가 대비 손절 1%, 익절 2%",
    },
    "confirm_executable_entry_missing": {
        "title": "실행 가능한 확인 조건이 없습니다",
        "explanation": "전략 설명은 있지만 NoahAI 신호를 어떤 조건으로 확인할지 구조화되지 않았습니다.",
        "action": "지표·비교값·방향을 원문에 추가하고 다시 분석하세요.",
        "example": "15분봉 RSI 35 이하일 때 NoahAI LONG 신호만 확인",
    },
    "source_conditions_require_definition": {
        "title": "원문 조건 일부를 실행식으로 변환하지 못했습니다",
        "explanation": "ENTRY/EXIT 항목 중 지원되는 비교식은 보존했고, 모호하거나 미지원인 나머지 조건은 생략하지 않았습니다.",
        "action": "분석 결과의 원문 행별 질문을 확인하세요. 수치 정의가 필요한 조건은 보완하고, 미지원 상태·지표는 엔진 지원 전까지 실행할 수 없습니다.",
        "example": "ENTRY: 아래 rsi <= 30.5 처럼 지원 지표·비교값 명시. 원래 전략의 조건 변경은 새 버전으로 검증",
    },
    "source_grounding_stale_after_execution_edit": {
        "title": "분석 후 실행 규칙이 변경됐습니다",
        "explanation": "현재 JSON이 분석한 원문과 달라 원문 근거 해시가 일치하지 않습니다.",
        "action": "변경 내용을 원문에 반영해 다시 분석하거나, 직접 편집한 내용이 맞다면 사용자 선언 확인란을 선택하세요.",
        "example": "원문 수정 → AI 분석 및 전략 초안 만들기 → 최종 재검증",
    },
    "source_grounding_user_override_not_confirmed": {
        "title": "직접 편집한 규칙의 사용자 확인이 필요합니다",
        "explanation": "원문 자동 변환본과 다른 JSON을 새 사용자 선언 버전으로 저장하기 위한 확인입니다.",
        "action": "고급 JSON 변경 내용을 검토한 뒤 사용자 선언 확인란을 선택하세요.",
        "example": "직접 편집한 JSON을 사용자 선언 규칙으로 저장",
    },
    "source_grounding_invalid": {
        "title": "원문과 실행 규칙의 연결 근거가 올바르지 않습니다",
        "explanation": "어떤 원문에서 현재 실행 규칙이 만들어졌는지 확인할 수 없습니다.",
        "action": "원문 분석을 다시 실행해 근거를 새로 만드세요.",
        "example": "원문 입력 → AI 분석 및 전략 초안 만들기",
    },
    "leverage_out_of_supported_range": {
        "title": "레버리지 값이 지원 범위를 벗어났습니다",
        "explanation": "정수가 아니거나 계좌·전략 계약에서 허용하는 범위를 넘었습니다.",
        "action": "암호화폐 선물은 1~10 사이 정수로 지정하고, 현물·주식은 1배를 사용하세요.",
        "example": "최대 레버리지 3배",
    },
}


def build_validation_issue_details(
    issues: Iterable[Any],
    unsupported_conditions: Iterable[Any] = (),
) -> List[Dict[str, str]]:
    """Translate fail-closed validation codes into beginner-actionable guidance."""
    expanded = [str(item).strip() for item in issues if str(item).strip()]
    unsupported = [str(item).strip() for item in unsupported_conditions if str(item).strip()]
    if unsupported:
        expanded = [item for item in expanded if item != "unsupported_executable_conditions"]
        expanded.extend(unsupported)
    details: List[Dict[str, str]] = []
    seen: set[str] = set()
    for code in expanded:
        if code in seen or code == "document_conditions_missing":
            continue
        if code == "confirm_executable_entry_missing" and any(
            item in expanded for item in ("entry", "missing_required_rule:entry")
        ):
            continue
        if code == "strategy_exit_rates_missing" and any(
            item in expanded for item in ("stop_loss_unit_missing", "take_profit_unit_missing")
        ):
            continue
        if code == "stop_loss" and "stop_loss_unit_missing" in expanded:
            continue
        if code == "take_profit" and "take_profit_unit_missing" in expanded:
            continue
        seen.add(code)
        field = (
            code.split(":", 1)[1]
            if code.startswith("missing_required_rule:")
            else code if code in FIELD_GUIDANCE else ""
        )
        if field in FIELD_GUIDANCE:
            guide = FIELD_GUIDANCE[field]
            detail = {
                "code": code,
                "title": f"{guide['label']} 항목이 없습니다",
                "explanation": "전략을 다른 의미로 추측해 실행하지 않기 위해 원문 확인이 필요합니다.",
                "action": guide["question"],
                "example": guide["example"],
            }
        elif code.startswith("pine_entry_condition_unresolved:"):
            alias = code.split(":", 1)[1] or "진입 변수"
            detail = {
                "code": code,
                "title": f"Pine 진입 변수 '{alias}'의 조건을 해석하지 못했습니다",
                "explanation": "변수 이름만 확인되고 그 값이 true가 되는 계산식을 안전하게 연결하지 못했습니다.",
                "action": "해당 변수의 지표·연산·임계값을 원문에 풀어 적고 다시 분석하세요.",
                "example": f"{alias} = RSI(14) < 30",
            }
        elif code.startswith("user_confirmation_conflicts_with_original:"):
            path = code.split(":", 1)[1] or "실행 조건"
            detail = {
                "code": code,
                "title": "보완 답변이 기존 원문과 충돌합니다",
                "explanation": (
                    f"보완 답변의 '{path}' 값이 원문에 이미 선언된 값과 다릅니다. "
                    "질문 답변은 누락값만 채울 수 있으며 기존 전략을 조용히 바꾸지 않습니다."
                ),
                "action": "기존 값을 바꾸려면 원문을 수정해 새 버전으로 다시 분석하세요.",
                "example": "원문 수정 → 다시 분석 → 변경점 확인 → 사용자 승인",
            }
        elif code in VALIDATION_ISSUE_GUIDANCE:
            detail = {"code": code, **VALIDATION_ISSUE_GUIDANCE[code]}
        elif "unsupported_field:" in code:
            value = code.rsplit("unsupported_field:", 1)[1] or "알 수 없는 필드"
            detail = {
                "code": code,
                "title": f"지원하지 않는 지표 필드 '{value}'가 있습니다",
                "explanation": "실행 엔진이 해당 이름의 시장 데이터를 안전하게 계산할 수 없습니다.",
                "action": "지원되는 지표로 바꾸거나 사용자 지표 정의에 계산식을 명시하세요.",
                "example": "RSI, EMA, SMA, MACD처럼 입력 데이터와 기간을 명시",
            }
        elif "unsupported_operator:" in code:
            value = code.rsplit("unsupported_operator:", 1)[1] or "알 수 없는 연산자"
            detail = {
                "code": code,
                "title": f"지원하지 않는 비교 연산자 '{value}'가 있습니다",
                "explanation": "조건의 참·거짓을 동일하게 재현할 수 없어 실행을 차단했습니다.",
                "action": "초과·이상·미만·이하·같음 또는 교차 조건으로 명확히 바꾸세요.",
                "example": "RSI가 30 이하일 때",
            }
        else:
            detail = {
                "code": code,
                "title": "실행 규칙에서 추가 확인이 필요합니다",
                "explanation": "안전하게 해석되지 않은 조건을 조용히 제거하지 않고 차단했습니다.",
                "action": "아래 기술 코드를 AI 어시스턴트에 질문하거나 원문 조건을 더 구체적으로 작성하세요.",
                "example": code,
            }
        details.append(detail)
    return details


def build_clarification_questions(
    details: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Turn fail-closed issues into a bounded user-confirmation interview.

    These questions never contain executable answers.  The caller may collect a
    user's own answer and submit it as a separate source supplement, but an AI
    suggestion cannot silently satisfy an execution requirement.
    """
    questions: List[Dict[str, Any]] = []
    definition_targets = set()
    for index, raw in enumerate(details):
        detail = dict(raw or {})
        code = str(detail.get("code") or "").strip()
        if not code:
            continue
        field = (
            code.split(":", 1)[1]
            if code.startswith("missing_required_rule:")
            else code if code in FIELD_GUIDANCE else ""
        )
        target = str(detail.get('answer_target') or '')
        definition = (detail.get('answer_kind') == 'condition_definition'
                      and bool(re.fullmatch(r'[A-Za-z_]\w{0,127}', target, re.ASCII)))
        if definition:
            if target in definition_targets:
                continue
            definition_targets.add(target)
        answerable = field in FIELD_GUIDANCE or definition
        questions.append({
            "id": f"clarification-{index + 1}-{field or 'contract'}",
            "code": code,
            "field": field,
            "title": str(detail.get("title") or "추가 확인 필요"),
            "question": str(detail.get("action") or "원문 조건을 구체적으로 설명해 주세요."),
            "why": str(detail.get("explanation") or "원문과 실행 규칙의 의미를 일치시키기 위한 확인입니다."),
            "example": str(detail.get("example") or ""),
            "resolution": (
                "confirmed_selection"
                if field in {"position_size", "market_conditions"}
                else "user_answer"
                if answerable
                else "source_rewrite"
            ),
            "answer_required": answerable,
            "auto_executable": False,
            **({'answer_kind': 'condition_definition', 'answer_target': target}
               if definition else {}),
        })
    return questions


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
