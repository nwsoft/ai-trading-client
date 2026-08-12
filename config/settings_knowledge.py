#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 어시스턴트가 현행 설정을 비밀값 없이 설명하기 위한 정본 검색."""

from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Tuple


SETTINGS_TABS: Dict[str, Dict[str, Any]] = {
    "일반": {
        "aliases": ("일반", "페이퍼", "learning", "paper", "live", "최상단", "포지션 모드"),
        "summary": "LEARNING·PAPER·LIVE 의미, 페이퍼 우선권, 동시 포지션 수와 대시보드 최상단 표시를 정합니다.",
    },
    "거래소 선택": {
        "aliases": ("거래소 선택", "실제 주문", "관찰", "학습 거래소", "다중 거래소", "증권사 선택"),
        "summary": "위쪽은 화면·시세·분석·학습 범위, 아래쪽은 신규 LIVE 주문 권한입니다. 다중 대상은 각각 실행·총위험 분할·우선순위 한 곳 중 선택합니다.",
    },
    "거래소 API": {
        "aliases": ("거래소 api", "api 키", "허용 ip", "passphrase", "증권 api", "계좌 연결"),
        "summary": "실잔고·비공개 포지션·실주문 연결을 설정합니다. 키가 입력돼도 조회/주문 권한과 허용 IP가 맞아야 합니다.",
    },
    "AI 엔진/API": {
        "aliases": ("ai 엔진", "provider", "모델", "openai", "deepseek", "claude", "gemini", "kimi", "kimi k3", "전사", "캐시", "비용", "호출예산", "ai 커스텀", "ai커스텀", "사용 난이도", "웹훅", "webhook"),
        "summary": "분석·대화·빈번/표준/정밀 역할별 Provider와 모델을 정합니다. Kimi K3는 Kimi Open Platform API 키와 계정 모델 권한을 확인해야 하며 일반 Kimi 서비스의 멤버십·잔액과 API 과금은 별도입니다. AI 커스텀 사용 난이도는 전략 엔진이 아니라 화면 복잡도·기능 노출 프로필이며 처음에는 일반(권장)을 사용합니다.",
    },
    "고급 매매 계층": {
        "aliases": ("고급 매매", "전략 엔진", "합의 임계값", "쿨다운", "고변동", "수익성 검증"),
        "summary": "표준 자동매매의 후보 뒤에서 수익성·포트폴리오·국면/합의·슬리피지·운영 상태를 검사하는 5개 후행 계층입니다. 처음에는 safe와 PAPER 7~14일 관찰을 권장합니다.",
    },
    "AlphaArena": {
        "aliases": ("alphaarena", "alpha arena", "알파아레나"),
        "summary": "기본 OFF인 숙련자용 Binance USDT 선물 LLM 실험 실행 체계입니다. 표준 고급 계층·보험·워치독과 분리되며 현재 선택 가능한 실행 엔진은 DeepSeek V4 Flash입니다.",
    },
    "AI 시스템 상태": {
        "aliases": ("ai 시스템 상태", "자동 최적화", "시장 국면 자동", "기본값 되돌리기"),
        "summary": "AI 자동 관리·시장 국면 보정 상태를 확인하고 설정 꼬임을 진단·복원하는 화면입니다.",
    },
    "업데이트": {
        "aliases": ("업데이트", "자동 다운로드", "종료 시 적용", "업데이트 주기", "복구"),
        "summary": "버전 확인·다운로드·종료 시 적용과 열린 포지션 처리 정책을 관리합니다. 안전검사가 실패하면 적용을 연기합니다.",
    },
}


def _project_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(str(bundled))
    return Path(__file__).resolve().parents[1]


def _query_tokens(query: str) -> List[str]:
    tokens = re.findall(r"[0-9a-zA-Z가-힣_./+-]{2,}", str(query or "").lower())
    stop = {"설정", "무엇", "뭐야", "어떻게", "알려줘", "설명", "하는데", "인가요", "있나요"}
    return [token for token in tokens if token not in stop]


def _reference_sections() -> List[Tuple[str, str]]:
    text = ""
    for filename in ("SETTINGS_REFERENCE_v3.9.0.8.md", "SETTINGS_REFERENCE_v3.9.0.5.md"):
        path = _project_root() / "docs" / filename
        try:
            text = path.read_text(encoding="utf-8")
            break
        except Exception:
            continue
    if not text:
        return []
    sections: List[Tuple[str, str]] = []
    title = "설정 정본"
    body: List[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if body:
                sections.append((title, "\n".join(body).strip()))
            title = line.lstrip("#").strip()
            body = []
        elif line.startswith("### "):
            body.append(line.lstrip("#").strip())
        else:
            body.append(line)
    if body:
        sections.append((title, "\n".join(body).strip()))
    return sections


def _safe_current_summary(settings: Dict[str, Any]) -> str:
    enabled = list(settings.get("enabled_exchanges", []) or [])
    live = list(settings.get("trade_enabled_exchanges", []) or [])
    multi = dict(settings.get("multi_venue_execution", {}) or {})
    ai_runtime = dict(settings.get("ai_custom_runtime", {}) or {})
    ai_features = dict(settings.get("ai_custom_features", {}) or {})
    advanced = dict(settings.get("advanced_trading_layers", {}) or {})
    strategy = dict(advanced.get("strategy_engine", {}) or {})
    alpha_arena = dict(settings.get("alpha_arena", {}) or {})
    stock = dict(settings.get("stock_auto_trading", {}) or {})
    ui_settings = dict(settings.get("ui_settings", {}) or {})
    lines = [
        f"- 현재 모드: {'PAPER' if settings.get('paper_trading') else ('LIVE/LEARNING 혼합' if live else 'LEARNING')}",
        f"- 관찰·분석 거래소: {', '.join(enabled) if enabled else '없음'}",
        f"- 실제 주문 거래소: {', '.join(live) if live else '없음'}",
        f"- 다중 실행 방식: {multi.get('mode', 'parallel')}",
        f"- 최대 동시 포지션: {settings.get('max_positions', 3)}",
        f"- 대시보드 최상단: {'ON' if ui_settings.get('always_on_top') else 'OFF'}",
        f"- AI 커스텀 런타임: {'ON' if ai_runtime.get('enabled') else 'OFF'}",
        f"- AI 커스텀 사용 난이도: {ai_features.get('profile', 'standard')}",
        f"- 고변동장 처리/합의/쿨다운: {strategy.get('high_vol_action', 'evaluate')} / {strategy.get('consensus_threshold', 0.60)} / {strategy.get('cooldown_sec', 60)}초",
        f"- 고급 매매 5계층: " + ", ".join(
            f"{key}={'ON' if dict(advanced.get(key, {}) or {}).get('enabled') else 'OFF'}"
            for key in ("profitability_validation", "portfolio_orchestration", "strategy_engine", "execution_optimizer", "ops_automation")
        ),
        f"- AlphaArena: {'ON' if alpha_arena.get('enabled') else 'OFF'} / {alpha_arena.get('exchange', 'binance-futures')} / {alpha_arena.get('engine', 'deepseek-v4-flash')}",
        f"- 증권 자동 시작/실주문: {'ON' if stock.get('auto_start') else 'OFF'} / {'ON' if settings.get('enable_stock_live_order') else 'OFF'}",
    ]
    return "\n".join(lines)


def build_settings_knowledge(query: str, settings: Dict[str, Any]) -> str:
    """질문과 관련된 설정 탭·정본 설명·현재 비밀값 없는 상태를 반환한다."""
    lower = str(query or "").lower()
    matched_tabs = [
        (name, item)
        for name, item in SETTINGS_TABS.items()
        if any(alias in lower for alias in item["aliases"])
    ]
    settings_topic = bool(
        matched_tabs
        or any(token in lower for token in ("설정", "환경설정", "옵션", "모드", "가드레일"))
    )
    if not settings_topic:
        return ""

    if not matched_tabs:
        tab_lines = [
            f"- {name}: {item['summary']}"
            for name, item in SETTINGS_TABS.items()
        ]
    else:
        tab_lines = [
            f"- {name}: {item['summary']}"
            for name, item in matched_tabs[:3]
        ]

    tokens = _query_tokens(query)
    scored: List[Tuple[int, str, str]] = []
    for title, body in _reference_sections():
        haystack = f"{title}\n{body}".lower()
        score = sum(3 if token in title.lower() else 1 for token in tokens if token in haystack)
        if score > 0:
            scored.append((score, title, body))
    scored.sort(key=lambda row: row[0], reverse=True)

    excerpts: List[str] = []
    for _, title, body in scored[:2]:
        compact = "\n".join(
            line for line in body.splitlines()
            if line.strip() and not line.strip().startswith("```")
        )
        excerpts.append(f"[{title}]\n{compact[:900]}")

    parts = [
        "[설정 화면 안내]",
        "\n".join(tab_lines),
        "[현재 설정 요약 - API 키 값 제외]",
        _safe_current_summary(settings if isinstance(settings, dict) else {}),
    ]
    if excerpts:
        parts.extend(["[v3.9.0.8 설정 정본 관련 내용]", "\n\n".join(excerpts)])
    parts.append(
        "설명과 설정 변경은 다릅니다. AI는 설명할 수 있지만 값 변경은 허용 키 검증과 사용자 최종 확인 후에만 저장합니다."
    )
    return "\n".join(parts)
