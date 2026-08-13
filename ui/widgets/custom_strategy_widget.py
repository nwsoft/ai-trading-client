#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 커스텀 전략 입력·분석·버전 저장 UI."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from trading.ai.openai_client import OpenAIClient
from ui.ai_custom_guidance import (
    AI_CUSTOM_CONFIRM_ROLE_HELP,
    AI_CUSTOM_CONFIRM_ROLE_LABEL,
    AI_CUSTOM_INDEPENDENT_ROLE_HELP,
    AI_CUSTOM_INDEPENDENT_ROLE_LABEL,
    AI_CUSTOM_RULE_EDITOR_TITLE,
    AI_CUSTOM_SAFE_STEPS,
    AI_CUSTOM_SETTINGS_PATH,
    build_ai_custom_safe_flow_compact,
)
from trading.custom_strategy_presets import (
    get_beginner_preset,
    list_beginner_presets,
)
from trading.custom_strategy_mentor import recommend_strategy_candidates
from trading.noah_strategy_ir import NoahStrategyIR
from trading.strategy_source_ingestor import StrategySourceIngestor
from trading.ai_custom_features import resolve_ai_custom_features


class CustomStrategyWidget(ctk.CTkScrollableFrame):
    BEGINNER_PRESET_LABELS = {
        item["name"]: item["key"] for item in list_beginner_presets()
    }
    SOURCE_LABELS = {
        "자동 판별": "auto",
        "텍스트/메모": "text",
        "Pine Script": "pine",
        "PDF 문서": "pdf",
        "차트 이미지/OCR": "image",
        "로컬 영상": "video",
        "YouTube 링크": "youtube",
        "TradingView 링크": "tradingview",
    }
    SCOPE_LABELS = {
        "Binance만": "exchange:binance", "Bybit만": "exchange:bybit",
        "OKX만": "exchange:okx", "Bitget만": "exchange:bitget",
        "Upbit만": "exchange:upbit", "Bithumb만": "exchange:bithumb",
        "모든 블록체인": "asset:crypto", "모든 주식/ETF": "asset:stock",
        "모든 자산": "asset:all", "키움증권만": "broker:kiwoom",
        "신한증권만": "broker:shinhan", "미래에셋만": "broker:miraeasset",
        "한국투자증권만": "broker:koreainvestment",
    }
    REGIME_LABELS = {
        "모든 시장상황": ["all"], "상승장": ["bull", "trend"],
        "하락장": ["bear"], "횡보장": ["range"],
        "고변동성": ["volatile"], "저변동성": ["calm"],
    }
    REGIME_SCOPE_LABELS = {
        "전체 시장 기준 (권장)": "market",
        "종목별 국면 기준": "symbol",
        "전체 시장 + 종목 모두": "both",
        "국면으로 제한하지 않음": "none",
    }

    def __init__(self, master, *, dashboard=None, settings: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(master, fg_color="#0b1120", corner_radius=0, **kwargs)
        self.dashboard = dashboard
        self.settings = settings or {}
        self.feature_state = resolve_ai_custom_features(self._runtime_settings())
        self.analysis_result: Optional[Dict[str, Any]] = None
        self.strategy_view_level = int(self.feature_state.get("view_level", 1))
        self.version_target_map: Dict[str, Any] = {}
        self._regime_value_map: Dict[str, Any] = dict(self.REGIME_LABELS)
        self._build()
        self._set_strategy_view_level(self.strategy_view_level)
        self.refresh_versions()

    def _font(self, size: int, weight: str = "normal"):
        return ctk.CTkFont(size=size, weight=weight)

    def _runtime_settings(self) -> Dict[str, Any]:
        dashboard_settings = getattr(self.dashboard, "settings", None)
        return dashboard_settings if isinstance(dashboard_settings, dict) else self.settings

    def _feature_enabled(self, key: str) -> bool:
        self.feature_state = resolve_ai_custom_features(self._runtime_settings())
        return bool((self.feature_state.get("features") or {}).get(key, False))

    def _selected_ai_model(self) -> str:
        settings = self._runtime_settings()
        roles = settings.get("ai_model_roles", {}) or {}
        premium = roles.get("premium") if isinstance(roles, dict) else None
        if isinstance(premium, dict):
            return str(premium.get("model") or settings.get("openai_model") or "gpt-5.6-terra")
        return str(premium or settings.get("openai_model") or "gpt-5.6-terra")

    def _selected_ai_provider(self) -> str:
        settings = self._runtime_settings()
        roles = settings.get("ai_model_roles", {}) or {}
        premium = roles.get("premium") if isinstance(roles, dict) else None
        if isinstance(premium, dict):
            return str(premium.get("provider") or settings.get("ai_provider") or "openai")
        return str(settings.get("ai_provider") or "openai")

    def _ai_api_ready(self) -> bool:
        """AI 커스텀 정밀 역할의 실제 Provider 자격증명 상태를 확인한다."""
        try:
            from trading.ai.provider_router import AIProviderRouter

            return AIProviderRouter.from_settings(
                self._runtime_settings(),
                workload="premium",
            ).client_facade().is_ready()
        except Exception:
            return bool(str(os.getenv("OPENAI_API_KEY", "") or "").strip())

    def _open_ai_settings(self):
        opener = getattr(self.dashboard, "show_settings_dialog", None)
        if callable(opener):
            opener()
        else:
            messagebox.showinfo(
                "AI 모델 설정",
                f"대시보드 상단 {AI_CUSTOM_SETTINGS_PATH} → 정밀 진단·최적화(고성능 모델)에서 설정하세요.",
            )

    def _refresh_ai_model_status(self) -> None:
        if not hasattr(self, "ai_model_status"):
            return
        api_ready = self._ai_api_ready()
        self.ai_model_status.configure(
            text=(
                f"사용 AI: {self._selected_ai_provider()} / {self._selected_ai_model()} · 정밀 분석 역할"
                if api_ready else "정밀 분석 역할 API 미설정 · 규칙 기반 1차 추출만 가능"
            ),
            text_color=("#38bdf8" if api_ready else "#f59e0b"),
        )

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        header.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(header, text="AI 커스텀 전략 센터", font=self._font(22, "bold"), text_color="#f8fafc").pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            header,
            text=(
                "TradingView·Pine·기존 전략의 익숙한 표현은 유지하고, 원문 근거·검증·PAPER·체결 감사를 더하는 "
                "AI 전략 운영체제입니다. 배우기 → 만들기 → 검증 → 실행 → 개선 흐름을 연결하며, "
                "전략이 바뀌면 다시 입력해 새 버전으로 분석·적용할 수 있습니다."
            ),
            font=self._font(13), text_color="#a9bad0", justify="left", wraplength=1120,
        ).pack(anchor="w", padx=18, pady=(0, 14))

        ai_status_row = ctk.CTkFrame(header, fg_color="#0b1120", corner_radius=10)
        ai_status_row.pack(fill="x", padx=18, pady=(0, 12))
        api_ready = self._ai_api_ready()
        self.ai_model_status = ctk.CTkLabel(
            ai_status_row,
            text=(
                f"사용 AI: {self._selected_ai_provider()} / {self._selected_ai_model()} · 정밀 분석 역할"
                if api_ready else
                f"{self._selected_ai_provider()} 정밀 분석 API 미설정 · 규칙 기반 1차 추출만 가능"
            ),
            font=self._font(12, "bold"), text_color=("#38bdf8" if api_ready else "#f59e0b"),
        )
        self.ai_model_status.pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            ai_status_row,
            text=f"사용 모드: {self.feature_state.get('profile_label', '일반')}",
            font=self._font(11, "bold"), text_color="#a78bfa",
        ).pack(side="left", padx=8)
        ctk.CTkLabel(
            ai_status_row,
            text=f"설정 경로: {AI_CUSTOM_SETTINGS_PATH} → 정밀 진단·최적화",
            font=self._font(11), text_color="#91a4bd",
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            ai_status_row, text="AI 모델 설정 열기", width=130, height=30,
            command=self._open_ai_settings,
        ).pack(side="right", padx=8, pady=6)
        ctk.CTkButton(
            ai_status_row, text="처음 사용법 AI에게 묻기", width=170, height=30,
            fg_color="#0f766e", hover_color="#0d9488",
            command=lambda: self._ask_assistant("getting_started"),
        ).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(
            ai_status_row, text="AI 멘토 인터뷰", width=145, height=30,
            fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._start_mentor_interview,
        ).pack(side="right", padx=4, pady=6)

        guide_card = ctk.CTkFrame(header, fg_color="#111c31", corner_radius=10)
        guide_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(
            guide_card,
            text="두 도움 기능의 차이",
            font=self._font(12, "bold"), text_color="#f8fafc",
        ).pack(anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(
            guide_card,
            text=(
                "AI 멘토 인터뷰: 투자 경험·목표·위험 허용도 등 8문항을 묻고 개인화된 교육용 전략 후보 2~3개를 만듭니다. 자동 저장·승인하지 않습니다.\n"
                "처음 사용법 AI에게 묻기: 현재 화면과 프로필을 기준으로 입력 → XAI 검토 → 저장 → 승인 → 자동검증 → PAPER 순서를 안내합니다. 전략 후보를 만들지는 않습니다."
            ),
            font=self._font(11), text_color="#b8c7dc", justify="left", wraplength=1060,
        ).pack(fill="x", padx=12, pady=(0, 10))

        badges = ctk.CTkFrame(header, fg_color="transparent")
        badges.pack(fill="x", padx=14, pady=(0, 14))
        for title, value, color in (
            ("승인 없는 실행", "차단", "#ef4444"),
            ("전략 버전", "최대 10개", "#a78bfa"),
            ("가드레일", "항상 우선", "#22c55e"),
            ("출금 API", "지원 안 함", "#f59e0b"),
        ):
            card = ctk.CTkFrame(badges, fg_color="#172033", corner_radius=10)
            card.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(card, text=title, font=self._font(11), text_color="#91a4bd").pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=value, font=self._font(13, "bold"), text_color=color).pack(anchor="w", padx=10, pady=(0, 8))

        feature_card = ctk.CTkFrame(header, fg_color="#0b1120", corner_radius=10)
        feature_card.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(
            feature_card,
            text=f"AI 커스텀 기능 위치 · 현재 {self.feature_state.get('profile_label', '일반')} / Level {self.feature_state.get('view_level', 2)}",
            font=self._font(12, "bold"), text_color="#a78bfa",
        ).pack(anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(
            feature_card,
            text=(
                "• 원문 근거·누락·모호함·지원 여부: 자료 분석 후 XAI 결과 카드\n"
                "• PnL·MDD·월별/연별 표·과최적화 경고: 저장 버전 자동검증이 끝난 뒤 검증 결과 카드\n"
                "• 전략 패키지: 저장 버전의 내보내기/가져오기 · Expression Graph/사용자 지표 언어: 설정에서 고급 프로필을 선택했을 때 노출\n"
                "기능이 보이지 않으면 고장이 아니라 현재 프로필, 분석 전 상태, 또는 검증 전 상태인지 먼저 확인하세요."
            ),
            font=self._font(11), text_color="#cbd5e1", justify="left", wraplength=1060,
        ).pack(fill="x", padx=12, pady=(0, 10))

        safe_flow = ctk.CTkFrame(header, fg_color="#0b1120", corner_radius=10)
        safe_flow.pack(fill="x", padx=18, pady=(0, 14))
        safe_flow_text = ctk.CTkFrame(safe_flow, fg_color="transparent")
        safe_flow_text.pack(side="left", fill="x", expand=True, padx=12, pady=9)
        ctk.CTkLabel(
            safe_flow_text,
            text="안전 사용 순서",
            font=self._font(12, "bold"),
            text_color="#38bdf8",
        ).pack(anchor="w")
        ctk.CTkLabel(
            safe_flow_text,
            text=build_ai_custom_safe_flow_compact(),
            font=self._font(11),
            text_color="#cbd5e1",
            justify="left",
            wraplength=980,
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(
            safe_flow,
            text="12단계 자세히",
            width=120,
            height=32,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
            command=self._show_safe_use_flow,
        ).pack(side="right", padx=10, pady=10)

        preset_card = ctk.CTkFrame(
            self, fg_color="#111827", corner_radius=16,
            border_width=1, border_color="#273449",
        )
        preset_card.pack(fill="x", padx=14, pady=8)
        preset_top = ctk.CTkFrame(preset_card, fg_color="transparent")
        preset_top.pack(fill="x", padx=16, pady=(13, 7))
        ctk.CTkLabel(
            preset_top,
            text="초보자 시작: AI 자동 대응 + 검토용 기본 전략 4개",
            font=self._font(16, "bold"),
            text_color="#f8fafc",
        ).pack(side="left")
        self.beginner_preset_combo = ctk.CTkComboBox(
            preset_top,
            values=list(self.BEGINNER_PRESET_LABELS),
            width=260,
            height=34,
        )
        self.beginner_preset_combo.set("AI가 시장에 맞춰 자동 대응")
        self.beginner_preset_combo.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            preset_top,
            text="선택 내용 불러오기",
            width=135,
            height=34,
            command=self.load_beginner_preset,
        ).pack(side="right", padx=8)
        ctk.CTkButton(
            preset_top,
            text="AI에게 설명 듣기",
            width=130,
            height=34,
            fg_color="#0f766e",
            hover_color="#0d9488",
            command=self._ask_selected_preset,
        ).pack(side="right")
        ctk.CTkLabel(
            preset_card,
            text=(
                "기본 선택인 AI 자동 대응은 기존 NoahAI 시장판단입니다. 나머지 4개는 편집 가능한 초안이며 "
                "성과를 보장하지 않습니다. 국면·다중 시간대·유동성·손익비가 충돌하면 HOLD가 항상 우선합니다."
            ),
            font=self._font(11),
            text_color="#a9bad0",
            justify="left",
            wraplength=1120,
        ).pack(anchor="w", padx=16, pady=(0, 13))

        source_card = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        source_card.pack(fill="x", padx=14, pady=8)
        top = ctk.CTkFrame(source_card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(top, text="1. 전략 소스 입력", font=self._font(16, "bold"), text_color="#f8fafc").pack(side="left")
        self.kind_combo = ctk.CTkComboBox(top, values=list(self.SOURCE_LABELS), width=180, height=34)
        self.kind_combo.set("자동 판별")
        self.kind_combo.pack(side="right")

        version_target_row = ctk.CTkFrame(source_card, fg_color="transparent")
        version_target_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            version_target_row, text="저장 대상", font=self._font(11), text_color="#91a4bd"
        ).pack(side="left", padx=(0, 8))
        self.version_target_combo = ctk.CTkComboBox(
            version_target_row, values=["새 전략으로 저장"], width=360, height=34
        )
        self.version_target_combo.set("새 전략으로 저장")
        self.version_target_combo.pack(side="left")
        ctk.CTkLabel(
            version_target_row, text="기존 전략을 고르면 같은 전략의 다음 버전(v2~v10)으로 저장됩니다.",
            font=self._font(11), text_color="#91a4bd",
        ).pack(side="left", padx=12)

        path_row = ctk.CTkFrame(source_card, fg_color="transparent")
        path_row.pack(fill="x", padx=16, pady=(0, 8))
        self.reference_entry = ctk.CTkEntry(
            path_row, height=38,
            placeholder_text="YouTube/TradingView URL 또는 Markdown·PDF·이미지·영상·Pine 파일 경로",
            fg_color="#0b1120", border_color="#334155",
        )
        self.reference_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(path_row, text="파일 선택", width=100, height=38, command=self._choose_file).pack(side="right")

        input_label_row = ctk.CTkFrame(source_card, fg_color="transparent")
        input_label_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            input_label_row, text="전략 설명 / Pine Script 직접 입력",
            font=self._font(12, "bold"), text_color="#e5edf6",
        ).pack(side="left")
        ctk.CTkLabel(
            input_label_row,
            text="예: RSI<30 + EMA200 상단에서 진입, 손절 1%, 익절 2%, 자산 5%",
            font=self._font(11), text_color="#91a4bd",
        ).pack(side="right")

        self.source_text = ctk.CTkTextbox(
            source_card, height=145, fg_color="#0b1120", border_width=1, border_color="#334155",
            text_color="#e5edf6", wrap="word",
        )
        self.source_text.pack(fill="x", padx=16, pady=(0, 8))
        self.source_text.insert("1.0", "전략 설명 또는 Pine Script를 붙여 넣으세요. 링크/파일을 선택한 경우 비워도 됩니다.")
        ctk.CTkLabel(
            source_card,
            text=(
                "분석 범위: PDF 앞 100쪽·AI 입력 60,000자 / YouTube watch·Shorts·공유 링크와 대표 장면 최대 9개 / "
                "무자막은 최대 45분·24MB 내 AI 음성 전사(API 사용량 발생 가능) / 보호된 TradingView는 본인 Pine 필요"
            ),
            font=self._font(10), text_color="#fbbf24", justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        action = ctk.CTkFrame(source_card, fg_color="transparent")
        action.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(action, text="적용 범위", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(0, 6))
        self.target_combo = ctk.CTkComboBox(
            action, values=list(self.SCOPE_LABELS), width=180, height=36,
        )
        self.target_combo.set("Binance만")
        self.target_combo.pack(side="left")
        ctk.CTkLabel(action, text="시장상황", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(14, 6))
        self.regime_combo = ctk.CTkComboBox(action, values=list(self.REGIME_LABELS), width=220, height=36)
        self.regime_combo.set("모든 시장상황")
        self.regime_combo.pack(side="left")
        ctk.CTkLabel(action, text="국면 기준", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(14, 6))
        self.regime_scope_combo = ctk.CTkComboBox(
            action,
            values=list(self.REGIME_SCOPE_LABELS),
            width=205,
            height=36,
        )
        self.regime_scope_combo.set("전체 시장 기준 (권장)")
        self.regime_scope_combo.pack(side="left")
        ctk.CTkLabel(action, text="우선순위", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(14, 6))
        self.priority_combo = ctk.CTkComboBox(action, values=[str(v) for v in range(10, 0, -1)], width=70, height=36)
        self.priority_combo.set("5")
        self.priority_combo.pack(side="left")

        signal_row = ctk.CTkFrame(source_card, fg_color="transparent")
        signal_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(signal_row, text="전략 역할", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(0, 6))
        self.signal_mode_combo = ctk.CTkComboBox(
            signal_row,
            values=[AI_CUSTOM_CONFIRM_ROLE_LABEL, AI_CUSTOM_INDEPENDENT_ROLE_LABEL],
            width=255,
            height=36,
            command=self._on_signal_mode_change,
        )
        self.signal_mode_combo.set(AI_CUSTOM_CONFIRM_ROLE_LABEL)
        self.signal_mode_combo.pack(side="left")
        self.entry_signal_label = ctk.CTkLabel(
            signal_row, text="진입 방향", font=self._font(11), text_color="#91a4bd",
        )
        self.entry_signal_combo = ctk.CTkComboBox(
            signal_row, values=["소스에서 자동", "LONG", "SHORT"], width=145, height=36,
        )
        self.entry_signal_combo.set("소스에서 자동")
        self.signal_mode_help_label = ctk.CTkLabel(
            signal_row,
            text=AI_CUSTOM_CONFIRM_ROLE_HELP,
            font=self._font(10), text_color="#64748b",
        )
        self.signal_mode_help_label.pack(side="left", padx=12)
        ctk.CTkLabel(
            source_card,
            text=(
                "전략 역할과 실행 안전등급은 주문 환경과 별개입니다. "
                "LEARNING은 전체 판단만 기록, PAPER는 가상 체결, LIVE는 명시 허용 범위만 실주문 후보입니다."
            ),
            font=self._font(10),
            text_color="#60a5fa",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self.strategy_universe_card = ctk.CTkFrame(
            source_card,
            fg_color="#0b1120",
            corner_radius=10,
            border_width=1,
            border_color="#334155",
        )
        universe_title = ctk.CTkFrame(self.strategy_universe_card, fg_color="transparent")
        universe_title.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            universe_title,
            text="고급 전략 종목 풀 · StrategyUniversePolicy",
            font=self._font(12, "bold"),
            text_color="#dbeafe",
        ).pack(side="left")
        ctk.CTkLabel(
            universe_title,
            text="LLM 호출 없이 거래소·증권사 제공 데이터만 사전 필터합니다.",
            font=self._font(10),
            text_color="#38bdf8",
        ).pack(side="right")

        universe_symbols = ctk.CTkFrame(self.strategy_universe_card, fg_color="transparent")
        universe_symbols.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(universe_symbols, text="항상 평가할 종목", font=self._font(10), text_color="#91a4bd").pack(side="left")
        self.universe_include_entry = ctk.CTkEntry(
            universe_symbols,
            width=290,
            height=32,
            placeholder_text="예: BTCUSDT, ETHUSDT 또는 005930",
        )
        self.universe_include_entry.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(universe_symbols, text="제외 종목", font=self._font(10), text_color="#91a4bd").pack(side="left")
        self.universe_exclude_entry = ctk.CTkEntry(
            universe_symbols,
            width=260,
            height=32,
            placeholder_text="쉼표로 구분",
        )
        self.universe_exclude_entry.pack(side="left", padx=6)

        universe_filters = ctk.CTkFrame(self.strategy_universe_card, fg_color="transparent")
        universe_filters.pack(fill="x", padx=12, pady=(4, 10))
        filter_specs = (
            ("24h 최소 거래대금", "universe_min_volume_entry", "0", 130),
            ("최대 스프레드(bp)", "universe_max_spread_entry", "30", 85),
            ("최소 변동성(%)", "universe_min_vol_entry", "0", 75),
            ("최대 변동성(%)", "universe_max_vol_entry", "100", 75),
            ("최대 후보", "universe_limit_entry", "20", 65),
        )
        for label, attr, default, width in filter_specs:
            ctk.CTkLabel(
                universe_filters, text=label, font=self._font(10), text_color="#91a4bd",
            ).pack(side="left", padx=(0 if attr == "universe_min_volume_entry" else 10, 4))
            entry = ctk.CTkEntry(universe_filters, width=width, height=30)
            entry.insert(0, default)
            entry.pack(side="left")
            setattr(self, attr, entry)
        ctk.CTkLabel(
            self.strategy_universe_card,
            text=(
                "직접 입력·코인/주식 정보에서 고정한 종목은 항상 평가하지만 강제 주문하지 않습니다. "
                "진입조건·데이터 품질·계좌·주문 안전을 모두 통과해야 합니다."
            ),
            font=self._font(10),
            text_color="#fbbf24",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        risk_row = ctk.CTkFrame(source_card, fg_color="transparent")
        self.risk_row = risk_row
        risk_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(risk_row, text="전략 위험예산", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(0, 6))
        self.risk_per_trade_combo = ctk.CTkComboBox(
            risk_row, values=["0.25", "0.5", "1.0", "2.0"], width=80, height=34,
        )
        self.risk_per_trade_combo.set("0.5")
        self.risk_per_trade_combo.pack(side="left")
        ctk.CTkLabel(risk_row, text="%/거래 · 증거금 최대", font=self._font(10), text_color="#91a4bd").pack(side="left", padx=(5, 5))
        self.max_margin_combo = ctk.CTkComboBox(
            risk_row, values=["5", "10", "20", "30"], width=75, height=34,
        )
        self.max_margin_combo.set("10")
        self.max_margin_combo.pack(side="left")
        ctk.CTkLabel(risk_row, text="% · 레버리지 상한", font=self._font(10), text_color="#91a4bd").pack(side="left", padx=(5, 5))
        self.max_leverage_combo = ctk.CTkComboBox(
            risk_row, values=["1", "2", "3", "5", "10"], width=70, height=34,
        )
        self.max_leverage_combo.set("3")
        self.max_leverage_combo.pack(side="left")
        ctk.CTkLabel(risk_row, text="국면 이탈 시", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(16, 6))
        self.transition_combo = ctk.CTkComboBox(
            risk_row, values=["기본 노아AI에 맡김", "커스텀 신규 진입 일시정지"], width=190, height=34,
        )
        self.transition_combo.set("기본 노아AI에 맡김")
        self.transition_combo.pack(side="left")
        ctk.CTkLabel(
            risk_row,
            text="실제 레버리지는 위험예산÷손절거리로 계산되며 상한을 넘지 않습니다.",
            font=self._font(10), text_color="#38bdf8",
        ).pack(side="left", padx=10)

        analyze_row = ctk.CTkFrame(source_card, fg_color="transparent")
        analyze_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(
            analyze_row, text="범위가 넓어도 거래소·증권사 데이터와 전략 성과는 서로 분리 기록됩니다.",
            font=self._font(11), text_color="#91a4bd",
        ).pack(side="left")
        self.analyze_button = ctk.CTkButton(
            analyze_row, text="AI 분석 및 전략 초안 만들기", width=220, height=38,
            fg_color="#2563eb", hover_color="#1d4ed8", command=self._start_analysis,
        )
        self.analyze_button.pack(side="right")

        advanced_card = ctk.CTkFrame(
            self, fg_color="#111827", corner_radius=16,
            border_width=1, border_color="#273449",
        )
        advanced_card.pack(fill="x", padx=14, pady=8)
        self.advanced_card = advanced_card
        advanced_header = ctk.CTkFrame(advanced_card, fg_color="transparent")
        advanced_header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(
            advanced_header,
            text=AI_CUSTOM_RULE_EDITOR_TITLE,
            font=self._font(16, "bold"),
            text_color="#f8fafc",
        ).pack(side="left")
        ctk.CTkButton(
            advanced_header, text="예제 넣기", width=90, height=30,
            command=self._insert_advanced_template,
        ).pack(side="right")
        ctk.CTkButton(
            advanced_header, text="그래프·지표 예제", width=125, height=30,
            state="normal" if self._feature_enabled("expression_graph") and self._feature_enabled("user_indicator_language") else "disabled",
            command=self._insert_expression_graph_template,
        ).pack(side="right", padx=8)
        ctk.CTkButton(
            advanced_header, text="AI 추출값 불러오기", width=145, height=30,
            fg_color="#0f766e", hover_color="#0d9488",
            command=self._load_extracted_rules_to_advanced,
        ).pack(side="right", padx=8)
        ctk.CTkLabel(
            advanced_card,
            text=(
                "EMA·SMA·RSI·ATR·거래량 평균, 중첩 AND/OR Expression Graph, 제한형 사용자 지표 수식을 "
                "JSON 그래프로 편집합니다. 임의 Python/Pine 코드는 실행하지 않습니다."
            ),
            font=self._font(11), text_color="#a9bad0", justify="left", wraplength=1120,
        ).pack(anchor="w", padx=16, pady=(0, 8))
        self.advanced_rules_text = ctk.CTkTextbox(
            advanced_card, height=190, fg_color="#0b1120",
            border_width=1, border_color="#334155",
            text_color="#dbeafe", wrap="none",
        )
        self.advanced_rules_text.pack(fill="x", padx=16, pady=(0, 8))
        self.advanced_rules_text.insert(
            "1.0",
            "선택 사항입니다. ‘예제 넣기’ 또는 ‘AI 추출값 불러오기’를 사용하세요.",
        )
        advanced_actions = ctk.CTkFrame(advanced_card, fg_color="transparent")
        advanced_actions.pack(fill="x", padx=16, pady=(0, 14))
        self.advanced_validation_label = ctk.CTkLabel(
            advanced_actions,
            text="고급 규칙 미사용",
            font=self._font(11), text_color="#94a3b8",
        )
        self.advanced_validation_label.pack(side="left")
        ctk.CTkButton(
            advanced_actions, text="규칙 안전성 검사", width=145, height=32,
            command=lambda: self._validate_advanced_editor(show_dialog=True),
        ).pack(side="right")

        result_card = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        result_card.pack(fill="x", padx=14, pady=8)
        self.result_card = result_card
        result_header = ctk.CTkFrame(result_card, fg_color="transparent")
        result_header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(result_header, text="2. XAI 분석 결과와 적용값", font=self._font(16, "bold"), text_color="#f8fafc").pack(side="left")
        self.strategy_view_combo = ctk.CTkComboBox(
            result_header,
            values=["Level 1 이해·시험", "Level 2 핵심값", "Level 3 전체 IR"],
            width=155,
            height=30,
            state="readonly",
            command=self._on_strategy_view_changed,
        )
        self.strategy_view_combo.set("Level 1 이해·시험")
        self.strategy_view_combo.set(
            "Level 3 전체 IR" if self.strategy_view_level == 3
            else "Level 2 핵심값" if self.strategy_view_level == 2
            else "Level 1 이해·시험"
        )
        self.strategy_view_combo.pack(side="left", padx=12)
        self.result_status = ctk.CTkLabel(result_header, text="분석 전", font=self._font(12), text_color="#94a3b8")
        self.result_status.pack(side="right")
        ctk.CTkButton(
            result_header, text="이 결과 AI에게 묻기", width=145, height=30,
            fg_color="#0f766e", hover_color="#0d9488",
            command=lambda: self._ask_assistant("analysis_result"),
        ).pack(side="right", padx=10)
        self.result_text = ctk.CTkTextbox(result_card, height=250, fg_color="#0b1120", border_width=1, border_color="#334155", text_color="#e5edf6", wrap="word")
        self.result_text.pack(fill="x", padx=16, pady=(0, 8))
        self.result_text.insert("1.0", "분석 결과에는 출처 근거, 명시된 조건, 누락 조건, 위험, 엔진 설정값이 표시됩니다.")
        self.result_text.configure(state="disabled")
        save_row = ctk.CTkFrame(result_card, fg_color="transparent")
        save_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(
            save_row, text="저장 후에도 즉시 실행되지 않으며 사용자 승인과 실행 검증을 거칩니다.",
            font=self._font(11), text_color="#fbbf24",
        ).pack(side="left")
        self.save_button = ctk.CTkButton(
            save_row, text="검토 및 전략 버전 저장", width=205, height=38,
            state="disabled", command=self._save_version,
        )
        self.save_button.pack(side="right")

        self.versions_card = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        self.versions_card.pack(fill="x", padx=14, pady=(8, 16))
        title_row = ctk.CTkFrame(self.versions_card, fg_color="transparent")
        title_row.pack(fill="x", padx=16, pady=(13, 7))
        ctk.CTkLabel(title_row, text="3. 내 프라이빗 전략 버전", font=self._font(16, "bold"), text_color="#f8fafc").pack(side="left")
        ctk.CTkButton(title_row, text="새로고침", width=90, height=30, command=self.refresh_versions).pack(side="right")
        ctk.CTkButton(
            title_row, text="전략 가져오기", width=105, height=30,
            state="normal" if self._feature_enabled("strategy_package") else "disabled",
            command=self._import_strategy_package,
        ).pack(side="right", padx=6)
        self.active_pool_label = ctk.CTkLabel(
            title_row, text="실행 풀 0/10", font=self._font(12, "bold"), text_color="#22c55e"
        )
        self.active_pool_label.pack(side="right", padx=12)
        self.version_rows = ctk.CTkFrame(self.versions_card, fg_color="transparent")
        self.version_rows.pack(fill="x", padx=12, pady=(0, 12))

    def _on_strategy_view_changed(self, value: str):
        level = 3 if "Level 3" in str(value) else 2 if "Level 2" in str(value) else 1
        self._set_strategy_view_level(level)

    def _set_strategy_view_level(self, level: int):
        """한 IR을 사용자 숙련도에 따라 단계적으로 표시한다."""
        self.strategy_view_level = int(level) if int(level) in {1, 2, 3} else 1
        advanced_card = getattr(self, "advanced_card", None)
        result_card = getattr(self, "result_card", None)
        if advanced_card is not None and result_card is not None:
            if self.strategy_view_level == 3:
                if not advanced_card.winfo_manager():
                    advanced_card.pack(
                        fill="x", padx=14, pady=8, before=result_card,
                    )
            elif advanced_card.winfo_manager():
                advanced_card.pack_forget()
        if self.analysis_result:
            self._show_analysis(self.analysis_result)

    def load_beginner_preset(self, preset_key: Optional[str] = None) -> bool:
        """선택 프리셋을 입력창에만 불러온다. 분석·저장·승인은 자동 수행하지 않는다."""
        key = str(
            preset_key
            or self.BEGINNER_PRESET_LABELS.get(self.beginner_preset_combo.get())
            or "auto_regime"
        )
        preset = get_beginner_preset(key)
        if not preset:
            messagebox.showwarning("기본 전략", "선택한 기본 전략을 찾지 못했습니다.")
            return False
        self.beginner_preset_combo.set(str(preset["name"]))
        if not bool(preset.get("executable_template")):
            messagebox.showinfo(
                "AI 자동 대응",
                str(preset.get("summary") or "")
                + "\n\n별도 커스텀 전략을 자동 저장하지 않습니다. "
                "시장 조건이 불명확하면 HOLD하며 기존 NoahAI 가드레일을 그대로 사용합니다.",
            )
            return True
        self.reference_entry.delete(0, "end")
        self.kind_combo.set("텍스트/메모")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", str(preset.get("source_text") or ""))
        self.result_status.configure(
            text="프리셋 초안 로드 · AI 분석 필요",
            text_color="#38bdf8",
        )
        self.analysis_result = None
        self.save_button.configure(state="disabled")
        return True

    def _start_mentor_interview(self) -> None:
        """사용자 여건을 묻고 검토 후보만 제안한다. 저장·승인·적용은 하지 않는다."""
        prompts = (
            ("asset_class", "운용 자산: crypto / stock / both", "crypto"),
            ("capital_band", "운용 규모: small / medium / large", "small"),
            ("max_loss_percent", "한 거래 최대 계좌 손실률(%): 0.05~5", "0.5"),
            ("review_frequency", "확인 주기: intraday / daily / weekly", "daily"),
            ("trade_frequency", "선호 거래 빈도: low / medium / high", "medium"),
            ("leverage_allowed", "레버리지 사용: yes / no", "no"),
            ("experience_level", "경험: beginner / intermediate / advanced", "beginner"),
            ("paper_ready", "PAPER 전진검증 가능: yes / no", "yes"),
        )
        profile: Dict[str, Any] = {}
        for field, prompt, default in prompts:
            dialog = ctk.CTkInputDialog(
                text=f"{prompt}\n기본값: {default}",
                title="AI 트레이딩 멘토",
            )
            answer = dialog.get_input()
            if answer is None:
                return
            value = str(answer or default).strip().lower()
            if field in {"leverage_allowed", "paper_ready"}:
                profile[field] = value in {"yes", "y", "true", "1", "예"}
            elif field == "max_loss_percent":
                try:
                    profile[field] = float(value)
                except ValueError:
                    messagebox.showwarning("AI 멘토", "최대 손실률은 숫자로 입력하세요.")
                    return
            else:
                profile[field] = value
        candidates = recommend_strategy_candidates(profile)
        if not candidates:
            messagebox.showwarning("AI 멘토", "입력 범위를 확인해 다시 진행하세요.")
            return
        self.mentor_profile = profile
        self.mentor_candidates = candidates
        lines = []
        for index, item in enumerate(candidates, start=1):
            lines.append(
                f"{index}. {item['name']}\n{item['why_fit']}\n"
                f"거래하지 않을 때: {item['when_not_to_trade']}"
            )
        first = candidates[0]
        use_first = messagebox.askyesno(
            "AI 멘토 후보",
            "\n\n".join(lines)
            + f"\n\n1순위 「{first['name']}」를 입력창에 불러올까요?\n"
              "불러오기는 분석·저장·승인·최종 적용이 아닙니다.",
        )
        if use_first:
            self.load_beginner_preset(str(first["preset_key"]))

    def _ask_selected_preset(self) -> None:
        name = self.beginner_preset_combo.get()
        self._ask_assistant("preset:" + name)

    def _on_signal_mode_change(self, selected: Optional[str] = None) -> None:
        """운용 역할과 선택형 규칙 편집을 서로 다른 개념으로 안내한다."""
        mode = str(selected or self.signal_mode_combo.get() or "")
        independent = self._is_independent_role(mode)
        if independent:
            self.entry_signal_label.pack(
                side="left", padx=(14, 6), before=self.signal_mode_help_label,
            )
            self.entry_signal_combo.pack(
                side="left", before=self.signal_mode_help_label,
            )
            self.signal_mode_help_label.configure(
                text=AI_CUSTOM_INDEPENDENT_ROLE_HELP
            )
            if not self.strategy_universe_card.winfo_manager():
                self.strategy_universe_card.pack(
                    fill="x",
                    padx=16,
                    pady=(0, 8),
                    before=getattr(self, "risk_row", None),
                )
        else:
            self.entry_signal_label.pack_forget()
            self.entry_signal_combo.pack_forget()
            self.signal_mode_help_label.configure(
                text=AI_CUSTOM_CONFIRM_ROLE_HELP
            )
            self.strategy_universe_card.pack_forget()

    @staticmethod
    def _is_independent_role(value: str) -> bool:
        """이전 표시명으로 열린 화면과 새 표시명을 모두 안전하게 해석한다."""
        normalized = str(value or "")
        return normalized.startswith(AI_CUSTOM_INDEPENDENT_ROLE_LABEL) or normalized.startswith(
            "사용자 전략 원형 독립 실행"
        )

    def _show_safe_use_flow(self) -> None:
        existing = getattr(self, "_safe_flow_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        window = ctk.CTkToplevel(self)
        self._safe_flow_window = window
        window.title("AI 커스텀 12단계 안전 사용 순서")
        window.geometry("780x640")
        window.minsize(700, 560)
        window.configure(fg_color="#050a13")
        try:
            window.transient(self.winfo_toplevel())
            window.grab_set()
        except Exception:
            pass

        header = ctk.CTkFrame(window, fg_color="#111827", corner_radius=14)
        header.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            header, text="AI 커스텀, 안전하게 시작하는 12단계",
            font=self._font(21, "bold"), text_color="#f8fafc",
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            header,
            text=(
                "저장과 실행은 다릅니다. 원본 근거를 확인하고 승인·검증·PAPER를 거친 뒤에만 LIVE로 이동하세요. "
                "각 단계는 앞 단계를 건너뛰지 않도록 설계되어 있습니다."
            ),
            font=self._font(12), text_color="#a9bad0", justify="left", wraplength=700,
        ).pack(fill="x", padx=18, pady=(0, 14))

        body = ctk.CTkScrollableFrame(window, fg_color="#080f1d", corner_radius=12)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        sections = (
            ("준비", 0, 2, "#38bdf8"),
            ("전략 만들기", 2, 6, "#a78bfa"),
            ("검토·적용", 6, 10, "#22c55e"),
            ("운영", 10, 12, "#f59e0b"),
        )
        for section_title, start, end, color in sections:
            card = ctk.CTkFrame(body, fg_color="#111827", corner_radius=12)
            card.pack(fill="x", padx=6, pady=6)
            ctk.CTkLabel(
                card, text=section_title, font=self._font(14, "bold"), text_color=color,
            ).pack(anchor="w", padx=14, pady=(11, 5))
            for index in range(start, end):
                ctk.CTkLabel(
                    card,
                    text=f"{index + 1:02d}  {AI_CUSTOM_SAFE_STEPS[index]}",
                    font=self._font(11), text_color="#dbe7f5", justify="left", wraplength=665,
                ).pack(fill="x", anchor="w", padx=14, pady=(0, 7))
            ctk.CTkFrame(card, height=3, fg_color=color, corner_radius=2).pack(
                fill="x", padx=14, pady=(2, 11)
            )

        footer = ctk.CTkFrame(window, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 16))

        def _ask_and_close() -> None:
            try:
                window.grab_release()
            except Exception:
                pass
            window.destroy()
            self._ask_assistant("getting_started")

        ctk.CTkButton(
            footer, text="AI에게 이 순서 묻기", width=190, height=38,
            fg_color="#0f766e", hover_color="#0d9488", command=_ask_and_close,
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="확인", width=120, height=38,
            fg_color="#1d4ed8", hover_color="#1e40af", command=window.destroy,
        ).pack(side="right")

    def _choose_file(self):
        path = filedialog.askopenfilename(
            title="전략 자료 선택",
            filetypes=[
                ("지원 파일", "*.md *.pdf *.pine *.txt *.png *.jpg *.jpeg *.webp *.mp4 *.mov *.mkv *.avi"),
                ("모든 파일", "*.*"),
            ],
        )
        if path:
            self.reference_entry.delete(0, "end")
            self.reference_entry.insert(0, path)
            self.kind_combo.set("자동 판별")

    def _ask_assistant(self, topic: str) -> None:
        """AI 커스텀 화면의 현재 맥락을 어시스턴트 질문으로 넘긴다."""
        dashboard = self.dashboard
        if dashboard is None:
            messagebox.showinfo(
                "AI 어시스턴트",
                "대시보드의 ‘AI 어시스턴트’ 탭에서 ‘AI 커스텀 사용법’을 질문해 주세요.",
            )
            return
        try:
            resolver = getattr(dashboard, "_get_live_ai_assistant", None)
            if callable(resolver):
                assistant = resolver()
            else:
                ensure = getattr(dashboard, "_ensure_ai_assistant_tab", None)
                if callable(ensure):
                    ensure()
                assistant = getattr(dashboard, "ai_assistant_widget", None)
            tab_widget = getattr(dashboard, "tab_widget", None)
            if assistant is None or tab_widget is None:
                raise RuntimeError("AI 어시스턴트 탭을 준비하지 못했습니다.")
            tab_widget.set("AI 어시스턴트")
            if topic.startswith("preset:"):
                preset_name = topic.split(":", 1)[1]
                prompt = (
                    f"AI 커스텀의 초보자 프리셋 ‘{preset_name}’을 설명해줘. "
                    "적합한 시장상황, 진입을 보류하는 HOLD 조건, 상대적 위험, "
                    "초안을 불러온 뒤 분석·검토·저장하는 버튼 순서를 알려줘. "
                    "높은 승률이나 수익을 보장하는 표현은 사용하지 마."
                )
            elif topic == "analysis_result" and self.analysis_result:
                source = dict(self.analysis_result.get("source", {}) or {})
                suggestion = dict(self.analysis_result.get("market_regime_suggestion", {}) or {})
                missing = list(self.analysis_result.get("missing_conditions", []) or [])
                prompt = (
                    "AI 커스텀 XAI 결과를 초보자에게 설명해줘. "
                    f"전략명={self.analysis_result.get('name', '-')}, 입력={source.get('kind', '-')}, "
                    f"추천 시장상황={','.join(suggestion.get('labels') or ['사용자 확인 필요'])}, "
                    f"누락조건={','.join(missing) if missing else '없음'}. "
                    "원문 근거, 실제 적용값, 지금 저장/승인해도 되는지, 다음에 누를 버튼을 순서대로 알려줘."
                )
            else:
                prompt = (
                    "AI 커스텀을 처음 쓰는 사용자입니다. 전략 자료를 어디에 넣고, "
                    "시장상황·적용범위·전략 역할을 어떻게 고르며, XAI에서 무엇을 확인하고 "
                    "저장·승인·자동검증·최종 적용하는지 화면 순서대로 설명해줘."
                )
            if not assistant.send_quick_question(prompt):
                raise RuntimeError("AI 어시스턴트 입력창이 활성 상태가 아닙니다.")
        except Exception as exc:
            messagebox.showerror("AI 어시스턴트 연결", f"질문 화면을 열지 못했습니다.\n{exc}")

    def _apply_market_regime_suggestion(self, result: Dict[str, Any]) -> None:
        suggestion = dict(result.get("market_regime_suggestion", {}) or {})
        regimes = list(suggestion.get("regimes", []) or [])
        labels = list(suggestion.get("labels", []) or [])
        if not suggestion.get("auto_select") or not regimes or regimes == ["all"]:
            return
        label = "AI 추천: " + " + ".join(labels)
        self._regime_value_map[label] = regimes
        values = list(self.REGIME_LABELS)
        if label not in values:
            values.append(label)
        self.regime_combo.configure(values=values)
        self.regime_combo.set(label)

    def _selected_market_regimes(self) -> list[str]:
        return list(self._regime_value_map.get(self.regime_combo.get(), ["all"]) or ["all"])

    @staticmethod
    def _split_symbols(value: str) -> list[str]:
        return list(
            dict.fromkeys(
                token.strip().upper()
                for token in str(value or "").replace(";", ",").split(",")
                if token.strip()
            )
        )

    def _strategy_universe_policy(self, signal_mode: str) -> Dict[str, Any]:
        if str(signal_mode or "").lower() != "independent":
            return {}

        def number(attr: str, default: float) -> float:
            widget = getattr(self, attr, None)
            try:
                return float(widget.get())
            except Exception:
                return float(default)

        return {
            "include_symbols": self._split_symbols(self.universe_include_entry.get()),
            "exclude_symbols": self._split_symbols(self.universe_exclude_entry.get()),
            "min_quote_volume": max(
                0.0, number("universe_min_volume_entry", 0.0)
            ),
            "max_spread_bps": max(
                0.0, number("universe_max_spread_entry", 30.0)
            ),
            "min_volatility_percent": max(
                0.0, number("universe_min_vol_entry", 0.0)
            ),
            "max_volatility_percent": max(
                0.0, number("universe_max_vol_entry", 100.0)
            ),
            "max_candidates": max(
                1, min(200, int(number("universe_limit_entry", 20)))
            ),
            "ranking": "liquidity",
        }

    def _input_value(self) -> str:
        reference = self.reference_entry.get().strip()
        body = self.source_text.get("1.0", "end").strip()
        placeholder = "전략 설명 또는 Pine Script를 붙여 넣으세요. 링크/파일을 선택한 경우 비워도 됩니다."
        return reference or ("" if body == placeholder else body)

    def _start_analysis(self):
        self._refresh_ai_model_status()
        value = self._input_value()
        if not value:
            messagebox.showwarning("전략 입력 필요", "링크/파일을 선택하거나 전략 설명·Pine Script를 입력하세요.")
            return
        self.analyze_button.configure(state="disabled", text="추출·분석 중...")
        self.save_button.configure(state="disabled")
        self.result_status.configure(text="소스 추출 중", text_color="#38bdf8")
        # Tk 위젯 값은 UI 스레드에서 읽고 작업 스레드에는 일반 문자열만 전달한다.
        kind = self.SOURCE_LABELS.get(self.kind_combo.get(), "auto")
        threading.Thread(target=self._analyze_worker, args=(value, kind), daemon=True).start()

    def _analyze_worker(self, value: str, kind: str = "auto"):
        try:
            settings = self._runtime_settings()
            model = self._selected_ai_model()
            try:
                from trading.ai.provider_router import AIProviderRouter

                client = AIProviderRouter.from_settings(
                    settings,
                    workload="premium",
                ).client_facade()
                transcription_client = AIProviderRouter.from_settings(
                    settings,
                    workload="transcription",
                ).client_facade()
            except Exception:
                client = OpenAIClient(
                    api_key=str(settings.get("openai_api_key", "") or ""),
                    model=model,
                    base_url=str(settings.get("openai_base_url", "") or "") or None,
                )
                transcription_client = client
            transcription = dict(settings.get("ai_custom_transcription", {}) or {})
            result = StrategySourceIngestor(
                client if client.is_ready() else None,
                transcription_client=(
                    transcription_client if transcription_client.is_ready() else None
                ),
                transcription_enabled=bool(transcription.get("enabled", True)),
                transcription_model=str(transcription.get("model", "gpt-4o-mini-transcribe") or "gpt-4o-mini-transcribe"),
                audio_max_duration_minutes=int(transcription.get("max_duration_minutes", 45) or 45),
                audio_max_file_mb=int(transcription.get("max_file_mb", 24) or 24),
            ).analyze(value, kind)
            result["ai_model"] = (
                f"{self._selected_ai_provider()} / {model}"
                if client.is_ready()
                else "규칙 기반 추출(API 미사용)"
            )
            self.after(0, lambda result=result: self._show_analysis(result))
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self.after(0, lambda error=error: self._show_error(error))

    def _show_analysis(self, result: Dict[str, Any]):
        self.analysis_result = result
        self._apply_market_regime_suggestion(result)
        source = result.get("source", {}) or {}
        evidence = dict(source.get("evidence", {}) or {})
        missing = result.get("missing_conditions", []) or []
        guidance = dict(result.get("guidance", {}) or {})
        questions = list(guidance.get("questions", []) or [])
        extracted_risk = dict((result.get("rules", {}) or {}).get("risk_model", {}) or {})
        if extracted_risk:
            for widget_name, key in (
                ("risk_per_trade_combo", "risk_per_trade_percent"),
                ("max_margin_combo", "max_margin_usage_percent"),
                ("max_leverage_combo", "max_leverage"),
            ):
                value = extracted_risk.get(key)
                widget = getattr(self, widget_name, None)
                if value not in (None, "") and widget is not None:
                    widget.set(str(value))
        transition = str((result.get("rules", {}) or {}).get("regime_transition", "delegate_to_noah"))
        self.transition_combo.set(
            "커스텀 신규 진입 일시정지" if transition == "pause" else "기본 노아AI에 맡김"
        )
        signal_role = self.signal_mode_combo.get()
        scope_label = self.target_combo.get()
        regime_label = self.regime_combo.get()
        regime_suggestion = dict(result.get("market_regime_suggestion", {}) or {})
        evidence_available = bool(
            evidence.get("strategy_evidence_available", True)
            if source.get("kind") == "youtube"
            else (source.get("text") or source.get("reference"))
        )
        strategy_ir = dict(result.get("strategy_ir", {}) or {})
        if not strategy_ir:
            strategy_ir = NoahStrategyIR.compile(
                dict(result.get("rules", {}) or {}),
                source_kind=str(source.get("kind") or "text"),
                source_reference=str(source.get("reference") or ""),
                missing_conditions=missing,
            )
            result["strategy_ir"] = strategy_ir
        ir_validation = NoahStrategyIR.validate(strategy_ir)
        try:
            ir_projection = NoahStrategyIR.project(
                strategy_ir, self.strategy_view_level,
            )
        except ValueError as exc:
            ir_projection = {
                "level": self.strategy_view_level,
                "support_status": "unsupported",
                "errors": [str(exc)],
            }
        ir_support = str(ir_projection.get("support_status") or "unsupported")
        ir_hash = str(strategy_ir.get("integrity_sha256") or "")
        lines = [
            f"전략명: {result.get('name', '-')}",
            f"입력 형식: {source.get('kind', '-')} / 출처: {source.get('reference', '-')}",
            f"사용 AI: {result.get('ai_model', '-')}",
            f"AI 구조화: {'완료' if result.get('ai_analyzed') else '규칙 기반 1차 추출(API 미사용)'}",
            f"분석 범위: {source.get('coverage_summary', '입력 원문 기준')}",
            f"음성 전사: {evidence.get('transcription_model', '자막 우선·전사 미사용')}",
            f"전략 근거 확보: {'예' if evidence_available else '아니오 · 원문/자막/화면 근거를 보강해야 함'}",
            "",
            "[이 전략은 무엇을 하나]",
            f"{result.get('summary', '-')}",
            "",
            "[저장하면 어디에 어떻게 적용되나]",
            f"- 적용 범위: {scope_label}",
            f"- 대상 시장상황: {regime_label}",
            f"- AI 시장상황 추천 근거: {regime_suggestion.get('evidence', '사용자 확인 필요')}",
            f"- 우선순위: {self.priority_combo.get()} (10에 가까울수록 먼저 검사)",
            f"- 전략 역할: {signal_role}",
            "- 지금은 분석 초안이며 저장·사용자 승인·자동검증·최종 적용 전에는 주문 판단에 사용되지 않음",
            "",
            "[원문에서 구조화한 전략 규칙]",
            json.dumps(result.get("rules", {}), ensure_ascii=False, indent=2),
            "",
            "[실행 엔진에 전달할 적용값]",
            json.dumps(result.get("engine_settings", {}), ensure_ascii=False, indent=2),
            "",
            "[누락/재확인]",
            "없음" if not missing else "\n".join(f"- {item}" for item in missing),
            "",
            "[AI가 사용자에게 확인할 질문]",
            "없음" if not questions else "\n".join(
                f"- {item.get('label', item.get('field', '-'))}: {item.get('question', '')}\n"
                f"  입력 예시: {item.get('example', '')}"
                for item in questions
            ),
            "",
            "[위험·레버리지 안내]",
            str(guidance.get(
                "risk_model_help",
                "실제 레버리지는 거래 위험예산, 손절거리, 증거금 한도와 레버리지 상한에서 계산됩니다.",
            )),
            "",
            "[위험/주의]",
            "\n".join(f"- {item}" for item in (result.get("risks", []) or [])),
            "",
            "[추출 경고]",
            "없음" if not source.get("warnings") else "\n".join(f"- {item}" for item in source.get("warnings", [])),
        ]
        if self.strategy_view_level == 1:
            summary = dict(ir_projection.get("summary", {}) or {})
            lines = [
                "[Level 1 · 이해하고 시험하기]",
                f"전략명: {result.get('name', '-')}",
                f"무엇을 하나: {result.get('summary', '-')}",
                f"진입: {summary.get('entry') or '사용자 확인 필요'}",
                f"종료: {summary.get('exit') or '사용자 확인 필요'}",
                f"손절 / 익절: {summary.get('stop_loss', '-')} / {summary.get('take_profit', '-')}",
                f"적용 범위 / 국면: {scope_label} / {regime_label}",
                f"원본 근거: {'확보' if evidence_available else '보강 필요'}",
                f"IR 상태: {ir_support} · v{strategy_ir.get('ir_version', '-')}",
                f"근거 연결: {ir_projection.get('evidence_coverage', {}).get('traced', 0)}/"
                f"{ir_projection.get('evidence_coverage', {}).get('nodes', 0)} 노드",
                "",
                "[시험 전 확인]",
                "- 저장만으로 주문하지 않음",
                "- 사용자 승인 후 자동 검증을 통과해야 최종 적용 가능",
                "- 백테스트·모의 성과는 실제 수익을 보장하지 않음",
                "",
                "[누락/재확인]",
                "없음" if not missing else "\n".join(f"- {item}" for item in missing),
                "",
                "[위험/주의]",
                "\n".join(f"- {item}" for item in (result.get("risks", []) or [])),
            ]
        elif self.strategy_view_level == 2:
            lines.extend([
                "",
                "[Level 2 · 같은 IR의 핵심 편집값]",
                json.dumps(ir_projection.get("editable_parameters", {}), ensure_ascii=False, indent=2),
                f"IR 무결성: {'통과' if ir_validation.get('valid') else '실패'} · {ir_hash[:16]}",
            ])
        else:
            lines.extend([
                "",
                "[Level 3 · 전체 Noah Strategy IR]",
                json.dumps(ir_projection, ensure_ascii=False, indent=2),
            ])
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "\n".join(lines))
        self.result_text.configure(state="disabled")
        self.result_status.configure(
            text=(
                "IR 무결성/지원 차단"
                if not ir_validation.get("valid") or ir_support == "unsupported"
                else "조건 재확인 필요"
                if missing or ir_support == "needs_clarification"
                else "저장 가능 · 승인 전 실행 차단"
            ),
            text_color=(
                "#ef4444"
                if not ir_validation.get("valid") or ir_support == "unsupported"
                else "#f59e0b"
                if missing or ir_support == "needs_clarification"
                else "#22c55e"
            ),
        )
        self.analyze_button.configure(state="normal", text="AI 분석 및 전략 초안 만들기")
        self.save_button.configure(
            state="disabled"
            if not ir_validation.get("valid") or ir_support == "unsupported"
            else "normal"
        )

    def _show_error(self, error: str):
        self.analysis_result = None
        self.result_status.configure(text="분석 실패", text_color="#ef4444")
        self.analyze_button.configure(state="normal", text="AI 분석 및 전략 초안 만들기")
        self.save_button.configure(state="disabled")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert(
            "1.0",
            "분석을 완료하지 못했습니다.\n\n"
            f"원인: {error}\n\n"
            "주소·네트워크·자막 공개 여부를 확인하거나 핵심 장면/전략 텍스트를 함께 입력하세요.",
        )
        self.result_text.configure(state="disabled")
        messagebox.showerror("전략 분석 실패", error)

    def _customizer(self):
        app = getattr(self.dashboard, "main_app", None)
        if app is None:
            return None
        if self.SCOPE_LABELS.get(self.target_combo.get()) == "exchange:binance":
            return getattr(app, "strategy_customizer", None)
        return getattr(app, "strategy_customizer_unified", None)

    def _scope_value(self) -> str:
        return self.SCOPE_LABELS.get(self.target_combo.get(), "exchange:binance")

    def _target_value(self) -> str:
        scope = self._scope_value()
        return scope.split(":", 1)[1] if scope.startswith(("exchange:", "broker:")) else ""

    def _insert_advanced_template(self):
        template = {
            "executable_entry": {
                "all": [
                    {
                        "field": {
                            "indicator": "ema", "period": 17,
                            "timeframe": "1h", "source": "close",
                        },
                        "operator": "gt_field",
                        "value_field": {
                            "indicator": "ema", "period": 63,
                            "timeframe": "1h", "source": "close",
                        },
                    }
                ],
                "any": [
                    {
                        "field": {
                            "indicator": "rsi", "period": 14,
                            "timeframe": "15m", "source": "close",
                        },
                        "operator": "gte", "value": 50,
                    }
                ],
            },
            "executable_exit": {
                "any": [
                    {
                        "field": {
                            "indicator": "rsi", "period": 14,
                            "timeframe": "15m", "source": "close",
                        },
                        "operator": "gte", "value": 72,
                    }
                ]
            },
            "advanced_order_plan": {
                "partial_take_profits": [
                    {"target_percent": 1.0, "close_fraction": 0.5},
                    {"target_percent": 2.0, "close_fraction": 0.5},
                ],
                "trailing_stop": {
                    "activation_percent": 1.0, "distance_percent": 0.5,
                },
                "break_even": {
                    "trigger_percent": 0.8, "offset_percent": 0.05,
                },
                "reentry": {"cooldown_bars": 3, "max_reentries": 1},
            },
        }
        self.advanced_rules_text.delete("1.0", "end")
        self.advanced_rules_text.insert("1.0", json.dumps(template, ensure_ascii=False, indent=2))
        self._validate_advanced_editor(show_dialog=False)

    def _insert_expression_graph_template(self):
        if not (self._feature_enabled("expression_graph") and self._feature_enabled("user_indicator_language")):
            messagebox.showwarning("고급 기능 꺼짐", "설정에서 Expression Graph와 사용자 지표 언어를 켜세요.")
            return
        template = {
            "user_indicators": {
                "trend_gap": "(ema(20, '15m') - ema(50, '15m')) / max(abs(ema(50, '15m')), 0.000001)"
            },
            "executable_entry": {
                "expression": {
                    "type": "group", "operator": "and", "children": [
                        {"type": "condition", "field": {"user_indicator": "trend_gap"}, "operator": "gt", "value": 0},
                        {"type": "group", "operator": "or", "children": [
                            {"type": "condition", "field": {"indicator": "rsi", "period": 14, "timeframe": "15m", "source": "close"}, "operator": "lte", "value": 35},
                            {"type": "condition", "field": "volume_ratio", "operator": "gte", "value": 1.2},
                        ]},
                    ],
                }
            },
        }
        self.advanced_rules_text.delete("1.0", "end")
        self.advanced_rules_text.insert("1.0", json.dumps(template, ensure_ascii=False, indent=2))
        self._validate_advanced_editor(show_dialog=False)

    def _load_extracted_rules_to_advanced(self):
        if not self.analysis_result:
            messagebox.showinfo("고급 규칙", "먼저 AI 분석 및 전략 초안을 만들어 주세요.")
            return
        rules = dict(self.analysis_result.get("rules", {}) or {})
        extracted = {
            key: rules.get(key)
            for key in ("executable_entry", "executable_exit", "advanced_order_plan")
            if rules.get(key)
        }
        if not extracted:
            messagebox.showwarning(
                "고급 규칙",
                "AI가 실행 가능한 선언형 조건을 추출하지 못했습니다. 예제를 바탕으로 직접 입력해 주세요.",
            )
            return
        self.advanced_rules_text.delete("1.0", "end")
        self.advanced_rules_text.insert("1.0", json.dumps(extracted, ensure_ascii=False, indent=2))
        self._validate_advanced_editor(show_dialog=False)

    def _validate_advanced_editor(self, *, show_dialog: bool = False) -> Optional[Dict[str, Any]]:
        raw = self.advanced_rules_text.get("1.0", "end").strip()
        if not raw or raw.startswith("선택 사항입니다"):
            self.advanced_validation_label.configure(text="고급 규칙 미사용", text_color="#94a3b8")
            return {}
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("최상위 값은 JSON 객체여야 합니다.")
            unsupported = set(payload) - {
                "executable_entry", "executable_exit", "advanced_order_plan", "user_indicators",
            }
            if unsupported:
                raise ValueError("지원하지 않는 키: " + ", ".join(sorted(unsupported)))
            uses_expression = any(
                isinstance(payload.get(section), dict) and payload[section].get("expression") is not None
                for section in ("executable_entry", "executable_exit")
            )
            if uses_expression and not self._feature_enabled("expression_graph"):
                raise ValueError("설정에서 Expression Graph 편집기를 먼저 켜야 합니다.")
            if payload.get("user_indicators") and not self._feature_enabled("user_indicator_language"):
                raise ValueError("설정에서 제한형 사용자 지표 언어를 먼저 켜야 합니다.")
            from trading.declarative_strategy_engine import DeclarativeStrategyEngine

            validation = DeclarativeStrategyEngine.validate_rule_spec(payload)
            if not validation.get("valid"):
                raise ValueError("; ".join(validation.get("errors") or []))
        except Exception as exc:
            self.advanced_validation_label.configure(
                text=f"차단됨 · {exc}", text_color="#ef4444",
            )
            if show_dialog:
                messagebox.showerror(
                    "고급 규칙 차단",
                    f"안전한 선언형 규칙으로 해석할 수 없습니다.\n\n{exc}",
                )
            return None
        self.advanced_validation_label.configure(
            text="안전성 검사 통과 · 저장 전 최종 검토 필요", text_color="#22c55e",
        )
        if show_dialog:
            messagebox.showinfo(
                "고급 규칙 검사",
                "허용 지표·기간·시간봉·연산자 검사에 통과했습니다. "
                "전략 저장·승인·과거 검증 전에는 실행되지 않습니다.",
            )
        return payload

    def _save_version(self):
        if not self.analysis_result:
            return
        selected_target = self.version_target_map.get(self.version_target_combo.get())
        customizer = selected_target[0] if selected_target else self._customizer()
        if customizer is None:
            messagebox.showerror("저장 불가", "전략 런타임이 아직 준비되지 않았습니다. 앱 초기화 로그를 확인하세요.")
            return
        source = self.analysis_result.get("source", {}) or {}
        engine = self.analysis_result.get("engine_settings", {}) or {}
        rules = dict(self.analysis_result.get("rules", {}) or {})
        advanced_rules = self._validate_advanced_editor(show_dialog=False)
        if advanced_rules is None:
            messagebox.showerror(
                "전략 버전 저장 실패",
                "고급 규칙이 안전성 검사에 통과하지 못했습니다. 표시된 오류를 먼저 수정하세요.",
            )
            return
        if advanced_rules:
            rules.update(advanced_rules)
            rules["advanced_mode"] = True
        scope = self._scope_value()
        target = self._target_value()
        regimes = self._selected_market_regimes()
        regime_scope = self.REGIME_SCOPE_LABELS.get(
            self.regime_scope_combo.get(),
            "market",
        )
        rules["target_exchange"] = target if scope.startswith("exchange:") else ""
        rules["target_scope"] = scope
        rules["market_regimes"] = regimes
        rules["regime_scope"] = regime_scope
        rules["priority"] = int(self.priority_combo.get() or 5)
        signal_mode = (
            "independent"
            if self._is_independent_role(self.signal_mode_combo.get())
            else "confirm"
        )
        selected_entry = self.entry_signal_combo.get()
        entry_signal = selected_entry if selected_entry in {"LONG", "SHORT"} else str(rules.get("entry_signal", "") or "").upper()
        if signal_mode == "independent" and entry_signal not in {"LONG", "SHORT"}:
            messagebox.showerror(
                "독립 진입 방향 필요",
                "독립 전략은 LONG 또는 SHORT 진입 방향이 반드시 필요합니다. 소스에 방향을 명시하거나 직접 선택하세요.",
            )
            return
        rules["signal_mode"] = signal_mode
        rules["entry_signal"] = entry_signal
        universe_policy = self._strategy_universe_policy(signal_mode)
        rules["universe_policy"] = universe_policy
        rules["risk_model"] = {
            "risk_per_trade_percent": float(self.risk_per_trade_combo.get()),
            "max_margin_usage_percent": float(self.max_margin_combo.get()),
            "max_leverage": int(float(self.max_leverage_combo.get())),
            "max_notional_percent": 100.0,
            "stop_mode": "configured",
        }
        rules["regime_transition"] = (
            "pause" if self.transition_combo.get().startswith("커스텀") else "delegate_to_noah"
        )
        missing = list(self.analysis_result.get("missing_conditions", []) or [])
        strategy_ir = NoahStrategyIR.compile(
            rules,
            source_kind=str(source.get("kind") or "text"),
            source_reference=str(source.get("reference") or ""),
            missing_conditions=missing,
        )
        ir_validation = NoahStrategyIR.validate(strategy_ir)
        ir_support = str((strategy_ir.get("support") or {}).get("status") or "unsupported")
        if not ir_validation.get("valid") or ir_support == "unsupported":
            reasons = list((strategy_ir.get("support") or {}).get("unsupported_reasons") or [])
            messagebox.showerror(
                "Noah Strategy IR 저장 차단",
                "원본 규칙을 안전한 실행 계약으로 변환하지 못했습니다.\n\n"
                + "\n".join(f"- {item}" for item in (reasons or ir_validation.get("errors") or ["unknown_ir_error"])),
            )
            return
        self.analysis_result["strategy_ir"] = strategy_ir
        try:
            strategy_id = customizer.create_custom_strategy({
                "name": self.analysis_result.get("name", "사용자 전략"),
                "rules": rules,
                "base_params": engine,
                "source_kind": source.get("kind", "text"),
                "source_reference": source.get("reference", ""),
                "target_exchange": target if scope.startswith("exchange:") else "",
                "target_scope": scope,
                "market_regimes": regimes,
                "regime_scope": regime_scope,
                "universe_policy": universe_policy,
                "priority": int(self.priority_combo.get() or 5),
                "signal_mode": signal_mode,
                "entry_signal": entry_signal,
                "strategy_key": selected_target[1] if selected_target else None,
            })
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self.result_status.configure(text="전략 버전 저장 실패", text_color="#ef4444")
            messagebox.showerror(
                "전략 버전 저장 실패",
                f"저장하지 못했습니다.\n\n원인: {error}\n\n"
                "누락 조건, 저장 대상 또는 앱 초기화 상태를 확인하세요.",
            )
            return
        if not strategy_id:
            self.result_status.configure(text="전략 버전 저장 실패", text_color="#ef4444")
            messagebox.showerror("전략 버전 저장 실패", "저장 ID가 생성되지 않았습니다. 앱 초기화 로그를 확인하세요.")
            return
        self.result_status.configure(
            text="버전 저장 완료 · 조건 보완 필요" if missing else "버전 저장 완료 · 사용자 승인 대기",
            text_color="#f59e0b" if missing else "#22c55e",
        )
        messagebox.showinfo(
            "전략 버전 저장",
            f"검토 및 전략 버전이 저장되었습니다.\n\nID: {strategy_id}\n적용 범위: {self.target_combo.get()}\n"
            f"시장상황: {self.regime_combo.get()}\n국면 기준: {self.regime_scope_combo.get()}\n"
            + (
                f"상태: 조건 보완 필요 ({len(missing)}개)\n원문을 보강해 다시 분석·저장해야 승인할 수 있습니다."
                if missing else
                "상태: 사용자 승인 대기\n승인·자동 검증·최종 적용 전에는 거래에 사용되지 않습니다."
            ),
        )
        self.refresh_versions()

    def refresh_versions(self):
        for child in self.version_rows.winfo_children():
            child.destroy()
        app = getattr(self.dashboard, "main_app", None)
        rows = []
        for scope, attr in (("Binance", "strategy_customizer"), ("기타 거래소", "strategy_customizer_unified")):
            customizer = getattr(app, attr, None) if app is not None else None
            if customizer and hasattr(customizer, "list_strategies"):
                rows.extend(
                    (str(item.get("target_scope") or item.get("target_exchange") or scope), item, customizer)
                    for item in customizer.list_strategies()
                    if not str(item.get("name", "")).startswith("auto_runtime_")
                )
        target_map: Dict[str, Any] = {}
        latest_by_key: Dict[str, Any] = {}
        for scope, item, customizer in rows:
            strategy_key = str(item.get("strategy_key") or "")
            if not strategy_key:
                continue
            current = latest_by_key.get(strategy_key)
            if current is None or int(item.get("version") or 0) > int(current[1].get("version") or 0):
                latest_by_key[strategy_key] = (scope, item, customizer)
        scope_names = {value: label for label, value in self.SCOPE_LABELS.items()}
        for strategy_key, (scope, item, customizer) in latest_by_key.items():
            label = f"기존: {item.get('name', '사용자 전략')} ({scope_names.get(str(scope).lower(), scope)})"
            target_map[label] = (customizer, strategy_key, item)
        self.version_target_map = target_map
        if hasattr(self, "version_target_combo"):
            current_target = self.version_target_combo.get()
            values = ["새 전략으로 저장", *target_map.keys()]
            self.version_target_combo.configure(values=values)
            self.version_target_combo.set(current_target if current_target in values else "새 전략으로 저장")
        rows = sorted(rows, key=lambda row: (str(row[1].get("created_at", "")), int(row[1].get("version") or 0)), reverse=True)
        active_count = sum(1 for _scope, item, _customizer in rows if str(item.get("status")) == "active")
        app = getattr(self.dashboard, "main_app", None)
        if app is not None and hasattr(app, "sync_custom_strategy_runtime_pools"):
            try:
                active_count = len(app.sync_custom_strategy_runtime_pools())
            except Exception:
                pass
        if hasattr(self, "active_pool_label"):
            self.active_pool_label.configure(text=f"실행 풀 {active_count}/10")
        rows = rows[:10]
        if not rows:
            ctk.CTkLabel(self.version_rows, text="저장된 전략이 없습니다.", font=self._font(12), text_color="#94a3b8").pack(anchor="w", padx=6, pady=10)
            return
        labels = {
            "needs_clarification": "조건 재확인 필요", "analyzed": "XAI 완료 · 승인 대기",
            "approved": "승인 완료 · 실행 검증 대기", "paper_validated": "검증 완료 · 최종 적용 대기",
            "execution_validated": "실행 검증 완료 · 최종 적용 대기", "active": "적용 중",
            "paper_rejected": "검증 미통과", "execution_rejected": "자동검증 미통과 · 1% 제한운용 선택 가능",
        }
        latest_version_ids = {
            str(item.get("version_id") or "")
            for _scope, item, _customizer in latest_by_key.values()
        }
        for scope, item, customizer in rows:
            row = ctk.CTkFrame(self.version_rows, fg_color="#172033", corner_radius=10)
            row.pack(fill="x", pady=4)
            summary_row = ctk.CTkFrame(row, fg_color="transparent")
            summary_row.pack(fill="x", padx=8, pady=(4, 0))
            ctk.CTkLabel(
                summary_row, text=(
                    f"{scope_names.get(scope.lower(), scope)} · {item.get('name', '사용자 전략')} · "
                    f"v{item.get('version', '-')} · "
                    f"역할 {'독립 원형' if str(item.get('signal_mode', 'confirm')) == 'independent' else '기본 후보 재확인'} · "
                    f"국면기준 {str(item.get('regime_scope') or (item.get('rules') or {}).get('regime_scope') or 'market')} · "
                    f"우선 {item.get('priority', 5)}"
                ),
                font=self._font(12, "bold"), text_color="#e5edf6",
            ).pack(side="left", padx=4, pady=6)
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
            status = str(item.get("status", "unknown"))
            if status == "analyzed":
                ctk.CTkButton(
                    actions, text="내용 확인 후 승인", width=125, height=30,
                    command=lambda it=item, c=customizer: self._approve(it, c),
                ).pack(side="right", padx=8)
            elif status == "approved":
                ctk.CTkButton(
                    actions, text="자동 검증 실행", width=115, height=30,
                    command=lambda it=item, c=customizer: self._record_validation(it, c),
                ).pack(side="right", padx=8)
            elif status == "paper_validated" or (
                status == "execution_validated"
                and str((item.get("execution_validation") or {}).get("mode") or "") in {"live_observation", "limited_live"}
            ):
                ctk.CTkButton(
                    actions, text="최종 적용", width=90, height=30,
                    fg_color="#10b981", hover_color="#059669",
                    command=lambda it=item, c=customizer: self._activate(it, c),
                ).pack(side="right", padx=8)
            elif status == "execution_validated":
                ctk.CTkButton(
                    actions, text="PAPER 전진검증 필요", width=135, height=30,
                    state="disabled", font=self._font(10),
                ).pack(side="right", padx=8)
            elif status == "execution_rejected":
                ctk.CTkButton(
                    actions, text="검증미통과 안전 시험", width=145, height=30,
                    fg_color="#d97706", hover_color="#b45309",
                    command=lambda it=item, c=customizer: self._activate(it, c, operation_mode="limited_live"),
                ).pack(side="right", padx=8)
            elif status == "active":
                ctk.CTkButton(
                    actions, text="적용 해제", width=90, height=30,
                    fg_color="#475569", hover_color="#64748b",
                    command=lambda it=item, c=customizer: self._deactivate(it, c),
                ).pack(side="right", padx=8)
            status_text = labels.get(status, status)
            if status == "active" and str(item.get("operation_mode", "standard")) == "limited_live":
                status_text = "적용 중 · 1배/최대 1% 제한시험"
            elif status == "active":
                status_text = "적용 중 · 검증 통과 운용"
            elif status == "execution_validated" and str(
                (item.get("execution_validation") or {}).get("mode") or ""
            ) == "historical_replay":
                status_text = "과거재생 통과 · PAPER 필요"
            ctk.CTkLabel(summary_row, text=status_text, font=self._font(11), text_color="#a9bad0").pack(side="right", padx=8)
            if item.get("strategy_ir"):
                ctk.CTkButton(
                    actions,
                    text=f"IR v{item.get('ir_version') or '1.0'}",
                    width=70,
                    height=30,
                    fg_color="#1e3a5f",
                    hover_color="#28527f",
                    font=self._font(10),
                    command=lambda payload=item: self._show_strategy_ir(payload),
                ).pack(side="right", padx=4)
            if item.get("strategy_ir") and self._feature_enabled("strategy_package"):
                ctk.CTkButton(
                    actions, text="내보내기", width=78, height=30,
                    fg_color="#0f766e", hover_color="#0d9488", font=self._font(10),
                    command=lambda payload=item: self._export_strategy_package(payload),
                ).pack(side="right", padx=4)
            version_diff = dict(item.get("version_diff", {}) or {})
            if int(version_diff.get("change_count", 0) or 0) > 0:
                ctk.CTkButton(
                    actions,
                    text=f"변경점 {int(version_diff.get('change_count', 0) or 0)}개",
                    width=94,
                    height=30,
                    fg_color="#334155",
                    hover_color="#475569",
                    font=self._font(10),
                    command=lambda payload=version_diff: self._show_version_diff(payload),
                ).pack(side="right", padx=6)
            advice = dict(item.get("improvement_advice", {}) or {})
            improvement_actions = list(advice.get("actions", []) or [])
            if improvement_actions and status in {"execution_rejected", "execution_validated", "paper_validated"}:
                ctk.CTkButton(
                    actions,
                    text=f"개선안 · {improvement_actions[0].get('priority', '검토')}",
                    width=116,
                    height=30,
                    fg_color="#854d0e",
                    hover_color="#a16207",
                    font=self._font(10),
                    command=lambda payload=advice: self._show_improvement_advice(payload),
                ).pack(side="right", padx=6)
            ctk.CTkButton(
                actions,
                text="수정본 만들기",
                width=105,
                height=30,
                fg_color="#2563eb",
                hover_color="#1d4ed8",
                command=lambda payload=item, c=customizer: self._load_version_for_edit(payload, c),
            ).pack(side="left", padx=4)
            if str(item.get("version_id") or "") in latest_version_ids:
                ctk.CTkButton(
                    actions,
                    text="전략 삭제",
                    width=90,
                    height=30,
                    fg_color="#7f1d1d",
                    hover_color="#991b1b",
                    command=lambda payload=item, c=customizer: self._delete_private_strategy(payload, c),
                ).pack(side="left", padx=4)

    @staticmethod
    def _set_entry_value(widget: Any, value: Any) -> None:
        try:
            widget.delete(0, "end")
            widget.insert(0, str(value))
        except Exception:
            pass

    def _load_version_for_edit(self, item: Dict[str, Any], customizer) -> None:
        """저장 버전을 편집기에 불러오되 기존 승인 기록은 덮어쓰지 않는다."""
        strategy_key = str(item.get("strategy_key") or "")
        version_id = str(item.get("version_id") or "")
        try:
            getter = getattr(customizer, "get_custom_strategy_version", None)
            version = getter(strategy_key, version_id) if callable(getter) else dict(item)
            rules = dict(version.get("rules", {}) or {})
            engine = dict(rules.get("engine_settings", {}) or item.get("base_params", {}) or {})
            source_kind = str(version.get("source_kind") or item.get("source_kind") or "text")
            source_reference = str(version.get("source_reference") or item.get("source_reference") or "")
            self.analysis_result = {
                "name": str(version.get("name") or item.get("name") or "사용자 전략"),
                "summary": str((version.get("xai") or {}).get("summary") or "저장된 전략 수정본"),
                "rules": rules,
                "engine_settings": engine,
                "source": {
                    "kind": source_kind,
                    "reference": source_reference,
                    "text": "저장된 프라이빗 전략 버전",
                    "coverage_summary": f"{strategy_key} / {version_id}",
                },
                "missing_conditions": list(version.get("missing_conditions", []) or []),
                "guidance": dict(version.get("guidance", {}) or {}),
                "strategy_ir": dict(version.get("strategy_ir", {}) or {}),
                "risks": list((version.get("xai") or {}).get("risks", []) or []),
                "ai_model": "저장 버전",
                "ai_analyzed": True,
            }

            for label, mapped in self.version_target_map.items():
                if mapped[0] is customizer and str(mapped[1]) == strategy_key:
                    self.version_target_combo.set(label)
                    break
            scope = str(rules.get("target_scope") or item.get("target_scope") or "exchange:binance")
            scope_label = next((label for label, value in self.SCOPE_LABELS.items() if value == scope), "Binance만")
            self.target_combo.set(scope_label)
            regimes = list(rules.get("market_regimes") or item.get("market_regimes") or ["all"])
            regime_label = next((label for label, value in self.REGIME_LABELS.items() if list(value) == regimes), None)
            if regime_label is None:
                regime_label = "수정본: " + " + ".join(regimes)
                self._regime_value_map[regime_label] = regimes
                values = list(self.REGIME_LABELS) + [regime_label]
                self.regime_combo.configure(values=values)
            self.regime_combo.set(regime_label)
            regime_scope = str(rules.get("regime_scope") or item.get("regime_scope") or "market")
            self.regime_scope_combo.set(next(
                (label for label, value in self.REGIME_SCOPE_LABELS.items() if value == regime_scope),
                "전체 시장 기준 (권장)",
            ))
            self.priority_combo.set(str(rules.get("priority") or item.get("priority") or 5))
            signal_mode = str(rules.get("signal_mode") or item.get("signal_mode") or "confirm")
            self.signal_mode_combo.set(
                AI_CUSTOM_INDEPENDENT_ROLE_LABEL if signal_mode == "independent" else AI_CUSTOM_CONFIRM_ROLE_LABEL
            )
            self._on_signal_mode_change()
            entry_signal = str(rules.get("entry_signal") or item.get("entry_signal") or "")
            self.entry_signal_combo.set(entry_signal if entry_signal in {"LONG", "SHORT"} else "소스에서 자동")
            risk = dict(rules.get("risk_model", {}) or {})
            self.risk_per_trade_combo.set(str(risk.get("risk_per_trade_percent", 0.5)))
            self.max_margin_combo.set(str(risk.get("max_margin_usage_percent", 10)))
            self.max_leverage_combo.set(str(risk.get("max_leverage", 3)))
            self.transition_combo.set(
                "커스텀 신규 진입 일시정지"
                if str(rules.get("regime_transition") or "delegate_to_noah") == "pause"
                else "기본 노아AI에 맡김"
            )
            universe = dict(rules.get("universe_policy", {}) or {})
            self._set_entry_value(self.universe_include_entry, ", ".join(universe.get("include_symbols", []) or []))
            self._set_entry_value(self.universe_exclude_entry, ", ".join(universe.get("exclude_symbols", []) or []))
            for attr, key, default in (
                ("universe_min_volume_entry", "min_quote_volume", 0),
                ("universe_max_spread_entry", "max_spread_bps", 30),
                ("universe_min_vol_entry", "min_volatility_percent", 0),
                ("universe_max_vol_entry", "max_volatility_percent", 100),
                ("universe_limit_entry", "max_candidates", 20),
            ):
                self._set_entry_value(getattr(self, attr, None), universe.get(key, default))
            advanced = {
                key: rules[key]
                for key in ("executable_entry", "executable_exit", "advanced_order_plan", "user_indicators")
                if key in rules
            }
            if advanced:
                self.advanced_rules_text.delete("1.0", "end")
                self.advanced_rules_text.insert("1.0", json.dumps(advanced, ensure_ascii=False, indent=2))
                self._validate_advanced_editor(show_dialog=False)
            else:
                self.advanced_rules_text.delete("1.0", "end")
                self.advanced_rules_text.insert(
                    "1.0",
                    "선택 사항입니다. ‘예제 넣기’ 또는 ‘AI 추출값 불러오기’를 사용하세요.",
                )
                self.advanced_validation_label.configure(
                    text="고급 규칙 미사용",
                    text_color="#94a3b8",
                )
            self._show_analysis(self.analysis_result)
            self.result_status.configure(text="수정본 준비 · 저장하면 새 버전", text_color="#38bdf8")
            messagebox.showinfo(
                "전략 수정본 불러오기",
                f"{self.analysis_result['name']} v{version.get('version', item.get('version', '-'))}를 불러왔습니다.\n\n"
                "적용 범위·시장상황·위험값·고급 규칙을 바꾼 뒤 ‘검토 및 전략 버전 저장’을 누르면 "
                "기존 승인본을 덮어쓰지 않고 다음 버전으로 저장됩니다. 새 버전은 다시 승인·검증해야 합니다.",
            )
        except Exception as exc:
            messagebox.showerror("전략 수정본 불러오기 실패", str(exc))

    def _delete_private_strategy(self, item: Dict[str, Any], customizer) -> None:
        strategy_key = str(item.get("strategy_key") or "")
        if str(item.get("status") or "") == "active":
            messagebox.showwarning("전략 삭제 차단", "적용 중인 전략입니다. 먼저 ‘적용 해제’를 누른 뒤 삭제하세요.")
            return
        if not messagebox.askyesno(
            "프라이빗 전략 삭제",
            f"{item.get('name', '사용자 전략')}의 저장된 모든 버전을 삭제할까요?\n\n"
            "실행 중 전략은 삭제할 수 없으며, 삭제한 전략 내용은 복구되지 않습니다. 삭제 행위 기록에는 식별자만 남습니다.",
        ):
            return
        try:
            result = customizer.delete_custom_strategy(
                strategy_key,
                deleted_by="dashboard_user",
            )
            if self.version_target_combo.get() not in {"", "새 전략으로 저장"}:
                selected = self.version_target_map.get(self.version_target_combo.get())
                if selected and str(selected[1]) == strategy_key:
                    self.version_target_combo.set("새 전략으로 저장")
            self.refresh_versions()
            messagebox.showinfo(
                "전략 삭제 완료",
                f"프라이빗 전략과 {int(result.get('deleted_versions', 0) or 0)}개 버전을 삭제했습니다.",
            )
        except Exception as exc:
            messagebox.showerror("전략 삭제 실패", str(exc))

    def _show_strategy_ir(self, item: Dict[str, Any]):
        ir = dict((item or {}).get("strategy_ir", {}) or {})
        try:
            projection = NoahStrategyIR.project(ir, 3)
        except ValueError as exc:
            messagebox.showerror("Noah Strategy IR", str(exc))
            return
        messagebox.showinfo(
            "Noah Strategy IR · 실행 계약",
            json.dumps(projection, ensure_ascii=False, indent=2),
        )

    def _export_strategy_package(self, item: Dict[str, Any]):
        if not self._feature_enabled("strategy_package"):
            messagebox.showwarning("전략 패키지 꺼짐", "설정에서 .noahstrategy 기능을 켜세요.")
            return
        from trading.strategy_package import build_strategy_package, export_strategy_package

        target = filedialog.asksaveasfilename(
            title="NoahAI 전략 내보내기", defaultextension=".noahstrategy",
            filetypes=[("NoahAI 전략", "*.noahstrategy")],
            initialfile=f"{item.get('name', 'strategy')}.noahstrategy",
        )
        if not target:
            return
        try:
            package = build_strategy_package(
                item,
                passport={
                    "validation_lab": dict(item.get("validation_lab") or {}),
                    "paper_validation": dict(item.get("paper_validation") or {}),
                    "performance_claim": "past_results_not_future_guarantee",
                },
                access_policy={"visibility": "private", "permissions": ["view", "use", "fork"]},
            )
            saved = export_strategy_package(target, package)
            messagebox.showinfo("전략 내보내기 완료", f"민감정보와 활성 상태를 제외한 검토용 패키지를 저장했습니다.\n\n{saved}")
        except Exception as exc:
            messagebox.showerror("전략 내보내기 실패", str(exc))

    def _import_strategy_package(self):
        if not self._feature_enabled("strategy_package"):
            messagebox.showwarning("전략 패키지 꺼짐", "설정에서 .noahstrategy 기능을 켜세요.")
            return
        target = filedialog.askopenfilename(
            title="NoahAI 전략 가져오기", filetypes=[("NoahAI 전략", "*.noahstrategy")],
        )
        if not target:
            return
        customizer = self._customizer()
        if customizer is None:
            messagebox.showerror("전략 가져오기 실패", "선택한 범위의 전략 런타임이 준비되지 않았습니다.")
            return
        try:
            from trading.strategy_package import import_strategy_package

            imported = import_strategy_package(target)
            rules = dict(imported.get("rules") or {})
            customizer.create_custom_strategy({
                "name": f"{imported.get('name') or '공유 전략'} (가져옴)",
                "rules": rules,
                "base_params": dict(rules.get("engine_settings") or {}),
                "source_kind": "noahstrategy",
                "source_reference": os.path.basename(target),
                "target_scope": str(rules.get("target_scope") or self._scope_value()),
                "target_exchange": str(rules.get("target_exchange") or self._target_value()),
                "signal_mode": str(rules.get("signal_mode") or "confirm"),
                "entry_signal": str(rules.get("entry_signal") or ""),
            })
            messagebox.showinfo(
                "전략 가져오기 완료",
                "검토 전용 비활성 버전으로 가져왔습니다. 내용 확인→승인→검증→PAPER 순서를 다시 거쳐야 합니다.",
            )
            self.refresh_versions()
        except Exception as exc:
            messagebox.showerror("전략 가져오기 실패", str(exc))

    def _show_version_diff(self, version_diff: Dict[str, Any]):
        changes = list((version_diff or {}).get("changes", []) or [])
        if not changes:
            messagebox.showinfo("전략 버전 변경점", "이전 버전과 비교할 변경점이 없습니다.")
            return
        lines = ["이전 전략 버전과 달라진 규칙입니다.", ""]
        for index, item in enumerate(changes[:30], start=1):
            path = str(item.get("path") or "-")
            before = item.get("before", "-")
            after = item.get("after", "-")
            lines.extend([
                f"{index}. {path}",
                f"   이전: {before}",
                f"   변경: {after}",
            ])
        if len(changes) > 30:
            lines.append(f"외 {len(changes) - 30}개 변경점")
        lines.extend([
            "",
            "변경점 확인만으로 승인·자동검증·적용되지 않습니다.",
            "내용을 검토한 뒤 사용자가 승인하고 검증을 실행해야 합니다.",
        ])
        messagebox.showinfo("전략 버전 변경점", "\n".join(lines))

    def _show_improvement_advice(self, advice: Dict[str, Any]):
        actions = list((advice or {}).get("actions", []) or [])
        if not actions:
            messagebox.showinfo("AI 개선안", "현재 표시할 개선안이 없습니다.")
            return
        lines = []
        for index, item in enumerate(actions, start=1):
            lines.extend([
                f"{index}. {item.get('priority', '검토 필요')}",
                f"근거: {item.get('reason', '-')}",
                f"제안: {item.get('suggestion', '-')}",
                "",
            ])
        lines.append("이 제안은 현재 전략에 자동 적용되지 않습니다.")
        lines.append("반영하려면 조건을 수정해 새 버전으로 저장·승인·자동검증하세요.")
        messagebox.showinfo("AI 전략 개선안", "\n".join(lines))

    def _approve(self, item: Dict[str, Any], customizer):
        xai = item.get("xai", {}) or {}
        if not messagebox.askyesno(
            "전략 승인 확인",
            f"{item.get('name', '사용자 전략')} v{item.get('version', '-')}\n\n"
            f"설명: {xai.get('summary', '구조화 완료')}\n\n"
            "이 승인은 저장된 규칙을 확인했다는 뜻이며 즉시 실거래하지 않습니다. 승인할까요?",
        ):
            return
        customizer.approve_custom_strategy(
            item.get("strategy_key") or item.get("pipeline_strategy_key"),
            item.get("version_id") or item.get("pipeline_version_id"),
            approved_by="dashboard_user",
        )
        self.refresh_versions()

    def _record_validation(self, item: Dict[str, Any], customizer):
        if not messagebox.askyesno(
            "과거 시세 자동 검증",
            "코인은 대상 거래소의 최근 15분봉, 주식/ETF는 활성 증권사의 가격 이력을 가져와 "
            "진입 조건, TP/SL, 비용, PnL, 최대 낙폭을 자동 재생합니다.\n\n"
            "백테스트는 보조 검증이며 실전 수익을 보장하지 않습니다. 실행할까요?",
        ):
            return
        self.result_status.configure(text="과거 시세 자동 검증 중", text_color="#38bdf8")
        threading.Thread(
            target=self._validation_worker, args=(item, customizer), daemon=True,
        ).start()

    def _validation_worker(self, item: Dict[str, Any], customizer):
        try:
            scope = str(item.get("target_scope", "") or "").lower()
            historical_data = None
            validation_target = None
            symbol = None
            if scope.startswith("asset:stock") or scope.startswith("broker:"):
                dashboard = self.dashboard
                settings = self._runtime_settings()
                if scope.startswith("broker:"):
                    broker = scope.split(":", 1)[1]
                else:
                    brokers = list(settings.get("enabled_stock_brokers", []) or [])
                    broker = str(brokers[0] if brokers else "")
                if not broker:
                    raise RuntimeError("주식/ETF 자동 검증을 위해 증권사 하나 이상을 먼저 활성화하세요.")
                adapter_getter = getattr(dashboard, "_get_stock_adapter", None)
                adapter = adapter_getter(broker) if callable(adapter_getter) else None
                if adapter is None or not hasattr(adapter, "get_price_history"):
                    raise RuntimeError(f"{broker} 어댑터가 가격 이력 자동 검증을 지원하지 않습니다.")
                auto_cfg = dict(settings.get("stock_auto_trading", {}) or {})
                candidates = list(auto_cfg.get("symbols", []) or [])
                candidates.extend(list((settings.get("stock_search_profile", {}) or {}).get("recent_codes", []) or []))
                symbol = str(candidates[0] if candidates else "005930").strip().upper()
                historical_data = list(adapter.get_price_history(symbol, count=500) or [])
                validation_target = broker
            version = customizer.run_historical_validation(
                item.get("strategy_key"), item.get("version_id"), limit=500,
                symbol=symbol, historical_data=historical_data, validation_target=validation_target,
            )
            metrics = dict((version.get("execution_validation") or {}).get("metrics", {}) or {})
            metrics["validation_lab"] = dict(version.get("validation_lab") or {})
            passed = bool((version.get("execution_validation") or {}).get("passed", False))
            self.after(0, lambda: self._show_validation_result(passed, metrics))
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self.after(0, lambda error=error: self._show_validation_error(error))

    def _show_validation_result(self, passed: bool, metrics: Dict[str, Any]):
        self.result_status.configure(
            text="과거재생 통과 · PAPER 필요" if passed else "자동 검증 미통과",
            text_color="#22c55e" if passed else "#f59e0b",
        )
        profit_factor = metrics.get("profit_factor", 0.0)
        profit_factor_text = "∞" if str(profit_factor).lower() == "inf" else f"{float(profit_factor or 0.0):.2f}"
        regime_labels = {"bull": "상승", "bear": "하락", "range": "횡보", "volatile": "고변동"}
        regime_lines = []
        for regime, values in dict(metrics.get("regime_results", {}) or {}).items():
            regime_lines.append(
                f"{regime_labels.get(regime, regime)} {int(values.get('decisions', 0) or 0)}회/"
                f"{float(values.get('net_pnl_percent', 0.0) or 0.0):+.2f}%"
            )
        regime_summary = " · ".join(regime_lines) if regime_lines else "분류 표본 없음"
        lab = dict(metrics.get("validation_lab") or {})
        sample = dict(lab.get("sample") or {})
        walkforward = dict(lab.get("walkforward") or {})
        cost = dict(lab.get("cost_sensitivity") or {})
        monte = dict(lab.get("monte_carlo") or {})
        paper = dict(lab.get("paper_forward") or {})
        overfit = dict(lab.get("overfit_risk") or {})
        performance = dict(lab.get("performance") or {})
        minimum_gate = dict(lab.get("minimum_quality_gate") or {})
        monthly = list(performance.get("monthly_returns") or [])
        yearly = list(performance.get("yearly_returns") or [])
        period_lines = []
        if self._feature_enabled("monthly_yearly_table"):
            if yearly:
                period_lines.extend(["[연도별 수익률 표]", "기간 | 수익률 | 거래 수"])
                period_lines.extend(
                    f"{row.get('period')} | {float(row.get('return_percent', 0) or 0):+.2f}% | {int(row.get('trades', 0) or 0)}"
                    for row in yearly[-8:]
                )
            if monthly:
                period_lines.extend(["[최근 월별 수익률 표]", "기간 | 수익률 | 거래 수"])
                period_lines.extend(
                    f"{row.get('period')} | {float(row.get('return_percent', 0) or 0):+.2f}% | {int(row.get('trades', 0) or 0)}"
                    for row in monthly[-12:]
                )
        period_summary = "\n".join(period_lines) if period_lines else "월별·연별 표 없음(타임스탬프 또는 기능 설정 확인)"
        lab_summary = (
            f"총 PnL {float(performance.get('total_net_pnl', 0.0) or 0.0):+.2f} · "
            f"총 수익률 {float(performance.get('total_return_percent', 0.0) or 0.0):+.2f}% · "
            f"MDD {float(performance.get('max_drawdown_percent', 0.0) or 0.0):.2f}%\n"
            f"최소 통과조건 {'통과' if minimum_gate.get('passed') else '미통과: ' + ', '.join(minimum_gate.get('reasons', []) or [])}\n"
            f"미사용 표본 {int(sample.get('out_of_sample', 0) or 0)}건 · "
            f"워크포워드 통과율 {float(walkforward.get('pass_rate', 0.0) or 0.0) * 100:.1f}%\n"
            f"비용 2배 PnL {float(cost.get('cost_2x', 0.0) or 0.0):+.3f} · "
            f"몬테카를로 최악 MDD {float(monte.get('worst_max_drawdown', 0.0) or 0.0):.3f}\n"
            f"과최적화 경고 {'있음: ' + ', '.join(overfit.get('reasons', []) or []) if overfit.get('flagged') else '없음'} · "
            f"PAPER {int(paper.get('trades', 0) or 0)}건/{'통과' if paper.get('passed') else '미완료'}\n"
            f"승격 준비 {'예' if lab.get('promotion_ready') else '아니오'} · 백테스트만으로 자동 승격 안 함\n"
            f"{period_summary}"
        ) if lab else "검증 연구소 상세 없음"
        messagebox.showinfo(
            "자동 검증 결과",
            f"결과: {'통과' if passed else '미통과'}\n"
            f"거래소/심볼: {metrics.get('exchange', '-')} / {metrics.get('symbol', '-')}\n"
            f"조건 일치: {metrics.get('decisions', 0)}회\n"
            f"승률: {float(metrics.get('win_rate', 0.0) or 0.0) * 100:.1f}%\n"
            f"총비용 반영 PnL: {float(metrics.get('net_pnl_percent', 0.0) or 0.0):.2f}% "
            f"(비용 전 {float(metrics.get('gross_pnl_percent', 0.0) or 0.0):.2f}%)\n"
            f"총 가정비용: {float(metrics.get('total_cost_percent', 0.0) or 0.0):.2f}% · "
            f"거래당 왕복 {float(metrics.get('round_trip_cost_percent', 0.0) or 0.0):.3f}%\n"
            f"Profit Factor: {profit_factor_text} · "
            f"거래당 기대값: {float(metrics.get('expectancy_percent', 0.0) or 0.0):+.3f}%\n"
            f"최대 낙폭: {float(metrics.get('max_drawdown_percent', 0.0) or 0.0):.2f}%\n"
            f"국면별: {regime_summary}\n\n"
            f"[검증 연구소]\n{lab_summary}\n\n"
            "비용 가정은 진입·청산 수수료, 양방향 슬리피지, 왕복 스프레드를 포함합니다.\n"
            "실전 체결 품질과 수익을 보장하지 않는 보조 검증입니다.",
        )
        self.refresh_versions()

    def _show_validation_error(self, error: str):
        self.result_status.configure(text="자동 검증 실패", text_color="#ef4444")
        messagebox.showerror("자동 검증 실패", error)

    def _activate(self, item: Dict[str, Any], customizer, operation_mode: str = "standard"):
        runtime_cfg = dict(self._runtime_settings().get("ai_custom_runtime", {}) or {})
        if not bool(runtime_cfg.get("enabled", False)):
            messagebox.showwarning(
                "AI 커스텀 사용 꺼짐",
                f"{AI_CUSTOM_SETTINGS_PATH} → ‘AI 커스텀 전략을 실제 자동매매 엔진에서 사용’을 켜고 저장하세요.",
            )
            return
        if str(operation_mode or "standard").lower() == "limited_live" and not bool(runtime_cfg.get("allow_limited_live", False)):
            messagebox.showwarning(
                "제한운용 사용 꺼짐",
                "설정에서 ‘자동검증 미통과 전략의 1배·최대 1% 제한운용 선택 허용’을 켜고 저장하세요.",
            )
            return
        app = getattr(self.dashboard, "main_app", None)
        if app is not None and hasattr(app, "sync_custom_strategy_runtime_pools"):
            try:
                if len(app.sync_custom_strategy_runtime_pools()) >= 10:
                    messagebox.showwarning(
                        "활성 전략 한도",
                        "실행 중인 전략이 이미 10개입니다. 기존 전략 하나를 적용 해제한 뒤 다시 시도하세요.",
                    )
                    return
            except Exception:
                pass
        limited = str(operation_mode or "standard").lower() == "limited_live"
        if not messagebox.askyesno(
            "1% 제한운용 확인" if limited else "전략 최종 적용",
            f"{item.get('name', '사용자 전략')} v{item.get('version', '-')}를 적용할까요?\n\n"
            f"범위: {item.get('target_scope', '-')}\n시장상황: {', '.join(item.get('market_regimes') or ['all'])}\n"
            f"국면 기준: {item.get('regime_scope') or (item.get('rules') or {}).get('regime_scope') or 'market'}\n\n"
            + (
                "자동검증 미통과 결과를 이해하고 최소단위로 시험하는 선택입니다.\n"
                "레버리지 1배·전략 포지션 비중 최대 1%가 강제되며 기존 가드레일이 계속 우선합니다."
                if limited else
                "검증 통과 운용으로 활성화합니다. 전략 역할과 공통 계좌·주문 안전 경계가 함께 적용됩니다."
            ),
        ):
            return
        try:
            customizer.activate_custom_strategy(
                item.get("strategy_key"), item.get("version_id"), live_confirmation=True,
                operation_mode=operation_mode,
            )
            if app is not None and hasattr(app, "sync_custom_strategy_runtime_pools"):
                app.sync_custom_strategy_runtime_pools()
            messagebox.showinfo(
                "전략 적용 완료",
                ("전략이 1배·최대 1% 제한시험으로 활성화되었습니다. " if limited else "전략이 검증 통과 운용으로 활성화되었습니다. ")
                + "거래소 시작 후 범위·시장상황·진입조건이 맞을 때 자동 선택되며 차단 사유는 실시간 로그에 표시됩니다.",
            )
            self.refresh_versions()
        except Exception as exc:
            messagebox.showerror("전략 적용 실패", str(exc))

    def _deactivate(self, item: Dict[str, Any], customizer):
        if not messagebox.askyesno(
            "전략 적용 해제", f"{item.get('name', '사용자 전략')} v{item.get('version', '-')}를 활성 풀에서 뺄까요?"
        ):
            return
        try:
            customizer.deactivate_custom_strategy(
                item.get("strategy_key"), item.get("version_id"), approved_by="dashboard_user",
            )
            app = getattr(self.dashboard, "main_app", None)
            if app is not None and hasattr(app, "sync_custom_strategy_runtime_pools"):
                app.sync_custom_strategy_runtime_pools()
            self.refresh_versions()
        except Exception as exc:
            messagebox.showerror("적용 해제 실패", str(exc))
