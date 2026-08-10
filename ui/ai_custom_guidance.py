"""AI 커스텀 화면·어시스턴트·메뉴얼이 공유하는 사용자 안내 정본."""

from __future__ import annotations

from typing import Tuple


AI_CUSTOM_SETTINGS_PATH = "설정 → AI 엔진/API"

AI_CUSTOM_CONFIRM_ROLE_LABEL = "기본 AI 후보 확인 (권장)"
AI_CUSTOM_INDEPENDENT_ROLE_LABEL = "사용자 전략 독립 신호 (숙련자)"

AI_CUSTOM_CONFIRM_ROLE_HELP = (
    "NoahAI의 실시간 후보를 내 전략 조건으로 한 번 더 확인합니다."
)
AI_CUSTOM_INDEPENDENT_ROLE_HELP = (
    "숙련자: 내 전략의 방향·조건·TP/SL을 유지하고, "
    "NoahAI는 국면·계좌·주문 안전만 감독합니다."
)

AI_CUSTOM_RULE_EDITOR_TITLE = "다중 시간봉 규칙 편집 (선택)"

AI_CUSTOM_PROVIDER_GUIDE: Tuple[str, ...] = (
    "OpenAI: 텍스트·JSON·차트/영상 비전·무자막 YouTube 음성 전사를 한 제공사에서 사용할 수 있습니다.",
    "DeepSeek: 텍스트·JSON 전략 구조화 중심이며 NoahAI 연결에서는 비전·음성 전사를 사용하지 않습니다.",
    "Claude: 현재 NoahAI 연결은 텍스트·JSON만 지원하며 차트/영상 비전은 사용하지 않습니다.",
    "Gemini: 텍스트·JSON·차트/영상 비전을 지원하며 무자막 음성 전사는 별도 OpenAI 전사 설정을 사용합니다.",
    "Kimi: OpenAI 호환 정식 API로 텍스트·JSON·차트/영상 비전을 지원합니다. 일반 Kimi 서비스와 개발자 API 과금·키는 별개입니다.",
)

AI_CUSTOM_SAFE_STEPS: Tuple[str, ...] = (
    "설정 → AI 엔진/API에서 Provider·API 키·모델을 확인합니다.",
    "AI 커스텀 엔진 사용을 ON으로 저장합니다.",
    "AI 멘토 인터뷰 또는 직접 자료 입력으로 시작합니다.",
    "처음에는 기본 AI 후보 확인(권장)을 선택합니다.",
    "XAI의 원문 근거·적용값·누락 조건을 확인합니다.",
    "다중 시간봉 규칙을 썼다면 규칙 안전성 검사를 통과합니다.",
    "검토한 전략을 새 버전으로 저장합니다.",
    "사용자가 저장 버전을 직접 승인합니다.",
    "수수료·슬리피지를 포함한 자동검증 결과를 확인합니다.",
    "검증된 버전을 최종 적용합니다.",
    "LEARNING 또는 PAPER에서 먼저 관찰합니다.",
    "실계정 권한·가드레일·소액 E2E 확인 후에만 LIVE를 사용합니다.",
)


def build_ai_custom_safe_flow(*, numbered: bool = True) -> str:
    if not numbered:
        return " → ".join(step.rstrip(".") for step in AI_CUSTOM_SAFE_STEPS)
    return "\n".join(
        f"{index}. {step}" for index, step in enumerate(AI_CUSTOM_SAFE_STEPS, start=1)
    )


def build_ai_custom_safe_flow_compact() -> str:
    """대시보드에 항상 노출할 수 있는 짧은 6구간 요약."""
    return (
        "AI 설정·엔진 ON → 멘토/자료 입력 → 권장 역할·XAI/규칙 확인 → "
        "버전 저장·승인·자동검증 → 최종 적용 → LEARNING/PAPER 후 LIVE"
    )


def build_ai_custom_provider_guide() -> str:
    return "\n".join(f"• {line}" for line in AI_CUSTOM_PROVIDER_GUIDE)
