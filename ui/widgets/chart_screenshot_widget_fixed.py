#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chart Screenshot Widget (CustomTkinter)

기능:
- 사용자가 차트 스크린샷(JPG/PNG)을 선택 후 로컬 분석 수행
- OCR + 간단 파싱 + LLM 분석 결과를 텍스트 및 JSON 형태로 출력
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
    # 선택: 이미지 미리보기 등에 사용 가능(현재 미사용)
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
                 colors: Optional[dict] = None,
                 **kwargs):
        super().__init__(master, **kwargs)
        self._ai_client = ai_client
        self._api_key = api_key
        self.colors = colors or {}
        self._analyzer = ChartScreenshotAnalyzer(openai_client=self._ai_client, api_key=self._api_key)

        # UI
        self._build_ui()

    def _color(self, key: str, fallback: str = '#ffffff') -> str:
        """고정 스킨 색상 가져오기"""
        return FIXED_COLORS.get(key, fallback)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # 제목
        title = ctk.CTkLabel(self, text="차트 스크린샷 자동 AI 분석 시스템", 
                            font=ctk.CTkFont(size=14, weight="bold"))
        title.grid(row=0, column=0, sticky="w", pady=(8, 6), padx=10)

        # 버튼 행
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10)

        self.select_btn = ctk.CTkButton(btn_row, text="이미지 선택", 
                                       command=self._on_select_image, width=120)
        self.select_btn.pack(side="left", padx=(0, 8), pady=4)

        self.help_btn = ctk.CTkButton(btn_row, text="사용방법", 
                                      command=self._open_help_modal, width=100)
        self.help_btn.pack(side="left", padx=(0, 8), pady=4)

        # 설정 옵션: OCR 비활성화(LLM만)
        self.ocr_disable_var = ctk.BooleanVar(value=False)
        self.ocr_checkbox = ctk.CTkCheckBox(btn_row, text="OCR 비활성화(LLM만)", 
                                           variable=self.ocr_disable_var)
        self.ocr_checkbox.pack(side="left", padx=(0, 8), pady=4)

        self.status_label = ctk.CTkLabel(btn_row, text="", 
                                        text_color=self._color('text_secondary', '#9aa0a6'))
        self.status_label.pack(side="left")

        # 결과 표시 영역(스크롤 가능)
        self.result_frame = ctk.CTkScrollableFrame(self)
        self.result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(8, 4))
        self.grid_rowconfigure(2, weight=1)

        # 하단 JSON 패널(기본 숨김)
        self.json_visible = False
        self.json_box = ctk.CTkTextbox(self, height=160)
        self.json_box.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.json_box.grid_remove()

        # 보조 버튼행
        aux = ctk.CTkFrame(self, fg_color="transparent")
        aux.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        self.toggle_json_btn = ctk.CTkButton(aux, text="JSON 보기", width=100, 
                                            command=self._toggle_json)
        self.toggle_json_btn.pack(side="left")
        
        self.copy_btn = ctk.CTkButton(aux, text="결과 복사", width=100, 
                                     command=self._copy_result)
        self.copy_btn.pack(side="left", padx=(8, 0))
        
        self.open_src_btn = ctk.CTkButton(aux, text="원본 열기", width=100, 
                                         command=self._open_source)
        self.open_src_btn.pack(side="left", padx=(8, 0))

        self._last_image_path: Optional[str] = None
        self._last_result: Optional[dict] = None

    def _set_status(self, msg: str) -> None:
        """상태 메시지 표시"""
        self.status_label.configure(text=msg)

    def _on_select_image(self) -> None:
        """이미지 파일 선택 및 분석 수행"""
        path = filedialog.askopenfilename(
            title="차트 스크린샷 선택",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        self._last_image_path = path
        self._set_status("분석 중...")
        self.select_btn.configure(state="disabled")

        def _analyze() -> None:
            try:
                use_ocr = not self.ocr_disable_var.get()
                result = self._analyzer.analyze_from_path(path, use_ocr=use_ocr)
                self._last_result = result
                self.after(0, lambda: self._display_result(result))
            except Exception as e:
                logging.error(f"차트 분석 오류: {e}")
                self.after(0, lambda: self._set_status(f"분석 오류: {str(e)}"))
            finally:
                self.after(0, lambda: self.select_btn.configure(state="normal"))

        threading.Thread(target=_analyze, daemon=True).start()

    def _display_result(self, result: dict) -> None:
        """분석 결과 표시"""
        # 기존 결과 제거
        for widget in self.result_frame.winfo_children():
            widget.destroy()

        self._set_status("분석 완료")

        # 결과 표시
        summary_frame = ctk.CTkFrame(self.result_frame)
        summary_frame.pack(fill="x", padx=10, pady=5)

        title = ctk.CTkLabel(summary_frame, text="분석 결과", 
                           font=ctk.CTkFont(size=13, weight="bold"))
        title.pack(anchor="w", padx=10, pady=(10, 5))

        # 분석 내용 표시
        analysis_text = result.get("analysis", {}).get("summary", "분석 내용 없음")
        text_box = ctk.CTkTextbox(summary_frame, height=200, wrap="word")
        text_box.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        text_box.insert("1.0", analysis_text)
        text_box.configure(state="disabled")

        # 추천 진입가/손절/익절 표시
        plan = result.get("analysis", {}).get("plan", {})
        if plan:
            plan_frame = ctk.CTkFrame(self.result_frame)
            plan_frame.pack(fill="x", padx=10, pady=5)

            plan_title = ctk.CTkLabel(plan_frame, text="거래 계획", 
                                     font=ctk.CTkFont(size=13, weight="bold"))
            plan_title.pack(anchor="w", padx=10, pady=(10, 5))

            plan_text = f"진입가: {plan.get('entry', 'N/A')}\n"
            plan_text += f"손절가: {plan.get('stop', 'N/A')}\n"
            plan_text += f"목표가: {plan.get('tp', 'N/A')}"

            plan_label = ctk.CTkLabel(plan_frame, text=plan_text, justify="left")
            plan_label.pack(anchor="w", padx=20, pady=(0, 10))

    def _toggle_json(self) -> None:
        """JSON 패널 토글"""
        self.json_visible = not self.json_visible
        if self.json_visible:
            self.json_box.grid()
            self.toggle_json_btn.configure(text="JSON 숨기기")
            if self._last_result:
                json_str = json.dumps(self._last_result, ensure_ascii=False, indent=2)
                self.json_box.delete("1.0", "end")
                self.json_box.insert("1.0", json_str)
        else:
            self.json_box.grid_remove()
            self.toggle_json_btn.configure(text="JSON 보기")

    def _copy_result(self) -> None:
        """결과를 클립보드에 복사"""
        if not self._last_result:
            return
        try:
            json_str = json.dumps(self._last_result, ensure_ascii=False, indent=2)
            self.clipboard_clear()
            self.clipboard_append(json_str)
            self._set_status("결과가 클립보드에 복사되었습니다")
        except Exception as e:
            self._set_status(f"복사 오류: {str(e)}")

    def _open_source(self) -> None:
        """원본 이미지 열기"""
        if not self._last_image_path or not os.path.exists(self._last_image_path):
            return
        try:
            sysname = platform.system().lower()
            if 'darwin' in sysname:
                subprocess.Popen(['open', self._last_image_path])
            elif sysname.startswith('win'):
                os.startfile(self._last_image_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(['xdg-open', self._last_image_path])
        except Exception:
            pass

    def _open_help_modal(self) -> None:
        """사용 가이드 모달 열기"""
        try:
            modal = ctk.CTkToplevel(self)
            modal.title("차트 스크린샷 분석 사용 가이드")
            modal.geometry("820x720")
            try:
                modal.update_idletasks()
                x = (modal.winfo_screenwidth() // 2) - (820 // 2)
                y = (modal.winfo_screenheight() // 2) - (720 // 2)
                modal.geometry(f"820x720+{x}+{y}")
            except Exception:
                pass

            modal.transient(self.master if self.master else self)

            tabs = ctk.CTkTabview(modal)
            tabs.pack(fill="both", expand=True, padx=10, pady=10)

            # 사용법 탭
            usage_tab = tabs.add("사용법")
            usage_text = """
차트 스크린샷 AI 분석 시스템

1⃣ 이미지 준비
   • 거래소 차트 스크린샷 (JPG/PNG)
   • 캔들, 이동평균선, 지표가 보이는 차트

2⃣ 분석 실행
   • "이미지 선택" 버튼 클릭
   • 차트 이미지 파일 선택
   • 자동 분석 시작 (10-30초 소요)

3⃣ 결과 확인
   • AI 분석 요약 (시장 상황, 추세, 패턴)
   • 거래 계획 (진입가, 손절가, 목표가)
   • JSON 데이터 (상세 정보)

4⃣ 옵션 설정
   • OCR 비활성화: LLM만 사용 (빠름)
   • OCR 활성화: 텍스트 추출 + LLM (정확)

5⃣ 결과 활용
   • "결과 복사": 클립보드에 복사
   • "원본 열기": 이미지 다시 보기
   • "JSON 보기": 상세 데이터 확인
"""
            usage_box = ctk.CTkTextbox(usage_tab, wrap="word")
            usage_box.pack(fill="both", expand=True, padx=10, pady=10)
            usage_box.insert("1.0", usage_text)
            usage_box.configure(state="disabled")

            # 예제 탭
            example_tab = tabs.add("예제")
            example_text = """
좋은 차트 예제:

1. 명확한 캔들스틱 패턴
2. 이동평균선 표시
3. 거래량 차트 포함
4. 주요 지표 (RSI, MACD 등)
5. 고해상도 이미지

피해야 할 차트:

1. 너무 작거나 흐릿한 이미지
2. 차트가 일부만 보이는 경우
3. 과도한 편집이나 필터
4. 여러 차트가 섞인 이미지

팁:
• 전체 화면 차트 스크린샷 권장
• PNG 형식 권장 (JPG도 가능)
• 1920x1080 이상 해상도 권장
"""
            example_box = ctk.CTkTextbox(example_tab, wrap="word")
            example_box.pack(fill="both", expand=True, padx=10, pady=10)
            example_box.insert("1.0", example_text)
            example_box.configure(state="disabled")

            # JSON 샘플 탭
            json_tab = tabs.add("JSON 샘플")
            json_example = {
                "analysis": {
                    "summary": "비트코인 4시간봉 차트 분석. 상승 추세 지속 중이나 과매수 구간 진입...",
                    "plan": {
                        "entry": 61234.5,
                        "stop": 60321.0,
                        "tp": [61800.0, 62500.0]
                    }
                },
                "ocr_text": "BTC/USDT 4H MA(20): 60800...",
                "timestamp": "2025-10-31T12:34:56"
            }
            json_str = json.dumps(json_example, ensure_ascii=False, indent=2)
            json_box = ctk.CTkTextbox(json_tab, wrap="word")
            json_box.pack(fill="both", expand=True, padx=10, pady=10)
            json_box.insert("1.0", json_str)
            json_box.configure(state="disabled")

            # 닫기 버튼
            close_btn = ctk.CTkButton(modal, text="닫기", command=modal.destroy, width=100)
            close_btn.pack(pady=10)

        except Exception as e:
            logging.error(f"도움말 모달 오류: {e}")
