#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena Runner

메인 실행 루프를 관리합니다.
기존 trader.py, unified_trader.py를 사용하지 않는 독립 모듈입니다.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from .prompt_builder import PromptBuilder
from .response_parser import ResponseParser
from .order_executor import OrderExecutor
from .metrics import ArenaMetrics

try:
    from api.binance_client import BinanceClient
    from trading.ai.ai_manager import AIManager
except ImportError:
    BinanceClient = None  # type: ignore
    AIManager = None  # type: ignore


class AlphaArenaRunner:
    """Alpha Arena 실행 루프"""
    
    def __init__(self, 
                 binance_client: Optional[BinanceClient] = None,
                 ai_manager: Optional[AIManager] = None,
                 settings: Optional[Dict[str, Any]] = None,
                 recorder: Optional[Any] = None):
        """
        Args:
            binance_client: Binance API 클라이언트
            ai_manager: AI Manager (LLM 호출용)
            settings: 설정 딕셔너리
            recorder: Recorder 인스턴스 (데이터베이스 저장용)
        """
        self.binance_client = binance_client
        self.ai_manager = ai_manager
        self.settings = settings or {}
        self.arena_settings = self.settings.get('alpha_arena', {})
        self.recorder = recorder  # 🔥 Recorder 인스턴스 추가
        
        self.logger = logging.getLogger(__name__)
        
        # 세션 정보
        self.session_id: Optional[str] = None
        self.session_start_time: Optional[datetime] = None
        
        # 실행 상태
        self.running = False
        self.stop_event = threading.Event()
        self.run_thread: Optional[threading.Thread] = None
        
        # 틱 주기 (기본 60초, 최소 30초)
        self.tick_interval_sec = max(
            self.arena_settings.get('tick_interval_sec', 60),
            30  # 최소 30초 가드레일
        )
        
        # 컴포넌트 초기화
        self.prompt_builder = PromptBuilder(binance_client=binance_client, settings=settings)
        self.response_parser = ResponseParser()
        self.order_executor = OrderExecutor(binance_client=binance_client, settings=settings, recorder=recorder)  # 🔥 recorder 전달
        
        # 메트릭
        self.metrics: Optional[ArenaMetrics] = None
        
        # 콜백 함수 (UI 업데이트용)
        self.on_model_chat: Optional[Callable[[str], None]] = None
        self.on_trading_decisions: Optional[Callable[[Dict[str, Dict]], None]] = None
        self.on_order_result: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        
        # 엔진 설정
        configured_engine = self.arena_settings.get('engine', 'deepseek-v4-flash')
        self.engine = 'deepseek-v4-flash' if configured_engine in ('deepseek-3.1', 'deepseek-chat-v3.1', 'deepseek-chat') else configured_engine
        self.available_engines = self.arena_settings.get('available_engines', ['deepseek-v4-flash', 'qwen3-max'])
        
        # 마지막 응답 (피드백 루프용)
        self.last_response: Optional[str] = None
        self.last_parse_result: Optional[Dict[str, Any]] = None
    
    def set_callbacks(self,
                     on_model_chat: Optional[Callable[[str], None]] = None,
                     on_trading_decisions: Optional[Callable[[Dict[str, Dict]], None]] = None,
                     on_order_result: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                     on_error: Optional[Callable[[str], None]] = None):
        """콜백 함수 설정 (UI 업데이트용)"""
        self.on_model_chat = on_model_chat
        self.on_trading_decisions = on_trading_decisions
        self.on_order_result = on_order_result
        self.on_error = on_error
    
    def start(self) -> bool:
        """Alpha Arena 실행 시작"""
        try:
            if self.running:
                self.logger.warning("Alpha Arena가 이미 실행 중입니다.")
                return False
            
            # 세션 초기화
            self.session_id = f"arena_{int(time.time())}"
            self.session_start_time = datetime.now()
            
            # 세션 정보 설정
            self.prompt_builder.set_session_info(self.session_id, self.session_start_time)
            self.order_executor.set_session_id(self.session_id)
            
            # 메트릭 초기화
            self.metrics = ArenaMetrics(self.session_id)
            # prompt_builder에 metrics 참조 주입 (sharpe_ratio 계산 연동)
            self.prompt_builder.set_metrics(self.metrics)

            # 초기 잔고 기록
            if self.binance_client:
                balance_info = self.binance_client.get_balance()
                usdt_balance = balance_info.get('USDT', {})
                if isinstance(usdt_balance, dict):
                    wallet_balance = usdt_balance.get('wallet_balance', 0)
                    if wallet_balance > 0:
                        self.metrics.update_balance(wallet_balance)
            
            # 실행 상태 설정
            self.running = True
            self.stop_event.clear()
            
            # 실행 스레드 시작
            self.run_thread = threading.Thread(target=self._run_loop, daemon=True)
            self.run_thread.start()
            
            self.logger.info(f"Alpha Arena 실행 시작: 세션 ID={self.session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Alpha Arena 실행 시작 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def stop(self):
        """Alpha Arena 실행 중지"""
        try:
            if not self.running:
                self.logger.warning("Alpha Arena가 실행 중이 아닙니다.")
                return
            
            # 실행 상태 변경
            self.running = False
            self.stop_event.set()
            
            # 스레드 종료 대기
            if self.run_thread and self.run_thread.is_alive():
                self.run_thread.join(timeout=5)
            
            # 메트릭 종료
            if self.metrics:
                self.metrics.finalize_session()
                self.metrics.log_metrics()
            
            self.logger.info("Alpha Arena 실행 중지")
            
        except Exception as e:
            self.logger.error(f"Alpha Arena 실행 중지 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _run_loop(self):
        """메인 실행 루프"""
        try:
            self.logger.info("Alpha Arena 실행 루프 시작")
            
            while self.running:
                try:
                    # 틱 실행
                    self._execute_tick()
                    
                    # 틱 주기 대기 (중단 가능)
                    if self.stop_event.wait(timeout=self.tick_interval_sec):
                        # 중단 신호 수신
                        self.logger.info("Alpha Arena 중단 신호 수신")
                        break
                    
                except Exception as e:
                    self.logger.error(f"틱 실행 오류: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    
                    # 에러 콜백
                    if self.on_error:
                        try:
                            self.on_error(str(e))
                        except Exception:
                            pass
                    
                    # 오류 발생 시에도 중단 가능하도록 대기
                    if self.stop_event.wait(timeout=5):
                        break
            
            self.logger.info("Alpha Arena 실행 루프 종료")
            
        except Exception as e:
            self.logger.error(f"Alpha Arena 실행 루프 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _execute_tick(self):
        """단일 틱 실행"""
        try:
            # 메트릭 기록
            if self.metrics:
                self.metrics.record_tick()
            
            # 1. 프롬프트 생성
            prompt = self.prompt_builder.build_prompt()
            if not prompt:
                self.logger.warning("프롬프트 생성 실패")
                return
            
            # 2. LLM 호출
            response = self._call_llm(prompt)
            if not response:
                self.logger.warning("LLM 응답 없음")
                return
            
            self.last_response = response
            
            # 3. 응답 파싱
            parse_result = self.response_parser.parse_response(response)
            self.last_parse_result = parse_result
            
            model_chat = parse_result.get('model_chat', '')
            trading_decisions = parse_result.get('trading_decisions', {})
            parse_errors = parse_result.get('parse_errors', [])
            
            # 파싱 오류 로깅
            if parse_errors:
                for error in parse_errors:
                    self.logger.warning(f"파싱 오류: {error}")
            
            # MODEL_CHAT 콜백
            if model_chat and self.on_model_chat:
                try:
                    self.on_model_chat(model_chat)
                except Exception as e:
                    self.logger.warning(f"MODEL_CHAT 콜백 오류: {e}")
            
            # TRADING_DECISIONS 콜백
            if trading_decisions and self.on_trading_decisions:
                try:
                    self.on_trading_decisions(trading_decisions)
                except Exception as e:
                    self.logger.warning(f"TRADING_DECISIONS 콜백 오류: {e}")
            
            # 4. 주문 실행
            if trading_decisions:
                self._execute_trading_decisions(trading_decisions)
            
            # 5. 피드백 루프 (주문 결과를 프롬프트 빌더에 추가)
            # 다음 틱에서 자동으로 반영됨
            
        except Exception as e:
            self.logger.error(f"틱 실행 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _call_llm(self, prompt: str) -> Optional[str]:
        """LLM 호출"""
        try:
            if not self.ai_manager:
                self.logger.error("AI Manager가 설정되지 않았습니다.")
                return None
            
            if not self.ai_manager.enabled():
                self.logger.error("AI Manager가 활성화되지 않았습니다.")
                return None
            
            # 모델 결정
            # DeepSeek는 OpenAI 호환 API이므로 동일한 클라이언트 사용
            # 모델 이름 매핑: 설정의 engine 값 -> 실제 API 모델명
            engine_to_model = {
                'deepseek-3.1': 'deepseek-v4-flash',
                'deepseek-chat-v3.1': 'deepseek-v4-flash',
                'deepseek-chat': 'deepseek-v4-flash',
                'deepseek-v4-flash': 'deepseek-v4-flash',
                'deepseek-v4-pro': 'deepseek-v4-pro',
                'qwen3-max': 'qwen-plus'  # Qwen API 모델명 (실제 사용 시 확인 필요)
            }
            use_model = engine_to_model.get(self.engine, self.engine)
            
            # 시스템 프롬프트 (간단한 지시사항)
            system_prompt = "You are an autonomous trading agent operating on Binance USDT perpetual futures. Follow the instructions carefully and provide both MODEL_CHAT and TRADING_DECISIONS."
            
            # LLM 호출
            response = self.ai_manager.client.chat(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=use_model,
                temperature=0.3,
                max_tokens=4000
            )
            
            if response:
                self.logger.debug(f"LLM 응답 수신 (모델: {use_model}, 길이: {len(response)})")
                return response
            else:
                self.logger.warning(f"LLM 응답 없음 (모델: {use_model})")
                return None
                
        except Exception as e:
            self.logger.error(f"LLM 호출 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def _execute_trading_decisions(self, trading_decisions: Dict[str, Dict]):
        """TRADING_DECISIONS 실행"""
        try:
            # 심볼 매핑 (BTC -> BTCUSDT)
            symbol_map = {
                'BTC': 'BTCUSDT',
                'ETH': 'ETHUSDT',
                'SOL': 'SOLUSDT',
                'XRP': 'XRPUSDT',
                'DOGE': 'DOGEUSDT',
                'BNB': 'BNBUSDT'
            }
            
            # 틱 시작 시 리스크 캡 리셋
            self.order_executor._reset_tick_tracking()
            
            # 각 심볼별 주문 실행
            for symbol_key, decision in trading_decisions.items():
                if not self.running:
                    break
                
                # 심볼 매핑
                symbol = symbol_map.get(symbol_key.upper(), symbol_key.upper())
                if not symbol.endswith('USDT'):
                    symbol = f"{symbol}USDT"
                
                # 주문 실행
                result = self.order_executor.execute_trading_decision(symbol, decision)
                
                # 주문 결과 기록
                if self.metrics:
                    self.metrics.record_order_result(result)
                
                # 주문 결과를 프롬프트 빌더에 추가 (피드백 루프)
                self.prompt_builder.add_order_result({
                    'symbol': symbol,
                    'decision': decision,
                    'result': result
                })
                
                # 에러 기록 (ERROR와 SKIPPED 모두 피드백에 포함)
                if result.get('status') == 'ERROR':
                    error_info = {
                        'symbol': symbol,
                        'error': result.get('error', 'Unknown error')
                    }
                    self.prompt_builder.add_error(error_info)
                elif result.get('status') == 'SKIPPED':
                    # 🔥 SKIPPED 상태도 피드백에 포함 (특히 TP/SL 누락)
                    skip_reason = result.get('skip_reason', 'Unknown')
                    skip_info = {
                        'symbol': symbol,
                        'error': f"주문 스킵: {skip_reason}",
                        'skip_reason': skip_reason
                    }
                    self.prompt_builder.add_error(skip_info)
                
                # 콜백 호출
                if self.on_order_result:
                    try:
                        self.on_order_result(symbol, result)
                    except Exception as e:
                        self.logger.warning(f"주문 결과 콜백 오류 ({symbol}): {e}")
                
                # 로깅
                status = result.get('status', 'UNKNOWN')
                if status == 'SUCCESS':
                    self.logger.info(f"[{symbol}] 주문 실행 성공: {result.get('order_id', 'N/A')}")
                elif status == 'SKIPPED':
                    skip_reason = result.get('skip_reason', 'Unknown')
                    self.logger.info(f"[{symbol}] 주문 스킵: {skip_reason}")
                elif status == 'ERROR':
                    error = result.get('error', 'Unknown error')
                    self.logger.error(f"[{symbol}] 주문 실행 오류: {error}")
                
        except Exception as e:
            self.logger.error(f"TRADING_DECISIONS 실행 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            'running': self.running,
            'session_id': self.session_id,
            'session_start_time': self.session_start_time.isoformat() if self.session_start_time else None,
            'tick_interval_sec': self.tick_interval_sec,
            'engine': self.engine,
            'metrics': self.metrics.get_metrics() if self.metrics else None
        }
