"""
시장 트렌드 분석 위젯
실시간 시장 데이터 수집 및 표시
"""

import threading
import customtkinter as ctk
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
from utils.perf_metrics_logger import log_ui_perf_metric

# 고정 색상 팔레트 사용
from utils.fixed_colors import build_widget_palette


class MarketTrendWidget(ctk.CTkFrame):
    def __init__(self, parent, dashboard_ref=None, colors=None, **kwargs):
        palette = build_widget_palette(colors)
        kwargs.setdefault("fg_color", palette["content_bg"])
        kwargs.setdefault("corner_radius", 0)
        super().__init__(parent, **kwargs)
        self.dashboard_ref = dashboard_ref
        self._trend_refreshing = False
        self._trend_sections = {}
        self._service_context = 'blockchain'
        self._last_visible_force_refresh_ts = 0.0
        self._last_refresh_started_at: Optional[datetime] = None
        self._last_refresh_success_at: Optional[datetime] = None
        self._last_refresh_error: str = ""
        self._disposed = False
        self._after_jobs = []
        self._auto_refresh_job = None

        # 로그인 직후 과도한 API 호출을 줄이기 위한 인메모리 캐시
        self._trend_cache: Dict[str, Dict[str, Any]] = {}
        self._trend_cache_ttl_sec = 180

        # 모든 서비스가 AI 커스텀·거래 통계와 같은 기능 탭 팔레트를 사용한다.
        self.colors = palette

        # 폰트 설정
        self.fonts = {
            "title": ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            "subtitle": ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            "body": ctk.CTkFont(family="Segoe UI", size=12),
            "small": ctk.CTkFont(family="Segoe UI", size=10)
        }

    # CustomTkinter 패치 제거 (2025-10-30): 렌더링 품질 문제의 원인이었음

        self.setup_ui()
        try:
            self.bind("<Destroy>", self._on_destroy, add="+")
            self.bind("<Unmap>", self._on_unmap_hidden, add="+")
        except Exception:
            pass

    def _color(self, key: str, fallback: str) -> str:
        try:
            if isinstance(self.colors, dict):
                value = self.colors.get(key)
                if value:
                    return value
        except Exception:
            pass
        return fallback

    @staticmethod
    def _shade_color(hex_color: str, factor: float = 0.85) -> str:
        try:
            color = hex_color.lstrip('#')
            if len(color) != 6:
                return hex_color
            r = max(0, min(255, int(int(color[0:2], 16) * factor)))
            g = max(0, min(255, int(int(color[2:4], 16) * factor)))
            b = max(0, min(255, int(int(color[4:6], 16) * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def setup_ui(self):
        """UI 구성 - 카드형 섹션 디자인"""
        # 스크롤 가능한 영역
        container = ctk.CTkScrollableFrame(
            self,
            label_text="시장 트렌드 인사이트",
            corner_radius=16,
            fg_color=self._color("content_bg", "#0b1120"),
            border_color=self._color("border_strong", "#334155"),
            border_width=1,
            label_fg_color=self._color("card", "#111827"),
            label_text_color=self._color("text_primary", "#f9fafb"),
            label_font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        )
        container.pack(fill="both", expand=True, padx=10, pady=(10, 10))

        # --- 상단 요약 칩(메트릭) 영역 ---
        try:
            # 투명색 금지 정책에 따라 컨테이너 배경색과 동일하게 설정
            metrics_frame = ctk.CTkFrame(
                container,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=0,
            )
            metrics_frame.pack(fill="x", padx=6, pady=(0, 8))

            def _chip(parent, text: str, color_key: str, fallback: str):
                fg = self._color(color_key, fallback)
                lbl = ctk.CTkLabel(parent, text=text, fg_color=fg, text_color="white", corner_radius=12, padx=10, pady=6)
                lbl.pack(side="left", padx=(0, 6))
                return lbl

            # 메트릭 칩 - 서비스 컨텍스트별로 나중에 업데이트됨
            self.trend_chip_direction = _chip(metrics_frame, "시장 방향: 연결 중", "info", "#1f538d")
            self.trend_chip_funding = _chip(metrics_frame, "펀딩비: 연결 중", "success", "#2b7a0b")
            self.trend_chip_fng = _chip(metrics_frame, "공포/탐욕: 연결 중", "border", "#6b7280")
        except Exception:
            pass

        # --- 본문 섹션: 카드/2열 레이아웃 ---
        sections: Dict[str, Any] = {}
        sections_container = ctk.CTkFrame(
            container,
            fg_color=self._color("content_bg", "#0b1120"),
            corner_radius=0,
        )
        sections_container.pack(fill="both", expand=True, padx=2, pady=2)
        try:
            sections_container.grid_columnconfigure(0, weight=1)
            sections_container.grid_columnconfigure(1, weight=1)
        except Exception:
            pass

        def _add_section(key: str, title: str, placeholder: str, icon: str = "", chip_color_key: str = "primary", chip_fallback: str = "#14375e", height: int = 220) -> None:
            # 2열 그리드 위치 계산
            idx = len(sections)
            row, col = divmod(idx, 2)
            frame = ctk.CTkFrame(
                sections_container,
                corner_radius=16,
                fg_color=self._color("card", "#111827"),
                border_color=self._color("border_soft", "#273449"),
                border_width=1,
            )
            try:
                frame.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            except Exception:
                frame.pack(fill="both", expand=True, padx=6, pady=6)

            # 헤더 라인: 아이콘 칩 + 제목
            header = ctk.CTkFrame(
                frame,
                fg_color=self._color("card", "#111827"),
                corner_radius=0,
            )
            header.pack(fill="x", padx=8, pady=(10, 6))
            chip_color = self._color(chip_color_key, chip_fallback)
            chip = ctk.CTkLabel(header, text=f"{icon}", fg_color=chip_color, text_color="white", corner_radius=12, padx=8, pady=4)  # 통일 (8 → 12)
            chip.pack(side="left", padx=(0, 8))
            title_lbl = ctk.CTkLabel(
                header,
                text=title,
                text_color=self._color("text_primary", "#f9fafb"),
                font=self.fonts.get("title", ctk.CTkFont(size=15, weight="bold")),
            )
            title_lbl.pack(side="left")

            # 내용 박스
            box = ctk.CTkTextbox(
                frame,
                height=height,
                fg_color=self._color("input", "#0b1120"),
                border_color=self._color("border_strong", "#334155"),
                border_width=1,
                text_color=self._color("text_secondary", "#9ca3af"),
                font=ctk.CTkFont(family="Segoe UI", size=12),
            )
            box.pack(fill="both", expand=True, padx=8, pady=(0, 10))
            try:
                box.configure(text_color=self._color("text_secondary", "#9ca3af"))
            except Exception:
                pass
            box.insert("1.0", placeholder)
            try:
                box.configure(state="disabled")
            except Exception:
                pass
            sections[key] = {
                "textbox": box,
                "title_label": title_lbl,
                "body_label": None,
            }

        _add_section(
            "market_momentum",
            "시장 방향 · 모멘텀",
            "• 일간/주간 주요 지수와 수익률 요약을 표시합니다.\n"
            "• 서비스 컨텍스트(블록체인/주식)에 맞는 대표 심볼 기준으로 해석합니다.\n"
            "• 데이터 수집이 없으면 연결 중 상태를 표시합니다.",
            icon="",
            chip_color_key="info",
            chip_fallback="#1f538d"
        )

        _add_section(
            "coin_sector",
            "대표 코인 · 섹터 흐름",
            "• BTC, ETH, 시총 상위 알트의 단기/중기/장기 추세 비교가 표시됩니다.\n"
            "• 디파이·메타버스·AI 등 섹터별 평균 수익률을 시각화하여 제공합니다.\n"
            "• 섹터별 성과를 색상으로 구분하여 표시 (녹색: 상승, 빨간색: 하락).",
            icon="",
            chip_color_key="success",
            chip_fallback="#2b7a0b"
        )

        _add_section(
            "sentiment_volume",
            "시장 심리 · 거래량 지표",
            "• 거래량 증감률, 펀딩비, 롱/숏 비율 등 심리 지표를 표시합니다.\n"
            "• 블록체인 컨텍스트에서는 온체인/파생 지표를 우선 반영합니다.\n"
            "• 주식 컨텍스트에서는 일반 거래량/수급 관점 설명으로 전환합니다.",
            icon="",
            chip_color_key="warning",
            chip_fallback="#92400e"
        )

        _add_section(
            "portfolio_trend",
            "나의 포트폴리오 트렌드",
            "• 활성 포지션, 거래 이력, 누적 손익 등 현재 조회 가능한 지표를 표시합니다.\n"
            "• 거래 데이터가 없으면 미집계 상태를 명확히 안내합니다.\n"
            "• 제공되지 않는 지표는 예정 문구 대신 미제공으로 표시합니다.",
            icon="",
            chip_color_key="success",
            chip_fallback="#0f766e"
        )

        _add_section(
            "ai_strategy",
            "AI 전략 상태",
            "• 현재 제공되는 AI 기능과 미제공 기능을 구분해 보여줍니다.\n"
            "• 전략 신호, 임계값 조정, TP/SL 보정 등 현재 동작 범위를 안내합니다.\n"
            "• 일정 약속 문구 없이 실제 배포 기능 기준으로 표시합니다.",
            icon="",
            chip_color_key="accent",
            chip_fallback="#6b21a8"
        )

        self.trend_sections = sections
        # 하단 스페이서로 마지막 콘텐츠 아래 여유 공간 확보(스크롤 끝 컷오프 방지)
        try:
            bottom_spacer = ctk.CTkFrame(
                container,
                height=24,
                fg_color=self._color("content_bg", "#0b1120"),
                corner_radius=0,
            )
            bottom_spacer.pack(fill="x", padx=4, pady=(4, 0))
        except Exception:
            pass

        # 자동 새로고침 시작
        self.safe_after(1000, self.start_auto_refresh)
        try:
            self.bind("<Map>", self._on_map_visible, add="+")
        except Exception:
            pass

    def _on_map_visible(self, event=None):
        """탭/위젯이 실제 표시될 때 1회 강제 갱신한다."""
        try:
            if event is not None and getattr(event, 'widget', None) is not self:
                return
        except Exception:
            pass

        if not self._is_visible_now() or self._trend_refreshing:
            return

        now_ts = time.time()
        # 탭 전환 시 과도한 연속 호출을 막기 위한 최소 간격(30초)
        if (now_ts - float(getattr(self, '_last_visible_force_refresh_ts', 0.0))) < 30.0:
            return

        self._last_visible_force_refresh_ts = now_ts
        log_ui_perf_metric("market_trend", "map_force_refresh", cooldown_sec=30)
        self.safe_after(100, lambda: self.collect_and_update(force_refresh=True))
        self._schedule_auto_refresh()

    def _on_unmap_hidden(self, event=None):
        try:
            if event is not None and getattr(event, "widget", None) is not self:
                return
        except Exception:
            pass
        if self._auto_refresh_job is not None:
            try:
                self.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            try:
                self._after_jobs.remove(self._auto_refresh_job)
            except (ValueError, AttributeError):
                pass
            self._auto_refresh_job = None

    def _is_visible_now(self) -> bool:
        """현재 위젯이 실제로 화면에 표시 중인지 확인한다."""
        try:
            return bool(self.winfo_exists() and self.winfo_ismapped() and self.winfo_viewable())
        except Exception:
            return False

    def start_auto_refresh(self):
        """자동 새로고침 시작"""
        if not self._is_visible_now():
            return
        self.collect_and_update(force_refresh=True)
        self._schedule_auto_refresh()

    def _schedule_auto_refresh(self):
        if self._disposed or not self._is_visible_now():
            return
        if self._auto_refresh_job is not None:
            try:
                self.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
        self._auto_refresh_job = self.safe_after(600000, self.start_auto_refresh)

    def set_service_context(self, service_name: str) -> None:
        """서비스 컨텍스트 변경 (blockchain / stock / etc.)"""
        try:
            self._service_context = service_name
            # 섹션 제목/설명을 서비스에 맞게 업데이트
            if service_name == 'stock':
                self._update_section_labels_for_stock()
            else:
                self._update_section_labels_for_blockchain()
            # 데이터 즉시 재수집
            self.collect_and_update()
        except Exception as e:
            print(f"MarketTrendWidget set_service_context 오류: {e}")

    def _get_cache_key(self) -> str:
        """서비스 컨텍스트별 캐시 키 반환"""
        try:
            return str(getattr(self, '_service_context', 'blockchain') or 'blockchain')
        except Exception:
            return 'blockchain'

    def _load_cached_insights(self, max_age_sec: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """유효한 캐시 데이터가 있으면 반환"""
        try:
            cache_key = self._get_cache_key()
            cached = self._trend_cache.get(cache_key)
            if not cached:
                return None

            ts = cached.get('ts')
            insights = cached.get('insights')
            if ts is None or insights is None:
                return None

            ttl = int(max_age_sec if max_age_sec is not None else self._trend_cache_ttl_sec)
            age = (datetime.now() - ts).total_seconds()
            if age > ttl:
                return None
            return insights
        except Exception:
            return None

    def _save_cached_insights(self, insights: Dict[str, Any]) -> None:
        """현재 컨텍스트 기준 캐시 저장"""
        try:
            if not isinstance(insights, dict) or not insights:
                return
            cache_key = self._get_cache_key()
            self._trend_cache[cache_key] = {
                'ts': datetime.now(),
                'insights': insights,
            }
        except Exception:
            pass

    def _update_section_labels_for_stock(self) -> None:
        """주식/ETF 모드에 맞게 섹션 레이블 업데이트"""
        try:
            label_map = {
                "market_momentum": ("주식 시장 방향성", "• KOSPI/KOSDAQ 지수 흐름, 외국인/기관 순매수 동향\n• 섹터 로테이션 및 업종별 강도 분석"),
                "coin_sector":      ("업종·섹터 흐름",   "• IT·바이오·금융·에너지 등 업종별 수익률 비교\n• 코스피200 대비 개별 종목 상대 강도"),
                "sentiment_volume": ("투자 심리 · 거래량", "• 신용잔고·공매도·외국인 보유율 지표\n• 주요 종목 거래대금 이상 급등·급락 감지"),
                "portfolio_trend":  ("내 포트폴리오 트렌드", "• 보유 종목 수익률, 평가손익, 리밸런싱 신호\n• 업종 편중도 및 위험 분산 지표"),
                "ai_strategy":      ("AI 전략 상태", "• AI 기반 매수/매도 시그널, 종목 스코어링\n• 실적 시즌·공시 이벤트 대응 전략 안내"),
            }
            self._apply_section_label_map(label_map)
        except Exception:
            pass

    def _update_section_labels_for_blockchain(self) -> None:
        """블록체인/암호화폐 모드에 맞게 섹션 레이블 복원"""
        try:
            label_map = {
                "market_momentum": ("시장 방향성",       "• 이동평균, MACD, RSI 기반의 방향성 분석\n• 상승/하락 전환 구간 자동 감지"),
                "coin_sector":      ("대표 코인 · 섹터 흐름", "• BTC, ETH, 시총 상위 알트 단기/중기/장기 추세\n• 디파이·메타버스·AI 섹터별 평균 수익률"),
                "sentiment_volume": ("시장 심리 · 거래량 지표", "• 거래소별 거래량 증감률, 펀딩비, 공매도 비율\n• 고래 순매수/순매도, 온체인 순유입·순유출"),
                "portfolio_trend":  ("나의 포트폴리오 트렌드", "• 총 자산 곡선, 변동성, 샤프 지수\n• 최근 7일 손익, 활성 포지션 추세 분석"),
                "ai_strategy":      ("AI 전략 상태", "• 거래소별 트렌드 스코어, 신호 분포\n• 커스텀 지표 연결 및 AI 추천 전략"),
            }
            self._apply_section_label_map(label_map)
        except Exception:
            pass

    def _get_section_textbox(self, section_key: str):
        section = self.trend_sections.get(section_key)
        if isinstance(section, dict):
            return section.get('textbox')
        return section

    def _apply_section_label_map(self, label_map: dict) -> None:
        """섹션 딕셔너리의 레이블 위젯 텍스트 일괄 업데이트"""
        try:
            sections = getattr(self, 'trend_sections', {}) or getattr(self, '_trend_sections', {})
            for key, (title_text, body_text) in label_map.items():
                section = sections.get(key)
                if section is None:
                    continue
                title_lbl = section.get('title_label')
                body_lbl = section.get('body_label')
                if title_lbl and hasattr(title_lbl, 'configure'):
                    title_lbl.configure(text=title_text)
                if body_lbl and hasattr(body_lbl, 'configure'):
                    body_lbl.configure(text=body_text)
        except Exception:
            pass

    def force_refresh(self):
        """수동 새로고침"""
        self.collect_and_update(force_refresh=True)

    def collect_and_update(self, force_refresh: bool = False):
        """데이터 수집 및 UI 업데이트"""
        if not self._is_visible_now():
            log_ui_perf_metric("market_trend", "skip_invisible", force_refresh=bool(force_refresh))
            return
        if self._trend_refreshing:
            return

        # 캐시가 유효하면 즉시 UI 반영 후 네트워크 호출 생략
        if not force_refresh:
            cached_insights = self._load_cached_insights()
            if cached_insights is not None:
                log_ui_perf_metric(
                    "market_trend",
                    "cache_hit",
                    ttl_sec=int(self._trend_cache_ttl_sec),
                    force_refresh=False,
                    service_context=self._get_cache_key(),
                )
                self._update_ui_with_data(cached_insights)
                return
            log_ui_perf_metric(
                "market_trend",
                "cache_miss",
                ttl_sec=int(self._trend_cache_ttl_sec),
                force_refresh=False,
                service_context=self._get_cache_key(),
            )

        self._trend_refreshing = True
        self._last_refresh_started_at = datetime.now()
        try:
            # 백그라운드에서 데이터 수집
            def _bg_collect():
                started = time.perf_counter()
                try:
                    insights = self._gather_market_trend_data()
                    self._save_cached_insights(insights)
                    self._last_refresh_success_at = datetime.now()
                    self._last_refresh_error = ""
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    log_ui_perf_metric(
                        "market_trend",
                        "fetch_done",
                        force_refresh=bool(force_refresh),
                        elapsed_ms=elapsed_ms,
                        daily_count=len((insights or {}).get('daily_changes', []) or []),
                        weekly_count=len((insights or {}).get('weekly_changes', []) or []),
                        sector_count=len((insights or {}).get('sector_summary', []) or []),
                    )
                    # 메인 스레드에서 UI 업데이트
                    self.safe_after(0, lambda: self._update_ui_with_data(insights))
                except Exception as e:
                    print(f"데이터 수집 오류: {e}")
                    self._last_refresh_error = str(e)
                    log_ui_perf_metric("market_trend", "fetch_error", error=str(e)[:120])
                finally:
                    self._trend_refreshing = False

            # 백그라운드 스레드에서 데이터 수집
            thread = threading.Thread(target=_bg_collect, daemon=True)
            thread.start()

        except Exception as e:
            print(f"collect_and_update 오류: {e}")
            self._trend_refreshing = False

    def _gather_market_trend_data(self) -> Dict[str, Any]:
        """시장 트렌드 데이터 수집"""
        print("_gather_market_trend_data 시작!")
        try:
            service_context = getattr(self, '_service_context', 'blockchain')
            # 기본 거래소 확인
            primary_exchange = self._get_primary_exchange()
            if not primary_exchange:
                return {}

            print(f"주요 거래소: {primary_exchange}, 서비스: {service_context}")

            # 데이터 수집
            insights = {
                'daily_changes': [],
                'weekly_changes': [],
                'sector_summary': [],
                'sentiment_summary': {},
                'service_context': service_context,
            }

            # 서비스 컨텍스트별 주요 심볼 결정
            if service_context == 'stock':
                # 주식: 네이버 금융 API 기반 전용 수집 경로
                return self._gather_stock_market_data()
            else:
                # 블록체인: 주요 코인
                major_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
                collect_sentiment = True

            # 일간 데이터 수집
            for symbol in major_symbols:
                print(f"일간 데이터 수집: {symbol}")
                trend_data = self._compute_symbol_trend(symbol, primary_exchange, '1d')
                if trend_data:
                    insights['daily_changes'].append(trend_data)

            # 주간 데이터 수집
            for symbol in major_symbols:
                print(f"주간 데이터 수집: {symbol}")
                weekly_data = self._compute_multi_period_change(symbol, primary_exchange, '1w')
                if weekly_data:
                    insights['weekly_changes'].append(weekly_data)

            # 섹터 데이터 수집
            sectors = self._get_sectors_for_exchange(primary_exchange, service_context)
            for sector_name, symbols in sectors.items():
                print(f"섹터 데이터 수집: {sector_name}")
                sector_data = self._compute_sector_trend(sector_name, symbols, primary_exchange)
                if sector_data:
                    insights['sector_summary'].append(sector_data)

            # 시장 심리 데이터 수집 (블록체인 컨텍스트에서만)
            if collect_sentiment:
                print("시장 심리 데이터 수집 시작...")
                sentiment_data = self._fetch_sentiment_summary('BTCUSDT')
                if sentiment_data:
                    insights['sentiment_summary'] = sentiment_data
                    print("시장 심리 데이터 수집 성공!")

            print(f"수집된 데이터: 일간={len(insights['daily_changes'])}, 주간={len(insights['weekly_changes'])}, 섹터={len(insights['sector_summary'])}")

            return insights

        except Exception as e:
            print(f"_gather_market_trend_data 오류: {e}")
            return {}

    def _get_primary_exchange(self) -> Optional[str]:
        """주요 거래소 반환"""
        try:
            if self.dashboard_ref and hasattr(self.dashboard_ref, 'enabled_exchanges'):
                enabled = self.dashboard_ref.enabled_exchanges
                if enabled and len(enabled) > 0:
                    return enabled[0]
            return 'binance'  # 기본값
        except Exception:
            return 'binance'

    def _compute_symbol_trend(self, symbol: str, exchange: str, interval: str) -> Optional[Dict[str, Any]]:
        """심볼 트렌드 계산"""
        try:
            klines = self._safe_fetch_klines(symbol, exchange, interval, 30)
            if not klines or len(klines) < 7:
                return None

            # 최신 가격과 7일 전 가격 비교
            current_price = float(klines[-1][4])  # 종가
            week_ago_price = float(klines[-7][4]) if len(klines) >= 7 else current_price

            # 변화율 계산
            change = ((current_price - week_ago_price) / week_ago_price) * 100

            # MA7 기울기 계산
            ma7_values = []
            for i in range(6, len(klines)):
                ma7 = sum(float(klines[j][4]) for j in range(i-6, i+1)) / 7
                ma7_values.append(ma7)

            ma7_slope = 0
            if len(ma7_values) >= 2:
                ma7_slope = (ma7_values[-1] - ma7_values[0]) / len(ma7_values)

            # 심볼 이름 정리
            symbol_name = symbol.replace('USDT', '')

            return {
                'symbol': symbol_name,
                'change': change,
                'ma7_slope': ma7_slope
            }
        except Exception as e:
            print(f"_compute_symbol_trend 오류: {e}")
            return None

    def _compute_multi_period_change(self, symbol: str, exchange: str, period: str) -> Optional[Dict[str, Any]]:
        """다중 기간 변화율 계산"""
        try:
            klines = self._safe_fetch_klines(symbol, exchange, '1d', 30)
            if not klines or len(klines) < 7:
                return None

            current_price = float(klines[-1][4])

            # 주간 변화율
            week_ago_price = float(klines[-7][4]) if len(klines) >= 7 else current_price
            weekly_change = ((current_price - week_ago_price) / week_ago_price) * 100

            return {
                'symbol': symbol,
                'weekly_change': weekly_change
            }
        except Exception:
            return None

    def _compute_sector_trend(self, sector_name: str, symbols: List[str], exchange: str) -> Optional[Dict[str, Any]]:
        """섹터 트렌드 계산"""
        try:
            changes = []
            for symbol in symbols:
                trend_data = self._compute_symbol_trend(symbol, exchange, '1d')
                if trend_data:
                    changes.append(trend_data['change'])

            if changes:
                avg_change = sum(changes) / len(changes)
                return {
                    'sector': sector_name,
                    'avg_change': avg_change
                }
        except Exception:
            pass
        return None

    def _get_sectors_for_exchange(self, exchange: str, service_context: str = 'blockchain') -> Dict[str, List[str]]:
        """거래소별/서비스별 섹터 매핑"""
        if service_context == 'stock':
            # 주식/ETF 업종별 대표주 (한국 시장 기준)
            return {
                'IT': ['005930', '000660', '006260'],  # 삼성전자, SK하이닉스, LS전선
                '금융': ['055550', '000810', '010140'],  # 신한지주, 미래에셋증권, 삼성화재
                '화학': ['010140', '006805', '028260'],  # 삼성화재, OCI, 삼성물산
                '에너지': ['034020', '034220', '267250'],  # 두산중공업, 남해화학, KT알파
                '통신': ['030200', '017670', '011200'],  # KT, SK텔레콤, 현대위아
            }
        
        # 블록체인/코인 (기본)
        if exchange == 'binance':
            return {
                'DeFi': ['UNIUSDT'],
                'Layer1': ['AVAXUSDT'],
                'AI': ['FETUSDT'],
                'Meme': ['DOGEUSDT'],
                'Gaming': ['AXSUSDT'],
                'Storage': ['FILUSDT'],
                'Metaverse': ['MANAUSDT'],
                'Privacy': ['MONEROUSDT']
            }
        return {}

    def _safe_fetch_klines(self, symbol: str, exchange: str, interval: str, limit: int) -> Optional[List[List[Any]]]:
        """안전한 K라인 조회"""
        try:
            # 캐시 확인
            if not hasattr(self, '_klines_cache'):
                self._klines_cache = {}
                self._klines_cache_duration = 60  # 1분

            cache_key = f"{symbol}_{exchange}_{interval}_{limit}"
            if cache_key in self._klines_cache:
                cache_entry = self._klines_cache[cache_key]
                if (datetime.now() - cache_entry['timestamp']).total_seconds() < self._klines_cache_duration:
                    return cache_entry['data']

            # ExchangeManager 우선 시도
            if self.dashboard_ref and hasattr(self.dashboard_ref, 'exchange_manager'):
                try:
                    em = self.dashboard_ref.exchange_manager
                    if em and hasattr(em, 'get_exchange'):
                        exchange_client = em.get_exchange(exchange)
                        if exchange_client and hasattr(exchange_client, 'fetch_klines'):
                            klines = exchange_client.fetch_klines(symbol, interval, limit=limit)
                            if klines:
                                self._klines_cache[cache_key] = {'data': klines, 'timestamp': datetime.now()}
                                return klines
                except Exception:
                    pass

            # 공개 API 폴백
            if exchange == 'binance':
                klines = self._fetch_binance_klines_public_with_retry(symbol, interval, limit)
                if klines:
                    self._klines_cache[cache_key] = {'data': klines, 'timestamp': datetime.now()}
                    return klines

            return None
        except Exception as e:
            print(f"_safe_fetch_klines 오류: {e}")
            return None

    def _fetch_binance_klines_public_with_retry(self, symbol: str, interval: str, limit: int) -> Optional[List[List[Any]]]:
        """바이낸스 공개 K라인 조회 (재시도 포함)"""
        for attempt in range(2):
            try:
                result = self._fetch_binance_klines_public(symbol, interval, limit)
                if result:
                    return result
            except Exception as e:
                print(f"바이낸스 K라인 조회 실패 (시도 {attempt+1}): {e}")
                if attempt < 1:
                    import time
                    time.sleep(1)
        return None

    def _fetch_binance_klines_public(self, symbol: str, interval: str, limit: int) -> Optional[List[List[Any]]]:
        """바이낸스 공개 K라인 조회"""
        try:
            import requests
            url = 'https://fapi.binance.com/fapi/v1/klines'
            params = {'symbol': symbol, 'interval': interval, 'limit': limit}
            r = requests.get(url, params=params, timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, list) and data and isinstance(data[0], list):
                return data
            return None
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # P3-1: 한국 주식 시장 데이터 (네이버 금융 공개 API)
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_naver_stock_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """네이버 금융 모바일 API에서 개별 종목 현재가 조회 (API 키 불필요)."""
        try:
            import requests
            url = f"https://m.stock.naver.com/api/stock/{symbol}/basic"
            r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            data = r.json()
            price = float(data.get('closePrice', '0').replace(',', '') or 0)
            change_rate = float(data.get('fluctuationsRatio', '0').replace('%', '').replace('+', '') or 0)
            name = str(data.get('stockName', symbol) or symbol)
            return {'symbol': symbol, 'name': name, 'price': price, 'change': change_rate,
                    'ma7_slope': change_rate * 0.1}
        except Exception:
            return None

    def _fetch_naver_index_data(self) -> Dict[str, Any]:
        """네이버 금융에서 KOSPI/KOSDAQ 지수 조회."""
        results: Dict[str, Any] = {}
        # 사용자 안내용 최근 상태 메타
        self._last_stock_index_fetch_status = {
            'ok': False,
            'message': '지수 정보를 가져오는 중입니다.',
            'action': '잠시 후 새로고침해 주세요.'
        }
        try:
            import requests
            status_codes: List[int] = []
            # KOSPI = 0001, KOSDAQ = 1001
            for idx_code, idx_name in [('0001', 'KOSPI'), ('1001', 'KOSDAQ')]:
                url = f"https://m.stock.naver.com/api/index/{idx_code}/basic"
                r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
                status_codes.append(int(r.status_code or 0))
                if r.status_code == 200:
                    data = r.json()
                    price = float(str(data.get('closePrice', '0')).replace(',', '') or 0)
                    change_rate = float(str(data.get('fluctuationsRatio', '0')).replace('%', '').replace('+', '') or 0)
                    results[idx_name] = {'price': price, 'change': change_rate}
            if results:
                self._last_stock_index_fetch_status = {
                    'ok': True,
                    'message': '지수 정보가 정상 연동되었습니다.',
                    'action': ''
                }
            elif 409 in status_codes:
                self._last_stock_index_fetch_status = {
                    'ok': False,
                    'message': '지수 정보 제공처 응답이 일시 지연되고 있습니다.',
                    'action': '잠시 후 새로고침하거나, 아래 대표 종목 변화율을 먼저 참고해 주세요.'
                }
            elif status_codes:
                self._last_stock_index_fetch_status = {
                    'ok': False,
                    'message': '현재 지수 정보를 불러오지 못했습니다.',
                    'action': '네트워크 연결 확인 후 새로고침해 주세요.'
                }
        except Exception:
            self._last_stock_index_fetch_status = {
                'ok': False,
                'message': '현재 지수 정보를 불러오지 못했습니다.',
                'action': '네트워크 연결 확인 후 새로고침해 주세요.'
            }
        return results

    def _gather_stock_market_data(self) -> Dict[str, Any]:
        """주식 서비스 전용 데이터 수집: 네이버 금융 API 기반."""
        insights: Dict[str, Any] = {
            'daily_changes': [],
            'weekly_changes': [],
            'sector_summary': [],
            'sentiment_summary': {},
            'service_context': 'stock',
            'index_data': {},
        }

        # 대표 종목 (삼성전자, SK하이닉스, NAVER, 카카오, 현대차, LG에너지솔루션)
        major_symbols = [
            ('005930', '삼성전자'),
            ('000660', 'SK하이닉스'),
            ('035420', 'NAVER'),
            ('035720', '카카오'),
            ('005380', '현대차'),
            ('373220', 'LG에너지솔루션'),
        ]

        for code, name in major_symbols:
            data = self._fetch_naver_stock_quote(code)
            if data:
                insights['daily_changes'].append(data)
            else:
                # 네트워크 불가 시 빈 슬롯 (UI에서 "데이터 없음"으로 처리)
                insights['daily_changes'].append({'symbol': code, 'name': name,
                                                   'price': 0, 'change': 0.0, 'ma7_slope': 0.0,
                                                   'no_data': True})

        # 지수 데이터
        insights['index_data'] = self._fetch_naver_index_data()

        # 섹터별 집계
        sector_map = {
            'IT·반도체': ['005930', '000660'],
            '인터넷·플랫폼': ['035420', '035720'],
            '자동차': ['005380', '012330'],
            '2차전지': ['373220', '006400'],
        }
        for sector_name, codes in sector_map.items():
            valid = [d for d in insights['daily_changes']
                     if d.get('symbol') in codes and not d.get('no_data')]
            if valid:
                avg = sum(d['change'] for d in valid) / len(valid)
                insights['sector_summary'].append({'sector': sector_name, 'avg_change': avg,
                                                   'count': len(valid)})

        return insights

    def _fetch_sentiment_summary(self, symbol: str) -> Optional[Dict[str, Any]]:
        """가벼운 시장 심리 요약 (공개 REST 사용, API 키 불필요)"""
        # 캐시 확인
        if not hasattr(self, '_sentiment_cache'):
            self._sentiment_cache = {}
            self._sentiment_cache_duration = 300  # 5분

        cache_key = f"sentiment_{symbol}"
        if cache_key in self._sentiment_cache:
            cache_entry = self._sentiment_cache[cache_key]
            if (datetime.now() - cache_entry['timestamp']).total_seconds() < self._sentiment_cache_duration:
                return cache_entry['data']

        try:
            import requests, time
            summary: Dict[str, Any] = {}
            print(f"바이낸스 API 호출 시작: {symbol}")

            # 펀딩비 (최근 1개) - 재시도 로직 포함
            for attempt in range(2):
                try:
                    fr = requests.get(
                        'https://fapi.binance.com/fapi/v1/fundingRate',
                        params={'symbol': symbol, 'limit': 1}, timeout=8
                    )
                    if fr.status_code == 200 and isinstance(fr.json(), list) and fr.json():
                        summary['funding_rate'] = float(fr.json()[0].get('fundingRate', 0.0))
                        print(f"펀딩비 수집 성공: {summary['funding_rate']}")
                        break
                except Exception as e:
                    print(f"펀딩비 수집 오류 (시도 {attempt+1}): {e}")
                    if attempt < 1:
                        time.sleep(1)
                    pass

            # 롱/숏 비율 (계정/상위) - 재시도 로직 포함
            for attempt in range(2):
                try:
                    gl = requests.get(
                        'https://fapi.binance.com/futures/data/globalLongShortAccountRatio',
                        params={'symbol': symbol, 'period': '5m', 'limit': 1}, timeout=8
                    )
                    if gl.status_code == 200 and isinstance(gl.json(), list) and gl.json():
                        summary['ls_account_ratio'] = float(gl.json()[0].get('longShortRatio', 0.0))
                        break
                except Exception:
                    if attempt < 1:
                        time.sleep(1)
                    pass

            for attempt in range(2):
                try:
                    tl = requests.get(
                        'https://fapi.binance.com/futures/data/topLongShortAccountRatio',
                        params={'symbol': symbol, 'period': '5m', 'limit': 1}, timeout=8
                    )
                    if tl.status_code == 200 and isinstance(tl.json(), list) and tl.json():
                        summary['ls_top_ratio'] = float(tl.json()[0].get('longShortRatio', 0.0))
                        break
                except Exception:
                    if attempt < 1:
                        time.sleep(1)
                    pass

            # 캐시 저장
            if summary:
                self._sentiment_cache[cache_key] = {'data': summary, 'timestamp': datetime.now()}
                return summary

        except Exception as e:
            print(f"시장 심리 데이터 수집 오류: {e}")

        return None

    def _update_ui_with_data(self, insights: Dict[str, Any]):
        """수집된 데이터로 UI 업데이트 - 카드형 섹션에 데이터 표시"""
        try:
            # 메트릭 칩 업데이트
            self._update_metric_chips(insights)

            # 각 섹션별 데이터 업데이트
            self._update_market_momentum_section(insights)
            self._update_coin_sector_section(insights)
            self._update_sentiment_section(insights)
            self._update_portfolio_section(insights)
            self._update_ai_strategy_section(insights)

        except Exception as e:
            print(f"UI 업데이트 오류: {e}")

    def _update_metric_chips(self, insights: Dict[str, Any]):
        """메트릭 칩 업데이트"""
        try:
            service_context = insights.get('service_context') or getattr(self, '_service_context', 'blockchain')
            success_color = self._color('success', '#059669')
            danger_color = self._color('danger', '#dc2626')
            neutral_color = self._color('border', '#6b7280')
            info_color = self._color('info', '#2563eb')

            # 주식 모드: 코인 전용 지표(펀딩/공포탐욕) 대신 일반화된 요약칩 사용
            if service_context == 'stock':
                daily_changes = [d for d in insights.get('daily_changes', []) if isinstance(d, dict) and 'change' in d]
                sector_summary = [s for s in insights.get('sector_summary', []) if isinstance(s, dict) and 'avg_change' in s]

                if daily_changes:
                    avg_change = sum(float(d.get('change', 0.0)) for d in daily_changes) / len(daily_changes)
                    if avg_change > 0.5:
                        direction_text, direction_color = "강세", success_color
                    elif avg_change < -0.5:
                        direction_text, direction_color = "약세", danger_color
                    else:
                        direction_text, direction_color = "중립", neutral_color
                else:
                    direction_text, direction_color = "⏳ 데이터 연결 중", neutral_color

                if sector_summary:
                    positive = sum(1 for s in sector_summary if float(s.get('avg_change', 0.0)) > 0)
                    total = len(sector_summary)
                    breadth_text = f"{positive}/{total} 섹터 상승"
                    breadth_color = success_color if positive >= max(1, total // 2) else neutral_color
                else:
                    breadth_text = "연동 대기"
                    breadth_color = neutral_color

                self.trend_chip_direction.configure(text=f"시장 방향: {direction_text}", fg_color=direction_color)
                self.trend_chip_funding.configure(text=f"섹터 브레드스: {breadth_text}", fg_color=breadth_color)
                # KOSPI/KOSDAQ 지수 표시
                index_data = dict(insights.get('index_data', {}) or {})
                if index_data:
                    kospi = index_data.get('KOSPI', {})
                    kospi_chg = float(kospi.get('change', 0) or 0)
                    kospi_price = float(kospi.get('price', 0) or 0)
                    idx_text = f"KOSPI {kospi_price:,.2f} ({kospi_chg:+.2f}%)" if kospi_price > 0 else "KOSPI 조회 중"
                    idx_color = success_color if kospi_chg > 0 else danger_color if kospi_chg < 0 else neutral_color
                    self.trend_chip_fng.configure(text=f"{idx_text}", fg_color=idx_color)
                else:
                    self.trend_chip_fng.configure(text="KOSPI/KOSDAQ: 연결 중", fg_color=info_color)
                return

            # 시장 방향
            sentiment = insights.get('sentiment_summary', {})
            if not sentiment:
                wait_text = "⏳ 데이터 연결 중"
                if bool(getattr(self, '_trend_refreshing', False)):
                    started_at = getattr(self, '_last_refresh_started_at', None)
                    if started_at:
                        try:
                            elapsed_sec = max(1, int((datetime.now() - started_at).total_seconds()))
                            wait_text = f"⏳ 수집 중({elapsed_sec}s)"
                        except Exception:
                            wait_text = "⏳ 수집 중"
                elif str(getattr(self, '_last_refresh_error', '') or '').strip():
                    wait_text = "수집 지연"

                daily_changes = [d for d in insights.get('daily_changes', []) if isinstance(d, dict) and 'change' in d]
                if daily_changes:
                    avg_change = sum(float(d.get('change', 0.0)) for d in daily_changes) / len(daily_changes)
                    if avg_change > 0.5:
                        direction_text, direction_color = "강세", success_color
                    elif avg_change < -0.5:
                        direction_text, direction_color = "약세", danger_color
                    else:
                        direction_text, direction_color = "횡보", neutral_color
                    self.trend_chip_direction.configure(text=f"시장 방향: {direction_text}", fg_color=direction_color)
                else:
                    self.trend_chip_direction.configure(text=f"시장 방향: {wait_text}", fg_color=neutral_color)

                self.trend_chip_funding.configure(text=f"펀딩비: {wait_text}", fg_color=neutral_color)
                self.trend_chip_fng.configure(text=f"공포/탐욕: {wait_text}", fg_color=neutral_color)
                return

            funding_rate = sentiment.get('funding_rate', 0.0)

            if funding_rate > 0.01:
                direction_text = "상승세"
                direction_color = success_color
            elif funding_rate < -0.01:
                direction_text = "하락세"
                direction_color = danger_color
            else:
                direction_text = "횡보"
                direction_color = neutral_color

            self.trend_chip_direction.configure(text=f"시장 방향: {direction_text}", fg_color=direction_color)

            # 펀딩비
            funding_text = f"{funding_rate:.4f}"
            if abs(funding_rate) > 0.01:
                funding_color = danger_color  # 과열
            elif abs(funding_rate) > 0.005:
                funding_color = self._color('warning', '#f59e0b')  # 주의
            else:
                funding_color = success_color  # 정상

            self.trend_chip_funding.configure(text=f"펀딩비: {funding_text}", fg_color=funding_color)

            # 공포/탐욕
            ls_ratio = sentiment.get('ls_account_ratio', 1.0)
            if ls_ratio > 1.2:
                fng_text = "탐욕"
                fng_color = danger_color
            elif ls_ratio < 0.8:
                fng_text = "공포"
                fng_color = self._color('info', '#2563eb')
            else:
                fng_text = "중립"
                fng_color = neutral_color

            self.trend_chip_fng.configure(text=f"공포/탐욕: {fng_text}", fg_color=fng_color)

        except Exception as e:
            print(f"메트릭 칩 업데이트 오류: {e}")

    def _update_market_momentum_section(self, insights: Dict[str, Any]):
        """시장 방향 · 모멘텀 섹션 업데이트"""
        try:
            section = self._get_section_textbox('market_momentum')
            if not section:
                return

            service_context = insights.get('service_context') or getattr(self, '_service_context', 'blockchain')

            # ── 주식 모드: 한국 지수 + 대표 종목 ────────────────────────
            if service_context == 'stock':
                index_data = dict(insights.get('index_data', {}) or {})
                daily_changes = [d for d in insights.get('daily_changes', []) if isinstance(d, dict)]

                content = "한국 주식 시장 방향·모멘텀\n\n"

                # 지수 섹션
                if index_data:
                    content += "주요 지수:\n"
                    for idx_name, idx_info in index_data.items():
                        price = float(idx_info.get('price', 0) or 0)
                        change = float(idx_info.get('change', 0) or 0)
                        em = "" if change > 0 else "" if change < 0 else ""
                        price_str = f"{price:,.2f}" if price > 0 else "—"
                        content += f"  {em} {idx_name}: {price_str}  ({change:+.2f}%)\n"
                    content += "\n"
                else:
                    status = getattr(self, '_last_stock_index_fetch_status', {}) or {}
                    msg = status.get('message', '현재 지수 정보를 불러오지 못했습니다.')
                    action = status.get('action', '잠시 후 새로고침해 주세요.')
                    content += f"주요 지수: {msg}\n"
                    content += f"  → 안내: {action}\n\n"

                # 대표 종목 섹션
                content += "대표 종목 일간 변화율:\n"
                available = [d for d in daily_changes if not d.get('no_data')]
                if available:
                    for stock in available[:6]:
                        name = stock.get('name', stock.get('symbol', ''))
                        change = float(stock.get('change', 0) or 0)
                        price = float(stock.get('price', 0) or 0)
                        em = "" if change > 0 else "" if change < 0 else ""
                        price_str = f"{price:,}" if price > 0 else "—"
                        content += f"  {em} {name}({stock.get('symbol', '')}): {price_str}원  {change:+.2f}%\n"
                else:
                    content += "  네이버 금융 연결 후 실시간 종목 현황이 표시됩니다.\n"
                    content += "  (네트워크 오프라인 시 데이터 없음)\n"

                section.configure(state="normal")
                section.delete("1.0", "end")
                section.insert("1.0", content)
                section.configure(state="disabled")
                return

            # ── 블록체인 모드 (기존 로직) ─────────────────────────────────
            unified_trader = None
            if self.dashboard_ref:
                unified_trader = getattr(self.dashboard_ref, 'unified_trader', None)

            total_stats = {}
            if unified_trader and hasattr(unified_trader, 'get_all_statistics'):
                try:
                    stats = unified_trader.get_all_statistics() or {}
                    total_stats = stats.get('total', {}) or {}
                except Exception:
                    total_stats = {}

            total_trades = total_stats.get('total_trades', 0)
            total_pnl = total_stats.get('total_pnl', 0.0)
            win_rate = total_stats.get('win_rate', 0.0)

            # 현재 선정된 코인
            selected_coins = getattr(self.dashboard_ref, 'selected_coins', []) if self.dashboard_ref else []
            if not selected_coins:
                selected_coins_text = "거래 시작 전 (기본 분석: BTC, ETH, BNB)"
            else:
                # 딕셔너리 리스트에서 symbol 추출
                coin_symbols = []
                for coin in selected_coins:
                    if isinstance(coin, dict):
                        symbol = coin.get('symbol', 'UNKNOWN')
                        coin_symbols.append(symbol)
                    else:
                        coin_symbols.append(str(coin))
                selected_coins_text = ", ".join(coin_symbols)

            content = f"""시장 방향·모멘텀

• 현재 선정된 주요 코인: {selected_coins_text}

대표 코인 일간 변화율:"""

            for coin in insights.get('daily_changes', []):
                try:
                    # 딕셔너리인지 확인
                    if isinstance(coin, dict):
                        change_emoji = "" if coin['change'] > 0 else "" if coin['change'] < 0 else ""
                        content += f"\n  {change_emoji} {coin['symbol']}: {coin['change']:+.2f}% (MA7 기울기 {coin['ma7_slope']:+.2f})"
                    else:
                        # 문자열인 경우
                        content += f"\n  {coin}: 분석 중..."
                except Exception as e:
                    print(f"코인 데이터 처리 오류: {coin} - {e}")
                    pass

            if not insights.get('daily_changes'):
                content += "\n  주요 코인 추세 분석 중..."

            # 포트폴리오 통계 추가
            if total_trades > 0:
                content += f"""

나의 거래 현황:
• 총 거래 수: {total_trades}회
• 누적 손익: {total_pnl:+.2f}%
• 승률: {win_rate:.1f}%"""
            else:
                content += f"""

나의 거래 현황:
• 아직 거래 이력이 없습니다
• 거래 시작 후 실시간 통계가 표시됩니다"""

            section.configure(state="normal")
            section.delete("1.0", "end")
            section.insert("1.0", content)
            section.configure(state="disabled")

        except Exception as e:
            print(f"시장 모멘텀 섹션 업데이트 오류: {e}")
            # 안전한 기본값으로 설정
            try:
                section = self._get_section_textbox('market_momentum')
                if section:
                    section.configure(state="normal")
                    section.delete("1.0", "end")
                    section.insert("1.0", "시장 방향·모멘텀\n\n• 시장 분석 중...")
                    section.configure(state="disabled")
            except Exception:
                pass

    def _update_coin_sector_section(self, insights: Dict[str, Any]):
        """대표 코인 · 섹터 흐름 섹션 업데이트"""
        try:
            section = self._get_section_textbox('coin_sector')
            if not section:
                return

            service_context = insights.get('service_context') or getattr(self, '_service_context', 'blockchain')
            sectors = insights.get('sector_summary', [])

            if service_context == 'stock':
                content = "한국 주식 업종·섹터 흐름:\n\n"
            else:
                content = "섹터별 평균 변화율:\n"

            # 섹터 데이터 처리
            for sector in sectors:
                try:
                    sector_name = sector.get('sector', 'Unknown')
                    avg_change = sector.get('avg_change', 0.0)

                    if avg_change > 2.0:
                        status = "[강세]"
                        color_indicator = ""
                    elif avg_change > 0:
                        status = "[소폭 상승]"
                        color_indicator = ""
                    elif avg_change < -2.0:
                        status = "[약세]"
                        color_indicator = ""
                    elif avg_change < 0:
                        status = "[소폭 하락]"
                        color_indicator = ""
                    else:
                        status = "[보통]"
                        color_indicator = ""

                    content += f"  {color_indicator} {sector_name}: {avg_change:+.2f}% {status}\n"
                except Exception:
                    pass

            if not sectors:
                if service_context == 'stock':
                    content += "  IT·반도체 / 인터넷·플랫폼 / 자동차 / 2차전지 섹터 수집 중...\n"
                    content += "  (네트워크 연결 시 네이버 금융 실시간 데이터 표시)\n"
                else:
                    content += "  섹터별 성과를 색상으로 구분하여 표시 (녹색: 상승, 빨간색: 하락)\n"
                    content += "  주요 코인들의 단기/중기/장기 추세를 수치로 비교 분석"

            section.configure(state="normal")
            section.delete("1.0", "end")
            section.insert("1.0", content)
            section.configure(state="disabled")

        except Exception as e:
            print(f"코인 섹터 섹션 업데이트 오류: {e}")

    def _update_sentiment_section(self, insights: Dict[str, Any]):
        """시장 심리 · 거래량 지표 섹션 업데이트"""
        try:
            section = self._get_section_textbox('sentiment_volume')
            if not section:
                return

            service_context = insights.get('service_context') or getattr(self, '_service_context', 'blockchain')
            if service_context == 'stock':
                content = "투자 심리·거래량\n\n"
                content += "• 현재 화면은 대표 종목/업종 흐름 중심으로 먼저 제공합니다.\n"
                content += "• 주식 심리·수급 지표는 제공처/연동 상태에 따라 순차 표시됩니다.\n"
                content += "• 지금 할 일: 대표 종목 변화율 + 섹터 흐름 + 내 포트폴리오 손익을 함께 확인하세요.\n"
                content += "• 지수/심리 값이 비어 있으면 네트워크 확인 후 새로고침을 눌러주세요.\n"

                section.configure(state="normal")
                section.delete("1.0", "end")
                section.insert("1.0", content)
                section.configure(state="disabled")
                return

            sentiment = insights.get('sentiment_summary', {})

            content = "시장 심리·거래량 지표\n\n"

            # 펀딩비 분석
            funding_rate = sentiment.get('funding_rate', 0.0)
            if abs(funding_rate) > 0.01:
                funding_status = "과열 상태"
            elif abs(funding_rate) > 0.005:
                funding_status = "주의 상태"
            else:
                funding_status = "정상 상태"

            # 펀딩비 표시 형식 개선 (과학적 표기법 고려)
            if abs(funding_rate) < 0.00001:
                funding_display = "0.0000"
            else:
                funding_display = f"{funding_rate:.4f}"

            content += f"• 펀딩비 분석: {funding_status} ({funding_display})\n"

            # 롱/숏 비율
            ls_ratio = sentiment.get('ls_account_ratio', 1.0)
            if ls_ratio > 1.2:
                ls_status = "고래 매수 우세"
            elif ls_ratio < 0.8:
                ls_status = "고래 매도 우세"
            else:
                ls_status = "고래 중립"

            content += f"• 고래 거래 비율: {ls_status} (비율: {ls_ratio:.2f})\n"

            # 시장 강도
            if ls_ratio > 1.1:
                market_strength = "강세"
            elif ls_ratio < 0.9:
                market_strength = "약세"
            else:
                market_strength = "중립"

            content += f"• 시장 강도: {market_strength} (롱/숏 비율 기반)\n"

            # 공포/탐욕 지수
            if ls_ratio > 1.2:
                fng_index = "탐욕 지수 높음"
            elif ls_ratio < 0.8:
                fng_index = "공포 지수 높음"
            else:
                fng_index = "심리 상태 중립"

            content += f"• 공포/탐욕 지수: {fng_index}"

            section.configure(state="normal")
            section.delete("1.0", "end")
            section.insert("1.0", content)
            section.configure(state="disabled")

        except Exception as e:
            print(f"시장 심리 섹션 업데이트 오류: {e}")

    def _update_portfolio_section(self, insights: Dict[str, Any]):
        """나의 포트폴리오 트렌드 섹션 업데이트"""
        try:
            section = self._get_section_textbox('portfolio_trend')
            if not section:
                return

            # 기본 통계 수집 (바이낸스 + CCXT 거래소 통합)
            total_trades = 0
            total_pnl = 0.0
            win_rate = 0.0
            active_positions = 0

            # 통합 통계 수집 (DB + 메모리)
            try:
                # DB에서 거래 통계 조회 - trade_log 직접 계산
                import os
                import sqlite3
                from path_utils import get_db_file_path
                db_path = get_db_file_path()

                if os.path.exists(db_path):
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        # exchange_trade_stats 대신 trade_log에서 직접 계산
                        cursor.execute("""
                            SELECT
                                COUNT(*) as total_trades,
                                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                                SUM(pnl) as total_pnl
                            FROM trade_log
                            WHERE exit_time IS NOT NULL
                        """)
                        row = cursor.fetchone()
                        if row:
                            total_trades = row[0] or 0
                            winning_trades = row[1] or 0
                            total_pnl = row[2] or 0.0
                            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            except Exception as e:
                print(f"포트폴리오 통계 조회 오류: {e}")
                pass

            # 메모리에서 활성 포지션 수 조회 (실시간)
            try:
                # 바이낸스 포지션
                if self.dashboard_ref and hasattr(self.dashboard_ref, 'main_app'):
                    main_app = getattr(self.dashboard_ref, 'main_app', None)
                    if main_app and hasattr(main_app, 'trader') and main_app.trader:
                        position_getter = getattr(main_app.trader, 'get_active_positions', None)
                        binance_positions = (
                            position_getter()
                            if callable(position_getter)
                            else getattr(main_app.trader, 'active_positions', {})
                        )
                        active_positions += len(binance_positions)

                # CCXT 거래소 포지션
                unified_trader = None
                if self.dashboard_ref:
                    unified_trader = getattr(self.dashboard_ref, 'unified_trader', None)

                if unified_trader and hasattr(unified_trader, 'get_active_positions'):
                    ccxt_positions = unified_trader.get_active_positions()
                    for exchange_positions in ccxt_positions.values():
                        active_positions += len(exchange_positions)
            except Exception:
                # 폴백: 기존 방식 사용
                pass

            # 거래소 상태
            running = 0
            enabled = 0
            if self.dashboard_ref:
                running = len(getattr(self.dashboard_ref, '_running_exchanges', set()))
                enabled = len(getattr(self.dashboard_ref, 'enabled_exchanges', []) or [])

            if total_trades > 0:
                # 성과 평가
                if total_pnl > 10 and win_rate > 70:
                    performance = "우수"
                elif total_pnl > 5 and win_rate > 60:
                    performance = "양호"
                elif total_pnl > 0 and win_rate > 50:
                    performance = "보통"
                else:
                    performance = "개선 필요"

                # 승률 수준
                if win_rate >= 80:
                    winrate_level = "매우 높음"
                elif win_rate >= 70:
                    winrate_level = "높음"
                elif win_rate >= 60:
                    winrate_level = "보통"
                else:
                    winrate_level = "낮음"

                content = f"""나의 포트폴리오 트렌드

• 활성 포지션 수: {active_positions}
• 자동 거래 상태: {'실행 중' if running > 0 else '대기'} ({running}/{enabled} 거래소)

포트폴리오 분석:
• 총 거래 수: {total_trades}회
• 누적 손익: {total_pnl:+.2f} USDT
• 승률: {win_rate:.1f}% ({winrate_level})
• 성과 평가: {performance}

ℹ현재 제공 범위:
• 총 자산 곡선/샤프 지수는 아직 제공되지 않습니다.
• 본 섹션은 거래 이력·손익·활성 포지션 중심으로 동작합니다."""
            else:
                content = """나의 포트폴리오 트렌드

• 활성 포지션 수: 0
• 자동 거래 상태: 대기 (0/1 거래소)

포트폴리오 분석:
• 아직 거래 이력이 없습니다

ℹ현재 제공 범위:
• 거래 이력 생성 전에는 성과 지표가 비어 있을 수 있습니다.
• 총 자산 곡선/샤프 지수는 아직 제공되지 않습니다."""

            section.configure(state="normal")
            section.delete("1.0", "end")
            section.insert("1.0", content)
            section.configure(state="disabled")

        except Exception as e:
            print(f"포트폴리오 섹션 업데이트 오류: {e}")

    def _update_ai_strategy_section(self, insights: Dict[str, Any]):
        """AI 전략 상태 섹션 업데이트 (커스텀 지표/고래분석/전략신뢰도 포함)"""
        try:
            section = self._get_section_textbox('ai_strategy')
            if not section:
                return

            # ── 커스텀 지표 설정 읽기 ──────────────────────────────
            custom_indicators = getattr(self, '_custom_indicators', [])
            if custom_indicators:
                custom_lines = "\n".join(f"  [{i+1}] {ind}" for i, ind in enumerate(custom_indicators))
                custom_block = f"커스텀 지표 ({len(custom_indicators)}개 등록):\n{custom_lines}"
            else:
                custom_block = "커스텀 지표: 없음 (AI 어시스턴트에서 '지표 추가 [지표명]'으로 등록)"

            # ── 고래/기관 활동 분석 ────────────────────────────────
            try:
                ls_ratio = float(insights.get('long_short_ratio', 1.0) or 1.0)
                oi = insights.get('open_interest', None)
                whale_dir = "고래 매수 우세 " if ls_ratio > 1.05 else ("고래 매도 우세 " if ls_ratio < 0.95 else "고래 중립 ")
                oi_txt = f"{float(oi):,.0f}" if oi else "정보 없음"
                whale_block = (
                    f"기관/고래 활동 분석:\n"
                    f"  • 롱/숏 비율: {ls_ratio:.2f} → {whale_dir}\n"
                    f"  • 미결제약정(OI): {oi_txt}\n"
                    f"  • 온체인 순매수 추정: {'긍정적' if ls_ratio > 1.0 else '부정적'}"
                )
            except Exception:
                whale_block = "기관/고래 활동 분석: 데이터 연결 중"

            # ── 전략 신뢰도 점수 ───────────────────────────────────
            try:
                raw_score = insights.get('confidence_score', None)
                if raw_score is None:
                    # 가용 지표들로 신뢰도 추정
                    indicators_ok = sum([
                        insights.get('trend_score', 0) != 0,
                        insights.get('rsi', 0) not in (0, None),
                        insights.get('macd', None) is not None,
                        insights.get('volume_ratio', 1.0) != 1.0,
                        insights.get('long_short_ratio', 1.0) != 1.0,
                    ])
                    raw_score = round((indicators_ok / 5.0) * 100)
                score = max(0, min(100, int(raw_score)))
                bar = "█" * (score // 10) + "░" * (10 - score // 10)
                level = "높음 " if score >= 70 else ("중간 " if score >= 40 else "낮음 ")
                confidence_block = (
                    f"전략 신뢰도 점수: {score}% [{bar}]\n"
                    f"  • 신뢰도 수준: {level}\n"
                    f"  • 가용 지표 수: {indicators_ok if 'indicators_ok' in dir() else '?'}/5\n"
                    f"  • 권장 행동: {'현재 전략 유지' if score >= 70 else ('신중하게 접근' if score >= 40 else '관망 권장')}"
                )
            except Exception:
                confidence_block = "전략 신뢰도 점수: 계산 불가 (지표 데이터 부족)"

            # ── 현재 AI 기능 요약 ──────────────────────────────────
            content = f"""AI 전략 상태

현재 AI 기능:
• 실시간 시장 분석 및 신호 생성 
• 동적 임계값 조정 (시장 변동성 기반) 
• 동적 TP/SL 조정 (패턴 기반) 
• 확장된 학습 데이터 (50회 거래 분석) 
• AI 모니터링 중심 거래 시스템 

{confidence_block}

{whale_block}

{custom_block}

AI 어시스턴트 활용:
• 자연어로 설정 변경 가능
• '지표 추가 RSI_14' 형태로 커스텀 지표 등록
• 실시간 거래 상황 문의 및 전략 조언"""

            section.configure(state="normal")
            section.delete("1.0", "end")
            section.insert("1.0", content)
            section.configure(state="disabled")

        except Exception as e:
            print(f"AI 전략 섹션 업데이트 오류: {e}")



    def safe_after(self, delay, func, *args, **kwargs):
        """안전한 after() 메서드 - 위젯 삭제 시 오류 방지"""
        import tkinter as tk

        try:
            if not self.winfo_exists():
                return None

            # 안전한 콜백 래핑
            job_ref = {"id": None}

            def safe_callback():
                try:
                    if self._disposed or not self.winfo_exists():
                        return
                    func(*args, **kwargs)
                except tk.TclError as e:
                    if "invalid command name" in str(e) or "border_parts" in str(e):
                        return
                    else:
                        raise e
                except Exception as e:
                    if "invalid command name" not in str(e) and "TclError" not in str(e) and "border_parts" not in str(e):
                        print(f"market_trend_widget 콜백 오류: {e}")
                finally:
                    job_id = job_ref.get("id")
                    if job_id:
                        try:
                            self._after_jobs.remove(job_id)
                        except (ValueError, AttributeError):
                            pass

            job = self.after(delay, safe_callback)
            job_ref["id"] = job
            if job:
                self._after_jobs.append(job)
            return job
        except tk.TclError as e:
            if "invalid command name" in str(e) or "border_parts" in str(e):
                return None
            else:
                raise e
        except Exception as e:
            print(f"market_trend_widget safe_after 오류: {e}")
            return None

    def cleanup_after_jobs(self):
        """after 작업 정리"""
        import tkinter as tk

        try:
            for job in getattr(self, "_after_jobs", []):
                try:
                    self.after_cancel(job)
                except tk.TclError as e:
                    if "invalid command name" in str(e) or "border_parts" in str(e):
                        continue
                    else:
                        raise e
                except:
                    pass
            self._after_jobs.clear()
            self._auto_refresh_job = None
        except tk.TclError as e:
            if "invalid command name" in str(e) or "border_parts" in str(e):
                pass
            else:
                raise e
        except Exception as e:
            print(f"market_trend_widget cleanup 오류: {e}")

    def _on_destroy(self, event=None):
        try:
            if event is not None and getattr(event, "widget", None) is not self:
                return
        except Exception:
            pass
        self._disposed = True
        self.cleanup_after_jobs()

    def destroy(self):
        self._disposed = True
        self.cleanup_after_jobs()
        return super().destroy()
