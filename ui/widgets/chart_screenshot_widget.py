#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chart Screenshot Widget (CustomTkinter)

역할
- 사용자가 차트 스크린샷(JPG/PNG)을 선택 → 로컬 분석 수행
- OCR + 간단 파싱 + LLM 분석 결과를 텍스트/JSON 형태로 출력
"""

from __future__ import annotations

import os
import json
import threading
from typing import Optional, Any
import shutil
import time

import customtkinter as ctk
from tkinter import filedialog
import platform
import subprocess

try:
    # 선택: 이미지 미리보기 등에 사용 가능 (현재 미사용)
    from PIL import Image  # type: ignore
except Exception:
    Image = None  # type: ignore

from trading.ai.chart_screenshot_analyzer import ChartScreenshotAnalyzer
import logging
from path_utils import get_app_data_dir
from trading.ai.openai_client import OpenAIClient
from utils.fixed_colors import FIXED_COLORS


class ChartScreenshotWidget(ctk.CTkFrame):
    def __init__(self, master=None,
                 ai_client: Optional[OpenAIClient] = None,
                 api_key: Optional[str] = None,
                 **kwargs):
        super().__init__(master, **kwargs)
        # 대시보드와 일관된 패널 배경 적용
        try:
            self.configure(fg_color=self._color('panel', '#252d38'))
        except Exception:
            pass
        self._ai_client = ai_client
        self._api_key = api_key
        self._analyzer = ChartScreenshotAnalyzer(openai_client=self._ai_client, api_key=self._api_key)

        # UI
        self._build_ui()

    def _color(self, key: str, fallback: str = '#ffffff') -> str:
        """고정 스킨 색상 가져오기"""
        return FIXED_COLORS.get(key, fallback)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            self,
            text="📈 차트 이미지 분석기",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self._color('text_primary', '#f9fafb')
        )
        title.grid(row=0, column=0, sticky="w", pady=(8, 6), padx=10)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10)

        self.select_btn = ctk.CTkButton(
            btn_row,
            text="이미지 선택",
            command=self._on_select_image,
            width=120,
            fg_color=self._color('button_primary', '#1f6feb'),
            hover_color=self._color('button_primary_hover', '#1a5fd1')
        )
        self.select_btn.pack(side="left", padx=(0, 8), pady=4)

        self.help_btn = ctk.CTkButton(
            btn_row,
            text="사용방법",
            command=self._open_help_modal,
            width=100,
            fg_color=self._color('button_secondary', '#3a5a7f'),
            hover_color=self._color('button_secondary_hover', '#4a6a8f')
        )
        self.help_btn.pack(side="left", padx=(0, 8), pady=4)

        # 안정성 옵션: OCR 비활성화(LLM만)
        self.ocr_disable_var = ctk.BooleanVar(value=False)
        self.ocr_checkbox = ctk.CTkCheckBox(btn_row, text="OCR 비활성화(LLM만)", variable=self.ocr_disable_var)
        self.ocr_checkbox.pack(side="left", padx=(0, 8), pady=4)

        self.status_label = ctk.CTkLabel(btn_row, text="", text_color=self._color('text_secondary', '#9aa0a6'))
        self.status_label.pack(side="left")

        # 결과 렌더 영역(스크롤 가능)
        self.result_frame = ctk.CTkScrollableFrame(self, fg_color=self._color('surface', '#1f2632'))
        self.result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(8, 4))
        self.grid_rowconfigure(2, weight=1)

        # 원시 JSON 패널(기본 숨김)
        self.json_visible = False
        self.json_box = ctk.CTkTextbox(self, height=160)
        self.json_box.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.json_box.grid_remove()

        # 보조 버튼들
        aux = ctk.CTkFrame(self, fg_color="transparent")
        aux.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.toggle_json_btn = ctk.CTkButton(
            aux, text="JSON 보기", width=100, command=self._toggle_json,
            fg_color=self._color('button_secondary', '#3a5a7f'),
            hover_color=self._color('button_secondary_hover', '#4a6a8f')
        )
        self.toggle_json_btn.pack(side="left")
        self.copy_btn = ctk.CTkButton(
            aux, text="결과 복사", width=100, command=self._copy_result,
            fg_color=self._color('button_secondary', '#3a5a7f'),
            hover_color=self._color('button_secondary_hover', '#4a6a8f')
        )
        self.copy_btn.pack(side="left", padx=(8, 0))
        self.open_src_btn = ctk.CTkButton(
            aux, text="원본 열기", width=100, command=self._open_source,
            fg_color=self._color('button_secondary', '#3a5a7f'),
            hover_color=self._color('button_secondary_hover', '#4a6a8f')
        )
        self.open_src_btn.pack(side="left", padx=(8, 0))

        self._last_image_path = None
        self._last_result = None

    def _set_status(self, text: str) -> None:
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass

    def _on_select_image(self):
        # macOS Tk와 호환되는 안전한 filetypes 구성
        try:
            sysname = platform.system().lower()
            if sysname.startswith('darwin'):
                ftypes = [("이미지 파일", (".png", ".jpg", ".jpeg")), ("모든 파일", "*")]
            else:
                ftypes = [("이미지 파일", "*.png *.jpg *.jpeg"), ("모든 파일", "*")]
            path = filedialog.askopenfilename(filetypes=ftypes)
        except Exception:
            # filetypes 인자와 관련된 플랫폼 이슈 시, 기본 다이얼로그로 폴백
            path = filedialog.askopenfilename()
        if not path:
            return
        # 로컬 캐시에 사본 저장 (빌드 환경 포함) → 서버 업로드 없음
        cached = self._cache_copy(path)
        show_name = os.path.basename(cached or path)
        self._last_image_path = cached or path
        self._set_status(f"분석 중... {show_name}")
        self._clear_result()
        threading.Thread(target=self._analyze_safe, args=(cached or path,), daemon=True).start()

    def _analyze_safe(self, path: str) -> None:
        try:
            # 런타임 토글 상태 반영
            try:
                self._analyzer.disable_ocr = bool(self.ocr_disable_var.get())
            except Exception:
                pass
            result = self._analyzer.analyze(path)
            self._last_result = result if isinstance(result, dict) else None
            def _apply_ui() -> None:
                self._render_result(self._last_result or {})
                # 원시 JSON 패널 업데이트(숨김 상태 유지)
                try:
                    pretty = json.dumps(result, ensure_ascii=False, indent=2)
                    self.json_box.configure(state="normal")
                    self.json_box.delete("1.0", "end")
                    self.json_box.insert("1.0", pretty)
                    self.json_box.configure(state="disabled")
                    self._set_status("분석 완료")
                except Exception:
                    pass

            self.after(0, _apply_ui)
        except Exception as e:
            self.after(0, lambda: self._render_result({"error": str(e)}))

    def _cache_copy(self, src_path: str) -> Optional[str]:
        try:
            from path_utils import get_chart_uploads_cache_dir
            cache_dir = get_chart_uploads_cache_dir()
            ts = time.strftime('%Y%m%d_%H%M%S')
            name = os.path.basename(src_path)
            dst = os.path.join(cache_dir, f"{ts}_{name}")
            shutil.copy2(src_path, dst)
            return dst
        except Exception:
            return None

    # --- Help Modal ---
    def _open_help_modal(self) -> None:
        try:
            # 빌드에 포함된 docs/assets/chart_analyzer가 있으면 사용자 경로로 사전 복사(최초 1회)
            try:
                self._ensure_user_assets_from_packaged()
            except Exception:
                pass
            modal = ctk.CTkToplevel(self)
            modal.title("📈 차트 스크린샷 분석기 — 사용 가이드")
            modal.geometry("820x720")
            try:
                modal.update_idletasks()
                x = (modal.winfo_screenwidth() // 2) - (820 // 2)
                y = (modal.winfo_screenheight() // 2) - (720 // 2)
                modal.geometry(f"820x720+{x}+{y}")
            except Exception:
                pass

            # 탭 뷰로 깔끔하게 분리
            tabs = ctk.CTkTabview(modal)
            tabs.pack(fill="both", expand=True, padx=14, pady=14)
            tabs.add("빠른 시작")
            tabs.add("캡처 가이드")
            tabs.add("예시 결과")

            # 1) 빠른 시작
            quick = ctk.CTkScrollableFrame(tabs.tab("빠른 시작"))
            quick.pack(fill="both", expand=True, padx=10, pady=10)
            # 사용자 가이드(User Guide)와 문구를 일치시킨 간단한 개요
            steps = (
                "기능: 차트 이미지 업로드만으로 AI 분석\n"
                "├─ 지원 형식: JPG/PNG 스크린샷\n"
                "├─ 분석 결과: 롱/숏/중립, 시나리오, 진입/청산/목표\n"
                "├─ 접근: 대시보드 Quick Actions에서 실행\n"
                "└─ 로컬 처리: 서버 업로드 없이 로컬에서 분석\n\n"
                "사용법:\n"
                "1) 차트 스크린샷 선택 (JPG/PNG)\n"
                "2) 자동 OCR 텍스트 추출\n"
                "3) AI LLM 분석 수행\n"
                "4) JSON 형태로 결과 확인\n"
            )
            ctk.CTkLabel(quick, text=steps, justify="left").pack(anchor="w")
            # 예시 이미지는 빌드에 포함되어 자동 표시됩니다.

            # 2) 캡처 가이드 (이미지 포함)
            guide = ctk.CTkScrollableFrame(tabs.tab("캡처 가이드"))
            guide.pack(fill="both", expand=True, padx=10, pady=10)
            img1 = self._load_help_image("1.png")
            if img1 is not None:
                ctk.CTkLabel(guide, text="① 권장 캡처 영역(바이낸스 예시)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 6))
                frame1 = ctk.CTkFrame(guide)
                frame1.pack(fill="x", pady=(0, 12))
                ctk.CTkLabel(frame1, image=img1, text="").pack(anchor="w", padx=6, pady=6)
            else:
                ctk.CTkLabel(guide, text=self._missing_image_hint("1.png"), justify="left", text_color=self._color('text_secondary', '#9aa0a6')).pack(anchor="w")
            img2 = self._load_help_image("2.png")
            if img2 is not None:
                ctk.CTkLabel(guide, text="② 권장 캡처 영역(업비트 예시)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(4, 6))
                frame2 = ctk.CTkFrame(guide)
                frame2.pack(fill="x", pady=(0, 12))
                ctk.CTkLabel(frame2, image=img2, text="").pack(anchor="w", padx=6, pady=6)
            else:
                ctk.CTkLabel(guide, text=self._missing_image_hint("2.png"), justify="left", text_color=self._color('text_secondary', '#9aa0a6')).pack(anchor="w")

            # 3) 예시 결과(설명)
            sample = ctk.CTkScrollableFrame(tabs.tab("예시 결과"))
            sample.pack(fill="both", expand=True, padx=10, pady=10)
            ctk.CTkLabel(sample, text="카드 요약 예시", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            preview = ctk.CTkFrame(sample)
            preview.pack(fill="x", pady=(6,10))
            ctk.CTkLabel(preview, text="추천: LONG", text_color=self._color('success', '#22c55e'), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=6, pady=2)
            ctk.CTkLabel(preview, text="신뢰도: 78%", text_color=self._color('text_secondary', '#9aa0a6')).pack(anchor="w", padx=6)
            ctk.CTkLabel(preview, text="🎯 트레이딩 플랜", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=6, pady=(6,2))
            ctk.CTkLabel(preview, text="진입가: 61,234.5 | 손절: 60,321.0 | 목표: 61,800.0, 62,500.0").pack(anchor="w", padx=6)
            ctk.CTkLabel(preview, text="📚 시나리오", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=6, pady=(6,2))
            ctk.CTkLabel(preview, text="• 돌파 지속 (55%)").pack(anchor="w", padx=12)
            ctk.CTkLabel(preview, text="• 돌파 실패 (30%)").pack(anchor="w", padx=12)
            ctk.CTkLabel(preview, text="🧩 추출 정보", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=6, pady=(6,2))
            ctk.CTkLabel(preview, text="심볼: BTC/USDT | 타임프레임: 1H | MA20: 61,000").pack(anchor="w", padx=6)

            # JSON 예시(참고)
            example = (
                "{\n"
                "  \"stance\": \"LONG\",\n"
                "  \"confidence\": 0.78,\n"
                "  \"scenarios\": [ { \"title\": \"상승 지속\", \"prob\": 0.55 } ],\n"
                "  \"plan\": { \"entry\": 61234.5, \"stop\": 60321.0, \"tp\": [61800.0, 62500.0] }\n"
                "}\n"
            )
            ctk.CTkLabel(sample, text="JSON 예시(참고)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(8,0))
            box = ctk.CTkTextbox(sample, height=140)
            box.pack(fill="x", pady=6)
            box.insert("1.0", example)
            box.configure(state="disabled")

            # 해석 가이드(시간축/근거/목표가 운용)
            guide2 = ctk.CTkFrame(sample)
            guide2.pack(fill="x", pady=(12,4))
            ctk.CTkLabel(guide2, text="해석 가이드", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=6, pady=(2,4))
            tips = (
                "• 분석 범위: 스크린샷의 타임프레임이 곧 분석 시간축입니다. 1H/15M이면 단기, 1D/1W면 중·장기 관점입니다.\n"
                "• 즉시 활용: entry/stop/tp는 캡처 시점 기준 추정값이며, 캡처 후 가격이 크게 변했으면 재캡처를 권장합니다.\n"
                "• 신뢰도 근거: OCR로 추출한 가격/MA/패턴 일치도와 LLM의 내부 일관성 점수로 산출합니다. 값이 낮으면 재촬영(가격축/심볼 포함)하세요.\n"
                "• 트레이딩 플랜 근거: price_range/median/top_prices_hint를 기반으로 보수적/공격적 시나리오를 조합합니다.\n"
                "• 목표가 운용: tp는 ‘도달 가능 구간’이며 전체 물량 고정 대기 의미가 아닙니다. 보통 분할 청산(1차→2차) 또는 트레일링을 권장합니다.\n"
                "• 업비트 차트: KRW-심볼 캡처를 권장하고, 가격 단위는 원화(KRW)로 해석합니다."
            )
            ctk.CTkLabel(sample, text=tips, justify="left").pack(anchor="w", padx=10)

            # 하단 버튼
            bottom = ctk.CTkFrame(modal)
            bottom.pack(fill="x", padx=14, pady=(0, 14))
            ctk.CTkButton(bottom, text="닫기", command=modal.destroy, width=100).pack(side="right")
        except Exception:
            pass

    def _ensure_user_assets_from_packaged(self) -> None:
        try:
            from path_utils import get_chart_analyzer_assets_dir
            user_dir = get_chart_analyzer_assets_dir()
            # 후보: 빌드 패키지 docs/assets, 패키지 assets
            candidates = []
            try:
                from path_utils import get_app_base_dir
                candidates.append(os.path.join(get_app_base_dir(), 'docs', 'assets', 'chart_analyzer'))
                candidates.append(os.path.join(get_app_base_dir(), 'assets', 'chart_analyzer'))
            except Exception:
                pass
            copied_any = False
            for name in ('1.png', '2.png'):
                dst = os.path.join(user_dir, name)
                if os.path.exists(dst):
                    continue
                for c in candidates:
                    src = os.path.join(c, name)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
                        copied_any = True
                        break
            if copied_any:
                # 상태 업데이트
                self._set_status("가이드 이미지를 사용자 폴더로 준비했습니다")
        except Exception:
            pass

    def _candidate_asset_paths(self, filename: str) -> list[str]:
        # 검색 우선순위: 사용자 데이터 경로 > 실행 파일(또는 패키지) assets > 개발 경로
        try:
            from path_utils import get_app_base_dir
        except Exception:
            def get_app_base_dir():
                return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        from path_utils import get_chart_analyzer_assets_dir
        app_data = get_chart_analyzer_assets_dir()
        # 빌드 패키지 포함 자원: 실행 경로/assets 및 실행 경로/docs/assets 모두 검색
        app_base_assets = os.path.join(get_app_base_dir(), "assets", "chart_analyzer")
        app_base_docs_assets = os.path.join(get_app_base_dir(), "docs", "assets", "chart_analyzer")
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return [
            os.path.join(app_data, filename),              # 사용자 관리(빌드/개발 공통)
            os.path.join(app_base_assets, filename),       # 빌드 패키징된 정적 자원(권장 배치)
            os.path.join(app_base_docs_assets, filename),  # 빌드된 docs 포함 자원
            os.path.join(repo_root, "docs", "assets", "chart_analyzer", filename),
            os.path.join(repo_root, "ui", "assets", "chart_analyzer", filename),
        ]

    def _load_help_image(self, filename: str) -> Optional[Any]:
        if Image is None:
            return None
        try:
            debug = os.getenv('NOAHAI_DEBUG_ASSETS', '0') == '1'
            logger = logging.getLogger(__name__)
            paths = self._candidate_asset_paths(filename)
            for p in paths:
                if debug:
                    logger.info(f"[assets] probe: {p}")
                if os.path.exists(p):
                    # 너비 기준으로 적당히 축소 표시
                    img = Image.open(p)
                    max_w = 640
                    ratio = min(1.0, max_w / max(1, img.width))
                    size = (int(img.width * ratio), int(img.height * ratio))
                    ctki = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                    if debug:
                        logger.info(f"[assets] loaded: {p}")
                    return ctki
            if debug:
                logger.warning(f"[assets] not found: {filename}")
        except Exception:
            return None
        return None

    def _missing_image_hint(self, filename: str) -> str:
        # 빌드에 예시 이미지가 포함되지 않은 경우
        return "예시 이미지가 준비되지 않았습니다. (빌드 패키징 누락)"

    # 사용자 자산 폴더 열기 기능은 제거(예시 이미지는 빌드 포함이 기본)

    # --- 결과 렌더링 보조 ---
    def _clear_result(self) -> None:
        try:
            for w in self.result_frame.winfo_children():
                w.destroy()
        except Exception:
            pass

    def _render_row(self, parent, label: str, value: str, color: Optional[str] = None, wrap: bool = False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, width=110, anchor="w", text_color=self._color('text_secondary', '#9aa0a6')).pack(side="left")
        kwargs = {}
        if wrap:
            # 대략적인 랩 길이(패딩 감안)
            try:
                wl = max(320, int(self.winfo_width() * 0.7))
            except Exception:
                wl = 520
            kwargs['wraplength'] = wl
            kwargs['justify'] = 'left'
        value_color = color or self._color('text_primary', '#f9fafb')
        ctk.CTkLabel(row, text=value, anchor="w", text_color=value_color, **kwargs).pack(side="left", fill="x", expand=True)

    def _render_result(self, result: dict) -> None:
        self._clear_result()
        root = self.result_frame
        # 경고/오류
        warn = (result or {}).get("warning")
        err = (result or {}).get("error")
        if warn:
            ctk.CTkLabel(root, text=f"⚠️ {warn}", text_color=self._color('warning', '#f59e0b')).pack(anchor="w", pady=(0,4))
        if err:
            ctk.CTkLabel(root, text=f"❌ 오류: {err}", text_color=self._color('danger', '#ef4444')).pack(anchor="w", pady=(0,4))

        # 상단 요약 (스탠스/신뢰도)
        head = ctk.CTkFrame(root)
        head.pack(fill="x", pady=(0,6))
        analysis = (result or {}).get("analysis") or {}
        stance = str(analysis.get("stance") or "-")
        conf = analysis.get("confidence")
        success_color = self._color('success', '#22c55e')
        danger_color = self._color('danger', '#ef4444')
        neutral_color = self._color('text_secondary', '#95a5a6')
        stance_upper = stance.upper()
        color = success_color if stance_upper == "LONG" else danger_color if stance_upper == "SHORT" else neutral_color
        ctk.CTkLabel(head, text=f"추천: {stance}", text_color=color, font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=(0,8))
        if conf is not None:
            try:
                pct = f"신뢰도: {float(conf)*100:.0f}%"
            except Exception:
                pct = f"신뢰도: {conf}"
            ctk.CTkLabel(head, text=pct, text_color=self._color('text_secondary', '#9aa0a6')).pack(side="left")

        # 플랜 (진입/손절/익절)
        plan = analysis.get("plan") or {}
        block = ctk.CTkFrame(root)
        block.pack(fill="x", pady=(4,6))
        ctk.CTkLabel(block, text="🎯 트레이딩 플랜", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        entry = plan.get("entry")
        stop = plan.get("stop")
        tps = plan.get("tp") or []
        def _fmt(n):
            try:
                f = float(n)
                return f"{f:,.4f}" if f < 1000 else f"{f:,.2f}"
            except Exception:
                return str(n)
        self._render_row(block, "진입가", "-" if entry in (None, "") else _fmt(entry))
        self._render_row(block, "손절", "-" if stop in (None, "") else _fmt(stop), color=self._color('danger', '#ef4444'))
        self._render_row(block, "목표가", ", ".join(_fmt(x) for x in tps) if tps else "-", color=self._color('success', '#22c55e'))
        notes = plan.get("notes")
        if notes:
            # 긴 메모 줄바꿈
            try:
                wl = max(320, int(self.winfo_width() * 0.86))
            except Exception:
                wl = 560
            ctk.CTkLabel(block, text=f"메모: {notes}", text_color=self._color('text_secondary', '#9aa0a6'), wraplength=wl, justify='left').pack(anchor="w", pady=(2,0))

        # 시나리오
        scenarios = analysis.get("scenarios") or []
        if scenarios:
            scf = ctk.CTkFrame(root)
            scf.pack(fill="x", pady=(4,6))
            ctk.CTkLabel(scf, text="📚 시나리오", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            for sc in scenarios[:5]:
                title = sc.get("title") or "-"
                prob = sc.get("prob")
                try:
                    ptxt = f"{float(prob)*100:.0f}%" if prob is not None else "-"
                except Exception:
                    ptxt = str(prob)
                ctk.CTkLabel(scf, text=f"• {title} ({ptxt})", anchor="w").pack(anchor="w")
                narrative = sc.get('narrative') or sc.get('comment') or ''
                if narrative:
                    try:
                        wl = max(320, int(self.winfo_width() * 0.86))
                    except Exception:
                        wl = 560
                    ctk.CTkLabel(scf, text=f"  - {narrative}", text_color=self._color('text_secondary', '#9aa0a6'), wraplength=wl, justify='left').pack(anchor="w")

        # 추출된 특징(심볼/TF/MA)
        feat = (result or {}).get("features") or {}
        ff = ctk.CTkFrame(root)
        ff.pack(fill="x", pady=(4,6))
        ctk.CTkLabel(ff, text="🧩 추출 정보", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        self._render_row(ff, "심볼", str(feat.get("symbol") or "-"))
        self._render_row(ff, "타임프레임", str(feat.get("timeframe") or "-"))
        mas = feat.get("moving_averages") or {}
        if mas:
            # 이동평균은 길 수 있으니 줄바꿈 허용
            self._render_row(ff, "이동평균", ", ".join(f"{k}:{v}" for k,v in mas.items()), wrap=True)
        tps = feat.get("top_prices_hint") or []
        if tps:
            self._render_row(ff, "가격 힌트", ", ".join(_fmt(x) for x in tps))

    def _toggle_json(self):
        try:
            self.json_visible = not self.json_visible
            if self.json_visible:
                self.json_box.grid()
                self.toggle_json_btn.configure(text="JSON 숨기기")
            else:
                self.json_box.grid_remove()
                self.toggle_json_btn.configure(text="JSON 보기")
        except Exception:
            pass

    def _copy_result(self):
        try:
            if not self._last_result:
                return
            pretty = json.dumps(self._last_result, ensure_ascii=False, indent=2)
            self.clipboard_clear()
            self.clipboard_append(pretty)
            self._set_status("결과 복사됨")
        except Exception:
            pass

    def _open_source(self):
        try:
            if not self._last_image_path:
                return
            sysname = platform.system().lower()
            if sysname.startswith('darwin'):
                subprocess.Popen(['open', self._last_image_path])
            elif sysname.startswith('win'):
                os.startfile(self._last_image_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(['xdg-open', self._last_image_path])
        except Exception:
            pass
