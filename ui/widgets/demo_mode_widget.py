#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
운영 리플레이 상태 위젯
"""

import customtkinter as ctk
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class DemoModeWidget(ctk.CTkFrame):
    """운영 리플레이 상태 표시 위젯"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.demo_trader = None
        self.is_demo_mode = False
        self._disposed = False
        self._update_job = None
        
        self._create_widgets()
        try:
            self.bind("<Map>", self._on_map_visible, add="+")
            self.bind("<Unmap>", self._on_unmap_hidden, add="+")
        except Exception:
            pass
    
    def _create_widgets(self):
        """위젯 생성"""
        # 스크롤 가능한 메인 컨테이너
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="운영 리플레이 상태")
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 상태 표시
        self.status_frame = ctk.CTkFrame(self.scrollable_frame)
        self.status_frame.pack(fill="x", padx=5, pady=5)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="운영 리플레이 비활성화",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(pady=10)

        self.warning_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#d97706"
        )
        self.warning_label.pack_forget()
        
        # 가상 잔고 표시
        self.balance_frame = ctk.CTkFrame(self.scrollable_frame)
        self.balance_frame.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(
            self.balance_frame,
            text="가상 잔고",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(pady=(10, 5))
        
        self.balance_text = ctk.CTkTextbox(
            self.balance_frame,
            height=120,
            font=ctk.CTkFont(size=10)
        )
        self.balance_text.pack(fill="x", padx=10, pady=(0, 10))
        
        # 성과 통계
        self.stats_frame = ctk.CTkFrame(self.scrollable_frame)
        self.stats_frame.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(
            self.stats_frame,
            text="성과 통계",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(pady=(10, 5))
        
        self.stats_text = ctk.CTkTextbox(
            self.stats_frame,
            height=120,
            font=ctk.CTkFont(size=10)
        )
        self.stats_text.pack(fill="x", padx=10, pady=(0, 10))
        
        # 거래 기록
        self.trades_frame = ctk.CTkFrame(self.scrollable_frame)
        self.trades_frame.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(
            self.trades_frame,
            text="최근 거래 기록",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(pady=(10, 5))
        
        self.trades_text = ctk.CTkTextbox(
            self.trades_frame,
            height=100,
            font=ctk.CTkFont(size=9)
        )
        self.trades_text.pack(fill="x", padx=10, pady=(0, 10))
        
        # 새로고침 버튼
        refresh_btn = ctk.CTkButton(
            self.scrollable_frame,
            text="새로고침",
            command=self._refresh_data,
            width=120
        )
        refresh_btn.pack(pady=10)
    
    def set_demo_trader(self, demo_trader):
        """데모 트레이더 설정"""
        self.demo_trader = demo_trader
        self.is_demo_mode = demo_trader is not None
        self._update_display()
    
    def _update_display(self):
        """화면 업데이트"""
        if not self.is_demo_mode or not self.demo_trader:
            self.status_label.configure(
                text="운영 리플레이 비활성화",
                text_color="gray"
            )
            self.balance_text.delete("1.0", "end")
            self.balance_text.insert("1.0", "운영 리플레이가 비활성화되어 있습니다.")
            self.stats_text.delete("1.0", "end")
            self.stats_text.insert("1.0", "운영 리플레이가 비활성화되어 있습니다.")
            self.trades_text.delete("1.0", "end")
            self.trades_text.insert("1.0", "운영 리플레이가 비활성화되어 있습니다.")
            return
        
        # 상태 업데이트
        self.status_label.configure(
            text="운영 리플레이 활성화",
            text_color="green"
        )
        
        # 가상 잔고 업데이트
        self._update_balance_display()
        
        # 성과 통계 업데이트
        self._update_stats_display()
        
        # 거래 기록 업데이트
        self._update_trades_display()
    
    def _update_balance_display(self):
        """가상 잔고 표시 업데이트"""
        if not self.demo_trader:
            return
        
        balances = self.demo_trader.virtual_balances
        balance_text = ""
        
        for exchange, balance in balances.items():
            balance_text += f"{exchange.upper()}:\n"
            for currency, amount in balance.items():
                if amount > 0:
                    if currency == 'KRW':
                        balance_text += f"  {currency}: {amount:,.0f}원\n"
                    else:
                        balance_text += f"  {currency}: {amount:,.2f}\n"
            balance_text += "\n"
        
        self.balance_text.delete("1.0", "end")
        self.balance_text.insert("1.0", balance_text)
    
    def _update_stats_display(self):
        """성과 통계 표시 업데이트"""
        if not self.demo_trader:
            return
        
        try:
            stats = self.demo_trader.get_performance_summary()
            
            stats_text = f"""총 거래 수: {stats.get('total_trades', 0)}회
승률: {stats.get('win_rate', 0):.1f}%
총 수익: {stats.get('total_profit_percent', 0):.2f}%
시간당 수익률: {stats.get('hourly_return_rate', 0):.2f}%
평균 수익/거래: {stats.get('avg_profit_per_trade', 0):.2f}
최대 수익: {stats.get('max_profit', 0):.2f}
최대 손실: {stats.get('max_loss', 0):.2f}

마지막 업데이트: {datetime.now().strftime('%H:%M:%S')}"""
            
            self.stats_text.delete("1.0", "end")
            self.stats_text.insert("1.0", stats_text)
            
        except Exception as e:
            self.stats_text.delete("1.0", "end")
            self.stats_text.insert("1.0", f"통계 로드 실패: {e}")
    
    def _update_trades_display(self):
        """거래 기록 표시 업데이트"""
        if not self.demo_trader:
            return
        
        try:
            trades = self.demo_trader.trade_history[-10:]  # 최근 10개 거래
            trades_text = ""
            
            if not trades:
                trades_text = "아직 거래 기록이 없습니다."
            else:
                for trade in reversed(trades):  # 최신 거래가 위에 오도록
                    timestamp = trade['timestamp'].strftime('%H:%M:%S')
                    symbol = trade['symbol']
                    side = trade['side']
                    profit_pct = trade['profit_percent']
                    close_reason = trade.get('close_reason', 'Unknown')
                    
                    # 수익/손실에 따른 색상 표시
                    if profit_pct > 0:
                        result_icon = ""
                        result_color = "green"
                    else:
                        result_icon = ""
                        result_color = "red"
                    
                    trades_text += f"{result_icon} {timestamp} | {symbol} {side.upper()}\n"
                    trades_text += f"   수익: {profit_pct:+.2f}% ({close_reason})\n\n"
            
            self.trades_text.delete("1.0", "end")
            self.trades_text.insert("1.0", trades_text)
            
        except Exception as e:
            self.trades_text.delete("1.0", "end")
            self.trades_text.insert("1.0", f"거래 기록 로드 실패: {e}")
    
    def _refresh_data(self):
        """데이터 새로고침"""
        self._update_display()
    
    def _start_updates(self):
        """자동 업데이트 시작"""
        if self._disposed:
            return
        try:
            if not self.winfo_viewable():
                self._update_job = None
                return
            self._update_display()
        except Exception:
            self._update_job = None
            return
        # 5초마다 업데이트
        self._update_job = self.after(5000, self._start_updates)

    def _on_map_visible(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return
        if not self._disposed and self._update_job is None:
            self._start_updates()

    def _on_unmap_hidden(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self:
            return
        if self._update_job is not None:
            try:
                self.after_cancel(self._update_job)
            except Exception:
                pass
            self._update_job = None

    def cleanup_after_jobs(self):
        self._disposed = True
        if self._update_job is not None:
            try:
                self.after_cancel(self._update_job)
            except Exception:
                pass
            self._update_job = None

    def destroy(self):
        self.cleanup_after_jobs()
        return super().destroy()
