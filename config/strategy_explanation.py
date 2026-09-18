"""Read-only, local explanation of the draft snapshot supplied by Strategy Studio.

This is display data, not an authenticated execution contract or performance proof.
Malformed input falls back to normal product help. No Provider or trading calls.
"""
import json

MARKER = "NOAH_STRATEGY_EXPLANATION_V1\n"
LABELS = {
    "entry": "진입 — 거래를 시작하는 조건",
    "exit": "청산 — 거래를 끝내는 조건",
    "stop_loss": "손절 — 손실을 제한하는 기준",
    "take_profit": "익절 — 이익을 확정하는 기준",
    "position_size": "위험·비중 — 사용할 자금의 기준",
    "market_conditions": "시장 — 전략을 사용할 상황",
}


def explain_strategy_snapshot(message: str) -> str:
    if MARKER not in message or len(message) > 4000:
        return ""
    try:
        data = json.loads(message.split(MARKER, 1)[1])
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict) or not isinstance(data.get("rules"), dict):
        return ""

    def text(value, limit=200):
        return " ".join(value.split())[:limit] if isinstance(value, str) else ""

    lines = [
        f"현재 초안 쉽게 읽기 · {text(data.get('name'), 80) or '사용자 전략'}",
        "화면에서 전달한 분석 요약입니다. 저장된 전략이나 실제 운용 성과를 확인한 답변은 아닙니다.",
        f"자료를 읽은 범위: {text(data.get('coverage')) or '미확인'}",
    ]
    for key, label in LABELS.items():
        lines.append(f"• {label}: {text(data['rules'].get(key)) or '확인되지 않음 · 보완 필요'}")
    excerpts = data.get("source_excerpts")
    lines.append("\n자료 속 성과와 NoahAI 검증은 다릅니다.")
    if isinstance(excerpts, list) and any(text(x) for x in excerpts):
        lines.append("성과 관련 원문 발췌입니다. 저자의 주장인지, 예시·질문인지도 문맥 확인이 필요합니다.")
        lines.extend(f"발췌: {text(item)}" for item in excerpts[:3] if text(item))
    else:
        lines.append("전달된 발췌에서 성과를 확인하지 못했습니다. 영상 전체에 성과 설명이 없다는 뜻은 아닙니다.")
    lines.append("기간·종목·비용·비교 조건을 확인하기 전에는 수익률을 검증된 성과로 보지 않습니다. 과거재생·PAPER·LIVE·여권은 별도 근거입니다.")
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        lines.extend(f"자료 읽기 주의: {text(item)}" for item in warnings[:2] if text(item))
    missing = data.get("missing")
    if isinstance(missing, list) and missing and text(missing[0]):
        lines.append(f"\n먼저 답할 질문: {text(missing[0])}")
    else:
        lines.append("\n먼저 확인할 질문: 위 진입·청산 조건이 본인이 의도한 전략과 같나요?")
    lines.append(
        "일반 안내는 외부 AI 없는 정형 설명입니다. 자료의 의미를 AI와 대화로 더 풀려면 기본 보호 경로의 심층분석을 선택하세요(Provider 설정·비용 적용). "
        "AI 답변은 검토 영역으로 가져온 뒤 필요한 조건만 남겨 사용자 보완 근거로 확정·재분석합니다. "
        "이 답변 전체를 실행 규칙으로 확정하지 마세요. 저장·승인·검증·PAPER·최종 적용·LIVE는 자동 실행되지 않습니다."
    )
    return "\n".join(lines)
