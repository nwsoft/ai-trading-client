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
from trading.strategy_source_ingestor import StrategySourceIngestor


class CustomStrategyWidget(ctk.CTkScrollableFrame):
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

    def __init__(self, master, *, dashboard=None, settings: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(master, fg_color="#0b1120", corner_radius=0, **kwargs)
        self.dashboard = dashboard
        self.settings = settings or {}
        self.analysis_result: Optional[Dict[str, Any]] = None
        self.version_target_map: Dict[str, Any] = {}
        self._build()
        self.refresh_versions()

    def _font(self, size: int, weight: str = "normal"):
        return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)

    def _runtime_settings(self) -> Dict[str, Any]:
        dashboard_settings = getattr(self.dashboard, "settings", None)
        return dashboard_settings if isinstance(dashboard_settings, dict) else self.settings

    def _selected_ai_model(self) -> str:
        settings = self._runtime_settings()
        roles = settings.get("ai_model_roles", {}) or {}
        return str(roles.get("premium") or settings.get("openai_model") or "gpt-5.6-terra")

    def _open_ai_settings(self):
        opener = getattr(self.dashboard, "show_settings_dialog", None)
        if callable(opener):
            opener()
        else:
            messagebox.showinfo(
                "AI 모델 설정",
                "대시보드 상단 설정 → OpenAI API → 정밀 진단·최적화(고성능 모델)에서 설정하세요.",
            )

    def _refresh_ai_model_status(self) -> None:
        if not hasattr(self, "ai_model_status"):
            return
        api_ready = bool(
            str(self._runtime_settings().get("openai_api_key", "") or "").strip()
            or str(os.getenv("OPENAI_API_KEY", "") or "").strip()
        )
        self.ai_model_status.configure(
            text=(
                f"사용 AI: {self._selected_ai_model()} · 정밀 분석 역할"
                if api_ready else "OpenAI API 미설정 · 규칙 기반 1차 추출만 가능"
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
                "텍스트·Pine Script·PDF·차트 이미지(OCR)·로컬 영상·YouTube·TradingView 자료를 분석해 "
                "진입/청산/손절/익절/포지션/시장조건과 엔진 설정 초안으로 변환합니다. 누락 조건은 추정하지 않습니다."
            ),
            font=self._font(13), text_color="#a9bad0", justify="left", wraplength=1120,
        ).pack(anchor="w", padx=18, pady=(0, 14))

        ai_status_row = ctk.CTkFrame(header, fg_color="#0b1120", corner_radius=10)
        ai_status_row.pack(fill="x", padx=18, pady=(0, 12))
        api_ready = bool(
            str(self._runtime_settings().get("openai_api_key", "") or "").strip()
            or str(os.getenv("OPENAI_API_KEY", "") or "").strip()
        )
        self.ai_model_status = ctk.CTkLabel(
            ai_status_row,
            text=(
                f"사용 AI: {self._selected_ai_model()} · 정밀 분석 역할"
                if api_ready else
                "OpenAI API 미설정 · 규칙 기반 1차 추출만 가능"
            ),
            font=self._font(12, "bold"), text_color=("#38bdf8" if api_ready else "#f59e0b"),
        )
        self.ai_model_status.pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            ai_status_row,
            text="설정 경로: 설정 → OpenAI API → 정밀 진단·최적화",
            font=self._font(11), text_color="#91a4bd",
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            ai_status_row, text="AI 모델 설정 열기", width=130, height=30,
            command=self._open_ai_settings,
        ).pack(side="right", padx=8, pady=6)

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
            placeholder_text="YouTube/TradingView URL 또는 PDF·이미지·영상·Pine 파일 경로",
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
                "분석 범위: PDF 앞 100쪽·AI 입력 60,000자 / 영상·YouTube 대표 장면 최대 9개 / "
                "보호된 TradingView는 본인 Pine 코드 입력 필요"
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
        self.regime_combo = ctk.CTkComboBox(action, values=list(self.REGIME_LABELS), width=145, height=36)
        self.regime_combo.set("모든 시장상황")
        self.regime_combo.pack(side="left")
        ctk.CTkLabel(action, text="우선순위", font=self._font(11), text_color="#91a4bd").pack(side="left", padx=(14, 6))
        self.priority_combo = ctk.CTkComboBox(action, values=[str(v) for v in range(10, 0, -1)], width=70, height=36)
        self.priority_combo.set("5")
        self.priority_combo.pack(side="left")

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

        result_card = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        result_card.pack(fill="x", padx=14, pady=8)
        result_header = ctk.CTkFrame(result_card, fg_color="transparent")
        result_header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(result_header, text="2. XAI 분석 결과와 적용값", font=self._font(16, "bold"), text_color="#f8fafc").pack(side="left")
        self.result_status = ctk.CTkLabel(result_header, text="분석 전", font=self._font(12), text_color="#94a3b8")
        self.result_status.pack(side="right")
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
        self.save_button = ctk.CTkButton(save_row, text="검토용 전략 버전 저장", width=190, height=38, state="disabled", command=self._save_version)
        self.save_button.pack(side="right")

        self.versions_card = ctk.CTkFrame(self, fg_color="#111827", corner_radius=16, border_width=1, border_color="#273449")
        self.versions_card.pack(fill="x", padx=14, pady=(8, 16))
        title_row = ctk.CTkFrame(self.versions_card, fg_color="transparent")
        title_row.pack(fill="x", padx=16, pady=(13, 7))
        ctk.CTkLabel(title_row, text="3. 내 프라이빗 전략 버전", font=self._font(16, "bold"), text_color="#f8fafc").pack(side="left")
        ctk.CTkButton(title_row, text="새로고침", width=90, height=30, command=self.refresh_versions).pack(side="right")
        self.active_pool_label = ctk.CTkLabel(
            title_row, text="활성 전략 0/10", font=self._font(12, "bold"), text_color="#22c55e"
        )
        self.active_pool_label.pack(side="right", padx=12)
        self.version_rows = ctk.CTkFrame(self.versions_card, fg_color="transparent")
        self.version_rows.pack(fill="x", padx=12, pady=(0, 12))

    def _choose_file(self):
        path = filedialog.askopenfilename(
            title="전략 자료 선택",
            filetypes=[
                ("지원 파일", "*.pdf *.pine *.txt *.png *.jpg *.jpeg *.webp *.mp4 *.mov *.mkv *.avi"),
                ("모든 파일", "*.*"),
            ],
        )
        if path:
            self.reference_entry.delete(0, "end")
            self.reference_entry.insert(0, path)
            self.kind_combo.set("자동 판별")

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
        threading.Thread(target=self._analyze_worker, args=(value,), daemon=True).start()

    def _analyze_worker(self, value: str):
        try:
            settings = self._runtime_settings()
            model = self._selected_ai_model()
            client = OpenAIClient(
                api_key=str(settings.get("openai_api_key", "") or ""),
                model=model,
                base_url=str(settings.get("openai_base_url", "") or "") or None,
            )
            kind = self.SOURCE_LABELS.get(self.kind_combo.get(), "auto")
            result = StrategySourceIngestor(client if client.is_ready() else None).analyze(value, kind)
            result["ai_model"] = model if client.is_ready() else "규칙 기반 추출(API 미사용)"
            self.after(0, lambda: self._show_analysis(result))
        except Exception as exc:
            self.after(0, lambda: self._show_error(str(exc)))

    def _show_analysis(self, result: Dict[str, Any]):
        self.analysis_result = result
        source = result.get("source", {}) or {}
        missing = result.get("missing_conditions", []) or []
        lines = [
            f"전략명: {result.get('name', '-')}",
            f"입력 형식: {source.get('kind', '-')} / 출처: {source.get('reference', '-')}",
            f"사용 AI: {result.get('ai_model', '-')}",
            f"AI 구조화: {'완료' if result.get('ai_analyzed') else '규칙 기반 1차 추출(API 미사용)'}",
            f"분석 범위: {source.get('coverage_summary', '입력 원문 기준')}",
            "",
            f"요약: {result.get('summary', '-')}",
            "",
            "[규칙]",
            json.dumps(result.get("rules", {}), ensure_ascii=False, indent=2),
            "",
            "[실행 엔진 설정값]",
            json.dumps(result.get("engine_settings", {}), ensure_ascii=False, indent=2),
            "",
            "[누락/재확인]",
            "없음" if not missing else "\n".join(f"- {item}" for item in missing),
            "",
            "[위험/주의]",
            "\n".join(f"- {item}" for item in (result.get("risks", []) or [])),
            "",
            "[추출 경고]",
            "없음" if not source.get("warnings") else "\n".join(f"- {item}" for item in source.get("warnings", [])),
        ]
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "\n".join(lines))
        self.result_text.configure(state="disabled")
        self.result_status.configure(
            text="조건 재확인 필요" if missing else "저장 가능 · 승인 전 실행 차단",
            text_color="#f59e0b" if missing else "#22c55e",
        )
        self.analyze_button.configure(state="normal", text="AI 분석 및 전략 초안 만들기")
        self.save_button.configure(state="normal")

    def _show_error(self, error: str):
        self.analysis_result = None
        self.result_status.configure(text="분석 실패", text_color="#ef4444")
        self.analyze_button.configure(state="normal", text="AI 분석 및 전략 초안 만들기")
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
        scope = self._scope_value()
        target = self._target_value()
        regimes = list(self.REGIME_LABELS.get(self.regime_combo.get(), ["all"]))
        rules["target_exchange"] = target if scope.startswith("exchange:") else ""
        rules["target_scope"] = scope
        rules["market_regimes"] = regimes
        rules["priority"] = int(self.priority_combo.get() or 5)
        strategy_id = customizer.create_custom_strategy({
            "name": self.analysis_result.get("name", "사용자 전략"),
            "rules": rules,
            "base_params": engine,
            "source_kind": source.get("kind", "text"),
            "source_reference": source.get("reference", ""),
            "target_exchange": target if scope.startswith("exchange:") else "",
            "target_scope": scope,
            "market_regimes": regimes,
            "priority": int(self.priority_combo.get() or 5),
            "strategy_key": selected_target[1] if selected_target else None,
        })
        messagebox.showinfo(
            "전략 버전 저장",
            f"검토용 전략이 저장되었습니다.\n\nID: {strategy_id}\n적용 범위: {self.target_combo.get()}\n"
            f"시장상황: {self.regime_combo.get()}\n승인·실행검증 전에는 거래에 적용되지 않습니다.",
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
        if hasattr(self, "active_pool_label"):
            self.active_pool_label.configure(text=f"활성 전략 {active_count}/10")
        rows = rows[:10]
        if not rows:
            ctk.CTkLabel(self.version_rows, text="저장된 전략이 없습니다.", font=self._font(12), text_color="#94a3b8").pack(anchor="w", padx=6, pady=10)
            return
        labels = {
            "needs_clarification": "조건 재확인 필요", "analyzed": "XAI 완료 · 승인 대기",
            "approved": "승인 완료 · 실행 검증 대기", "paper_validated": "검증 완료 · 최종 적용 대기",
            "execution_validated": "실행 검증 완료 · 최종 적용 대기", "active": "적용 중",
            "paper_rejected": "검증 미통과", "execution_rejected": "검증 미통과",
        }
        for scope, item, customizer in rows:
            row = ctk.CTkFrame(self.version_rows, fg_color="#172033", corner_radius=10)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row, text=(
                    f"{scope_names.get(scope.lower(), scope)} · {item.get('name', '사용자 전략')} · "
                    f"v{item.get('version', '-')} · 우선 {item.get('priority', 5)}"
                ),
                font=self._font(12, "bold"), text_color="#e5edf6",
            ).pack(side="left", padx=12, pady=10)
            status = str(item.get("status", "unknown"))
            if status == "analyzed":
                ctk.CTkButton(
                    row, text="내용 확인 후 승인", width=125, height=30,
                    command=lambda it=item, c=customizer: self._approve(it, c),
                ).pack(side="right", padx=8)
            elif status == "approved":
                ctk.CTkButton(
                    row, text="실행 검증 기록", width=115, height=30,
                    command=lambda it=item, c=customizer: self._record_validation(it, c),
                ).pack(side="right", padx=8)
            elif status in {"execution_validated", "paper_validated"}:
                ctk.CTkButton(
                    row, text="최종 적용", width=90, height=30,
                    fg_color="#10b981", hover_color="#059669",
                    command=lambda it=item, c=customizer: self._activate(it, c),
                ).pack(side="right", padx=8)
            elif status == "active":
                ctk.CTkButton(
                    row, text="적용 해제", width=90, height=30,
                    fg_color="#475569", hover_color="#64748b",
                    command=lambda it=item, c=customizer: self._deactivate(it, c),
                ).pack(side="right", padx=8)
            ctk.CTkLabel(row, text=labels.get(status, status), font=self._font(11), text_color="#a9bad0").pack(side="right", padx=8)

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
        decisions_dialog = ctk.CTkInputDialog(
            title="실행 검증 결과", text="실제 시장 관찰/과거 재생/제한 운용에서 확인한 의사결정 수를 입력하세요. (최소 3)"
        )
        value = decisions_dialog.get_input()
        if value is None:
            return
        try:
            decisions = int(value)
        except (TypeError, ValueError):
            messagebox.showerror("입력 오류", "의사결정 수는 정수로 입력하세요.")
            return
        mode_dialog = ctk.CTkInputDialog(
            title="검증 방식", text="검증 방식을 입력하세요: live_observation / historical_replay / limited_live"
        )
        mode = str(mode_dialog.get_input() or "live_observation").strip().lower()
        try:
            customizer.record_execution_validation(
                item.get("strategy_key"), item.get("version_id"), decisions=decisions,
                guardrail_violations=0, metrics={"recorded_from": "dashboard"}, mode=mode,
            )
            messagebox.showinfo("실행 검증 기록", "검증 결과를 전략 버전에 연결했습니다. 통과 상태를 확인하세요.")
            self.refresh_versions()
        except Exception as exc:
            messagebox.showerror("검증 기록 실패", str(exc))

    def _activate(self, item: Dict[str, Any], customizer):
        if not messagebox.askyesno(
            "전략 최종 적용",
            f"{item.get('name', '사용자 전략')} v{item.get('version', '-')}를 적용할까요?\n\n"
            f"범위: {item.get('target_scope', '-')}\n시장상황: {', '.join(item.get('market_regimes') or ['all'])}\n\n"
            "최대손실·포지션·집중도·시장위험 가드레일은 계속 우선합니다.",
        ):
            return
        try:
            customizer.activate_custom_strategy(
                item.get("strategy_key"), item.get("version_id"), live_confirmation=True,
            )
            app = getattr(self.dashboard, "main_app", None)
            if app is not None and hasattr(app, "sync_custom_strategy_runtime_pools"):
                app.sync_custom_strategy_runtime_pools()
            messagebox.showinfo("전략 적용 완료", "승인 전략이 활성 전략 풀에 추가되었습니다. 시장상황에 맞을 때 자동 선택됩니다.")
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
