"""현행 AI 커스텀 사용자 안내 정본.

대시보드 AI 어시스턴트가 외부 Provider 없이도 새 기능, 현재 프로필,
백테스트/PAPER 경계와 안전한 사용 순서를 일관되게 설명하는 데 사용한다.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from config.app_version import RELEASE_BUILD_LABEL
from config.assistant_support_knowledge import build_support_answer
from config.strategy_explanation import explain_strategy_snapshot
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


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


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

    snapshot_answer = explain_strategy_snapshot(message)
    if snapshot_answer:
        return snapshot_answer
    support_answer = build_support_answer(message)
    if support_answer:
        return support_answer

    header = f"NoahAI입니다. {RELEASE_BUILD_LABEL}의 AI 커스텀 기준으로 안내합니다.\n"
    profile = _profile_status(settings)

    if _topic(message, "전략 상담", "AI와 전략", "워뇨띠", "버핏", "대회 우승", "strategy consultation"):
        return header + (
            "Web UI AI 어시스턴트의 `전략 상담 · 외부 AI` 또는 전략 스튜디오의 `AI와 전략 상담`을 누르세요. "
            "전송할 때 설정된 외부 AI 비용·한도를 사용합니다. 일반 개념은 예산 없이 설명하고 맞춤 초안은 목적·상품·예산·손실 허용 범위·기간·레버리지를 하나씩 확인합니다. "
            "조건을 확인한 초안만 검토 영역으로 전달하며 사용자 검토·재분석·버전 저장·승인·과거재생/PAPER 절차는 유지됩니다. 대화만으로 거래하지 않습니다. "
            "공개 원칙·해석·사용자 변형을 구분하며 비공개 매매법이나 최신 우승/수익률을 추측하지 않습니다. 실시간 웹 검색은 없고 원문·자막이 필요할 수 있습니다. "
            "미지원 규칙이나 부족한 근거는 검증에서 보류합니다. 설정 기본값이나 AI 제안을 사용자 동의로 취급하지 않습니다."
        )

    root_settings = dict(settings or {})
    sizing_policy = dict(root_settings.get("position_sizing_policy") or {})
    sizing_mode = str(sizing_policy.get("mode") or "legacy_venue").strip().lower()
    if sizing_mode == "fixed_notional":
        sizing_mode = "manual_notional"
    fixed_notional = _number(root_settings.get("min_trade_amount", 20.0) or 20.0, 20.0)
    risk_percent = _number(sizing_policy.get("risk_per_trade_percent", 0.5) or 0.5, 0.5)
    max_margin_percent = _number(sizing_policy.get("max_margin_usage_percent", 10.0) or 10.0, 10.0)
    max_notional_percent = _number(sizing_policy.get("max_notional_percent", 50.0) or 50.0, 50.0)
    layers = dict(root_settings.get("advanced_trading_layers") or {})
    profitability = dict(layers.get("profitability_validation") or {})
    min_trades = max(1, _integer(profitability.get("min_trades", 10) or 10, 10))
    recovery_window = max(1, _integer(profitability.get("recovery_review_interval_trades", 20) or 20, 20))
    recovery_multiplier = _number(profitability.get("recovery_risk_multiplier", 0.15) or 0.15, 0.15)

    if _topic(message, "429", "interactive_ai_budget_exceeded", "30개 제한", "30회 제한", "심층분석 한도"):
        ai_cost = dict(root_settings.get("ai_cost_control") or {})
        daily_limit = max(1, _integer(ai_cost.get("max_daily_interactive_calls", 30) or 30, 30))
        monthly_limit = max(1, _integer(ai_cost.get("max_monthly_interactive_calls", 500) or 500, 500))
        body = (
            f"대화형 AI 한도와 Provider 오류는 지원 코드로 구분합니다. "
            f"현재 저장 기준은 하루 {daily_limit}회, 월 {monthly_limit}회입니다. 기본 일 30회·월 500회는 API 비용 폭주와 실수로 같은 분석을 반복하는 상황을 막기 위한 안전 기본값이며 설정 → AI 엔진/API → AI 비용 관리에서 일 1~1000회·월 1~30000회 범위로 사용자가 바꿀 수 있습니다. 일일 집계는 UTC 00:00(한국시간 09:00)에 갱신됩니다.\n"
            "오류 코드가 interactive_ai_budget_exceeded이면 NoahAI가 Provider 요청 전에 막은 로컬 비용 보호 429입니다. Provider가 직접 반환하는 429는 해당 제공사의 요청 속도·동시 요청·쿼터·결제 문제이므로 NoahAI 한도와 다른 원인입니다.\n"
            "v3.9.1.27부터 텍스트·Pine의 전략 규칙 분석과 5분 따라 만들기는 한도에 도달해도 결정형 로컬 컴파일러로 계속됩니다. 이때 외부 AI 설명만 생략되고 실행 가능 여부·누락 조건·원문 근거 검사는 동일합니다. 일반 안내도 외부 호출 없이 계속 사용할 수 있습니다. 이미지·영상 전사처럼 외부 모델이 꼭 필요한 자료와 사용자가 누른 심층분석은 한도 갱신 또는 설정 변경 후 다시 실행해야 합니다. 한도를 높이면 Provider 비용도 늘 수 있으므로 테스트 목적에 맞는 값만 승인해 저장하세요."
        )
    elif _topic(message, "시간봉", "15분봉", "1분봉", "4시간봉", "고정 기간", "이전 버전과 변경점", "고칠 항목으로 이동"):
        body = (
            "과거 시세 재생 검사는 저장된 전략 규칙을 과거 봉에 적용하는 제한된 역사적 시뮬레이션입니다. 실시간 PAPER나 실제 체결 검증과 같지 않으며, 전체 Pine 문법이나 TradingView 계산과 동일하다고 보장하지 않습니다.\n"
            "v3.9.1.30부터 원문의 판단 시간봉을 확인해 저장하고, 그 시간봉의 완료된 봉으로 평가합니다. 기간은 고정 3일이 아니라 실제 확보된 봉 수와 간격으로 결정하며 검증 근거에 UTC 시작·종료·시간봉·봉 수를 표시합니다. 현재 증권사 과거 공급은 일봉만 지원하므로 미지원 분봉을 일봉으로 바꿔 통과시키지 않습니다. 시간봉이 없는 구버전은 원문을 확인해 새 버전으로 저장하세요.\n"
            "NoahAI 기본 진입 보조 전략은 독립 진입 로직을 검증했다고 표시하지 않고 PAPER에서 사용자 위험·청산 계약을 확인합니다. 최초 v1에는 이전 버전 비교가 없고, v2부터 실제 저장 규칙 차이를 보여줍니다. 따라하기의 `고칠 항목으로 이동`은 안내창을 닫고 실제 입력 화면의 보완 안내로 이동합니다. 수정·재분석·저장·승인·PAPER 시작은 각각 확인해야 합니다."
        )
    elif _topic(message, "업데이트", "3.9.1.30", "새 기능"):
        body = (
            build_support_answer("업데이트 내용") or "설정 → 업데이트에서 설치 버전을 확인하세요."
        )
    elif _topic(message, "gpt 6", "gpt-6", "luna", "deepseek 4.1", "4.1 flash", "v4 flash", "deepseek 모델", "작업별 모델", "나만의 ai 구성"):
        body = (
            "3.9.2.0 모델 목록에는 `gpt-6-luna`(빈번·저비용), `gpt-6.1-sol`, Claude Sonnet/Opus 5.5, Kimi K2.7 Code가 추가됩니다. 기존 Gemini 3.8 Flash도 유지합니다. GPT-6 Luna가 저렴하다는 것이 투자 판단 정확도나 수익을 보장하지는 않습니다.\n"
            "2026-10-01 확인 기준 DeepSeek 최신 정식 별칭은 `deepseek-flash`와 `deepseek-v4-pro`입니다. "
            "`deepseek-flash`는 V4.1 Flash의 텍스트·JSON·이미지 입력을 지원합니다. `deepseek-v4-flash`와 `deepseek-v4-flash-vision-exp`는 제공사가 최신 Flash로 연결하는 임시 호환 ID입니다. 확인되지 않은 `deepseek-v4.1-flash`를 임의로 만들지 않습니다. 계정별 제공 여부는 실제 연결 점검으로 확인하세요.\n"
            "설정 → AI 엔진/API의 `나만의 AI 구성 · 작업별 모델`에서 빈번·저비용, 표준 분석, 정밀·전략, AI 애널리스트, AI 어시스턴트를 서로 다른 Provider와 모델로 배치할 수 있습니다. "
            "모델 변경은 초안이며 현재 설정 저장 후 실제 작업에 적용됩니다. `선택 모델 1회 실제 호출 점검`은 Provider 모델 목록만 보여 주는 검사가 아니라 비민감 고정 문장으로 AI 애널리스트 선택 모델을 한 번 호출합니다. 요청 모델·Provider 실제 응답 모델·토큰을 각각 표시하고 AI 비용 관리에 외부 호출 1회로 기록합니다. 목록에 모델이 없어도 실제 호출이 성공하면 호출 결과를 우선하며, 화면의 `변경 대기` 값으로 점검했다면 설정 저장 전까지 다른 작업에는 반영되지 않습니다. "
            "차트 분석은 이미지 기능이 확인된 모델만 허용하고, YouTube는 공개 자막과 다운로드 가능한 자막을 먼저 사용해 비용을 피한 뒤 자막이 없을 때만 별도 OpenAI 전사를 사용합니다. "
            "비용·속도·정밀도의 최적 조합은 사용자 키의 권한·단가·작업에 따라 달라지므로 NoahAI가 미확인 모델로 자동 교체하거나 저장하지 않습니다. NoahAI 로컬 원장은 성공 응답에서 Provider가 반환한 실제 모델을 기록하며, 실제 청구 대조는 같은 Organization·Project·UTC 기간을 선택한 Provider Usage가 정본입니다."
        )
    elif _topic(message, "데이터 공유", "무료 토큰", "100만 토큰", "모델 학습", "학습에 사용"):
        body = (
            "OpenAI API 데이터는 기본적으로 모델 학습에 사용되지 않으며, 조직 관리자가 별도 데이터 공유 설정에 명시적으로 동의한 경우에만 모델 개선에 사용될 수 있습니다. "
            "공유에 따른 무료 토큰·대상 모델·기간·적용 여부는 계정과 당시 프로그램 조건에 따라 달라져 NoahAI가 확인하거나 보장하지 않습니다.\n"
            "비공개 전략·Pine·문서·차트·포지션·계좌·설정 문맥은 기본 보호 경로에 둬야 합니다. v3.9.1.27은 설정 → AI 엔진/API에서 기본 보호 Project와 공개 일반 질문용 Project 키를 분리합니다. 공개 경로는 기본 OFF이며, AI 어시스턴트 심층분석에서 사용자가 공개 질문 1건을 별도로 확인할 때만 최근 대화와 앱 상태를 제외하고 공유용 키를 사용합니다. "
            "공유용 키가 없거나 설정이 꺼져 있으면 기본 보호 경로를 사용하며 보호 요청이 공유용 키를 빌려 쓰지 않습니다. NoahAI는 조직 공유 활성화나 무료량을 확인·보장하지 않습니다. 설정 → AI 엔진/API에서 공식 정책과 조직 설정을 직접 확인하세요. 일반 안내와 결정형 전략 분석은 외부 호출이 없으며 실제 청구는 Provider Usage가 정본입니다."
        )
    elif _topic(
        message,
        "거래소 승인", "승인 전", "승인 대기", "레퍼럴 승인", "레퍼럴 uid",
        "membership_exchange", "거래 권한", "바이비트 권한", "bybit 권한",
    ):
        body = (
            "거래소 API 키 인증과 NoahAI 계정의 거래 권한은 별도입니다. API 인증·잔고 조회가 성공해도 레퍼럴 무료회원의 해외 거래소가 서버 정책에서 승인되지 않았다면 LEARNING/PAPER/LIVE 엔진 시작은 차단됩니다.\n"
            "화면의 `승인 필요`, `UID 확인 대기`, `승인 거절`, `승인 만료`, `승인 후 운영 활성화 대기` 안내를 확인하세요. noahai.net에서 해당 거래소 UID와 승인 상태를 확인하고, 승인되지 않은 거래소는 관리자에게 권한 승인을 요청하세요. 유료 코인·프리미엄 계정은 자신의 라이선스 범위를 확인하세요.\n"
            "관리자가 승인한 뒤에는 NoahAI가 시작 명령 직전에 서버 회원정책을 다시 확인합니다. 계속 차단되면 재로그인 후 다시 시도하고, 거래소명·계정명·화면의 승인 상태만 전달하세요. API Secret이나 전체 키는 지원 요청에 보내지 마세요."
        )
    elif _topic(
        message,
        "무료 3개", "유료 5개", "포지션 상한", "다중포지션", "집중운용",
        "코인원", "coinone", "전략 회원등급", "전략 유료", "전략 무료",
    ):
        body = (
            "v3.9.1.29에서 전략 제작과 실제 계정 운용 용량은 분리됩니다. "
            "Strategy Studio의 제작·로컬 분석·PAPER 검증·내보내기·공유 준비는 회원등급과 무관하게 같은 Level 1~5와 검증 계약을 사용합니다. 유료 여부가 전략 점수나 증거등급을 높이지 않습니다.\n"
            "실제 계정은 집중운용 1개를 유지합니다. 관리형 다중포지션은 국내 무료와 레퍼럴 확인 해외 무료가 거래소별 최대 3개, pro_coin·premium이 최대 5개입니다. 이 값은 반드시 채우는 목표가 아니라 계정 상한입니다. 전략 요청, 계좌 총위험, 시장 위험, 성과회복과 하드 가드레일 중 더 작은 값이 최종 적용되므로 0~상한 사이가 될 수 있습니다.\n"
            "Upbit·Bithumb·Coinone 국내 현물은 레퍼럴 UID 없이 무료 경로입니다. 세 거래소의 공개 코인 선택·분석과 PAPER는 개인 API 키 없이 공개 KRW 시세와 로컬 가상 원장으로 실행하며, 실제 잔고·주문·체결 동기화에는 인증이 필요합니다. 해외 무료는 서버에서 레퍼럴 귀속이 확인된 Binance·Bybit·OKX·Bitget만 실행할 수 있습니다. Coinone은 KRW 현물 시세·PAPER·통계·Strategy Studio 준비 상태지만 실계좌 주문·부분체결·수수료·재시작 대조 E2E 전에는 LIVE와 주문이 차단됩니다."
        )
    elif _topic(
        message,
        "거래 위험예산", "거래당 계좌 손실", "증거금 사용", "증거금 최대",
        "종목당 투자 비중", "위험예산 누락", "ai가 알아서 판단",
        "노아가 자동으로 판단", "현재 선택값을 원문에 추가", "현재 선택값을 보완 근거로 추가",
        "원문 그대로 구조화", "질문으로 함께 완성", "답변 확정 후 다시 분석",
    ):
        body = (
            "v3.9.1.25에서는 화면이 `거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%`를 안내했지만 원문 컴파일러가 이 문장형 위험예산을 읽지 못해 같은 누락이 반복되는 버그가 있었습니다. "
            "거래당 계좌 손실·1회 위험·risk per trade의 명시적 퍼센트를 거래당 위험으로, 암호화폐의 증거금 비중과 주식·ETF의 종목당 투자 비중을 최대 운용 비중으로 구조화합니다. `%` 없는 숫자는 단위를 추측하지 않습니다. 제작 방식은 `원문 그대로 구조화 / 질문으로 함께 완성 / 기본 NoahAI에 맡기기`이며 Level 1~5와 안전 검사는 별개입니다.\n"
            "누락 카드의 `현재 선택값을 보완 근거로 추가`를 누르면 AI가 새 값을 정하는 것이 아니라 현재 Strategy Studio 화면에서 사용자가 고른 위험값 또는 시장국면을 원본과 분리된 사용자 확인 근거에 넣습니다. 추가 뒤 다시 분석해야 하며 분석된 위험값은 저장 화면과 동기화됩니다.\n"
            "`질문으로 함께 완성`에서 AI는 질문과 예시만 제공하고, 사용자가 직접 입력·확정한 누락 답변만 원본과 별도 SHA-256 근거로 재분석합니다. 이미 원문에 선언된 값과 충돌하면 덮어쓰지 않고 원문 수정과 새 버전을 요구합니다. 진입·청산·LONG/SHORT·지표·임계값은 전략의 정체성과 책임 범위이므로 자동으로 만들어 넣지 않습니다. 이 부분까지 NoahAI 판단을 원하면 불완전한 사용자 전략을 완성했다고 표시하는 대신 기본 NoahAI 운용 또는 `NoahAI 기본 진입 + 사용자 위험·청산` confirm 역할을 명시적으로 선택해야 합니다. AI 어시스턴트는 설명만 제공하고 원문·승인·PAPER·LIVE를 대신 변경하지 않습니다."
        )
    elif _topic(
        message,
        "최종 재검증", "최종 규칙 재검증", "보완할 조건", "missing_required_rule",
        "pine_dynamic_input_requires_user_confirmation", "pine_custom_function_not_supported",
    ):
        from trading.custom_strategy_advisor import build_validation_issue_details

        known_codes = re.findall(
            r"(?:missing_required_rule:[a-z_]+|pine_[a-z0-9_:.-]+|confirm_executable_entry_missing|"
            r"strategy_exit_rates_missing|stop_loss_unit_missing|take_profit_unit_missing|"
            r"source_grounding_[a-z_]+)",
            str(message or "").lower(),
        )
        details = build_validation_issue_details(known_codes)
        if details:
            issue_lines = []
            for index, item in enumerate(details, 1):
                issue_lines.extend([
                    f"{index}. {item.get('title') or item.get('code')}",
                    f"   고치는 방법: {item.get('action') or '원문 조건을 구체적으로 작성한 뒤 다시 분석하세요.'}",
                    f"   입력 예시: {item.get('example') or '진입·청산·위험 조건을 숫자와 단위로 명시'}",
                ])
            issue_text = "\n".join(issue_lines)
        else:
            issue_text = (
                "화면의 각 차단 항목에서 ‘고치는 방법’과 ‘입력 예시’를 확인하세요. "
                "코드만 보이면 전략 스튜디오로 돌아가 원문 분석 결과의 누락 조건을 펼쳐 확인합니다."
            )
        body = (
            "최종 재검증 차단은 오류를 무시하라는 뜻이 아니라, 원문에서 확인되지 않은 조건을 NoahAI가 임의로 만들어 실행하지 않는 안전 차단입니다.\n\n"
            f"{issue_text}\n\n"
            "수정 순서: 1) 전략 스튜디오로 돌아가기 → 2) 원문 수정 칸에 조건을 숫자·단위와 함께 명시 → "
            "3) 원문 다시 분석 → 4) 보완할 조건 0개와 실행 규칙 구조화 완료 확인 → 5) 버전 저장. "
            "AI에게 묻기는 설명만 제공하며 원문·규칙·설정·주문을 자동 변경하지 않습니다."
        )
    elif _topic(message, "과거재생 비대상", "실행 가능한 진입 조건이 없어", "자동검증 확정", "자동 검증 확정", "paper 단계로"):
        body = (
            "v3.9.1.24의 관리형 '추세 따라가기'는 LONG/SHORT 조건을 분리 저장했지만 과거재생기가 단일 진입 필드만 읽어 '실행 가능한 진입 조건이 없어'로 잘못 멈출 수 있었습니다. v3.9.1.25에서는 두 방향을 각각 재생하고 동시에 성립하면 충돌 HOLD로 기록합니다. "
            "승인 뒤 '과거재생 비대상'이 표시되는 것은 검증 실패가 아닙니다. 자체 LONG/SHORT 진입조건이 있는 전략만 과거 시세에서 독립 재생할 수 있습니다. "
            "'NoahAI 기본 진입 + 사용자 위험·청산' confirm 전략은 NoahAI의 실시간 후보 흐름이 있어야 작동하므로 단독 과거재생을 통과한 것처럼 만들지 않습니다. "
            "전략 스튜디오에서 'PAPER 단계로 이동'을 누른 뒤 'PAPER 전진검증 시작'을 두 번 확인하세요. PAPER는 실주문 없이 실제 NoahAI 후보와 이 버전의 위험·청산값을 함께 검증합니다. "
            "자체 진입조건 전략인데 같은 문구가 나오면 실행 규칙의 executable_entry/independent_entries와 validation_subject를 확인해야 합니다. 자동 LIVE 적용은 여전히 없습니다."
        )
    elif _topic(message, "ai멘토", "ai 멘토", "멘토 인터뷰", "처음 사용법", "처음사용법", "5분 따라", "따라 만들기", "따라만들기"):
        body = (
            "AI 멘토 인터뷰는 투자 경험·목표·위험 허용도 등 8문항을 묻고 개인화된 교육용 전략 후보 2~3개를 만드는 시작 도구입니다. "
            "후보를 자동 저장·승인·적용하지 않으며 사용자가 고른 뒤 원문 분석, 최종 규칙 재검증과 XAI 검토를 계속해야 합니다. "
            "멘토는 NoahAI 클라이언트 안에서 동작합니다. daltrading은 제출·탐색·다운로드, NoahAI Labs는 제품 설명과 연결을 담당하며 프라이빗 전략을 자동 수집하지 않습니다.\n"
            "‘처음 사용법 AI에게 묻기’는 현재 화면과 프로필을 기준으로 자료 입력 → XAI → 저장 → 승인 → 선택적 과거재생 → PAPER 순서를 설명하며 개인화 전략 후보를 만들지는 않습니다. "
            "‘처음 사용 · 5분 따라 만들기’는 모든 Level에서 현재 Level을 유지한 채 기본 NoahAI·관리형 예제·내 전략 가져오기 중 하나를 선택하고, 한 문항씩 답하며 같은 과정을 화면에서 직접 진행하는 안내입니다. 관리형 예제는 외부 AI API를 호출하지 않습니다. "
            "따라하기 초기화는 안내만 다시 시작하고 전략·PAPER·거래·학습 데이터를 삭제하지 않습니다. 저장·승인·PAPER·LIVE는 자동으로 건너뛰지 않습니다."
        )
    elif _topic(message, "api 비용", "호출 비용", "호출량", "토큰", "과호출", "deepseek 비용", "openai 비용", "ai 비용"):
        body = (
            "설정 → AI 엔진/API의 비용 카드는 AI 어시스턴트·전략 스튜디오 외부 보조·차트 분석·전사처럼 사용자가 직접 실행한 호출을 로컬에서 집계합니다. "
            "성공 응답의 실제 토큰과 기준일 공개 단가가 모두 있을 때만 오늘·이번 달 예상 달러 비용을 표시합니다. 구버전 호출, 토큰 미제공 모델, 단가 미등록 모델은 0달러로 꾸미지 않고 `비용 미산출`로 분리합니다. 이 값은 Provider 청구서가 아니며 자동매매 백그라운드 호출과 같은 API 키를 쓴 다른 앱의 비용은 포함하지 않습니다.\n"
            "Fix 4는 자동 AI 호출과 사용자가 직접 보낸 질문을 분리합니다. 자동 시장분석은 같은 상태를 30분 재사용하고, "
            "단순 새 캔들·지속 중인 LONG/SHORT·계속 과매수/과매도인 RSI만으로 반복 호출하지 않습니다. "
            "미세 변화는 최소 5분 간격이며 후보 방향 전환·RSI 임계 진입·MACD 교차·국면 전환은 즉시 분석합니다.\n"
            "기본 시장 상한은 전체 240회/일, 거래소별 40회/일, 6,000회/월입니다. 패턴·진입·포지션 크기·손익·리포트·진단을 포함한 "
            "모든 자동 AI는 360회/일·9,000회/월과 역할별 상한을 함께 적용합니다. 한도 도달 시 외부 AI만 로컬 신호로 대체하며 거래 안전검사는 계속됩니다.\n"
            "비용을 더 줄이려면 사용하지 않는 관찰·학습 거래소를 끄고 `나만의 AI 구성 · 작업별 모델`에서 빈번 호출 역할을 계정에서 확인된 저비용 모델로 두세요. "
            "YouTube는 공개 자막을 먼저 사용하고 자막이 없을 때만 OpenAI 전사를 호출합니다. Provider 청구액은 모델 단가·토큰·다른 앱/API 키 사용까지 포함할 수 있어 NoahAI 원장과 차이가 날 수 있습니다."
        )
    elif _topic(message, "전략 삭제", "프라이빗 삭제", "수정본", "전략 수정", "범위 변경", "시장상황 변경", "국면 변경", "초기화", "다시 입력"):
        body = (
            "저장 전 다시 시작하려면 전략 소스 입력의 ‘새로 시작 · 입력 초기화’를 누르세요. 입력 중인 초안만 지우며 저장된 전략은 삭제하지 않습니다. 새 URL·텍스트·파일을 넣으면 이전 분석 결과와 이전 파일 선택은 자동 해제되므로 ‘AI 분석 및 전략 초안 만들기’를 다시 실행하면 됩니다.\n"
            "저장된 전략을 수정하려면 저장 대상에서 기존 전략을 고르고 수정한 자료를 다시 분석한 뒤 ‘검토 및 전략 버전 저장’을 누르세요. 승인된 버전을 덮어쓰지 않고 같은 전략의 다음 버전으로 저장되며 XAI 확인·사용자 승인과 해당 버전의 PAPER 자격을 다시 확인합니다. 과거재생은 선택입니다.\n"
            "프라이빗 전략 전체를 지우려면 최신 버전 행의 ‘전략 삭제’를 누릅니다. 적용 중 전략은 사고 방지를 위해 삭제할 수 없으므로 먼저 ‘적용 해제’를 눌러 실행 풀에서 제거해야 합니다. "
            "삭제한 규칙은 복구되지 않으며 삭제 감사에는 전략/버전 식별자, 행위자, 시각만 남고 전략 규칙이나 API 자격증명은 남기지 않습니다."
        )
    elif _topic(message, "업비트 거래", "빗썸 거래", "국내 거래소", "원화 현물", "현물 short", "현물 숏", "시장가 매수"):
        body = (
            "Upbit와 Bithumb은 KRW 현물 거래소라 신규 SHORT와 레버리지가 없습니다. 분석 규칙과 구형 전략 호환을 위해 SHORT라는 토큰이 보일 수 있지만, 실행에서는 NoahAI가 직접 매수해 관리 중인 LONG의 청산으로만 해석합니다. 관리 LONG이 없으면 수동 매수·에어드롭·외부 봇 보유분을 보호하고 주문하지 않습니다.\n"
            "Upbit 시장가 매수는 코인 수량이 아니라 KRW 총액, 시장가 매도는 보유 코인 수량입니다. Bithumb과 해외 선물에는 Upbit의 총액 파라미터를 복사하지 않습니다. PAPER도 거래소 상품을 바꾸지 않으므로 국내 현물에서는 가상 LONG/청산만 만들고, LEARNING은 분석·신호를 기록해도 가상/실제 체결을 만들지 않습니다.\n"
            "v3.9.1.16은 이 계약을 코드와 회귀 테스트에 고정한 소스 후보입니다. Windows 설치본, Upbit/Bithumb PAPER와 승인된 최소 LIVE 매수→조회→청산을 거래소 원장과 대조하기 전에는 배포 완료로 판단하지 않습니다."
        )
    elif _topic(message, "일반", "고급") and _topic(message, "코인 선정", "종목 선정", "국면 기준", "국면 차이"):
        body = (
            "화면의 일반·고급 프로필과 실행 후보의 일반·독립 전략 경로는 서로 다릅니다. 프로필은 표시 복잡도이며 수익 조건을 자동으로 바꾸지 않습니다.\n"
            "일반 후보 경로는 거래소 시세·유동성 등으로 분석 대상을 선정하고 기본 NoahAI 신호를 평가합니다. 고급 후보 경로는 대상 기관에 맞는 independent 전략의 universe_policy와 우선순위로 대상을 추가합니다. "
            "두 목록이 겹치면 중복 종목은 합치되 출처와 평가 가능한 전략 ID를 보존합니다. 고급 전용 후보를 기본 confirm 전략 후보로 바꾸지는 않습니다.\n"
            "국면 판단은 후보 선정과 별도입니다. 각 전략의 market_conditions와 regime_scope(시장·종목·둘 다)를 확인해야 하며 고급이라는 이유로 국면·비용·주문 안전 검사를 생략하지 않습니다. "
            f"현재 저장된 국면 재확인 주기는 {_integer(root_settings.get('market_regime_check_interval_seconds', 300), 300)}초입니다. "
            "선택 전략의 실제 국면 범위와 유니버스는 해당 버전의 실행 파라미터에서 확인하세요.\n" + profile
        )
    elif _topic(message, "코인 선정", "코인 선택", "종목 선정", "종목 선택", "종합점수", "미산출", "고정 10개"):
        body = (
            "코인 선정은 주문이 아니라 현재 거래소에서 후속 분석할 후보를 좁히는 규칙 기반 단계입니다. "
            "거래소 지원 시장·유동성·캔들·변동성·거래량·추세·거래 빈도를 평가하고 Binance는 펀딩비·미결제약정을 보조 반영합니다.\n"
            "상태는 세 가지입니다. scored는 목표 수량 정상 평가, scored_partial은 정상 후보가 목표보다 적어 유효 후보만 부분 사용, "
            "fallback_unscored는 API·티커·캔들·점수 계산 문제로 평가 후보가 하나도 없어 진단용 주요 심볼을 미산출로 표시한 상태입니다. "
            "미산출 참조 목록은 PAPER와 LIVE 신규 진입을 만들지 않으며 기존 포지션의 감시·TP/SL·청산만 계속합니다. AI 커스텀도 이 차단을 우회하지 않습니다.\n"
            "숫자 점수 후보가 있어도 실시간 신호가 HOLD이거나 전략·비용·손실·포지션·주문 가드레일이 차단하면 주문하지 않습니다. "
            "시장의 다른 참여자가 거래한다는 사실과 NoahAI 진입 조건 통과는 별개입니다. `선택된 코인 수: 10`이어도 모두 미산출이면 실행 가능한 후보는 0개입니다. 같은 목록 반복은 시장 판단이 아니라 선정 복구 실패입니다.\n"
            "공개 v3.9.1.17 이후 OKX 피드백에서는 CCXT quoteVolume이 비어 모든 후보가 유동성 0으로 탈락하고 fallback_unscored 10개가 약 1분마다 새 세션으로 저장된 사실을 확인했습니다. v3.9.1.18 소스 후보는 OKX 원문의 volCcy24h 기초자산 수량×현재가로 USDT 거래대금을 복원하고 vol24h 계약 수는 수량으로 오인하지 않습니다. 미산출 복구를 즉시 1회 뒤 60초부터 최대 15분까지 점진 재시도하며 동일 실패 원장은 기본 15분에 한 번만 저장합니다. 회복 전 반복 상세 분석과 신규 진입은 생략하고 기존 포지션 보호는 유지합니다. 공개 v3.9.1.17 설치본에는 이 수정이 포함되지 않으므로 v3.9.1.18 Windows 빌드와 OKX PAPER 검증 전에는 해결 완료가 아닙니다. "
            "주식·ETF는 사용자 지정 종목 우선, 거래정지 제외, 거래대금 순 기본 8개이며 증권사별 유니버스와 분석 서비스를 5분 재사용합니다. 캐시 2초·단일 거래소 초기 p95 10초·6개 병렬 p95 15초는 Windows 실거래소 환경에서 확인할 설계 목표입니다."
        )
    elif _topic(
        message,
        "투자금", "진입 금액", "진입금액", "거래 금액", "거래금액",
        "notional", "노셔널", "복리", "성과 회복", "성과회복", "레버리지",
    ):
        mode_label = {
            "account_risk": "NoahAI 자동 위험관리",
            "manual_notional": "수동 목표 거래 금액",
            "legacy_venue": "기존 거래소별 호환",
        }.get(sizing_mode, "기존 거래소별 호환")
        if sizing_mode == "account_risk":
            mode_detail = (
                f"현재는 계좌 위험 기반입니다. 계좌 평가금액 × {risk_percent:g}% × 성과 위험배수를 "
                "SL 거리로 나눈 값을 출발점으로 하며, "
                f"거래당 최대 증거금 {max_margin_percent:g}%와 최대 Notional {max_notional_percent:g}%를 함께 적용합니다. "
                "따라서 평가금·SL 거리·성과 단계·레버리지 상한이 같지 않으면 주문 Notional도 달라집니다."
            )
        elif sizing_mode == "manual_notional":
            mode_detail = (
                f"현재는 사용자가 선택한 수동 목표금액 모드이고 정상 운용의 목표 Notional은 {fixed_notional:g}입니다. "
                "성과가 좋아져 제한이 해제돼도 이 설정값보다 자동 증액하지 않습니다. "
                "레버리지가 3배에서 5배로 바뀌어도 목표 Notional이 같다면 시장 노출은 같고 필요한 증거금만 줄어듭니다."
            )
        else:
            mode_detail = (
                "이 계정은 v3.9.1.22 이전 계산을 보존한 마이그레이션 상태입니다. 거래소마다 과거 수량 계산이 달랐기 때문에 자동으로 계좌비례 금액으로 바꾸지 않습니다. "
                "설정에서 NoahAI 자동 위험관리 또는 수동 목표금액을 한 번 확인해 선택하면 이후 모든 기관에서 같은 의미의 계약을 사용합니다."
            )
        body = (
            f"현재 저장된 투자금 계산 방식: {mode_label}\n"
            f"• {mode_detail}\n"
            f"• 신규·데이터 부족 구간은 유효 청산 {min_trades}건까지 각 청산 뒤 다시 평가하며 위험배수를 초기값에서 최대 0.50까지 점진 회복합니다.\n"
            f"• 표본 충족 뒤 KPI가 미달하면 최근 {recovery_window}건 창을 보며 기본 위험배수 {recovery_multiplier:g} 수준의 제한 회복 운용을 계속합니다. KPI 통과 뒤에도 즉시 1.0으로 점프하지 않고 기준 통과 폭에 따라 0.50~1.00 사이에서 점진 복구합니다. 달력상의 며칠 뒤가 아니라 유효 청산 수와 KPI가 기준입니다.\n"
            "• 성과회복은 허용 위험을 원래 설정까지 되돌리는 기능이지 수익에 따라 무제한 복리 증액하는 기능이 아닙니다. 자동 위험관리에서는 계좌 평가금과 전략 요청이 변하면 Notional도 바뀌며, 수동 목표금액은 사용자가 정한 값을 유지합니다.\n"
            "• Strategy Studio Level 4의 위험·레버리지·동시 포지션 값은 전략 요청입니다. 최종값은 계좌 마스터 상한, 시장 조정, 성과 조정과 거래소 규격 중 더 작은 값이며 다운로드 전략이 계좌 한도를 높일 수 없습니다.\n"
            "• 실제 최종 금액은 거래소 최소주문·수량 정밀도·포지션 한도·SL·최대 증거금·최대 노출 가드레일을 통과한 값이며, 근거가 없거나 최소주문이 승인 상한을 넘으면 주문하지 않습니다.\n"
            "위 설명은 현재 저장 설정을 읽은 안내이며 설정을 변경하거나 주문을 실행하지 않습니다."
        )
    elif _topic(message, "최종 검증 실패", "최소 주문", "min_notional", "5.10 usdt", "20 usdt"):
        body = (
            "v3.9.1.14 이전의 `5.10 USDT < 20 USDT` 최종 검증 실패는 정상 HOLD가 아니라 Binance 수량 계약 오류입니다. "
            "설정의 20 USDT는 목표 주문금액이고, 초기·회복 위험배수 0.10이 적용되면 2 USDT까지 축소됩니다. "
            "수량 계산기는 거래소 최소 주문 약 5 USDT와 2% 버퍼를 맞춰 5.10 USDT로 보정했지만, 구형 최종 검사가 이를 다시 사용자 목표 20 USDT와 비교해 주문을 차단했습니다.\n"
            "v3.9.1.15 소스 후보는 사용자 목표·위험 승인 상한·거래소 최소 규격을 분리합니다. 승인 상한 안에서 거래소 최소 규격을 만족하면 진행하고, 만족할 수 없으면 수량을 억지로 늘리지 않고 주문 가드레일 사유로 차단합니다. "
            "이는 소스 후보이며 Windows 설치본·Binance PAPER·소액 LIVE E2E 전에는 배포 해결로 표기하지 않습니다."
        )
    elif _topic(
        message,
        "누적 pnl", "최대 수익", "최대 손실", "체결 동기화",
        "화면 다시 계산", "거래 통계 가져오기", "거래 통계 새로고침",
        "대조 미확정", "거래소 실현 pnl", "기관 실현 pnl",
    ):
        body = (
            "v3.9.1.28의 LIVE 거래 통계는 청산 건수와 금액의 근거를 구분합니다. "
            "`화면 다시 계산`은 로컬 청산 원장을 다시 읽기만 하며 거래소 API를 호출하지 않습니다. "
            "`거래소 체결 동기화`는 선택한 거래소의 실제 체결을 가져와 주문 ID·종목·체결수량이 정확히 연결되는 NoahAI 청산과 대조한 뒤 화면을 다시 계산합니다. 전체를 선택하면 활성화된 거래소를 순서대로 처리합니다. "
            "주식·ETF의 증권사 체결은 각 증권사 동기화 경로에서 같은 외부 체결 원장에 보관되고, 매수 로트와 매도 수량을 연결한 순손익만 통계에 반영됩니다.\n"
            "누적값·최대 수익·최대 손실·승률은 체결 대조가 끝난 거래만 계산합니다. 거래소가 제공한 realized PnL은 `거래소 실현 PnL`, 진입·청산 수수료와 주식 세금까지 같은 기준통화로 확인된 값은 `체결 대조 완료 순손익`입니다. KRW와 USDT는 합산하지 않습니다. "
            "주문 ID가 없거나 수량이 맞지 않거나 수수료 통화 환산 근거가 없는 구버전 기록은 숫자를 꾸며 덮어쓰지 않고 `대조 미확정`으로 남습니다. 따라서 동기화 직후에도 미확정 건수가 있을 수 있으며, 이는 데이터 삭제나 거래 실패가 아니라 확정 근거 부족 표시입니다. "
            "PAPER 통계는 거래소 실체결이 아닌 독립 가상 원장을 사용하므로 체결 동기화 버튼이 나타나지 않습니다."
        )
    elif _topic(message, "통계 초기화", "통계 리셋", "표시 기준", "오늘 통계", "7일 통계", "30일 통계", "기간 통계", "사용자 지정 기간", "거래 통계 꼬임", "운영 kpi"):
        body = (
            "v3.9.1.23의 LIVE 거래 통계는 trade_log, PAPER 거래 통계는 독립 가상 청산 원장을 기준으로 계산하며 서로 섞지 않습니다. 실행 기관이 모두 PAPER이면 메인 운영 KPI는 별도 설정 없이 가상 포지션과 오늘 PAPER 청산으로 자동 전환됩니다. 거래 통계 탭에서 LIVE/PAPER와 오늘·7일·30일·전체·사용자 지정 기간을 선택할 수 있으며 KRW와 USDT 손익은 합산하지 않습니다. 거래소 출처가 없는 구형 LIVE 행은 보존하되 대표 합계나 Binance 성과로 추정하지 않습니다. "
            "'통계 표시 기준 새로 시작'은 거래 기록을 삭제하는 초기화가 아닙니다. 확인 후 누른 정확한 시각을 기준시각으로 저장하고, 그 뒤 청산된 LIVE 거래부터 기본 통계를 계산합니다. 누르기 전에 진입했더라도 기준시각 뒤 청산되면 포함됩니다. "
            "학습 데이터, Strategy Studio PAPER 검증, 거래소 체결·감사 원장, 성과회복·Profitability Gate·일일 손실 가드레일, 열린 포지션은 유지됩니다. 과거 숫자는 '전체 기록 복원'으로 다시 볼 수 있습니다. 기간과 초기화 기능은 거래소 카드가 아니라 거래 통계 탭에만 있습니다."
        )
    elif _topic(message, "웹 ui", "web ui", "새 기능", "업데이트 변경"):
        body = build_support_answer("업데이트 내용") or "설정 → 업데이트에서 설치 버전을 확인하세요."
    elif _topic(message, "검증 거래 내보내기", "paper 세부 내역", "진입 청산 사유", "smart exit 내보내기", "tp sl 내보내기"):
        body = (
            "v3.9.1.24의 '검증 거래 내보내기'는 선택한 전략 key/version의 계정 로컬 PAPER 청산만 JSON으로 저장합니다. "
            "종목, LONG/SHORT, 진입·청산 시각과 가격, 보유시간, 수량·Notional·레버리지, gross/net PnL, 수수료·슬리피지·세금, 진입·청산 사유, 진입 국면·신호 출처·수량 목표/최종값과 제한 사유, 실제 적용 TP/SL과 Smart Exit 근거를 기록된 범위에서 포함합니다. "
            "예전 버전이 저장하지 않은 항목은 0으로 추정하지 않고 기록 없음으로 남습니다.\n"
            "이 파일은 전략 개선과 오류 분석을 위한 개인 근거입니다. API 키, 잔고, 거래소 주문 ID, 전략 원문 파일, AI 내부 추론은 제외하며 .noahstrategy에 합치거나 daltrading으로 자동 업로드하지 않습니다. "
            "허브 증거 등급은 로컬 파일을 자체 신고한 것이 아니라 서버가 확인할 수 있는 서명된 집계·체결 근거로만 올라갑니다."
        )
    elif _topic(message, "paper 일시정지", "paper 중지", "paper 재개", "검증 재시작", "검증 근거 없어", "검증 기록 없어", "검증일수", "미통과 초기화", "v1 v2", "버전 초기화"):
        body = (
            "v3.9.1.23에서 Strategy Studio의 PAPER 중지는 삭제나 미통과가 아니라 일시정지입니다. 현재 전략 key/version, 거래소별 가상 청산 근거와 누적 활성 검증시간을 보존하고, 'PAPER 검증 재개'를 누르면 같은 검증 시도를 이어갑니다. 일시정지 중 흐른 시간과 정지 뒤 새로 열린 가상 포지션은 7일 관찰에 포함하지 않습니다.\n"
            "v3.9.1.24에서는 같은 전략의 v1이 검증 중일 때 v2를 시작해 v1 권한과 근거가 조용히 교체되는 경로를 차단합니다. 먼저 v1을 PAPER 일시정지한 뒤 v2를 시작해야 하며, v1의 attempt ID·거래·손익·활성 검증일수는 보존됩니다.\n"
            "최소 거래 수 또는 7일을 아직 채우지 못한 상태는 `in_progress`이며 실패가 아닙니다. '새 검증 시작'은 재개와 다른 명시적 작업으로, 같은 버튼을 두 번 확인한 경우에만 현재 시도를 이전 attempt 이력으로 보관하고 0일부터 시작합니다. 이전 원장과 여권 근거는 삭제하지 않습니다. v3.9.1.22 이하 중지 저장본도 시작·중지 시각과 진행 근거가 있으면 재개 가능한 상태로 비파괴 복구합니다.\n"
            "단, v3.9.1.22에서 이미 새 검증을 시작한 뒤 내보낸 패키지에 이전 이력이 포함되지 않았다면 그 패키지 파일만으로 과거 근거를 복원할 수는 없습니다. 원래 사용자 데이터 폴더의 전략 저장본과 PAPER 원장이 남아 있어야 화면에서 복구할 수 있습니다."
        )
    elif _topic(message, "paper 검증 거래", "paper 검증 안", "전략 때문에 거래", "no_strategy_matched", "실행 규칙 미구조화"):
        body = (
            "PAPER 전진검증 후보는 최종 적용 전략이 아니라 새 버전의 가상 성과를 모으는 관찰 대상입니다. 후보가 현재 종목·국면·진입조건에 맞지 않으면 그 후보만 표본을 만들지 않고 기본 NoahAI 후보 판단은 계속합니다. 반대로 사용자가 최종 적용한 전략은 그 조건이 운용 계약이므로 조건 미충족 시 신규 진입을 차단할 수 있습니다.\n"
            "독립 전략은 LONG 또는 SHORT 방향, 실행 가능한 선언형 진입조건, 단위가 명확한 TP/SL이 모두 있어야 PAPER 전진검증을 시작할 수 있습니다. 자연어 원문이 저장되고 IR 무결성이 정상이어도 실행 노드가 비어 있으면 아직 실행 가능한 전략은 아닙니다. 화면의 ‘PAPER 실행 규칙 미구조화’를 확인하고 LONG/SHORT 버전과 진입조건을 구조화해 새 버전으로 검증하세요.\n"
            "v3.9.1.17 이전에 등록된 미구조화 PAPER 후보는 기록을 삭제하지 않지만 기본 NoahAI 거래를 막지 않으며, 해당 후보의 검증 수치는 증가하지 않습니다."
        )
    elif _topic(message, "백테스트", "pnl", "mdd", "월별", "연별", "수익률", "과최적화"):
        body = (
            "백테스트는 미래 수익 예측이나 수익 보장이 아니라 전략 규칙·비용·손실 구조를 살피는 선택적 과거 시뮬레이션입니다. 백테스트 합격은 PAPER 시작의 필수조건이 아닙니다. "
            "총 PnL·총 수익률·MDD·승률·Profit Factor와 월별·연별 표를 확인하되, 표본 부족·PnL 음수·과도한 MDD는 실패 이유로 표시합니다. v3.9.1.19 Strategy Studio의 저장 버전에서 검증 근거를 펼치면 OOS·워크포워드·과최적화 필터, 거래소/기준통화별 PAPER 결과와 실제 검증 대상 유형을 함께 확인할 수 있습니다.\n"
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
    elif _topic(message, "패키지", "noahstrategy", "내보내기", "가져오기", "공유", "여권", "전략 허브", "제출", "업로드", "랭킹", "다운로드", "어디 저장"):
        body = (
            ".noahstrategy는 전략 규칙·IR·전략 여권을 공유하는 로컬 패키지입니다. API 키·계좌·잔고·개인 거래·절대경로·승인/활성 상태는 제외합니다. "
            "v3.9.1.19부터 서버가 만든 JSON을 그대로 저장하며, 가져올 때 IR과 전체 SHA-256·선택형 서명을 확인합니다. 일부 구형 브라우저 파일도 두 해시가 모두 재현될 때만 복구합니다. 항상 비활성 검토 상태로 열리므로 다시 검토·승인·검증해야 합니다.\n"
            "전략 여권의 검증 대상을 확인하세요. 원문 구조화 논리와 NoahAI 기본 진입+사용자 위험·청산값은 같은 성과 유형이 아니며 랭킹에서도 분리해야 합니다.\n"
            "NoahAI는 세계 최초의 전략 검증 여권 생태계를 구축합니다. 여기서 최초의 범주는 백테스트 한 기능이 아니라 TradingView·Pine·문서 원문에서 제한형 실행 규칙, 미해석 조건 차단, 거래소별 PAPER·확인 체결의 정확한 버전 귀속, 다운로드 사용자의 재검증까지 이어지는 전체 생명주기입니다.\n"
            "실제 투자 시드가 없어도 전략을 만들고 PAPER에서 시장 데이터 기반 가상 체결로 시험해 공유할 수 있습니다. 다만 PAPER는 거래소 확인 체결이나 미래 수익 보증이 아닙니다.\n"
            "검증 여권은 수익 보증서가 아니며 모든 전략 지원, 사기 불가능, 미래 수익 보장으로 설명하면 안 됩니다. 현재 공개 v3.9.1.25, v3.9.1.26 소스 후보, 무료 허브, 향후 Noah Point·제작자 정산을 구분해 안내해야 합니다.\n"
            "회원 제출은 자동이 아닙니다. AI 커스텀의 내 프라이빗 전략 버전에서 공개할 버전을 ‘패키지 내보내기’한 뒤 ‘내 전략 제출’ 또는 ‘허브에 제출’을 눌러 daltrading에 로그인하고, 파일·권리 근거·공개 설명을 직접 확인해 제출합니다. "
            "내보낸 파일은 운영체제 다운로드 위치에 있고, 제출 원본은 서버 생성 ID로 권한 제한 저장소에 보관하며 DB에는 소유 회원·패키지/IR 해시·권리 선언·증거 단계·신고·감사·다운로드 기록을 둡니다. 권리 자기선언과 패키지·IR 실행 구조 검사를 통과하면 운영자 사전승인 없이 E0로 공개되지만, E0는 성과 검증이나 권리 검토 완료를 뜻하지 않습니다.\n"
            "전략 허브는 파일의 자기신고 승률·수익률을 랭킹에 쓰지 않습니다. E0는 검증 랭킹에서 분리해 순위나 0.0점을 표시하지 않으며, 서버 서명·계정 연동·거래소 확인 근거만 미사용 구간·워크포워드·비용 스트레스·MDD·PAPER·확인 체결·가드레일·설명 품질의 E2~E5 증거로 승격합니다. 복수의 독립 권리·무결성 신고는 공개 격리하고 운영자가 최종 판정합니다. "
            "이 구조도 미래 수익이나 조작 불가능을 보장하지 않으므로 다운로드 사용자는 검증 여권을 확인하고 자신의 NoahAI에서 PAPER를 다시 수행해야 합니다.\n"
            "현재는 무료 공개 베타이며 결제·전략 판매·제작자 정산은 제공하지 않습니다. 제작자 프로필·팀 공유·서버 서명 이후 약관·환불·결제·세금·정산 E2E가 준비된 경우에만 유료 구독·검증·B2B 배포를 검토합니다. 블록체인은 전략 원문이 아니라 해시·버전·공개·철회 상태의 선택적 증명 단계로 뒤에 검토합니다."
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
            "Level 1은 초보자용 요약·근거·누락, Level 2는 핵심 파라미터와 위험·국면, Level 3은 전체 IR·그래프·안전 DSL, Level 4는 같은 IR의 전문가 운용 정책, Level 5는 연구·분석 깊이입니다. "
            "Level 4는 안정형·표준형·적극형 3단계로 거래당 위험예산, 최대 비중, 레버리지 상한과 국면 이탈 대응을 조절하지만 사용자 승인·LIVE 명시 허용·일일 손실 중단·주문 규격·TP/SL·중복 주문·긴급 정지를 해제하지 못합니다. "
            "다섯 단계는 같은 전략 ID·버전·IR을 사용하며 모호함은 사용자 확인 필요, 미지원은 차단으로 남깁니다. Level 5도 새로운 거래 권한이나 위험예산을 부여하지 않습니다."
        )
    else:
        body = (
            "AI 커스텀은 자연어·Pine·PDF·이미지·영상·TradingView 자료를 원본 근거가 연결된 제한형 전략 IR로 만들고, "
            "모호함·미지원 조건을 차단한 뒤 국면·위험·주문·체결까지 같은 버전으로 관리하는 AI 전략 운영체제입니다.\n"
            "저장과 실행은 다릅니다. 전략 버전 저장 → 사용자 승인 → 선택적 과거재생 → PAPER 전진검증 → 적용 자격 확인·사용자 최종 적용 → 제한 LIVE 순서이며 각 단계의 안전 검사를 유지합니다."
        )

    extras = []
    if safe_flow and _topic(message, "사용법", "순서", "시작", "적용", "실행", "live", "paper"):
        extras.append("안전 사용 순서:\n" + safe_flow)
    if provider_guide and _topic(message, "provider", "모델", "openai", "deepseek", "claude", "gemini", "kimi", "api"):
        extras.append("AI Provider별 연결 범위:\n" + provider_guide)
    return header + body + (("\n\n" + "\n\n".join(extras)) if extras else "")
