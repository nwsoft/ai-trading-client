#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
범용 트레이딩 워커 - 모든 거래소 지원
"""

import threading
import time
import gc
from typing import Any, Optional, Dict

class TradingWorker:
    """범용 트레이딩 워커 - 바이낸스, CCXT 모든 거래소 지원"""
    
    def __init__(self, main_app: Any):
        self.main_app = main_app
        self.running = False
        # 🔥 중첩 실행 방지: 15개 코인 분석 시간 고려 (60초)
        self.interval = 60
        if hasattr(main_app, "settings") and main_app.settings:
            self.interval = main_app.settings.get("auto_trade_interval", 60)
        self.stop_event = threading.Event()  # 🔥 즉시 종료를 위한 이벤트
        
    def start(self):
        """트레이딩 워커 시작"""
        self.running = True
        self.stop_event.clear()  # 🔥 이벤트 초기화
        # 🔥 로그는 main.py에서 관리 (중복 방지)
        
    def run_trading_loop(self):
        """범용 트레이딩 루프 실행"""
        # 🔥 중복 제거: self.running = True 제거 (stop() 메서드와 충돌)
        # self.running은 __init__에서 False로 초기화되고, start()에서만 True로 설정되어야 함
        last_cleanup_time = time.time()
        
        from log_system.log_adapter import log_event
        log_event('system', '🔥 트레이딩 워커 시작')
        
        # 🔥 즉시 첫 실행 (60초 대기 없이)
        try:
            selected_exchange = "binance"
            if hasattr(self.main_app, "settings") and self.main_app.settings:
                selected_exchange = self.main_app.settings.get("selected_exchange", "binance")
            
            log_event('system', f'🔥 첫 거래 실행 시작: {selected_exchange}')
            
            if selected_exchange == "binance":
                log_event('system', '🔥 바이낸스 거래 실행 호출')
                self._run_binance_trading()
            else:
                log_event('system', f'🔥 통합 거래소 거래 실행 호출: {selected_exchange}')
                self._run_unified_trading(selected_exchange)
                
            log_event('system', '🔥 첫 거래 실행 완료')
                
        except Exception as e:
            log_event('system', f'❌ 첫 거래 실행 오류: {e}')
            import traceback
            log_event('system', f'❌ 상세 오류: {traceback.format_exc()}')
        
        # 🔥 이후 60초 간격으로 실행
        while self.running:
            try:
                current_time = time.time()
                if current_time - last_cleanup_time >= 3600:
                    self.cleanup_memory()
                    last_cleanup_time = current_time
                
                selected_exchange = "binance"
                if hasattr(self.main_app, "settings") and self.main_app.settings:
                    selected_exchange = self.main_app.settings.get("selected_exchange", "binance")
                
                from log_system.log_adapter import log_event
                log_event('system', f'🔥 정기 거래 실행: {selected_exchange}')
                
                if selected_exchange == "binance":
                    self._run_binance_trading()
                else:
                    self._run_unified_trading(selected_exchange)
                
                # 🔥 즉시 종료를 위한 인터럽트 가능한 sleep
                if self.stop_event.wait(timeout=self.interval):
                    # stop_event가 설정되면 즉시 종료
                    from log_system.log_adapter import log_event
                    log_event('system', '🔥 즉시 종료 신호 수신 - 루프 중단')
                    break
                
            except Exception as e:
                from log_system.log_adapter import log_event
                log_event('system', f'❌ 트레이딩 루프 오류: {e}')
                # 🔥 오류 발생 시에도 즉시 종료 가능하도록
                if self.stop_event.wait(timeout=5):
                    log_event('system', '🔥 오류 복구 중 즉시 종료 신호 수신')
                    break
                
        from log_system.log_adapter import log_event
        log_event('system', '🔥 트레이딩 루프 종료')
    
    def _run_binance_trading(self):
        """바이낸스 거래 실행 - 코인 선택 + 분석만"""
        from log_system.log_adapter import log_event
        try:
            log_event('system', '🔥 _run_binance_trading 시작')
            
            # 1. 코인 선택 (필요시에만)
            if not hasattr(self.main_app, 'selected_coins') or not self.main_app.selected_coins:
                log_event('system', '🔥 코인 선택 필요 - select_trading_coins 호출')
                if hasattr(self.main_app, "select_trading_coins"):
                    self.main_app.select_trading_coins()
            else:
                log_event('system', f'🔥 코인 이미 선택됨: {len(self.main_app.selected_coins)}개')
            
            # 2. Trader 객체 확인 및 main_app 참조 설정
            if not hasattr(self.main_app, 'trader') or not self.main_app.trader:
                log_event('system', '❌ Trader 객체가 없습니다!')
                return
            
            # 🔥 Trader에 main_app 참조 설정
            self.main_app.trader.main_app = self.main_app
            
            log_event('system', '🔥 Trader 객체 확인 완료')
            
            # 3. 선택된 코인 분석 (trader.execute_trading_cycle에 위임)
            if hasattr(self.main_app.trader, "execute_trading_cycle"):
                log_event('system', '🔥 trader.execute_trading_cycle 호출 시작')
                self.main_app.trader.execute_trading_cycle()
                log_event('system', '🔥 trader.execute_trading_cycle 호출 완료')
            else:
                log_event('system', '❌ trader.execute_trading_cycle 메서드가 없습니다!')
                    
        except Exception as e:
            log_event('system', f'❌ 바이낸스 거래 실행 오류: {e}')
            import traceback
            log_event('system', f'❌ 상세 오류: {traceback.format_exc()}')
    
    def _run_unified_trading(self, exchange_name: str):
        """통합 거래소 거래 실행"""
        if hasattr(self.main_app, "unified_trader") and self.main_app.unified_trader:
            try:
                ut = self.main_app.unified_trader
                # 이미 모니터링 스레드가 실행 중이면 사이클만 실행(재진입 방지)
                if getattr(ut, 'monitoring_flags', {}).get(exchange_name, False):
                    if hasattr(ut, 'execute_trading_cycle_unified'):
                        ut.execute_trading_cycle_unified(exchange_name)
                elif hasattr(ut, "start_trading"):
                    ut.start_trading(exchange_name)
            except Exception as e:
                from log_system.log_adapter import log_event
                log_event('system', f'❌ {exchange_name} 거래 실행 오류: {e}')
    
    def _get_logger(self):
        """안전한 로거 접근"""
        if hasattr(self.main_app, "_get_main_logger"):
            return self.main_app._get_main_logger()
        return None
                
    def cleanup_memory(self):
        """메모리 정리"""
        try:
            gc.collect()
            from log_system.log_adapter import log_event
            log_event('system', '메모리 정리 완료')
        except Exception as e:
            from log_system.log_adapter import log_event
            log_event('system', f'❌ 메모리 정리 오류: {e}')
            
    def stop(self):
        """트레이딩 워커 중지 (즉시 종료)"""
        self.running = False
        self.stop_event.set()  # 🔥 즉시 종료 신호 전송
        from log_system.log_adapter import log_event
        log_event('system', '🔥 트레이딩 워커 즉시 중지 요청됨')

        # STOP 포지션 처리 정책 확인
        # close_all: 기존 포지션 즉시 청산 (stop_trading_gracefully 호출)
        # keep_with_tp_sl (기본): 신규 진입만 차단, TP/SL에 맡김
        _coin_policy = 'keep_with_tp_sl'
        try:
            settings = {}
            if hasattr(self.main_app, 'settings') and isinstance(self.main_app.settings, dict):
                settings = self.main_app.settings
            _coin_policy = str(
                settings.get(
                    'asset_stop_position_policy',
                    settings.get('stock_stop_position_policy', 'keep_with_tp_sl')
                )
            )
        except Exception:
            pass

        # 🔥 실행 중인 거래 중단 (정책에 따라 graceful 또는 즉시)
        if hasattr(self.main_app, 'trader') and self.main_app.trader:
            try:
                if _coin_policy == 'close_all' and hasattr(self.main_app.trader, 'stop_trading_gracefully'):
                    self.main_app.trader.stop_trading_gracefully()
                    log_event('system', '🔥 close_all 정책: Binance 포지션 즉시 청산 요청')
                elif hasattr(self.main_app.trader, 'stop_trading'):
                    self.main_app.trader.stop_trading()
                    log_event('system', '🔥 keep_with_tp_sl 정책: Binance 신규 진입 차단, TP/SL 유지')
            except Exception as e:
                log_event('system', f'❌ Binance 거래 중단 오류: {e}')

        # CCXT(unified_trader) 거래소도 동일 정책 적용
        if hasattr(self.main_app, 'unified_trader') and self.main_app.unified_trader:
            try:
                ut = self.main_app.unified_trader
                if hasattr(ut, 'monitoring_flags'):
                    for exchange_name in list(ut.monitoring_flags.keys()):
                        if hasattr(ut, 'stop_trading'):
                            ut.stop_trading(exchange_name, close_all=(_coin_policy == 'close_all'))
                            log_event('system', f'🔥 CCXT {exchange_name} 거래 중단 (close_all={_coin_policy == "close_all"})')
            except Exception as e:
                log_event('system', f'❌ CCXT 거래 중단 오류: {e}')
    
    # 🔥 중복 제거: stop_trading() 메서드 삭제 (stop() 메서드로 통합)
