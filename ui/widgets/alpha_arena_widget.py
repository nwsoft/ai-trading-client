#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 위젯 (CustomTkinter)

Alpha Arena 모드의 UI 위젯입니다.
기존 자동거래와 완전히 분리된 독립 모드입니다.
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkTextbox, CTkScrollableFrame, CTkTabview, CTkComboBox

try:
    from trading.alpha_arena import AlphaArenaRunner
except ImportError:
    AlphaArenaRunner = None  # type: ignore


class AlphaArenaWidget(CTkFrame):
    """Alpha Arena 위젯"""
    
    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "surface": "#1f2937",
        "background": "#0f172a",
        "border": "#374151",
        "primary": "#3b82f6",
        "secondary": "#4b5563",
        "success": "#22c55e",
        "danger": "#ef4444",
        "warning": "#f59e0b",
        "info": "#3b82f6",
        "accent": "#8b5cf6",
    }
    
    def __init__(self, parent=None, 
                 binance_client=None,
                 ai_manager=None,
                 alpha_arena_runner=None,
                 settings: Optional[Dict[str, Any]] = None,
                 colors: Optional[Dict[str, str]] = None,
                 recorder=None,  # Recorder 인스턴스 추가
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)
        
        # 의존성
        self.binance_client = binance_client
        self.ai_manager = ai_manager
        self.settings = settings or {}
        self.arena_settings = self.settings.get('alpha_arena', {})
        self.recorder = recorder  # Recorder 인스턴스 저장
        
        # 색상 설정
        self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
        
        # Runner 초기화 (전달받은 runner 사용, 없으면 나중에 생성)
        self.runner: Optional[AlphaArenaRunner] = alpha_arena_runner
        self._first_visit = True  # 첫 방문 여부 (모달 표시용)
        
        # UI 초기화 (콜백 설정 전에 UI 요소 생성)
        self.init_ui()
        
        # Runner가 전달되었으면 콜백 설정 (UI 초기화 후)
        if self.runner:
            try:
                self.runner.set_callbacks(
                    on_model_chat=self._on_model_chat,
                    on_trading_decisions=self._on_trading_decisions,
                    on_order_result=self._on_order_result,
                    on_error=self._on_error
                )
                self.logger.info("AlphaArenaRunner 콜백 설정 완료.")
            except Exception as e:
                self.logger.error(f"AlphaArenaRunner 콜백 설정 오류: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
        
        # 첫 방문 시 모달 표시
        if self._first_visit:
            self._show_info_modal()
            self._first_visit = False
    
    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        """색상 가져오기"""
        if fallback is None:
            fallback = self.DEFAULT_COLORS.get(key, "#9ca3af")
        try:
            if isinstance(self.colors, dict):
                value = self.colors.get(key)
                if value:
                    return value
        except Exception:
            pass
        return fallback
    
    def init_ui(self):
        """UI 초기화"""
        # 메인 레이아웃
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 상단: 제어 패널
        self._create_control_panel()
        
        # 본문: 탭 뷰
        self._create_main_content()
    
    def _create_control_panel(self):
        """제어 패널 생성"""
        control_frame = CTkFrame(self, fg_color=self._color("surface"))
        control_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        control_frame.grid_columnconfigure(1, weight=1)
        
        # 제목
        title_label = CTkLabel(
            control_frame,
            text="AlphaArena",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._color("text_primary")
        )
        title_label.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        # 엔진 선택 (Qwen은 현재 미지원 표기)
        engine_frame = CTkFrame(control_frame, fg_color="transparent")
        engine_frame.grid(row=0, column=1, padx=20, pady=15, sticky="e")
        
        CTkLabel(
            engine_frame,
            text="엔진:",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary")
        ).pack(side="left", padx=(0, 10))
        
        # OpenAI만 지원, Qwen은 미지원 표기
        self.engine_combo = CTkComboBox(
            engine_frame,
            values=["deepseek-v4-flash"],  # 멀티 엔진 실거래는 다음 업데이트
            width=150,
            command=self._on_engine_change
        )
        configured_engine = self.arena_settings.get('engine', 'deepseek-v4-flash')
        self.engine_combo.set('deepseek-v4-flash' if configured_engine in ('deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat') else configured_engine)
        self.engine_combo.pack(side="left", padx=(0, 10))
        
        # Qwen 미지원 안내
        CTkLabel(
            engine_frame,
            text="(Qwen: 다음 버전 예정)",
            font=ctk.CTkFont(size=10),
            text_color="#ef4444"
        ).pack(side="left", padx=(0, 20))
        
        # 시작/정지 버튼
        self.start_stop_btn = CTkButton(
            engine_frame,
            text="▶시작",
            width=100,
            height=35,
            fg_color=self._color("success"),
            hover_color="#16a34a",
            command=self._toggle_runner
        )
        self.start_stop_btn.pack(side="left")
    
    def _create_main_content(self):
        """메인 콘텐츠 생성"""
        # 탭 뷰
        self.tabview = CTkTabview(self, fg_color=self._color("surface"))
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # MODEL_CHAT 탭
        self.model_chat_tab = self.tabview.add("MODEL_CHAT")
        self._create_model_chat_tab()
        
        # TRADING_DECISIONS 탭
        self.decisions_tab = self.tabview.add("TRADING_DECISIONS")
        self._create_decisions_tab()
        
        # 포지션/PnL 탭
        self.positions_tab = self.tabview.add("포지션/PnL")
        self._create_positions_tab()
        
        # 거래소 응답 탭
        self.response_tab = self.tabview.add("거래소 응답")
        self._create_response_tab()
    
    def _create_model_chat_tab(self):
        """MODEL_CHAT 탭 생성"""
        self.model_chat_text = CTkTextbox(
            self.model_chat_tab,
            font=ctk.CTkFont(family="Menlo", size=11),
            wrap="word"
        )
        self.model_chat_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.model_chat_text.configure(state="disabled")
    
    def _create_decisions_tab(self):
        """TRADING_DECISIONS 탭 생성"""
        scroll_frame = CTkScrollableFrame(self.decisions_tab)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.decisions_label = CTkLabel(
            scroll_frame,
            text="TRADING_DECISIONS가 여기에 표시됩니다.",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary"),
            anchor="w",
            justify="left"
        )
        self.decisions_label.pack(fill="x", padx=10, pady=10)
    
    def _create_positions_tab(self):
        """포지션/PnL 탭 생성"""
        scroll_frame = CTkScrollableFrame(self.positions_tab)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 포지션 표시 영역
        self.positions_label = CTkLabel(
            scroll_frame,
            text="포지션 정보가 여기에 표시됩니다.",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary"),
            anchor="w",
            justify="left"
        )
        self.positions_label.pack(fill="x", padx=10, pady=10)
        
        # PnL 표시 영역
        self.pnl_label = CTkLabel(
            scroll_frame,
            text="PnL 정보가 여기에 표시됩니다.",
            font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary"),
            anchor="w",
            justify="left"
        )
        self.pnl_label.pack(fill="x", padx=10, pady=10)
    
    def _create_response_tab(self):
        """거래소 응답 탭 생성"""
        self.response_text = CTkTextbox(
            self.response_tab,
            font=ctk.CTkFont(family="Menlo", size=10),
            wrap="word"
        )
        self.response_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.response_text.configure(state="disabled")
    
    def _show_info_modal(self):
        """Alpha Arena 안내 모달 표시"""
        try:
            modal = ctk.CTkToplevel(self)
            modal.title("Alpha Arena 모드 안내")
            modal.geometry("600x400")
            
            try:
                modal.transient(self.winfo_toplevel())
            except Exception:
                modal.transient(modal)
            modal.grab_set()
            
            # 창 중앙 배치
            modal.update_idletasks()
            x = (modal.winfo_screenwidth() // 2) - (600 // 2)
            y = (modal.winfo_screenheight() // 2) - (400 // 2)
            modal.geometry(f"600x400+{x}+{y}")
            
            # 메인 프레임
            main_frame = CTkFrame(modal)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # 제목
            title_label = CTkLabel(
                main_frame,
                text="Alpha Arena 모드 안내",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=self._color("text_primary")
            )
            title_label.pack(pady=20)
            
            # 안내 문구
            info_text = """
AlphaArena는 기본 OFF인 숙련자용 Binance USDT 선물 독립 실험 모드입니다.

시장 데이터와 직전 결과 → DeepSeek V4 Flash 판단 → 구조화 파서 →
AlphaArena 자체 주문 게이트 → Binance 선물 주문 순서로 동작합니다.

기본 가드레일:
• 60초 판단 주기(최소 30초), BTC/ETH/SOL/XRP/DOGE/BNB
• 레버리지 10~20배 제한, 진입마다 TP와 SL 필수
• 심볼 쿨다운 30초, 최대 동시 포지션 6개
• 틱당 모델 제시 위험 합계 상한 1,500 USDT

표준 자동매매의 수익성·포트폴리오·전략 합의 계층과 기존 TP/SL 보험·
워치독을 공유하지 않습니다. 처음 사용자는 표준 LEARNING/PAPER와
AI 커스텀부터 검증하고, 자세한 내용은 사용자 메뉴얼 → AlphaArena에서 확인하세요.
            """
            
            info_label = CTkLabel(
                main_frame,
                text=info_text.strip(),
                font=ctk.CTkFont(size=12),
                text_color=self._color("text_secondary"),
                justify="left",
                anchor="w"
            )
            info_label.pack(padx=20, pady=10, fill="x")
            
            # 확인 버튼
            ok_btn = CTkButton(
                main_frame,
                text="확인",
                width=100,
                command=modal.destroy
            )
            ok_btn.pack(pady=20)
            
        except Exception as e:
            self.logger.error(f"안내 모달 표시 오류: {e}")
    
    def _on_engine_change(self, value: str):
        """엔진 변경 핸들러"""
        try:
            if self.runner and self.runner.running:
                self.logger.warning("실행 중에는 엔진을 변경할 수 없습니다.")
                try:
                    configured_engine = self.arena_settings.get('engine', 'deepseek-v4-flash')
                    self.engine_combo.set('deepseek-v4-flash' if configured_engine in ('deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat') else configured_engine)
                except Exception:
                    pass
                return

            self.arena_settings['engine'] = value
            if isinstance(self.settings, dict):
                self.settings.setdefault('alpha_arena', {})
                self.settings['alpha_arena']['engine'] = value

            try:
                from config.settings import load_settings, save_settings

                current_settings = load_settings()
                current_settings.setdefault('alpha_arena', {})
                current_settings['alpha_arena']['engine'] = value
                save_settings(current_settings)
            except Exception as save_err:
                self.logger.warning(f"AlphaArena 엔진 설정 저장 실패: {save_err}")

            if self.runner:
                self.runner.engine = value

            self.logger.info(f"엔진 변경: {value}")

        except Exception as e:
            self.logger.error(f"엔진 변경 오류: {e}")
    
    def _toggle_runner(self):
        """Runner 시작/정지 토글"""
        try:
            if isinstance(self.settings, dict):
                self.settings.setdefault('alpha_arena', {})
                self.settings['alpha_arena']['engine'] = self.engine_combo.get()
                self.arena_settings = self.settings.get('alpha_arena', {})

            if not self.runner:
                # Runner 초기화 (전달받은 runner가 없을 때만 생성)
                if not AlphaArenaRunner:
                    self.logger.error("AlphaArenaRunner를 import할 수 없습니다.")
                    return
                
                if not self.binance_client:
                    self.logger.error("BinanceClient가 없어 AlphaArenaRunner를 초기화할 수 없습니다.")
                    return
                
                if not self.ai_manager:
                    self.logger.error("AIManager가 없어 AlphaArenaRunner를 초기화할 수 없습니다.")
                    return
                
                self.runner = AlphaArenaRunner(
                    binance_client=self.binance_client,
                    ai_manager=self.ai_manager,
                    settings=self.settings,
                    recorder=self.recorder  # Recorder 전달 (데이터베이스 저장용)
                )
                
                # 콜백 설정
                self.runner.set_callbacks(
                    on_model_chat=self._on_model_chat,
                    on_trading_decisions=self._on_trading_decisions,
                    on_order_result=self._on_order_result,
                    on_error=self._on_error
                )
                self.logger.info("AlphaArenaRunner 초기화 및 콜백 설정 완료.")
            
            if self.runner.running:
                # 정지
                self.runner.stop()
                self.start_stop_btn.configure(
                    text="▶시작",
                    fg_color=self._color("success")
                )
                self.logger.info("Alpha Arena 정지")
            else:
                # 시작
                if self.runner.start():
                    self.start_stop_btn.configure(
                        text="⏹정지",
                        fg_color=self._color("danger")
                    )
                    self.logger.info("Alpha Arena 시작")
                else:
                    self.logger.error("Alpha Arena 시작 실패")
                    
        except Exception as e:
            self.logger.error(f"Runner 토글 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _on_model_chat(self, chat: str):
        """MODEL_CHAT 콜백"""
        try:
            self.model_chat_text.configure(state="normal")
            self.model_chat_text.delete("1.0", "end")
            self.model_chat_text.insert("1.0", chat)
            self.model_chat_text.configure(state="disabled")
            
            # 자동 스크롤
            self.model_chat_text.see("end")
            
        except Exception as e:
            self.logger.warning(f"MODEL_CHAT 업데이트 오류: {e}")
    
    def _on_trading_decisions(self, decisions: Dict[str, Dict]):
        """TRADING_DECISIONS 콜백"""
        try:
            # JSON 포맷팅
            decisions_json = json.dumps(decisions, indent=2, ensure_ascii=False)
            
            # 요약 생성 (TP/SL 누락 표시 포함)
            summary_lines = []
            warnings = []
            for symbol, decision in decisions.items():
                signal = decision.get('signal', 'UNKNOWN')
                # TP/SL 누락 확인
                if signal in ['ENTER_LONG', 'ENTER_SHORT']:
                    profit_target = decision.get('profit_target')
                    stop_loss = decision.get('stop_loss')
                    error = decision.get('error')
                    
                    if error == 'TP/SL 누락' or profit_target is None or stop_loss is None:
                        summary_lines.append(f"{symbol}: {signal} (TP/SL 누락 - 실행 안 됨)")
                        warnings.append(f"{symbol}: TP/SL 누락으로 주문이 실행되지 않습니다.")
                    else:
                        summary_lines.append(f"{symbol}: {signal} (TP: {profit_target}, SL: {stop_loss})")
                else:
                    summary_lines.append(f"{symbol}: {signal}")
            
            summary = "\n".join(summary_lines)
            
            # 경고 메시지 추가
            if warnings:
                warning_text = "\n\n경고:\n" + "\n".join(warnings)
                summary += warning_text
            
            full_text = f"=== 요약 ===\n{summary}\n\n=== 전체 JSON ===\n{decisions_json}"
            
            self.decisions_label.configure(
                text=full_text,
                justify="left",
                anchor="w"
            )
            
        except Exception as e:
            self.logger.warning(f"TRADING_DECISIONS 업데이트 오류: {e}")
    
    def _on_order_result(self, symbol: str, result: Dict[str, Any]):
        """주문 결과 콜백"""
        try:
            self.response_text.configure(state="normal")
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = result.get('status', 'UNKNOWN')
            
            # 상태별 명확한 표시
            if status == 'SUCCESS':
                log_line = f"[{timestamp}] {symbol}: 주문 실행 성공\n"
                if result.get('order_id'):
                    log_line += f"  주문 ID: {result.get('order_id')}\n"
            elif status == 'SKIPPED':
                skip_reason = result.get('skip_reason', 'Unknown')
                # TP/SL 누락을 명확히 강조
                if 'TP/SL' in skip_reason or 'profit_target' in skip_reason or 'stop_loss' in skip_reason:
                    log_line = f"[{timestamp}] {symbol}: 주문 스킵 - TP/SL 누락!\n"
                    log_line += f"  ENTER_LONG/ENTER_SHORT 신호는 profit_target과 stop_loss 둘 다 필수입니다.\n"
                    log_line += f"  스킵 사유: {skip_reason}\n"
                else:
                    log_line = f"[{timestamp}] {symbol}: 주문 스킵\n"
                    log_line += f"  스킵 사유: {skip_reason}\n"
            elif status == 'ERROR':
                error = result.get('error', 'Unknown error')
                log_line = f"[{timestamp}] {symbol}: 주문 오류\n"
                log_line += f"  오류: {error}\n"
            else:
                log_line = f"[{timestamp}] {symbol}: {status}\n"
                if result.get('error'):
                    log_line += f"  오류: {result.get('error')}\n"
                if result.get('skip_reason'):
                    log_line += f"  스킵 사유: {result.get('skip_reason')}\n"
                if result.get('order_id'):
                    log_line += f"  주문 ID: {result.get('order_id')}\n"
            
            log_line += "\n"
            
            self.response_text.insert("end", log_line)
            self.response_text.configure(state="disabled")
            
            # 자동 스크롤
            self.response_text.see("end")
            
        except Exception as e:
            self.logger.warning(f"주문 결과 업데이트 오류: {e}")
    
    def _on_error(self, error: str):
        """에러 콜백"""
        try:
            self.response_text.configure(state="normal")
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] 오류: {error}\n\n"
            
            self.response_text.insert("end", log_line)
            self.response_text.configure(state="disabled")
            
            # 자동 스크롤
            self.response_text.see("end")
            
        except Exception as e:
            self.logger.warning(f"에러 업데이트 오류: {e}")
    
    def update_positions_and_pnl(self):
        """포지션 및 PnL 업데이트"""
        try:
            if not self.binance_client:
                return
            
            # 포지션 정보 수집
            positions_info = []
            pnl_info = []
            
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
            
            for symbol in symbols:
                position_info = self.binance_client.get_position_info(symbol)
                if position_info:
                    position_amt = float(position_info.get('positionAmt', 0))
                    if abs(position_amt) > 1e-8:
                        entry_price = float(position_info.get('entryPrice', 0))
                        unrealized_pnl = float(position_info.get('unRealizedProfit', 0))
                        leverage = int(position_info.get('leverage', 1))
                        
                        side = 'LONG' if position_amt > 0 else 'SHORT'
                        positions_info.append(
                            f"{symbol}: {side} {abs(position_amt):.4f} @ ${entry_price:.2f} (레버리지: {leverage}x)"
                        )
                        pnl_info.append(
                            f"{symbol}: ${unrealized_pnl:.2f} USDT"
                        )
            
            # 업데이트
            if positions_info:
                positions_text = "\n".join(positions_info)
            else:
                positions_text = "포지션 없음"
            
            if pnl_info:
                pnl_text = "\n".join(pnl_info)
            else:
                pnl_text = "PnL 없음"
            
            self.positions_label.configure(
                text=f"=== 포지션 ===\n{positions_text}",
                justify="left",
                anchor="w"
            )
            
            self.pnl_label.configure(
                text=f"=== 미실현 PnL ===\n{pnl_text}",
                justify="left",
                anchor="w"
            )
            
        except Exception as e:
            self.logger.warning(f"포지션/PnL 업데이트 오류: {e}")
    
    def cleanup(self):
        """위젯 정리"""
        try:
            if self.runner and self.runner.running:
                self.runner.stop()
        except Exception:
            pass
