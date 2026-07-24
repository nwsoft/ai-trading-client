#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 학습 위젯 (CustomTkinter)
AI 학습 과정과 데이터를 모니터링하는 전용 위젯
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkProgressBar, CTkScrollableFrame, CTkTextbox
from utils.perf_metrics_logger import log_ui_perf_metric

class AILearningWidget(CTkFrame):
    """AI 학습 전용 위젯 (CustomTkinter)"""
    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "success": "#22c55e",
        "info": "#3b82f6",
        "danger": "#ef4444",
        "accent": "#9b59b6",
    }

    # 렌더링 성능 제어 (초기 표시 지연/멈춤 방지)
    MAX_RENDER_ROWS: int = 50    # 처음에 표시할 최대 행 수 (원래 정책: 최근 50개)
    BATCH_SIZE: int = 50         # 배치 렌더링 단위
    BATCH_DELAY_MS: int = 1      # 배치 간 지연(ms)


    def __init__(self, parent=None, colors: Optional[Dict[str, str]] = None, exchange_name: Optional[str] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
        self.exchange_name = exchange_name
        self._summary_callback = None
        self._last_data_mtime: Optional[float] = None  # 파일이 변하지 않으면 렌더 생략
        self._data_file_path: Optional[str] = None     # 현재 사용 중인 데이터 파일 경로
        self._service_context = kwargs.get('service_context', 'blockchain')  # 서비스 컨텍스트 저장
        self._learning_cache_ts: float = 0.0
        self._learning_cache_ttl_sec: int = 180
        self._last_visible_force_refresh_ts: float = 0.0

        # AI 학습 데이터 저장용 (콜백 업데이트를 위해 필요)
        self.learning_data: List[Dict] = []

        # 자동 학습 상태 업데이트 타이머 (5분마다)
        self.auto_update_timer = None
        self.data_update_timer = None

        # UI 초기화
        self.init_ui()

        # 초기 로드는 이벤트 루프 시작 후로 지연 (대시보드 표시를 먼저 보장)
        try:
            self.after_idle(self._initial_load_async)
        except Exception:
            # after_idle 사용이 불가한 환경에서는 최소 지연으로 예약
            self.after(0, self._initial_load_async)
        try:
            self.bind("<Map>", self._on_map_visible, add="+")
        except Exception:
            pass

    def _is_visible_now(self) -> bool:
        try:
            return bool(self.winfo_exists() and self.winfo_ismapped() and self.winfo_viewable())
        except Exception:
            return False

    def _on_map_visible(self, event=None):
        """탭 진입 시 1회 강제 새로고침 트리거"""
        try:
            if event is not None and getattr(event, 'widget', None) is not self:
                return
        except Exception:
            pass

        if not self._is_visible_now():
            return

        now_ts = time.time()
        if (now_ts - float(getattr(self, '_last_visible_force_refresh_ts', 0.0))) < 30.0:
            return
        self._last_visible_force_refresh_ts = now_ts
        log_ui_perf_metric("ai_learning", "map_force_refresh", cooldown_sec=30)
        try:
            self.after(100, lambda: self.refresh_learning_data(force_refresh=True))
        except Exception:
            pass

    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        if fallback is None:
            fallback = self.DEFAULT_COLORS.get(key, "#9ca3af")
        try:
            value = self.colors.get(key) if isinstance(self.colors, dict) else None
            if value:
                return value
        except Exception:
            pass
        return fallback

    def _filter_data_by_service(self, data: List[Dict], service_context: str) -> List[Dict]:
        """서비스 컨텍스트에 따라 데이터 필터링"""
        if not isinstance(data, list):
            return []
        
        if service_context == 'stock':
            # 주식/ETF 데이터만 필터: 증권사명 또는 symbol에 주식 특성 있는지 확인
            # 주식: 6자리 숫자 코드 (000001 ~ 999999)
            # 코인: XXXUSDT 형식
            filtered = []
            for item in data:
                try:
                    symbol = str(item.get('symbol', '')).strip().upper()
                    # 주식: 숫자만, 코인: USDT/등 문자
                    if symbol and symbol.isdigit():
                        filtered.append(item)
                    # 또는 source/exchange 필드로 확인
                    elif item.get('source') in ('kiwoom', 'shinhan', 'mirae'):
                        filtered.append(item)
                except Exception:
                    pass
            return filtered
        
        elif service_context == 'blockchain':
            # 블록체인/코인 데이터만 필터: XXXUSDT 형식 또는 exchange=binance/bybit 등
            filtered = []
            for item in data:
                try:
                    symbol = str(item.get('symbol', '')).strip().upper()
                    # 코인: USDT 포함
                    if 'USDT' in symbol or 'BTC' in symbol or 'ETH' in symbol:
                        filtered.append(item)
                    # 또는 exchange 필드로 확인
                    elif item.get('exchange') in ('binance', 'bybit', 'okx', 'bitget'):
                        filtered.append(item)
                except Exception:
                    pass
            return filtered
        
        # 기본: 필터링 없음
        return data

    def set_summary_callback(self, callback):
        """상단 요약 바 업데이트 콜백 설정"""
        self._summary_callback = callback
        # 즉시 현재 데이터로 한 번 호출
        try:
            if callback and callable(callback):
                self._trigger_summary_update()
        except Exception:
            pass

    def _trigger_summary_update(self):
        """요약 정보 콜백 호출 - 실제 데이터 기반 통계 계산"""
        try:
            if not self._summary_callback or not callable(self._summary_callback):
                return

            # 현재 학습 데이터 기반 요약 정보 생성
            today_count = 0
            weekly_count = 0
            long_signals = 0
            short_signals = 0
            hold_signals = 0

            # 실제 데이터가 있다면 집계
            if self.learning_data:
                today_count = self._count_today_learning(self.learning_data)
                weekly_count = self._count_weekly_learning(self.learning_data)

                # 시그널별 개수 계산
                for item in self.learning_data:
                    signal = item.get('signal', '')
                    if signal == 'LONG':
                        long_signals += 1
                    elif signal == 'SHORT':
                        short_signals += 1
                    elif signal == 'HOLD':
                        hold_signals += 1

            payload = {
                'today_count': today_count,
                'weekly_count': weekly_count,
                'long_signals': long_signals,
                'short_signals': short_signals,
                'hold_signals': hold_signals
            }
            self._summary_callback(payload)
        except Exception as e:
            self.logger.warning(f"요약 업데이트 콜백 호출 실패: {e}")

    def set_exchange(self, exchange_name: str):
        """거래소 변경 시 경로 라벨 갱신, mtime 리셋 후 새로고침"""
        self.exchange_name = exchange_name
        # 경로 라벨 즉시 갱신 시도
        try:
            from path_utils import get_exchange_ai_learning_data_path, get_ai_learning_data_path
            try:
                self._data_file_path = get_exchange_ai_learning_data_path(self.exchange_name) if self.exchange_name else get_ai_learning_data_path()
            except Exception:
                self._data_file_path = get_ai_learning_data_path()
            if hasattr(self, 'data_path_label') and self.data_path_label:
                self.data_path_label.configure(text=f"데이터 파일: {self._shorten_path(self._data_file_path)}")
        except Exception:
            pass
        # mtime 리셋 후 새로고침
        self._last_data_mtime = None
        self.refresh_learning_data()

    def set_service_context(self, service_name: str) -> None:
        """서비스 컨텍스트 변경 (blockchain / stock / etc.) — 제목·안내문 전환 및 데이터 재필터링"""
        try:
            old_context = getattr(self, '_service_context', 'blockchain')
            self._service_context = service_name
            
            # 헤더 레이블 업데이트
            if hasattr(self, 'service_context_label') and self.service_context_label:
                label_text = {
                    'blockchain': 'AI 학습 모니터 (암호화폐)',
                    'stock':      'AI 학습 모니터 (주식/ETF)',
                }.get(service_name, 'AI 학습 모니터')
                self.service_context_label.configure(text=label_text)
            
            # 컨텍스트 변경되면 데이터 재필터링 및 재표시
            if old_context != service_name:
                self.logger.info(f"[DEBUG] 서비스 컨텍스트 변경: {old_context} → {service_name}")
                self._last_data_mtime = None  # mtime 리셋하여 재로드 강제
                self.refresh_learning_data()
        except Exception as e:
            print(f"AILearningWidget set_service_context 오류: {e}")

    def init_ui(self):
        """UI 초기화"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. AI 학습 상태 섹션
        self.create_status_section()

        # 2. 학습 데이터 테이블 섹션
        self.create_data_section()

        # 3. AI 학습 통계 섹션
        self.create_performance_section()

    def create_status_section(self):
        """AI 학습 상태 섹션 생성"""
        status_frame = CTkFrame(self)
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        status_frame.grid_columnconfigure(1, weight=1)

        # 제목 (서비스 컨텍스트 레이블 겸용)
        self.service_context_label = CTkLabel(
            status_frame,
            text="AI 학습 상태",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.service_context_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        # 현재 상태
        CTkLabel(status_frame, text="현재 상태:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.learning_status_label = CTkLabel(
            status_frame,
            text="대기 중",
            font=ctk.CTkFont(weight="bold")
        )
        self.learning_status_label.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # 진행률 표시
        self.learning_progress = CTkProgressBar(status_frame)
        self.learning_progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.learning_progress.set(0)

    def create_data_section(self):
        """학습 데이터 테이블 섹션 생성 (중복 통계/상태 제거)"""
        data_frame = CTkFrame(self)
        data_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        data_frame.grid_columnconfigure(0, weight=1)
        data_frame.grid_rowconfigure(1, weight=1)

        # 제목
        title_label = CTkLabel(
            data_frame,
            text="AI 학습 데이터",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        # 새로고침 버튼
        refresh_button = CTkButton(
            data_frame,
            text="새로고침",
            command=self.refresh_learning_data,
            width=100,
            height=30
        )
        refresh_button.grid(row=0, column=0, sticky="e", padx=10, pady=(10, 5))

        # 현재 사용 중인 데이터 파일 경로 표시 행
        path_row = CTkFrame(data_frame)
        path_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        path_row.grid_columnconfigure(0, weight=1)
        self.data_path_label = CTkLabel(
            path_row,
            text="데이터 파일: 확인 중...",
            font=ctk.CTkFont(size=11),
            text_color="#95a5a6",
            anchor="w",
        )
        self.data_path_label.grid(row=0, column=0, sticky="w")

        # 스크롤 가능한 데이터 영역
        self.data_scroll = CTkScrollableFrame(data_frame)
        self.data_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        self.data_scroll.grid_columnconfigure(0, weight=1)

        # 헤더 생성
        self.create_data_headers()

        # (중복 통계/상태 라벨 제거)

    def create_data_headers(self):
        """데이터 테이블 헤더 생성"""
        headers = ["시간", "코인", "시그널", "신뢰도", "RSI", "MACD", "트렌드", "추론"]
        header_frame = CTkFrame(self.data_scroll)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        col_widths = [60, 90, 70, 70, 80, 80, 80, 420]  # 추론만 넓게, 나머지 좁게
        for i, header in enumerate(headers):
            header_label = CTkLabel(
                header_frame,
                text=header,
                font=ctk.CTkFont(weight="bold", size=14),
                width=col_widths[i],
                anchor="w",
                padx=4, pady=4
            )
            header_label.grid(row=0, column=i, padx=(10 if i==0 else 4), pady=8, sticky="w")
            header_frame.grid_columnconfigure(i, weight=1)

    # create_stats_info 제거 (중복 통계/상태 라벨)

    def create_performance_section(self):
        """AI 학습 통계 섹션 생성 - 2행 3열로 컴팩트하게 배치"""
        performance_frame = CTkFrame(self)
        performance_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        # 두 줄(행)로 구성, 각 줄은 3개의 아이템(라벨+값 페어)을 가짐
        for c in range(3):
            performance_frame.grid_columnconfigure(c, weight=1)

        # 제목
        title_label = CTkLabel(
            performance_frame,
            text="AI 학습 통계",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 6))

        # 통계 항목들(6개를 2행 x 3열로 배치)
        self.performance_labels = {}
        performance_items = [
            ("총 분석 수", "total_analysis", "0"),
            ("평균 신뢰도", "avg_confidence", "0.0"),
            ("마지막 업데이트", "last_update", "N/A"),
            ("LONG 신호", "long_signals", "0"),
            ("SHORT 신호", "short_signals", "0"),
            ("HOLD 신호", "hold_signals", "0"),
        ]

        def make_pair(parent, text_left: str, key: str, default: str):
            pair = CTkFrame(parent)
            # 얇은 내부 패딩으로 공간 절약
            pair.grid_columnconfigure(0, weight=0)
            pair.grid_columnconfigure(1, weight=0)
            # 좌측 정렬로 값이 너무 오른쪽으로 밀리지 않도록 함
            lbl = CTkLabel(pair, text=f"{text_left}:", anchor="w")
            lbl.grid(row=0, column=0, sticky="w")
            val = CTkLabel(pair, text=default, font=ctk.CTkFont(weight="bold"), text_color=self._color("success", "#27ae60"))
            val.grid(row=0, column=1, sticky="w", padx=(6, 0))
            self.performance_labels[key] = val
            return pair

        # 2행 x 3열 배치
        for i, (label, key, default) in enumerate(performance_items):
            row = 1 + (i // 3)  # 1,2행 사용(0행은 제목)
            col = i % 3
            cell = make_pair(performance_frame, label, key, default)
            cell.grid(row=row, column=col, sticky="w", padx=10, pady=4)

    def update_auto_learning_status(self):
        """AI 학습 상태 업데이트"""
        try:
            self.logger.info("[DEBUG] update_auto_learning_status 시작")
            # ai_learning_data.json에서 최신 데이터 확인
            from path_utils import get_ai_learning_data_path, get_exchange_ai_learning_data_path
            try:
                data_file = get_exchange_ai_learning_data_path(self.exchange_name) if self.exchange_name else get_ai_learning_data_path()
            except Exception:
                data_file = get_ai_learning_data_path()
            self.logger.info(f"[DEBUG] 상태 업데이트용 데이터 경로: {data_file}")
            # 경로 라벨 최신화
            self._data_file_path = data_file
            try:
                if hasattr(self, 'data_path_label') and self.data_path_label:
                    self.data_path_label.configure(text=f"데이터 파일: {self._shorten_path(self._data_file_path)}")
            except Exception:
                pass

            if os.path.exists(data_file):
                self.logger.info("[DEBUG] 상태 데이터 파일 읽기")
                data = self._load_json_list_safely(data_file)

                if data:
                    # 최신 AI 분석 데이터 기반으로 상태 업데이트
                    latest_data = data[-1]
                    signal = latest_data.get('signal', 'N/A')
                    confidence = latest_data.get('confidence', 0)
                    symbol = latest_data.get('symbol', 'N/A')

                    # 상태 정보 및 통계(상단만)
                    try:
                        self.learning_status_label.configure(text=f"최근: {symbol} {signal} (신뢰도 {confidence:.2f})")
                        self.learning_progress.set(1.0)
                    except Exception:
                        pass
                    # 성능 지표(오늘/주간/신호/평균 등)만 performance_labels로 업데이트
                    self.logger.info("[DEBUG] 성능 지표 자동 업데이트 시작")
                    self._update_performance_from_data(data)
                    self.logger.info("[DEBUG] update_auto_learning_status 완료")
                else:
                    self.logger.info("[DEBUG] 데이터 비어있음")
                    self.learning_status_label.configure(text="데이터 수집 중...")
                    self.learning_progress.set(0)
            else:
                self.logger.info("[DEBUG] 파일 없음 - 초기화 중")
                self.learning_status_label.configure(text="초기화 중...")
                self.learning_progress.set(0)

        except Exception as e:
            import traceback
            self.logger.error(f"AI 학습 상태 업데이트 오류: {e}")
            self.logger.error(f"상세 오류:\n{traceback.format_exc()}")
            self.learning_status_label.configure(text="AI 학습 상태 업데이트 오류")
            self.learning_progress.set(0)

    def _shorten_path(self, p: Optional[str]) -> str:
        """홈 경로를 ~로 치환하여 경로 표시를 간결하게 만듭니다."""
        try:
            if not p:
                return "(경로 확인 불가)"
            home = os.path.expanduser('~')
            if p.startswith(home):
                return p.replace(home, '~')
            return p
        except Exception:
            return p or ""

    def _update_performance_from_data(self, data):
        """데이터에서 AI 학습 통계 자동 업데이트"""
        try:
            if data:
                # 총 분석 데이터 수
                self.performance_labels['total_analysis'].configure(text=str(len(data)))

                # 시그널별 개수 계산
                long_count = sum(1 for item in data if item.get('signal') == 'LONG')
                short_count = sum(1 for item in data if item.get('signal') == 'SHORT')
                hold_count = sum(1 for item in data if item.get('signal') == 'HOLD')

                self.performance_labels['long_signals'].configure(text=str(long_count))
                self.performance_labels['short_signals'].configure(text=str(short_count))
                self.performance_labels['hold_signals'].configure(text=str(hold_count))

                # 평균 신뢰도 계산
                confidences = [item.get('confidence', 0) for item in data if isinstance(item.get('confidence'), (int, float))]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    self.performance_labels['avg_confidence'].configure(text=f"{avg_confidence:.2f}")
                else:
                    self.performance_labels['avg_confidence'].configure(text="0.0")

                # 마지막 업데이트
                self.performance_labels['last_update'].configure(text=datetime.now().strftime("%H:%M"))

        except Exception as e:
            self.logger.warning(f"AI 학습 통계 자동 업데이트 오류: {e}")

    def _count_today_learning(self, learning_data):
        """오늘 AI 분석 데이터 개수 계산 (UTC→KST 변환)"""
        try:
            from datetime import timezone, timedelta
            KST = timezone(timedelta(hours=9))
            today = datetime.now(KST).date()
            count = 0
            for data in learning_data:
                timestamp = data.get('timestamp', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        dt = dt.astimezone(KST)
                        if dt.date() == today:
                            count += 1
                    except Exception:
                        pass
            return count
        except:
            return 0

    def _count_weekly_learning(self, learning_data):
        """주간 AI 분석 데이터 개수 계산 (UTC→KST 변환)"""
        try:
            from datetime import timezone, timedelta
            KST = timezone(timedelta(hours=9))
            today = datetime.now(KST).date()
            week_ago = today - timedelta(days=7)
            count = 0
            for data in learning_data:
                timestamp = data.get('timestamp', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        dt = dt.astimezone(KST)
                        if week_ago <= dt.date() <= today:
                            count += 1
                    except Exception:
                        pass
            return count
        except:
            return 0

    def load_learning_data(self):
        """학습 데이터 로드 (초기 로드용) - 서비스 컨텍스트 기반 필터링"""
        try:
            self.logger.info("[DEBUG] load_learning_data 시작")
            # ai_learning_data.json에서 데이터 로드 (거래소별 경로 우선)
            from path_utils import get_ai_learning_data_path, get_exchange_ai_learning_data_path
            try:
                data_file = get_exchange_ai_learning_data_path(self.exchange_name) if self.exchange_name else get_ai_learning_data_path()
            except Exception:
                data_file = get_ai_learning_data_path()
            self.logger.info(f"[DEBUG] 학습 데이터 경로: {data_file}")
            self.logger.info(f"[DEBUG] 파일 존재 여부: {os.path.exists(data_file)}")
            # 경로 라벨 최신화
            self._data_file_path = data_file
            try:
                if hasattr(self, 'data_path_label') and self.data_path_label:
                    self.data_path_label.configure(text=f"데이터 파일: {self._shorten_path(self._data_file_path)}")
            except Exception:
                pass

            if os.path.exists(data_file):
                # 변경 없으면 스킵
                try:
                    mtime = os.path.getmtime(data_file)
                    if self._last_data_mtime is not None and mtime == self._last_data_mtime:
                        self.logger.info("[DEBUG] 파일 변경 없음 - 렌더링 생략")
                        return
                except Exception:
                    pass
                self.logger.info("[DEBUG] 파일 읽기 시작")
                data = self._load_json_list_safely(data_file)

                self.logger.info(f"[DEBUG] 데이터 로드 완료: {len(data) if isinstance(data, list) else 0}개 항목")

                # 서비스 컨텍스트 기반 필터링
                service_context = getattr(self, '_service_context', 'blockchain')
                data = self._filter_data_by_service(data, service_context)
                self.logger.info(f"[DEBUG] 필터링 후 데이터: {len(data)}개 항목 (서비스: {service_context})")

                # 데이터 저장 (콜백 업데이트용)
                self.learning_data = data if isinstance(data, list) else []
                try:
                    self._last_data_mtime = os.path.getmtime(data_file)
                except Exception:
                    pass

                # 대량 데이터는 배치로 렌더링 (UI 초기 표시 지연 방지)
                self.logger.info("[DEBUG] 테이블 배치 렌더링 시작")
                self._render_data_in_batches(self.learning_data)
                self.logger.info("[DEBUG] load_learning_data 예약 완료")
                # 통계/현재 상태/요약을 전체 데이터 기준으로 즉시 갱신
                try:
                    self._update_performance_from_data(self.learning_data)
                except Exception:
                    pass
                try:
                    if self.learning_data:
                        latest = self.learning_data[-1]
                        self.learning_status_label.configure(
                            text=f"최근: {latest.get('symbol','N/A')} {latest.get('signal','N/A')} (신뢰도 {float(latest.get('confidence',0)):.2f})"
                        )
                        self.learning_progress.set(1.0)
                except Exception:
                    pass
                try:
                    if self._summary_callback:
                        self._trigger_summary_update()
                except Exception:
                    pass
            else:
                self.logger.info(f"[DEBUG] 학습 데이터 파일 없음: {data_file}")
                self.learning_data = []

        except Exception as e:
            import traceback
            self.logger.error(f"학습 데이터 로드 오류: {e}")
            self.logger.error(f"상세 오류:\n{traceback.format_exc()}")
            self.learning_data = []

    def _initial_load_async(self):
        """이벤트 루프 시작 후 안전하게 초기 데이터/상태를 채웁니다."""
        try:
            if not self._is_visible_now():
                log_ui_perf_metric("ai_learning", "initial_defer_not_visible", delay_ms=1200)
                self.after(1200, self._initial_load_async)
                return
            self.load_learning_data()
            # 상태/성능은 데이터 렌더 예약과 무관하게 업데이트 가능
            try:
                self.update_auto_learning_status()
            except Exception:
                pass
        except Exception as e:
            self.logger.warning(f"초기 로드 지연 처리 중 오류: {e}")

    def refresh_learning_data(self, force_refresh: bool = False):
        """AI 학습 데이터 실시간 새로고침 - 서비스 컨텍스트 기반 필터링"""
        try:
            if not force_refresh and not self._is_visible_now():
                log_ui_perf_metric("ai_learning", "skip_invisible", force_refresh=False)
                return

            if not force_refresh:
                now_ts = time.time()
                if self.learning_data and (now_ts - float(getattr(self, '_learning_cache_ts', 0.0))) < float(self._learning_cache_ttl_sec):
                    log_ui_perf_metric("ai_learning", "ttl_hit", ttl_sec=int(self._learning_cache_ttl_sec))
                    return
                log_ui_perf_metric("ai_learning", "ttl_miss", ttl_sec=int(self._learning_cache_ttl_sec))

            # ai_learning_data.json에서 최신 데이터 로드 (거래소별 경로 우선)
            from path_utils import get_ai_learning_data_path, get_exchange_ai_learning_data_path
            try:
                data_file = get_exchange_ai_learning_data_path(self.exchange_name) if self.exchange_name else get_ai_learning_data_path()
            except Exception:
                data_file = get_ai_learning_data_path()
            # 경로 라벨 최신화
            self._data_file_path = data_file
            try:
                if hasattr(self, 'data_path_label') and self.data_path_label:
                    self.data_path_label.configure(text=f"데이터 파일: {self._shorten_path(self._data_file_path)}")
            except Exception:
                pass
            if os.path.exists(data_file):
                # 변경 없으면 스킵
                try:
                    mtime = os.path.getmtime(data_file)
                    if self._last_data_mtime is not None and mtime == self._last_data_mtime:
                        self.logger.info("[DEBUG] refresh: 파일 변경 없음 - 렌더링 생략")
                        return
                except Exception:
                    pass
                data = self._load_json_list_safely(data_file)

                # 서비스 컨텍스트 기반 필터링
                service_context = getattr(self, '_service_context', 'blockchain')
                data = self._filter_data_by_service(data, service_context)
                
                # 데이터 저장 (콜백 업데이트용)
                self.learning_data = data if isinstance(data, list) else []
                try:
                    self._last_data_mtime = os.path.getmtime(data_file)
                except Exception:
                    pass

                # 테이블 최신 데이터도 배치로 표시
                self._render_data_in_batches(self.learning_data)

                # 성능 지표도 함께 업데이트
                self._update_performance_from_data(data)
                # 현재 상태 라벨도 최신 정보로 갱신
                try:
                    if self.learning_data:
                        latest = self.learning_data[-1]
                        self.learning_status_label.configure(
                            text=f"최근: {latest.get('symbol','N/A')} {latest.get('signal','N/A')} (신뢰도 {float(latest.get('confidence',0)):.2f})"
                        )
                        self.learning_progress.set(1.0)
                except Exception:
                    pass

                # 요약 콜백이 설정되어 있으면 업데이트
                if self._summary_callback:
                    self._trigger_summary_update()

                self._learning_cache_ts = time.time()
                log_ui_perf_metric(
                    "ai_learning",
                    "refresh_done",
                    rows=len(data),
                    force_refresh=bool(force_refresh),
                    service_context=str(getattr(self, '_service_context', 'blockchain')),
                )

                self.logger.info(f"AI 학습 데이터 테이블 새로고침 완료: {len(data)}개 항목")
            else:
                self.logger.debug("AI 학습 데이터 파일을 찾을 수 없습니다.")
                self.learning_data = []

        except Exception as e:
            self.logger.warning(f"AI 학습 데이터 새로고침 오류: {e}")
            self.learning_data = []

    def _load_json_list_safely(self, data_file: str, retries: int = 3, delay_sec: float = 0.12) -> List[Dict]:
        """쓰기 중간 상태를 고려해 JSON 리스트를 안전하게 읽습니다."""
        last_error: Optional[Exception] = None
        for attempt in range(retries):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    return loaded
                return []
            except json.JSONDecodeError as e:
                last_error = e
                # 저장 중간 상태일 수 있어 짧게 재시도
                if attempt < retries - 1:
                    time.sleep(delay_sec)
                    continue
            except Exception as e:
                last_error = e
                break

        self.logger.warning(f"AI 학습 데이터 읽기 실패(임시/손상 가능): {last_error}")
        return []

    def update_learning_table(self, data):
        """AI 학습 데이터 테이블 업데이트 (이제 배치 렌더러로 위임)."""
        try:
            self._render_data_in_batches(data)
        except Exception as e:
            self.logger.warning(f"AI 학습 테이블 업데이트 오류: {e}")

    def _render_data_in_batches(self, data: List[Dict]):
        """큰 데이터를 배치로 렌더링하여 UI 프리즈를 방지합니다. (최신순 역순 렌더링)"""
        try:
            data = data or []
            # 기존 행 제거 (헤더/통계는 row<=1 유지)
            for widget in self.data_scroll.winfo_children():
                try:
                    if isinstance(widget, CTkFrame) and widget.grid_info().get('row', 0) > 1:
                        widget.destroy()
                except Exception:
                    pass

            # 최신 항목 위주로 최대 MAX_RENDER_ROWS만 표시 (최신순 역순)
            if len(data) > self.MAX_RENDER_ROWS:
                to_render = list(reversed(data[-self.MAX_RENDER_ROWS:]))
            else:
                to_render = list(reversed(data))

            self.logger.info(f"[DEBUG] 배치 렌더 대상: {len(to_render)}행 (원본 {len(data)}행, 최신순)")

            def render_batch(start_idx: int = 0):
                try:
                    end_idx = min(start_idx + self.BATCH_SIZE, len(to_render))
                    for idx in range(start_idx, end_idx):
                        item = to_render[idx]
                        # 헤더/통계가 row 0~1을 사용하므로 +2부터 시작
                        self.create_data_row(item, (idx - 0) + 2)
                    if end_idx < len(to_render):
                        # 다음 배치 예약
                        self.after(self.BATCH_DELAY_MS, lambda: render_batch(end_idx))
                    else:
                        # 모든 배치 완료 후 성능/요약 갱신
                        try:
                            self.update_performance_indicators(to_render)
                        except Exception:
                            pass
                        try:
                            if self._summary_callback:
                                self._trigger_summary_update()
                        except Exception:
                            pass
                except Exception as e:
                    self.logger.warning(f"배치 렌더링 오류: {e}")

            # 첫 배치 시작
            render_batch(0)
        except Exception as e:
            self.logger.warning(f"배치 렌더링 준비 오류: {e}")

    def create_data_row(self, item, row):
        """데이터 행 생성 (robust, KST 시간 변환, N/A 방지, 컬럼 매핑 보강, UI 개선)"""
        try:
            from datetime import timezone, timedelta
            KST = timezone(timedelta(hours=9))
            row_frame = CTkFrame(self.data_scroll)
            row_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=8)
            col_widths = [60, 90, 70, 70, 80, 80, 80, 420]
            for i in range(8):
                row_frame.grid_columnconfigure(i, weight=1)

            # robust timestamp 파싱 및 KST 변환
            timestamp = item.get('timestamp', '')
            time_str = 'N/A'
            if isinstance(timestamp, str) and timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    dt = dt.astimezone(KST)
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    time_str = timestamp[:5] if len(timestamp) >= 5 else timestamp
            elif hasattr(timestamp, 'strftime'):
                try:
                    time_str = timestamp.astimezone(KST).strftime("%H:%M")
                except Exception:
                    time_str = timestamp.strftime("%H:%M")
            else:
                time_str = str(timestamp)

            # robust 숫자 변환 (소수점 4자리 제한)
            def safe_num(val, fmt, na_val="N/A"):
                try:
                    if val is None or val == '':
                        return na_val
                    if isinstance(val, str):
                        val = float(val) if val.replace('.', '', 1).replace('-', '', 1).isdigit() else 0
                    return fmt(val)
                except Exception:
                    return na_val

            # reason/추론 robust 매핑 (최대 65자까지 표시)
            reason_val = item.get('reasoning', '') or item.get('reason', '')
            if reason_val and len(str(reason_val)) > 65:
                reason_val = str(reason_val)[:65] + "..."
            else:
                reason_val = str(reason_val)

            # RSI, MACD, trend robust 매핑 (fixed 버전과 동일하게 fallback, trend도 4자리)
            rsi_val = safe_num(
                item.get('rsi', item.get('RSI', item.get('market_volatility', None))),
                lambda x: f"{float(x):.4f}"
            )
            macd_val = safe_num(
                item.get('macd', item.get('MACD', item.get('trend_strength', None))),
                lambda x: f"{float(x):.4f}"
            )
            # trend: trend, trend_strength, 없으면 N/A, 있으면 4자리 제한
            trend_val = item.get('trend', None)
            if trend_val is None or trend_val == '':
                trend_val = item.get('trend_strength', None)
            if trend_val is None or trend_val == '':
                trend_val = "N/A"
            else:
                try:
                    trend_val = float(str(trend_val).replace('TrendDirection.', ''))
                    trend_val = f"{trend_val:.4f}"
                except Exception:
                    trend_val = str(trend_val).replace('TrendDirection.', '')

            columns = [
                time_str,
                str(item.get('symbol', 'N/A')),
                str(item.get('signal', 'N/A')),
                safe_num(item.get('confidence', 0), lambda x: f"{float(x):.1f}"),
                rsi_val,
                macd_val,
                trend_val,
                reason_val
            ]

            # 컬럼 간격 및 폰트, 패딩 개선
            for i, col_data in enumerate(columns):
                label = CTkLabel(
                    row_frame,
                    text=col_data,
                    width=col_widths[i],
                    anchor="w",
                    font=ctk.CTkFont(size=13, weight="normal"),
                    padx=4, pady=4
                )
                label.grid(row=0, column=i, padx=(10 if i==0 else 4), pady=8, sticky="w")

        except Exception as e:
            self.logger.warning(f"데이터 행 생성 오류: {e}")

    def update_performance_indicators(self, data):
        """AI 학습 통계 업데이트"""
        try:
            if data:
                # 총 분석 데이터 수
                total = len(data)
                self.performance_labels['total_analysis'].configure(text=str(total))

                # 시그널별 개수 계산
                long_count = sum(1 for item in data if item.get('signal') == 'LONG')
                short_count = sum(1 for item in data if item.get('signal') == 'SHORT')
                hold_count = sum(1 for item in data if item.get('signal') == 'HOLD')

                self.performance_labels['long_signals'].configure(text=str(long_count))
                self.performance_labels['short_signals'].configure(text=str(short_count))
                self.performance_labels['hold_signals'].configure(text=str(hold_count))

                # 평균 신뢰도 계산
                confidences = [item.get('confidence', 0) for item in data if isinstance(item.get('confidence'), (int, float))]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    self.performance_labels['avg_confidence'].configure(text=f"{avg_confidence:.2f}")
                else:
                    self.performance_labels['avg_confidence'].configure(text="0.0")

                # 마지막 업데이트
                self.performance_labels['last_update'].configure(text=datetime.now().strftime("%H:%M"))

        except Exception as e:
            self.logger.warning(f"AI 학습 통계 업데이트 오류: {e}")
