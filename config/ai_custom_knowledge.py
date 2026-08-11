"""v3.9.0.8 AI 커스텀 사용자 안내 정본.

대시보드 AI 어시스턴트가 외부 Provider 없이도 새 기능, 현재 프로필,
백테스트/PAPER 경계와 안전한 사용 순서를 일관되게 설명하는 데 사용한다.
"""

from __future__ import annotations

from typing import Any, Mapping

from config.app_version import RELEASE_BUILD_LABEL
from trading.ai_custom_features import resolve_ai_custom_features


FEATURE_LABELS = {
    "replay_analytics": "과거 재생 요약(PnL·MDD)",
    "monthly_yearly_table": "월별·연별 수익률 표",
    "expression_graph": "Expression Graph",
    "user_indicator_language": "제한형 사용자 지표 언어",
    "strategy_package": ".noahstrategy 내보내기·가져오기",
    "team_sharing": "팀 공유 권한 메타데이터",
    "quality_report": "과최적화·PAPER 품질 리포트",
    "signed_webhook": "서명 webhook 게이트",
    "b2b_audit": "B2B 감사 번들",
}


def _topic(message: str, *tokens: str) -> bool:
    normalized = str(message or "").lower().replace(" ", "")
    return any(str(token).lower().replace(" ", "") in normalized for token in tokens)


def _profile_status(settings: Mapping[str, Any] | None) -> str:
    resolved = resolve_ai_custom_features(settings or {})
    enabled = [
        FEATURE_LABELS[key]
        for key, value in resolved["features"].items()
        if value and key in FEATURE_LABELS
    ]
    disabled = [
        FEATURE_LABELS[key]
        for key, value in resolved["features"].items()
        if not value and key in FEATURE_LABELS
    ]
    return (
        f"현재 프로필: {resolved['profile_label']} · 보기 Level {resolved['view_level']}\n"
        f"켜짐: {', '.join(enabled) if enabled else '없음'}\n"
        f"꺼짐: {', '.join(disabled) if disabled else '없음'}"
    )


def build_ai_custom_knowledge(
    message: str,
    settings: Mapping[str, Any] | None = None,
    *,
    safe_flow: str = "",
    provider_guide: str = "",
) -> str:
    """질문 의도에 맞는 AI 커스텀 로컬 정본 답변을 만든다."""

    header = f"NoahAI입니다. {RELEASE_BUILD_LABEL}의 AI 커스텀 기준으로 안내합니다.\n"
    profile = _profile_status(settings)

    if _topic(message, "ai멘토", "ai 멘토", "멘토 인터뷰", "처음 사용법", "처음사용법"):
        body = (
            "AI 멘토 인터뷰는 투자 경험·목표·위험 허용도 등 8문항을 묻고 개인화된 교육용 전략 후보 2~3개를 만드는 시작 도구입니다. "
            "후보를 자동 저장·승인·적용하지 않으며 사용자가 고른 뒤 XAI 검토를 계속해야 합니다.\n"
            "‘처음 사용법 AI에게 묻기’는 현재 화면과 프로필을 기준으로 자료 입력 → XAI → 저장 → 승인 → 자동검증 → PAPER 순서를 안내하는 사용 설명입니다. "
            "개인화 전략 후보를 만들지는 않습니다. 전략이 막막하면 멘토, 이미 가진 전략이나 자료가 있으면 사용법 안내를 선택하세요."
        )
    elif _topic(message, "버전", "업데이트", "3.9.0.8", "새 기능", "추가", "변경", "고도화"):
        body = (
            "Fix 1은 설정창을 프로세스당 하나만 재사용하고 블록체인/주식 전환의 탭 소유권과 순서를 단일 정책으로 고정합니다. "
            "설정창이 비거나 열리지 않는 문제, 거래소와 증권사 탭 혼합, 코인 정보 순서 이동, 포지션 빈 카드의 자원 원인을 함께 줄였습니다. "
            "추가 피드백으로 현재 잔고 기반 통합자산·KRW/USDT 분리, AI 애널리스트의 생존 입력창 재연결, 실제 AI 질문의 하단 실행 기록도 보강했습니다.\n"
            "AI 커스텀 본 업데이트는 Noah Strategy IR v1과 원본 근거 추적, Level 1·2·3, "
            "초보자/일반/고급/실험실 프로필, PnL·MDD·월별·연별 검증표, 중첩 Expression Graph, "
            "제한형 사용자 지표 언어, .noahstrategy 패키지, 품질·감사 보고서와 서명 webhook 게이트를 포함합니다.\n"
            "Windows 새 실행 파일과 실제 TradingView/webhook·장시간 PAPER/LIVE·서버 팀 공유는 별도 검증 대상이며, "
            "소스 기능과 배포·실환경 검증을 같은 의미로 설명하지 않습니다."
        )
    elif _topic(message, "백테스트", "pnl", "mdd", "월별", "연별", "수익률", "과최적화"):
        body = (
            "백테스트는 미래 수익 예측이나 수익 보장이 아니라 전략 규칙·비용·손실 구조의 최소 통과조건입니다. "
            "총 PnL·총 수익률·MDD·승률·Profit Factor와 월별·연별 표를 확인하되, 표본 부족·PnL 음수·과도한 MDD는 실패 이유로 표시합니다.\n"
            "과거 재생만으로 전략을 자동 승격하지 않습니다. 현재 시장의 PAPER 전진검증을 거쳐야 하며, "
            "PAPER와 LIVE의 주문·슬리피지·부분체결 차이도 별도로 보아야 합니다."
        )
    elif _topic(message, "프로필", "초보자", "일반", "고급", "실험실", "그래프", "지표언어", "켜", "끄", "on", "off"):
        body = (
            "프로필은 다른 전략 엔진이 아니라 화면 복잡도의 시작값입니다. 설정 → AI 엔진/API → AI 커스텀 사용 난이도에서 "
            "초보자·일반·고급·실험실을 선택하고 각 기능을 다시 켜거나 끌 수 있습니다. 기반 기능을 끄면 종속 기능도 안전하게 꺼집니다.\n"
            "초보자는 요약·근거·품질 중심, 일반은 핵심값과 성과표·패키지, 고급은 전체 IR·Expression Graph·사용자 지표, "
            "실험실은 서명 webhook까지 노출합니다. 어떤 프로필도 승인·검증·계좌·주문 안전을 우회하지 않습니다.\n"
            "개별 기능은 기본으로 접혀 있으므로 필요할 때만 ‘개별 고급 기능 펼치기’를 누릅니다. 분석 전·검증 전에는 결과 카드가 아직 보이지 않을 수 있습니다.\n"
            + profile
        )
    elif _topic(message, "패키지", "noahstrategy", "내보내기", "가져오기", "공유", "여권"):
        body = (
            ".noahstrategy는 전략 규칙·IR·전략 여권을 공유하는 로컬 패키지입니다. API 키·계좌·잔고·개인 거래·절대경로·승인/활성 상태는 제외합니다. "
            "가져올 때 SHA-256과 선택형 서명을 확인하고 항상 비활성 검토 상태로 열리므로 다시 검토·승인·검증해야 합니다.\n"
            "private/team/unlisted는 권한 메타데이터이며 실제 서버 팀 초대·철회·다운로드와 유료 마켓은 아직 별도 운영 게이트입니다."
        )
    elif _topic(message, "웹훅", "webhook", "tradingview", "트레이딩뷰", "서명", "nonce"):
        body = (
            "지정 거래소를 연결하거나 NoahAI 앱 안에서 전략을 계산·실행할 때는 webhook이 필요하지 않습니다. "
            "webhook은 TradingView 같은 외부 서비스가 만든 알림을 NoahAI로 들여오는 선택형 입력 통로이며 거래소 주문 연결 방식이 아닙니다.\n"
            "외부 TradingView 신호도 주문 후보일 뿐 자동 승인이나 자동 주문이 아닙니다. 실험실 프로필의 게이트는 HMAC 서명, 시간창, nonce와 delivery ID 중복을 검사합니다. "
            "검사를 통과해도 저장된 전략 버전·사용자 승인·PAPER/LIVE 권한·국면·계좌·주문 가드레일을 다시 통과해야 합니다.\n"
            "현재 클라이언트에는 검증 계약만 있으며 운영 endpoint·영속 nonce 저장소·실제 TradingView 전달 E2E는 별도 검증 대상입니다. 그래서 실험실 프로필 외에는 강제로 OFF됩니다."
        )
    elif _topic(message, "xai", "설명", "근거", "ir", "level", "레벨", "모호", "미지원"):
        body = (
            "XAI는 전략 요약만 말하는 기능이 아닙니다. 원문의 어느 문장·화면이 어떤 IR 노드와 실행 조건이 되었는지, "
            "필요 데이터·지표·시간봉·상태·주문 capability가 무엇인지 보여줍니다.\n"
            "Level 1은 초보자용 요약·근거·누락, Level 2는 핵심 파라미터와 위험·국면, Level 3은 전체 IR·그래프·안전 DSL입니다. "
            "세 화면은 같은 전략 ID·버전·IR을 사용하며 모호함은 사용자 확인 필요, 미지원은 차단으로 남깁니다."
        )
    else:
        body = (
            "AI 커스텀은 자연어·Pine·PDF·이미지·영상·TradingView 자료를 원본 근거가 연결된 제한형 전략 IR로 만들고, "
            "모호함·미지원 조건을 차단한 뒤 국면·위험·주문·체결까지 같은 버전으로 관리하는 AI 전략 운영체제입니다.\n"
            "저장과 실행은 다릅니다. 전략 버전 저장 → 사용자 승인 → 자동검증 → 최종 적용 → LEARNING/PAPER/LIVE 시작 순서를 지켜야 합니다."
        )

    extras = []
    if safe_flow and _topic(message, "사용법", "순서", "시작", "적용", "실행", "live", "paper"):
        extras.append("안전 사용 순서:\n" + safe_flow)
    if provider_guide and _topic(message, "provider", "모델", "openai", "deepseek", "claude", "gemini", "kimi", "api"):
        extras.append("AI Provider별 연결 범위:\n" + provider_guide)
    return header + body + (("\n\n" + "\n\n".join(extras)) if extras else "")
