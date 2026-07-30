#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 패턴 분석 기반 TP/SL/Position Size 자동 조정
손실 원인 분석 및 전략 수정
"""

import numpy as np
import pandas as pd
import logging
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import sqlite3
import json

# 통합 로그 어댑터 (print 제거 후 구조화 이벤트 로깅 사용)
try:
    from log_system.log_adapter import log_event  # type: ignore
except Exception:  # 안전장치 (초기 로딩 순서 문제 시)
    def log_event(category: str, message: str, *_, **__):  # type: ignore
        logging.getLogger(__name__).info(f"[{category}] {message}")


class OptimizationType(Enum):
    """최적화 타입"""
    TP_SL = "TP_SL"
    POSITION_SIZE = "POSITION_SIZE"
    ENTRY_TIMING = "ENTRY_TIMING"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"


@dataclass
class OptimizationResult:
    """최적화 결과"""
    symbol: str
    optimization_type: OptimizationType
    original_params: Dict
    optimized_params: Dict
    improvement_score: float
    confidence: float
    reasoning: str
    timestamp: datetime


@dataclass
class LossAnalysis:
    """손실 분석"""
    symbol: str
    loss_reason: str
    frequency: int
    avg_loss: float
    max_loss: float
    pattern: str
    recommendation: str
    timestamp: datetime


class Optimizer:
    """AI 기반 거래 파라미터 최적화"""
    
    def __init__(self, recorder, settings=None, binance_client=None, logger=None, ai_manager=None):
        self.recorder = recorder
        self.settings = settings or {}
        self.binance_client = binance_client
        # logger가 주입되면 사용, 아니면 로컬 logger
        self.logger = logger or logging.getLogger(__name__)
        
        # 🔥 AI 매니저 설정
        self.ai_manager = ai_manager
        
        # 🔥 설정값 검증 및 기본값 설정
        if not self.settings:
            self.logger.warning("⚠️ Optimizer에 settings가 전달되지 않음 - 기본값 사용")
            self.settings = {
                'min_trade_amount': 5.0,
                'default_tp': 0.0018,
                'default_sl': 0.0020,
                'default_leverage': 1
            }
        else:
            self.logger.info(f"✅ Optimizer 설정값 로드: min_trade_amount={self.settings.get('min_trade_amount', 5.0)}")
        
        # 최적화 설정(기본값)
        self.opt_cfg = {
            'optimization_interval': 6,   # 시간
            'learning_period': 7,         # 일
            'min_trades_for_analysis': 10,
            'max_optimization_iterations': 100,
            'improvement_threshold': 0.05,
            'risk_adjustment_factor': 0.8
        }
        
        self.opt_cfg.update(self.settings.get('optimizer', {}))
        self.optimization_history = []
        self.pattern_db = {}
        
        # AI 포지션 크기 최적화 캐시. 시장분석 추론 캐시와는 별도 경로이므로
        # 동일한 ai_cost_control 설정 아래에서 호출 조건을 명시적으로 제한한다.
        ai_cost_cfg = dict(self.settings.get('ai_cost_control', {}) or {})
        self.ai_cache = {}
        self.ai_last_attempt = {}
        self.cache_duration = max(
            60,
            int(ai_cost_cfg.get('position_sizing_cache_sec', 900) or 900),
        )
        self.ai_retry_cooldown_sec = max(
            10,
            int(ai_cost_cfg.get('position_sizing_retry_cooldown_sec', 120) or 120),
        )
        self.ai_position_price_change_bps = max(
            1.0,
            float(ai_cost_cfg.get('position_sizing_price_change_bps', 100.0) or 100.0),
        )
        self.ai_position_confidence_delta = max(
            0.01,
            float(ai_cost_cfg.get('position_sizing_confidence_delta', 0.10) or 0.10),
        )
        self.max_cache_size = max(
            10,
            int(ai_cost_cfg.get('position_sizing_max_cache_entries', 100) or 100),
        )
        
        self.logger.info("Optimizer 초기화 완료 (settings/binance_client/ai_manager 연동 + AI 캐싱 시스템)")
        
        # 🔥 심볼 필터 오버라이드 캐시 초기화
        self.symbol_filter_overrides = {}

        # 디버그 옵션 (settings.optimizer.debug_filters 또는 settings.debug_filters)
        self.debug_filters = False
        try:
            self.debug_filters = (
                (self.settings.get('optimizer', {}) or {}).get('debug_filters') or
                self.settings.get('debug_filters', False)
            ) is True
        except Exception:
            self.debug_filters = False

    # 내부 디버그 로깅 헬퍼 (print 대체)
    def _dbg(self, symbol: str, msg: str):
        if getattr(self, 'debug_filters', False):
            try:
                log_event('trade', f"{msg}", exchange=symbol, level='DEBUG', logger=self.logger)
            except Exception:
                pass
        
    def update_symbol_filter_override(self, symbol: str, data: dict):
        """심볼별 필터 오버라이드 업데이트 (Trader에서 학습한 값 반영)"""
        try:
            # 메모리 캐시 업데이트
            if not hasattr(self, 'symbol_filter_overrides'):
                self.symbol_filter_overrides = {}
            
            if symbol not in self.symbol_filter_overrides:
                self.symbol_filter_overrides[symbol] = {}
            
            # 기존 데이터와 병합
            self.symbol_filter_overrides[symbol].update(data)
            
            self.logger.info(f"[{symbol}] ✅ symbol filter override updated: {data}")
            
        except Exception as e:
            self.logger.error(f"[{symbol}] ❌ symbol filter override update failed: {e}")
        
    def update_settings(self, new_settings: Dict):
        """설정 업데이트"""
        if not new_settings:
            self.logger.warning("⚠️ 빈 설정으로 업데이트 시도")
            return
            
        # 기존 설정 백업
        old_settings = self.settings.copy()
        
        # 새 설정으로 업데이트. TP/SL은 모든 입력 경계에서 fraction으로 고정한다.
        sanitized = dict(new_settings)
        from config.settings import normalize_trade_rate
        for key, kind in (("default_tp", "tp"), ("default_sl", "sl")):
            if key in sanitized:
                fallback, _ = normalize_trade_rate(
                    self.settings.get(key, 0.0018 if kind == "tp" else 0.0020),
                    kind=kind,
                )
                sanitized[key], changed = normalize_trade_rate(
                    sanitized[key], kind=kind, fallback=fallback
                )
                if changed:
                    try:
                        raw_rate = float(new_settings[key])
                        maximum = 0.05 if kind == "tp" else 0.03
                        legacy_percent = (
                            math.isfinite(raw_rate) and maximum < raw_rate <= 5.0
                        )
                    except Exception:
                        legacy_percent = False
                    if legacy_percent:
                        self.logger.info(
                            f"{key} 레거시 퍼센트 단위 자동 변환: "
                            f"{new_settings[key]} → {sanitized[key]}"
                        )
                    else:
                        self.logger.warning(
                            f"⚠️ {key} 비정상 입력 안전값 복구: "
                            f"{new_settings[key]} → {sanitized[key]}"
                        )
        self.settings.update(sanitized)
        
        # 🔥 중요 설정값 검증
        min_trade_amount = self.settings.get('min_trade_amount', 5.0)
        if min_trade_amount < 5.0:
            self.logger.warning(f"⚠️ min_trade_amount가 너무 작음: {min_trade_amount} → 5.0으로 조정")
            self.settings['min_trade_amount'] = 5.0
        
        # 변경된 설정값 로깅
        changed_settings = {}
        for key, value in sanitized.items():
            if key in old_settings and old_settings[key] != value:
                changed_settings[key] = {'old': old_settings[key], 'new': value}
        
        if changed_settings:
            self.logger.info(f"✅ 설정값 변경 감지: {changed_settings}")
        
        self.logger.info(f"✅ 최적화 설정 업데이트 완료: min_trade_amount={self.settings.get('min_trade_amount', 5.0)}")
        
    def apply_parameters(self, symbol: str, signal: str, confidence: float, base_params: Dict) -> Dict:
        """최적화된 파라미터 적용"""
        try:
            # 기본 파라미터 복사
            optimized_params = base_params.copy()
            
            # 심볼별 최적화 결과 가져오기
            symbol_optimization = self.get_symbol_optimization(symbol)
            
            if symbol_optimization:
                # TP/SL 최적화 적용
                if 'tp_ratio' in symbol_optimization:
                    optimized_params['tp_price'] = self.calculate_optimized_tp(
                        symbol, signal, symbol_optimization['tp_ratio']
                    )
                    
                if 'sl_ratio' in symbol_optimization:
                    optimized_params['sl_price'] = self.calculate_optimized_sl(
                        symbol, signal, symbol_optimization['sl_ratio']
                    )
                    
                # 포지션 크기 최적화
                if 'position_size_factor' in symbol_optimization:
                    optimized_params['quantity'] *= symbol_optimization['position_size_factor']
                    
                # 레버리지 최적화
                if 'leverage_factor' in symbol_optimization:
                    optimized_params['leverage'] = int(optimized_params['leverage'] * symbol_optimization['leverage_factor'])
                    
            # 신뢰도 기반 조정
            optimized_params = self.adjust_by_confidence(optimized_params, confidence)
            
            # 리스크 관리 적용
            optimized_params = self.apply_risk_management(optimized_params, symbol)
            
            self.logger.info(f"{symbol} 최적화된 파라미터 적용: {optimized_params}")
            
            return optimized_params
            
        except Exception as e:
            self.logger.error(f"파라미터 적용 중 오류: {e}")
            return base_params
            
    def get_symbol_optimization(self, symbol: str) -> Optional[Dict]:
        """심볼별 최적화 결과 가져오기"""
        try:
            # 데이터베이스에서 최적화 결과 조회
            query = """
                SELECT optimization_data FROM ai_optimization 
                WHERE symbol = ? AND timestamp > datetime('now', '-1 day')
                ORDER BY timestamp DESC LIMIT 1
            """
            
            result = self.recorder.execute_query(query, (symbol,))
            
            if result:
                return json.loads(result[0][0])
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"심볼 최적화 결과 조회 중 오류: {e}")
            return None
            
    def calculate_optimized_tp(self, symbol: str, signal: str, tp_ratio: float) -> float:
        """최적화된 TP 가격 계산 (tp_ratio는 0.0018 = 0.18%)"""
        try:
            current_price = self.get_current_price(symbol)
            if current_price <= 0:
                return 0.0
            if signal.upper() == "LONG":
                return current_price * (1 + tp_ratio)
            else:
                return current_price * (1 - tp_ratio)
        except Exception as e:
            self.logger.error(f"TP 최적화 계산 중 오류: {e}")
            return 0.0
            
    def calculate_optimized_sl(self, symbol: str, signal: str, sl_ratio: float) -> float:
        """최적화된 SL 가격 계산 (sl_ratio는 0.002 = 0.20%)"""
        try:
            current_price = self.get_current_price(symbol)
            if current_price <= 0:
                return 0.0
            if signal.upper() == "LONG":
                return current_price * (1 - sl_ratio)
            else:
                return current_price * (1 + sl_ratio)
        except Exception as e:
            self.logger.error(f"SL 최적화 계산 중 오류: {e}")
            return 0.0

    def get_current_price(self, symbol: str) -> float:
        """현재가 가져오기: binance_client 우선, 없으면 0"""
        try:
            if self.binance_client and hasattr(self.binance_client, "get_current_price"):
                return float(self.binance_client.get_current_price(symbol) or 0.0)
            return 0.0
        except Exception as e:
            self.logger.error(f"현재가 가져오기 오류: {e}")
            return 0.0

    # ====== 거래 실행 파라미터 빌드 ======
    def _round_to_step(self, qty: float, step: float) -> float:
        if step and step > 0:
            # 🔥 ceil to step (올림 방향으로 수정)
            return math.ceil(qty / step) * step
        return qty

    def _resolve_exchange_filters(self, symbol: str) -> dict:
        """거래소 minQty/stepSize 등 필터 조회 (autotrade.py 방식으로 개선)"""
        # 디버그 추적 (기존 print → 구조화 로그)
        self._dbg(symbol, "🔥 _resolve_exchange_filters 시작")
        # 명시적 타입: 값은 float/int/None 허용 (pyright 타입 경고 방지)
        filters: Dict[str, float | int | None] = {
            'minQty': None,
            'stepSize': None,
            'quantity_precision': None,
            'price_precision': None,
            'minNotional': None
        }
        
        # 🔥 min_notional 초기화 및 안전장치
        min_notional = None
        
        try:
            self._dbg(symbol, "🔥 _resolve_exchange_filters 시작 (중복 호출)")
            self.logger.info(f"[{symbol}] 🔍 _resolve_exchange_filters 시작")
            self._dbg(symbol, f"🔥 binance_client 존재: {self.binance_client is not None}")
            self.logger.info(f"[{symbol}] 🔍 binance_client 존재: {self.binance_client is not None}")
            self._dbg(symbol, f"🔥 get_symbol_info_direct 메서드 존재: {hasattr(self.binance_client, 'get_symbol_info_direct') if self.binance_client else False}")
            self.logger.info(f"[{symbol}] 🔍 get_symbol_info_direct 메서드 존재: {hasattr(self.binance_client, 'get_symbol_info_direct') if self.binance_client else False}")
            
            if self.binance_client and hasattr(self.binance_client, "get_symbol_info_direct"):
                self.logger.info(f"[{symbol}] 🔍 get_symbol_info_direct 호출 시작")

                # 메서드 호출 전 검증
                try:
                    self._dbg(symbol, "🔥 메서드 호출 전 검증 시작")
                    method = getattr(self.binance_client, "get_symbol_info_direct")
                    self._dbg(symbol, f"🔥 메서드 객체 확인: {type(method)}")
                    self._dbg(symbol, f"🔥 메서드 호출 가능 여부: {callable(method)}")
                except Exception as e:
                    self._dbg(symbol, f"❌ 메서드 검증 실패: {e}")
                    self.logger.error(f"[{symbol}] ❌ 메서드 검증 실패: {e}")
                    symbol_info = None
                else:
                    # 실제 호출
                    try:
                        self._dbg(symbol, "🔥 get_symbol_info_direct 실제 호출 시작")
                        symbol_info = method(symbol)
                        self._dbg(symbol, f"🔥 get_symbol_info_direct 호출 완료, 결과 keys: {list(symbol_info.keys()) if isinstance(symbol_info, dict) else type(symbol_info)}")
                    except Exception as e:
                        self._dbg(symbol, f"❌ get_symbol_info_direct 호출 실패: {e}")
                        self.logger.error(f"[{symbol}] ❌ get_symbol_info_direct 호출 실패: {e}")
                        symbol_info = None
                
                self.logger.info(f"[{symbol}] 🔍 get_symbol_info_direct 호출 완료, 결과: {symbol_info is not None}")
                if symbol_info:
                    # 🔥 에러 상태 감지
                    if symbol_info.get('status') == 'ERROR':
                        self.logger.warning(f"[{symbol}] ⚠️ get_symbol_info_direct 에러: {symbol_info.get('error', 'Unknown error')}")
                        symbol_info = None  # 에러 상태면 None으로 처리
                    else:
                        filters['minQty'] = symbol_info.get('minQty')
                        filters['stepSize'] = symbol_info.get('stepSize')
                        filters['quantity_precision'] = symbol_info.get('quantityPrecision')
                        filters['price_precision'] = symbol_info.get('pricePrecision')
                        
                        # 🔥 MIN_NOTIONAL 추출: get_symbol_info_direct는 이미 평탄화된 딕셔너리를 반환하므로 직접 접근
                        # get_symbol_info_direct는 'minNotional' (camelCase)로 반환함
                        min_notional = symbol_info.get('minNotional') or symbol_info.get('min_notional')
                        
                        if min_notional is not None:
                            try:
                                min_notional = float(min_notional)
                                self.logger.info(f"[{symbol}] ✅ MIN_NOTIONAL API에서 직접 가져옴: {min_notional}")
                            except (ValueError, TypeError):
                                min_notional = None

                        # B) 선물 Leverage Bracket 폴백 (notionalFloor 사용)
                        if min_notional is None:
                            try:
                                # python-binance: client.futures_leverage_bracket(symbol=symbol) 형식
                                if hasattr(self.binance_client, 'client') and hasattr(self.binance_client.client, 'futures_leverage_bracket'):
                                    lb = self.binance_client.client.futures_leverage_bracket(symbol=symbol)
                                    # 반환 구조는 계정마다 다르지만 일반적으로 리스트/딕셔너리 조합
                                    # 첫 구간의 notionalFloor를 최소 노셔널로 사용
                                    # 안전한 brackets 추출 (list 또는 dict 모두 처리)
                                    if isinstance(lb, list):
                                        first = lb[0] if lb else {}
                                        brackets = first.get('brackets', []) if isinstance(first, dict) else []
                                    elif isinstance(lb, dict):
                                        brackets = lb.get('brackets', [])
                                    else:
                                        brackets = []
                                    if brackets:
                                        floor = brackets[0].get('notionalFloor')
                                        if floor is not None:
                                            min_notional = float(floor)
                                            self.logger.info(f"[{symbol}] 🔧 leverage_bracket 폴백 min_notional: {min_notional}")
                            except Exception as e:
                                self.logger.info(f"[{symbol}] ℹ️ leverage_bracket 폴백 실패: {e}")

                        # C) LOT_SIZE × 현재가 기반 추정 (거래 불가 최소치를 대충 추정)
                        if min_notional is None:
                            try:
                                cur_price = float(self.get_current_price(symbol) or 0.0)
                                lot_min_qty = None
                                for f in symbol_info.get('filters', []):
                                    if f.get('filterType') == 'LOT_SIZE':
                                        lot_min_qty = float(f.get('minQty') or 0.0)
                                        break
                                if cur_price > 0 and lot_min_qty and lot_min_qty > 0:
                                    # 약간 보수적으로 ×1.01 버퍼
                                    min_notional = cur_price * lot_min_qty * 1.01
                                    self.logger.info(f"[{symbol}] 🔧 LOT_SIZE×현재가 추정 min_notional={min_notional:.4f}")
                            except Exception as e:
                                self.logger.info(f"[{symbol}] ℹ️ LOT_SIZE×현재가 추정 실패: {e}")

                        # C) 마지막 폴백: Binance 선물 거래소의 실제 최소값 사용 (안전한 기본값)
                        if min_notional is None or min_notional <= 0:
                            # 🔥 Binance 선물 거래소는 대부분 20 USDT를 요구하므로 안전한 기본값 사용
                            min_notional = 20.0
                            self.logger.warning(f"[{symbol}] ⚠️ MIN_NOTIONAL API 조회 실패 - 안전한 기본값 사용: {min_notional} USDT (Binance 선물 표준)")

                        filters['minNotional'] = min_notional
                        filters['min_notional'] = min_notional  # 🔥 snake_case도 추가
                        
                        # 🔥 필터 오버라이드에 저장 (재탐색 방지)
                        self.update_symbol_filter_override(symbol, {'min_notional': min_notional})
                        
                        # 🔥 상세 로깅으로 정밀도 정보 확인
                        self.logger.info(f"[{symbol}] 🔍 정밀도 정보 조회 성공:")
                        self.logger.info(f"  - stepSize: {filters['stepSize']}")
                        self.logger.info(f"  - quantity_precision: {filters['quantity_precision']}")
                        self.logger.info(f"  - price_precision: {filters['price_precision']}")
                        self.logger.info(f"  - minQty: {filters['minQty']}")
                        self.logger.info(f"  - minNotional: {filters['minNotional']}")
                        
                        if not filters['stepSize']:
                            self.logger.warning(f"[{symbol}] ⚠️ stepSize를 가져올 수 없음 - 기본 정밀도 사용")
                else:
                    self.logger.warning(f"[{symbol}] ⚠️ get_symbol_info_direct에서 심볼 정보를 가져올 수 없음")
                    
                    # 🔥 Fallback: 기존 get_symbol_filters 메서드 시도
                    if hasattr(self.binance_client, "get_symbol_filters"):
                        try:
                            fallback_filters = self.binance_client.get_symbol_filters(symbol)
                            if fallback_filters and fallback_filters.get('stepSize'):
                                filters['minQty'] = fallback_filters.get('minQty')
                                filters['stepSize'] = fallback_filters.get('stepSize')
                                self.logger.info(f"[{symbol}] 🔧 Fallback 방식으로 필터 정보 획득: {filters}")
                            else:
                                self.logger.warning(f"[{symbol}] ⚠️ Fallback 방식도 실패")
                                
                                # 🔥 3단계 폴백: wrapper 메서드 우선 사용 (일관성 유지)
                                try:
                                    self._dbg(symbol, "🔥 3단계 폴백 시작")
                                    
                                    # 🔥 wrapper 메서드 우선 시도 (일관성 유지)
                                    if hasattr(self.binance_client, 'get_exchange_info'):
                                        try:
                                            exchange_info = self.binance_client.get_exchange_info()
                                            symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
                                            self._dbg(symbol, "✅ 3단계 폴백 (wrapper) 성공")
                                        except Exception as wrapper_e:
                                            self._dbg(symbol, f"⚠️ wrapper 메서드 실패: {wrapper_e}")
                                            # 🔥 최후 수단: 직접 client 호출
                                            exchange_info = self.binance_client.client.futures_exchange_info()
                                            symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
                                            self._dbg(symbol, "✅ 3단계 폴백 (직접 호출) 성공")
                                    else:
                                        # 🔥 최후 수단: 직접 client 호출
                                        exchange_info = self.binance_client.client.futures_exchange_info()
                                        symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
                                        self._dbg(symbol, "✅ 3단계 폴백 (직접 호출) 성공")
                                    
                                    if symbol_info:
                                        # quantityPrecision과 pricePrecision만이라도 확보
                                        if 'quantityPrecision' in symbol_info:
                                            filters['quantity_precision'] = symbol_info['quantityPrecision']
                                            self._dbg(symbol, f"✅ 3단계 폴백 성공: quantity_precision={filters['quantity_precision']}")
                                        
                                        if 'pricePrecision' in symbol_info:
                                            filters['price_precision'] = symbol_info['pricePrecision']
                                            self._dbg(symbol, f"✅ 3단계 폴백 성공: price_precision={filters['price_precision']}")
                                        
                                        # LOT_SIZE 필터가 있다면 stepSize도 확보
                                        for filter_info in symbol_info.get('filters', []):
                                            if filter_info['filterType'] == 'LOT_SIZE':
                                                filters['stepSize'] = float(filter_info['stepSize'])
                                                filters['minQty'] = float(filter_info['minQty'])
                                                self._dbg(symbol, f"✅ 3단계 폴백 성공: stepSize={filters['stepSize']}")
                                                break
                                        
                                        # 🔥 MIN_NOTIONAL 필터도 3단계 폴백에서 시도 (강화판)
                                        min_notional = None
                                        
                                        # A) filters[]에서 여러 키 이름 대응
                                        for filter_info in symbol_info.get('filters', []):
                                            if filter_info['filterType'] == 'MIN_NOTIONAL':
                                                raw = filter_info.get('notional') if ('notional' in filter_info) else filter_info.get('minNotional')
                                                if raw is not None:
                                                    min_notional = float(raw)
                                                    self._dbg(symbol, f"✅ 3단계 폴백 MIN_NOTIONAL 성공: {min_notional}")
                                                    break
                                        
                                        # B) Leverage Bracket 폴백
                                        if min_notional is None:
                                            try:
                                                if hasattr(self.binance_client, 'client') and hasattr(self.binance_client.client, 'futures_leverage_bracket'):
                                                    lb = self.binance_client.client.futures_leverage_bracket(symbol=symbol)
                                                    if isinstance(lb, list):
                                                        first = lb[0] if lb else {}
                                                        brackets = first.get('brackets', []) if isinstance(first, dict) else []
                                                    elif isinstance(lb, dict):
                                                        brackets = lb.get('brackets', [])
                                                    else:
                                                        brackets = []
                                                    if brackets:
                                                        floor = brackets[0].get('notionalFloor')
                                                        if floor is not None:
                                                            min_notional = float(floor)
                                                            self._dbg(symbol, f"✅ 3단계 폴백 leverage_bracket 성공: {min_notional}")
                                            except Exception as e:
                                                self._dbg(symbol, f"ℹ️ 3단계 폴백 leverage_bracket 실패: {e}")
                                        
                                        # C) LOT_SIZE × 현재가 추정
                                        if min_notional is None:
                                            try:
                                                cur_price = float(self.get_current_price(symbol) or 0.0)
                                                lot_min_qty = None
                                                for filter_info in symbol_info.get('filters', []):
                                                    if filter_info['filterType'] == 'LOT_SIZE':
                                                        lot_min_qty = float(filter_info.get('minQty') or 0.0)
                                                        break
                                                if cur_price > 0 and lot_min_qty and lot_min_qty > 0:
                                                    min_notional = cur_price * lot_min_qty * 1.01
                                                    self._dbg(symbol, f"✅ 3단계 폴백 LOT_SIZE×현재가 추정: {min_notional:.4f}")
                                            except Exception as e:
                                                self._dbg(symbol, f"ℹ️ 3단계 폴백 LOT_SIZE×현재가 추정 실패: {e}")
                                        
                                        # D) 마지막 폴백: settings (None 또는 0.0인 경우)
                                        if min_notional is None or min_notional <= 0:
                                            min_notional = float(self.settings.get('min_trade_amount', 5.0))
                                            self._dbg(symbol, f"✅ 3단계 폴백 settings 폴백: {min_notional}")
                                        
                                        if min_notional is not None and min_notional > 0:
                                            filters['minNotional'] = min_notional
                                            filters['min_notional'] = min_notional  # 🔥 snake_case도 추가
                                            # 필터 오버라이드에 저장
                                            self.update_symbol_filter_override(symbol, {'min_notional': min_notional})
                                    else:
                                        self._dbg(symbol, "❌ 3단계 폴백 실패: 심볼 정보 없음")
                                except Exception as e:
                                    self._dbg(symbol, f"❌ 3단계 폴백 오류: {e}")
                                    self.logger.warning(f"[{symbol}] ❌ 3단계 폴백 오류: {e}")
                        except Exception as e:
                            self.logger.warning(f"[{symbol}] ⚠️ Fallback 방식 오류: {e}")
                    else:
                        self.logger.warning(f"[{symbol}] ⚠️ Fallback 메서드도 없음")
            else:
                self.logger.warning(f"[{symbol}] ⚠️ binance_client 또는 get_symbol_info_direct 메서드 없음")
        except Exception as e:
            self.logger.warning(f"[{symbol}] ❌ 정밀도 정보 조회 실패: {e}")
        
        # 🔥 🔥 🔥 오버라이드 적용: 학습된 값, 설정 오버라이드, 파일 오버라이드 순서로 적용
        # --- at the top of override section ---
        runtime_override = None          # <- 항상 정의
        settings_overrides = {}          # <- 항상 정의
        
        final_min_notional = min_notional
        self.logger.info(f"[{symbol}] 🔍 final_min_notional 초기값: {final_min_notional} (타입: {type(final_min_notional)})")
        
        # 1. 런타임 캐시 오버라이드 (Trader에서 학습한 값)
        if hasattr(self, 'symbol_filter_overrides') and symbol in self.symbol_filter_overrides:
            runtime_override = self.symbol_filter_overrides[symbol].get('min_notional')
            if runtime_override:
                final_min_notional = float(runtime_override)
                self.logger.info(f"[{symbol}] ✅ using learned min_notional override: {final_min_notional} (source=runtime_cache)")
        
        # 2. 설정 파일 오버라이드
        if not runtime_override:  # 런타임 오버라이드가 없을 때만
            settings_overrides = self.settings.get('symbol_min_notional_overrides', {})
            if symbol in settings_overrides:
                final_min_notional = float(settings_overrides[symbol])
                self.logger.info(f"[{symbol}] ✅ using settings min_notional override: {final_min_notional} (source=settings)")
        
        # 3. 파일 오버라이드 (exchange_overrides.json)
        if not runtime_override and not settings_overrides.get(symbol):  # 위 둘 다 없을 때만
            try:
                import os, json
                from path_utils import get_exchange_overrides_path
                override_path = get_exchange_overrides_path()
                if os.path.exists(override_path):
                    with open(override_path, "r", encoding="utf-8") as f:
                        file_overrides = json.load(f)
                    
                    if symbol in file_overrides:
                        file_override = file_overrides[symbol].get('min_notional')
                        if file_override:
                            final_min_notional = float(file_override)
                            self.logger.info(f"[{symbol}] ✅ using file min_notional override: {final_min_notional} (source=exchange_overrides.json)")
            except Exception as e:
                self.logger.warning(f"[{symbol}] 파일 오버라이드 읽기 실패: {e}")
        
        # 🔥 min_notional 폴백 보장 (절대 None 또는 0 안 나가게)
        if final_min_notional is None or final_min_notional <= 0:
            final_min_notional = float(self.settings.get('min_trade_amount', 5.0))
            self.logger.info(f"[{symbol}] 🔧 min_notional 폴백 적용: {final_min_notional} (원인: {final_min_notional})")
        
        # 🔥 filters에 min_notional 강제 설정 (모든 경우에)
        filters['minNotional'] = final_min_notional
        filters['min_notional'] = final_min_notional  # 🔥 snake_case도 추가
        self.logger.info(f"[{symbol}] 🔍 filters에 설정된 min_notional: {final_min_notional}")
        
        # 🔥 최종 검증: 필수 키가 모두 None이면 현실적인 기본값 설정
        if not filters['stepSize'] and not filters['quantity_precision']:
            self.logger.warning(f"[{symbol}] ⚠️ 모든 폴백 실패 - 현실적인 기본값 사용")
            # 개별 할당 (dict 값 타입 None -> float/int 허용하도록)
            filters['stepSize'] = 0.01
            filters['quantity_precision'] = 2
            filters['price_precision'] = 2
            filters['minQty'] = 0.01
        
        # 🔥 snake_case로 정규화하여 반환 (Trader 호환성)
        normalized_filters = {
            'step_size': filters.get('stepSize'),
            'min_qty': filters.get('minQty'),
            'quantity_precision': filters.get('quantity_precision') or filters.get('quantityPrecision') or 2,  # 🔥 None 처리 추가
            'price_precision': filters.get('price_precision') or filters.get('pricePrecision') or 2,          # 🔥 None 처리 추가
            'min_notional': float(final_min_notional)  # 🔥 최종 오버라이드된 min_notional 사용
        }
        self.logger.info(f"[{symbol}] 🔍 normalized_filters의 min_notional: {normalized_filters['min_notional']}")
        
        return normalized_filters

    def _build_trade_config(self, symbol: str, signal: str, confidence: float,
                            base_price: Optional[float] = None,
                            tp_ratio: Optional[float] = None,
                            sl_ratio: Optional[float] = None,
                            position_size_factor: float = 1.0,
                            leverage_factor: float = 1.0) -> Dict:
        """
        Trader가 바로 실행할 수 있는 파라미터 생성:
        side, qty, price, leverage, tp, sl, orderType, mode
        """
        # 기본값
        default_leverage = int(self.settings.get('default_leverage', 1))  # ✅ 설정 파일과 일치
        from config.settings import normalize_trade_rate
        default_tp, _ = normalize_trade_rate(self.settings.get('default_tp', 0.0018), kind="tp")
        default_sl, _ = normalize_trade_rate(self.settings.get('default_sl', 0.0020), kind="sl")
        min_trade_amount = float(self.settings.get('min_trade_amount', 5.0))  # 🔥 설정 파일에서 가져오고, 없으면 5.0 (최소값)
        if min_trade_amount < 5.0:
            self.logger.warning(f"⚠️ min_trade_amount가 너무 작음: {min_trade_amount}, 5.0으로 조정")
            min_trade_amount = 5.0

        side = "BUY" if signal.upper() == "LONG" else "SELL"

        price = float(base_price or self.get_current_price(symbol) or 0.0)
        if price <= 0:
            # 가격을 못구하면 실행 파라미터 생성 불가
            self.logger.warning(f"[{symbol}] 현재가 조회 실패 - 거래 파라미터 생성 불가 (base_price: {base_price}, current_price: {self.get_current_price(symbol)})")
            return {}

        # 레버리지
        leverage = max(1, int(default_leverage * leverage_factor))

        # 🔥 AI가 판단할 수 있도록 컨텍스트 정보 수집
        ai_context = {
            'position_size_factor': position_size_factor,
            'min_trade_amount': min_trade_amount,
            'current_price': price,
            'confidence': confidence,
            'signal': signal
        }
        
        # 🔥 사용자 잔고 정보 수집 (AI 판단용)
        try:
            if hasattr(self, 'binance_client') and self.binance_client:
                account_info = self.binance_client.get_account_info()
                if account_info:
                    available_balance = float(account_info.get('available_balance', 0))
                    ai_context['available_balance'] = available_balance
                    self.logger.info(f"[{symbol}] AI 컨텍스트 준비: 잔고 {available_balance:.2f} USDT, position_size_factor {position_size_factor:.2f}")
        except Exception as e:
            self.logger.warning(f"[{symbol}] 잔고 정보 수집 실패: {e}")
            ai_context['available_balance'] = 0
        
        # 🔥 스마트 AI 호출 + 캐싱 시스템
        if hasattr(self, 'ai_manager') and self.ai_manager:
            # AI 호출이 필요한지 판단
            if self._should_call_ai(symbol, confidence, ai_context):
                try:
                    self._mark_ai_attempt(symbol)
                    # 🔥 settings 정보를 AI 컨텍스트에 추가
                    ai_context['settings'] = self.settings
                    ai_decision = self.ai_manager.optimize_position_size(ai_context)
                    
                    if ai_decision and 'adjusted_position_size_factor' in ai_decision:
                        ai_position_factor = ai_decision['adjusted_position_size_factor']
                        
                        # 🔥 AI 제안값 검증 및 보정
                        min_trade_amount = self.settings.get('min_trade_amount', 5)
                        price = ai_context.get('current_price', 0)
                        
                        if price > 0:
                            # AI가 제안한 거래 금액 계산
                            ai_qty = (min_trade_amount / price) * ai_position_factor
                            ai_trade_amount = ai_qty * price
                            
                            # 최소 거래 금액 미달 시 보정
                            if ai_trade_amount < min_trade_amount:
                                required_factor = min_trade_amount / (min_trade_amount / price * price)
                                ai_position_factor = max(required_factor, ai_position_factor)
                                self.logger.warning(f"[{symbol}] AI 제안값 보정: {ai_trade_amount:.2f} USDT < {min_trade_amount} USDT → factor {ai_position_factor:.2f}로 조정")
                            
                            position_size_factor = ai_position_factor
                            log_event('analysis', f"[{symbol}] AI 결정: position_size_factor {ai_context['position_size_factor']:.2f} → {position_size_factor:.2f}", exchange='binance')
                            log_event('analysis', f"[{symbol}] AI 리스크 관리: {ai_decision.get('risk_reasoning', 'N/A')}", exchange='binance')
                            log_event('analysis', f"[{symbol}] 최종 거래 금액: {ai_trade_amount:.2f} USDT (최소: {min_trade_amount} USDT)", exchange='binance')
                            
                            # 🔥 AI 결과를 캐시에 저장
                            self._cache_ai_decision(symbol, ai_decision, ai_context)
                        else:
                            self.logger.warning(f"[{symbol}] 가격 정보 없음 - 기본값 사용")
                            position_size_factor = ai_context['position_size_factor']
                    else:
                        self.logger.warning(f"[{symbol}] AI 응답 형식 오류 - 기본값 사용")
                        position_size_factor = ai_context['position_size_factor']
                        
                except Exception as e:
                    self.logger.warning(f"[{symbol}] AI 최적화 실패: {e} - 기본값 사용")
                    position_size_factor = ai_context['position_size_factor']
            else:
                # 🔥 캐시된 AI 결과 사용
                cached_decision = self._get_cached_ai_decision(symbol)
                if cached_decision:
                    position_size_factor = cached_decision.get('position_size_factor', position_size_factor)
                    self.logger.info(f"[{symbol}] 🚀 캐시된 AI 결과 사용: position_size_factor {position_size_factor:.2f}")
                else:
                    self.logger.info(f"[{symbol}] AI 매니저 없음 - 기본 position_size_factor 사용: {position_size_factor:.2f}")
        else:
            self.logger.info(f"[{symbol}] AI 매니저 없음 - 기본 position_size_factor 사용: {position_size_factor:.2f}")
        
        # 🔥 수량 계산: autotrade.py 방식으로 정밀도 처리
        qty = (min_trade_amount / price) * position_size_factor
        
        # 🔥 수량 계산 로그 추가 (디버깅용) - log_event 사용
        log_event('analysis', f"[{symbol}] 🔍 수량 계산: min_trade_amount={min_trade_amount}, price={price}, position_size_factor={position_size_factor}, 초기수량={qty}", exchange='binance')

        # 🔥 거래소 필터 반영 (autotrade.py 방식) - 정규화된 필터 사용
        filters = self._resolve_exchange_filters(symbol)
        
        # 🔥 필터 정보 로그 추가 (디버깅용) - log_event 사용
        log_event('analysis', f"[{symbol}] 🔍 거래소 필터: step_size={filters.get('step_size')}, quantity_precision={filters.get('quantity_precision')}, min_notional={filters.get('min_notional')}", exchange='binance')
        
        if filters['step_size'] and filters['quantity_precision']:
            # 🔥 step_size 기반으로 정확한 수량 계산 (올림 방향으로 수정)
            step_size = filters['step_size']
            quantity_precision = filters['quantity_precision']
            
            # 🔥 올림 방향으로 step_size의 배수로 수량 조정 (내림이 아닌 올림)
            qty = math.ceil(qty / step_size) * step_size
            
            # 정밀도에 맞게 포맷팅
            qty = float(format(qty, f'.{quantity_precision}f'))
            
            log_event('analysis', f"[{symbol}] 🔧 step_size 기반 수량 조정 (올림): step_size={step_size}, precision={quantity_precision}, 최종수량={qty}", exchange='binance')
            
            # 🔥 최소 노셔널 보장 (올림 방향)
            min_notional = filters.get('min_notional') or filters.get('minNotional')
            
            # 🔥 min_notional 이중 안전장치 (절대 None 안 나가게)
            if min_notional is None or min_notional <= 0:
                # 🔥 Binance 선물 거래소는 대부분 20 USDT를 요구하므로 안전한 기본값 사용
                min_notional = 20.0
                self.logger.warning(f"[{symbol}] ⚠️ MIN_NOTIONAL 필터 없음 - 안전한 기본값 사용: {min_notional} USDT")
            try:
                min_notional = float(min_notional)
            except Exception:
                min_notional = 20.0
            
            ref_price = price * 1.005 if side == 'BUY' else price * 0.995  # 🔥 Trader와 동일한 0.5% 버퍼
            
            # 🔥 ref_price가 0/None일 때 대비
            if not ref_price or ref_price <= 0:
                try:
                    if self.binance_client and hasattr(self.binance_client, 'get_current_price'):
                        ref_price = float(self.binance_client.get_current_price(symbol) or 0.0)
                except Exception:
                    ref_price = 0.0
            
            if ref_price > 0 and qty * ref_price < min_notional:
                # 올림 방향으로 최소 노셔널 충족
                required_steps = math.ceil((min_notional / ref_price) / step_size)
                qty = required_steps * step_size
                qty = float(format(qty, f'.{quantity_precision}f'))
                log_event('analysis', f"[{symbol}] 🔧 최소 노셔널 보장 (올림): {qty} (amount: {qty * ref_price:.2f} USDT)", exchange='binance')
            
            # 🔥 최종 검증: 수량이 여전히 0이면 거래 불가
            if qty <= 0:
                log_event('trade', f"[{symbol}] ❌ 최종 수량이 0 - 거래 파라미터 생성 불가", exchange='binance', level='WARNING')
                return {}
            
        elif filters['min_qty']:
            # 기존 방식 (fallback) - 올림 방향으로 수정
            qty = max(qty, filters['min_qty'])
            if filters['step_size']:
                # 🔥 올림 방향으로 step_size 조정
                qty = math.ceil(qty / filters['step_size']) * filters['step_size']
            
            # 🔥 거래량 정밀도 강제 조정 (Binance 정밀도 오류 방지)
            if qty > 0:
                # 소수점 자릿수를 적절하게 조정 (너무 정밀하지 않게)
                if qty < 1:
                    qty = round(qty, 6)  # 0.123456
                elif qty < 10:
                    qty = round(qty, 4)  # 1.2345
                elif qty < 100:
                    qty = round(qty, 3)  # 12.345
                else:
                    qty = round(qty, 2)  # 123.45
                
                self.logger.info(f"[{symbol}] 🔧 기존 방식 정밀도 조정 (올림): {qty}")
                
                # 🔥 최소 노셔널 보장 (올림 방향)
                min_notional = filters.get('min_notional', 5.0)
                
                # 🔥 min_notional 이중 안전장치 (절대 None 안 나가게)
                if min_notional is None:
                    min_notional = filters.get('minNotional')  # camelCase도 허용
                if min_notional is None:
                    min_notional = self.settings.get('min_trade_amount', 5.0)
                try:
                    min_notional = float(min_notional)
                except Exception:
                    min_notional = 5.0
                
                ref_price = price * 1.005 if side == 'BUY' else price * 0.995  # 🔥 Trader와 동일한 0.5% 버퍼
                
                # 🔥 ref_price가 0/None일 때 대비
                if not ref_price or ref_price <= 0:
                    try:
                        if self.binance_client and hasattr(self.binance_client, 'get_current_price'):
                            ref_price = float(self.binance_client.get_current_price(symbol) or 0.0)
                    except Exception:
                        ref_price = 0.0
                
                if ref_price > 0 and qty * ref_price < min_notional:
                    required_steps = math.ceil((min_notional / ref_price) / (filters.get('step_size', 0.01)))
                    qty = required_steps * (filters.get('step_size', 0.01))
                    self.logger.info(f"[{symbol}] 🔧 기존 방식 최소 노셔널 보장 (올림): {qty}")
                    
                    # 🔥 추가 검증: 최종 거래 금액이 최소 요구사항을 충족하는지 확인
                    final_amount = qty * ref_price
                    if final_amount < min_notional:
                        # 추가 버퍼 적용 (1% 여유)
                        buffer_amount = min_notional * 1.01
                        required_steps = math.ceil((buffer_amount / ref_price) / (filters.get('step_size', 0.01)))
                        qty = required_steps * (filters.get('step_size', 0.01))
                        self.logger.info(f"[{symbol}] 🔧 기존 방식 버퍼 적용 최소 노셔널 보장: {qty} (amount: {qty * ref_price:.2f} USDT)")
        else:
            # 🔥 필터 정보가 없을 때의 안전장치
            log_event('analysis', f"[{symbol}] ⚠️ 정밀도 정보 없음 - 기본 수량 사용: {qty}", exchange='binance', level='WARNING')
            
            # 🔥 최소 노셔널 보장
            min_notional = self.settings.get('min_trade_amount', 5.0)
            if qty * price < min_notional:
                qty = min_notional / price
                log_event('analysis', f"[{symbol}] 🔧 기본 min_notional 보장으로 수량 조정: {qty}", exchange='binance')
            
            # 🔥 최종 검증: 수량이 여전히 0이면 거래 불가
            if qty <= 0:
                log_event('trade', f"[{symbol}] ❌ 최종 수량이 0 - 거래 파라미터 생성 불가", exchange='binance', level='WARNING')
                return {}

        # TP/SL 비율 (fraction) 확정
        tp_frac, tp_changed = normalize_trade_rate(
            default_tp if tp_ratio is None else tp_ratio, kind="tp", fallback=default_tp
        )
        sl_frac, sl_changed = normalize_trade_rate(
            default_sl if sl_ratio is None else sl_ratio, kind="sl", fallback=default_sl
        )
        if tp_changed or sl_changed:
            self.logger.warning(
                f"[{symbol}] 비정상 TP/SL 실행값 차단·정규화: tp={tp_ratio}, sl={sl_ratio} "
                f"→ tp={tp_frac}, sl={sl_frac}"
            )

        # 신뢰도 기반의 경미한 조정(선택)
        if confidence < 0.6:
            qty *= 0.8
        elif confidence > 0.8:
            qty *= 1.2

        # 최소 수량 안정화
        if qty <= 0:
            log_event('trade', f"[{symbol}] ❌ 신뢰도 조정 후 수량이 0 - 거래 파라미터 생성 불가", exchange='binance', level='WARNING')
            return {}

        # 🔥 필터 정보를 trade_config에 포함 (Trader가 재조회 방지)
        trade_cfg = {
            'symbol': symbol,
            'side': side,
            'qty': float(qty),
            'price': price,        # should_execute_trade 에서 금액검증에 사용
            'leverage': leverage,
            'tp': tp_frac,         # Trader는 fraction을 기대
            'sl': sl_frac,         # Trader는 fraction을 기대
            'orderType': 'MARKET',
            'mode': 'optimized',
            'filters': {            # 🔥 필터 정보 포함 (snake_case로 통일)
                'step_size': float(filters.get('step_size', 0.01)),
                'min_qty': float(filters.get('min_qty', 0.01)),
                'quantity_precision': int(filters.get('quantity_precision', 2)),
                'price_precision': int(filters.get('price_precision', 2)),
                'min_notional': float(filters.get('min_notional', 5.0))
            }
        }
        
        # 🔥 최종 거래 파라미터 로그 (디버깅용) - log_event 사용
        log_event('trade', f"[{symbol}] ✅ 최종 거래 파라미터 확정 (단일 권위):", exchange='binance')
        log_event('trade', f"[{symbol}]   - 수량: {qty}", exchange='binance')
        log_event('trade', f"[{symbol}]   - 가격: {price}", exchange='binance')
        log_event('trade', f"[{symbol}]   - 거래금액: {qty * price:.2f} USDT", exchange='binance')
        log_event('trade', f"[{symbol}]   - 레버리지: {leverage}x", exchange='binance')
        log_event('trade', f"[{symbol}]   - TP: {tp_frac:.4f} ({tp_frac*100:.2f}%)", exchange='binance')
        log_event('trade', f"[{symbol}]   - SL: {sl_frac:.4f} ({sl_frac*100:.2f}%)", exchange='binance')
        
        return trade_cfg
            
    def adjust_by_confidence(self, params: Dict, confidence: float) -> Dict:
        """신뢰도 기반 파라미터 조정"""
        try:
            adjusted_params = params.copy()
            
            # 신뢰도가 높을수록 더 공격적인 설정
            if confidence > 0.8:
                # TP 비율 증가
                if 'tp_price' in adjusted_params:
                    adjusted_params['tp_price'] *= 1.1
                    
                # 포지션 크기 증가
                if 'quantity' in adjusted_params:
                    adjusted_params['quantity'] *= 1.2
                    
            elif confidence < 0.6:
                # 신뢰도가 낮으면 보수적인 설정
                if 'tp_price' in adjusted_params:
                    adjusted_params['tp_price'] *= 0.9
                    
                if 'quantity' in adjusted_params:
                    adjusted_params['quantity'] *= 0.8
                    
            return adjusted_params
            
        except Exception as e:
            self.logger.error(f"신뢰도 기반 조정 중 오류: {e}")
            return params
            
    def apply_risk_management(self, params: Dict, symbol: str) -> Dict:
        """리스크 관리 적용"""
        try:
            risk_adjusted_params = params.copy()
            
            # 최근 손실 패턴 분석
            loss_patterns = self.analyze_loss_patterns(symbol)
            
            if loss_patterns:
                # 손실 빈도가 높으면 보수적으로 조정
                if loss_patterns['frequency'] > 3:
                    risk_factor = self.settings['risk_adjustment_factor']
                    
                    if 'quantity' in risk_adjusted_params:
                        risk_adjusted_params['quantity'] *= risk_factor
                        
                    if 'leverage' in risk_adjusted_params:
                        risk_adjusted_params['leverage'] = max(1, int(risk_adjusted_params['leverage'] * risk_factor))
                        
            return risk_adjusted_params
            
        except Exception as e:
            self.logger.error(f"리스크 관리 적용 중 오류: {e}")
            return params
            
    def optimize_parameters(self, candidates_or_symbol, signal_data=None) -> Dict:
        """
        오버로드된 메서드:
        1. optimize_parameters(candidates: List[Dict]) -> Dict
        2. optimize_parameters(symbol: str, signal_data: Dict) -> Dict
        """
        # 첫 번째 인자가 리스트인지 확인
        if isinstance(candidates_or_symbol, list):
            # 기존 방식: candidates 리스트
            return self._optimize_parameters_from_candidates(candidates_or_symbol)
        else:
            # 새로운 방식: symbol + signal_data
            symbol = candidates_or_symbol
            if signal_data is None:
                return {}
            candidates = [{'symbol': symbol, 'signal': signal_data.get('signal', 'HOLD'), 
                          'confidence': signal_data.get('confidence', 0.5), 
                          'price': signal_data.get('entry_price', 0)}]
            return self._optimize_parameters_from_candidates(candidates)
    
    def _optimize_parameters_from_candidates(self, candidates: List[Dict]) -> Dict:
        """
        각 candidate = {symbol, signal, side(옵션), confidence, price(옵션), ...}
        반환: {symbol: {side, qty, price, leverage, tp, sl, orderType, mode, ...}}
        """
        results = {}
        try:
            self.logger.info(f"최적화 시작: {len(candidates)}개 후보")
            for c in candidates:
                symbol = c.get('symbol') or ''
                if not symbol:
                    self.logger.warning("빈 symbol 후보 건너뜀")
                    continue
                signal = c.get('signal') or ('LONG' if (c.get('side') == 'BUY') else 'SHORT')
                confidence = float(c.get('confidence', 0.5))
                base_price = c.get('price')

                # 과거데이터 기반 심볼 최적화(없으면 기본값)
                per_symbol_opt = self.optimize_symbol_parameters(symbol) or {
                    'tp_ratio': self.settings.get('default_tp', 0.0018),
                    'sl_ratio': self.settings.get('default_sl', 0.0020),
                    'position_size_factor': 1.0,
                    'leverage_factor': 1.0,
                }

                trade_cfg = self._build_trade_config(
                    symbol=symbol,
                    signal=signal,
                    confidence=confidence,
                    base_price=base_price,
                    tp_ratio=per_symbol_opt.get('tp_ratio'),
                    sl_ratio=per_symbol_opt.get('sl_ratio'),
                    position_size_factor=per_symbol_opt.get('position_size_factor', 1.0),
                    leverage_factor=per_symbol_opt.get('leverage_factor', 1.0),
                )

                if not trade_cfg:
                    self.logger.warning(f"[{symbol}] 실행 파라미터 생성 실패(가격/수량)")
                    continue

                results[symbol] = trade_cfg
                self.logger.info(f"[{symbol}] 최종 실행 파라미터: {trade_cfg}")

            self.logger.info(f"최적화 완료: {len(results)}개 결과")
            return results
            
        except Exception as e:
            self.logger.error(f"파라미터 최적화 중 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            return {}
            
    def optimize_symbol_parameters(self, symbol: str) -> Optional[Dict]:
        """개별 심볼 파라미터 최적화"""
        try:
            # 최근 거래 데이터 가져오기
            trade_data = self.get_recent_trades(symbol)
            
            # ✅ 안전한 기본값 + opt_cfg 우선
            min_needed = (
                self.settings.get('min_trades_for_analysis') or
                self.opt_cfg.get('min_trades_for_analysis', 10)
            )
            if len(trade_data) < min_needed:
                self.logger.info(f"{symbol} 최적화 데이터 부족: {len(trade_data)} < {min_needed} (기본값 사용)")
                return {
                    'tp_ratio': self.settings.get('default_tp', 0.0018),
                    'sl_ratio': self.settings.get('default_sl', 0.0020),
                    'position_size_factor': 1.0,
                    'leverage_factor': 1.0,
                    'entry_conditions': {},
                    'confidence': 0.5,
                    'improvement_score': 0.0,
                    'timestamp': datetime.now(),
                    'is_default': True
                }
                
            # TP/SL 최적화
            tp_optimization = self.optimize_tp_sl(trade_data)
            
            # 포지션 크기 최적화
            position_size_optimization = self.optimize_position_size(trade_data)
            
            # 진입 타이밍 최적화
            entry_timing_optimization = self.optimize_entry_timing(trade_data)
            
            # 최적화 결과 조합
            optimization_result = {
                            'tp_ratio': tp_optimization.get('optimal_tp_ratio', 0.0018),  # 0.18%
            'sl_ratio': tp_optimization.get('optimal_sl_ratio', 0.002),   # 0.20%
                'position_size_factor': position_size_optimization.get('optimal_size_factor', 1.0),
                'leverage_factor': position_size_optimization.get('optimal_leverage_factor', 1.0),
                'entry_conditions': entry_timing_optimization.get('optimal_conditions', {}),
                'confidence': self.calculate_optimization_confidence(trade_data),
                'improvement_score': self.calculate_improvement_score(trade_data),
                'timestamp': datetime.now()
            }
            
            # 최적화 결과 저장
            self.save_symbol_optimization(symbol, optimization_result)
            
            return optimization_result
            
        except Exception as e:
            self.logger.error(f"{symbol} 파라미터 최적화 중 오류: {e}")
            return None
            
    def optimize_tp_sl(self, trade_data: List[Dict]) -> Dict:
        """TP/SL 최적화"""
        try:
            profitable_trades = [trade for trade in trade_data if trade['pnl'] > 0]
            losing_trades = [trade for trade in trade_data if trade['pnl'] < 0]
            
            if not profitable_trades:
                from config.settings import normalize_trade_rate
                default_tp, _ = normalize_trade_rate(
                    getattr(self, 'settings', {}).get('default_tp', 0.0018), kind="tp"
                )
                default_sl, _ = normalize_trade_rate(
                    getattr(self, 'settings', {}).get('default_sl', 0.002), kind="sl"
                )
                return {'optimal_tp_ratio': default_tp, 'optimal_sl_ratio': default_sl}
                
            # 수익 거래의 평균 수익률 분석
            # DB pnl_percent는 0.63 == 0.63%인 퍼센트 포인트다.
            avg_profit_pct = np.mean([trade['pnl_percent'] for trade in profitable_trades])
            max_profit_pct = np.max([trade['pnl_percent'] for trade in profitable_trades])
            
            # 손실 거래의 평균 손실률 분석
            avg_loss_pct = np.mean([abs(trade['pnl_percent']) for trade in losing_trades]) if losing_trades else 0.2
            
            # 최적 TP/SL 비율 계산
            optimal_tp_ratio = max(0.0005, min(min(max_profit_pct * 0.8, avg_profit_pct * 1.2) / 100.0, 0.05))
            optimal_sl_ratio = max(0.0005, min((avg_loss_pct * 1.1) / 100.0, 0.03))
            
            return {
                'optimal_tp_ratio': optimal_tp_ratio,
                'optimal_sl_ratio': optimal_sl_ratio,
                'avg_profit': avg_profit_pct,
                'avg_loss': avg_loss_pct
            }
            
        except Exception as e:
            self.logger.error(f"TP/SL 최적화 중 오류: {e}")
            from config.settings import normalize_trade_rate
            default_tp, _ = normalize_trade_rate(
                getattr(self, 'settings', {}).get('default_tp', 0.0018), kind="tp"
            )
            default_sl, _ = normalize_trade_rate(
                getattr(self, 'settings', {}).get('default_sl', 0.002), kind="sl"
            )
            return {'optimal_tp_ratio': default_tp, 'optimal_sl_ratio': default_sl}
            
    def optimize_position_size(self, trade_data: List[Dict]) -> Dict:
        """포지션 크기 최적화"""
        try:
            # 수익률과 포지션 크기의 관계 분석
            size_profit_correlation = []
            
            for trade in trade_data:
                size_profit_correlation.append({
                    'size': trade['quantity'],
                    'profit': trade['pnl_percent']
                })
                
            # 최적 포지션 크기 계산
            profitable_trades = [item for item in size_profit_correlation if item['profit'] > 0]
            
            if profitable_trades:
                optimal_size = np.mean([item['size'] for item in profitable_trades])
                size_factor = optimal_size / np.mean([item['size'] for item in size_profit_correlation])
                
                # 🔥 size_factor 로깅 (잔고 기반 조정으로 대체됨)
                self.logger.info(f"계산된 size_factor: {size_factor:.2f} (잔고 기반으로 최종 조정됨)")
            else:
                size_factor = 1.0
                
            # 레버리지 최적화
            leverage_analysis = self.analyze_leverage_performance(trade_data)
            optimal_leverage_factor = leverage_analysis.get('optimal_factor', 1.0)
            
            return {
                'optimal_size_factor': size_factor,
                'optimal_leverage_factor': optimal_leverage_factor
            }
            
        except Exception as e:
            self.logger.error(f"포지션 크기 최적화 중 오류: {e}")
            return {'optimal_size_factor': 1.0, 'optimal_leverage_factor': 1.0}
            
    def optimize_entry_timing(self, trade_data: List[Dict]) -> Dict:
        """진입 타이밍 최적화"""
        try:
            # 시간대별 수익률 분석
            hourly_performance = {}
            
            for trade in trade_data:
                hour = trade['entry_time'].hour
                if hour not in hourly_performance:
                    hourly_performance[hour] = []
                hourly_performance[hour].append(trade['pnl_percent'])
                
            # 최적 시간대 찾기
            best_hours = []
            for hour, profits in hourly_performance.items():
                avg_profit = np.mean(profits)
                if avg_profit > 0.1:  # 0.1% 이상 수익
                    best_hours.append(hour)
                    
            # 기술적 지표 조건 분석
            technical_conditions = self.analyze_technical_conditions(trade_data)
            
            return {
                'optimal_conditions': {
                    'best_hours': best_hours,
                    'technical_conditions': technical_conditions
                }
            }
            
        except Exception as e:
            self.logger.error(f"진입 타이밍 최적화 중 오류: {e}")
            return {'optimal_conditions': {}}
            
    def analyze_loss_patterns(self, symbol: str) -> Optional[Dict]:
        """손실 패턴 분석"""
        try:
            # 최근 손실 거래 데이터 가져오기
            query = """
                SELECT pnl_percent, entry_time, exit_time, reason 
                FROM trade_log 
                WHERE symbol = ? AND pnl_percent < 0 
                AND exit_time > datetime('now', '-7 days')
                ORDER BY exit_time DESC
            """
            
            loss_trades = self.recorder.execute_query(query, (symbol,))
            
            if not loss_trades:
                return None
                
            # 손실 원인 분석
            loss_reasons = {}
            for trade in loss_trades:
                reason = trade[3] or 'Unknown'
                if reason not in loss_reasons:
                    loss_reasons[reason] = []
                loss_reasons[reason].append(trade[0])
                
            # 가장 빈번한 손실 원인 찾기
            most_frequent_reason = max(loss_reasons.items(), key=lambda x: len(x[1]))
            
            return {
                'frequency': len(loss_trades),
                'avg_loss': np.mean([trade[0] for trade in loss_trades]),
                'max_loss': np.min([trade[0] for trade in loss_trades]),
                'most_frequent_reason': most_frequent_reason[0],
                'reason_frequency': len(most_frequent_reason[1])
            }
            
        except Exception as e:
            self.logger.error(f"손실 패턴 분석 중 오류: {e}")
            return None
            
    def analyze_leverage_performance(self, trade_data: List[Dict]) -> Dict:
        """레버리지 성과 분석"""
        try:
            leverage_performance = {}
            
            for trade in trade_data:
                leverage = trade.get('leverage', 1)
                if leverage not in leverage_performance:
                    leverage_performance[leverage] = []
                leverage_performance[leverage].append(trade['pnl_percent'])
                
            # 최적 레버리지 찾기 (상한 적용)
            best_leverage = 1
            best_avg_profit = 0
            max_leverage_factor = 5  # 레버리지 상한: 5배
            
            for leverage, profits in leverage_performance.items():
                avg_profit = np.mean(profits)
                if avg_profit > best_avg_profit:
                    best_avg_profit = avg_profit
                    best_leverage = min(leverage, max_leverage_factor)  # 상한 적용
                    
            return {
                'optimal_factor': best_leverage,
                'best_avg_profit': best_avg_profit,
                'max_leverage_factor': max_leverage_factor
            }
            
        except Exception as e:
            self.logger.error(f"레버리지 성과 분석 중 오류: {e}")
            return {'optimal_factor': 1.0}
            
    def analyze_technical_conditions(self, trade_data: List[Dict]) -> Dict:
        """기술적 지표 조건 분석"""
        try:
            # 수익 거래의 기술적 지표 패턴 분석
            profitable_trades = [trade for trade in trade_data if trade['pnl_percent'] > 0]
            
            if not profitable_trades:
                return {}
                
            # RSI 조건 분석
            rsi_conditions = [trade.get('rsi', 50) for trade in profitable_trades]
            optimal_rsi_range = {
                'min': np.percentile(rsi_conditions, 25),
                'max': np.percentile(rsi_conditions, 75)
            }
            
            # MACD 조건 분석
            macd_conditions = [trade.get('macd', 0) for trade in profitable_trades]
            optimal_macd_threshold = np.median(macd_conditions)
            
            return {
                'rsi_range': optimal_rsi_range,
                'macd_threshold': optimal_macd_threshold
            }
            
        except Exception as e:
            self.logger.error(f"기술적 조건 분석 중 오류: {e}")
            return {}
            
    def calculate_optimization_confidence(self, trade_data: List[Dict]) -> float:
        """최적화 신뢰도 계산"""
        try:
            if len(trade_data) < 10:
                return 0.5
                
            # 수익 거래 비율
            profitable_ratio = len([t for t in trade_data if t['pnl_percent'] > 0]) / len(trade_data)
            
            # 수익률 일관성
            profits = [t['pnl_percent'] for t in trade_data if t['pnl_percent'] > 0]
            if profits:
                profit_consistency = 1 - (np.std(profits) / np.mean(profits)) if np.mean(profits) > 0 else 0
            else:
                profit_consistency = 0
                
            # 데이터 품질
            data_quality = min(len(trade_data) / 50, 1.0)  # 50개 이상이면 최고 품질
            
            confidence = (profitable_ratio * 0.4 + profit_consistency * 0.4 + data_quality * 0.2)
            
            return float(min(confidence, 1.0))
            
        except Exception as e:
            self.logger.error(f"최적화 신뢰도 계산 중 오류: {e}")
            return 0.5
            
    def calculate_improvement_score(self, trade_data: List[Dict]) -> float:
        """개선 점수 계산"""
        try:
            if len(trade_data) < 10:
                return 0.0
                
            # 최근 거래와 이전 거래 비교
            recent_trades = trade_data[-10:]
            older_trades = trade_data[:-10] if len(trade_data) > 10 else trade_data
            
            recent_avg = np.mean([t['pnl_percent'] for t in recent_trades])
            older_avg = np.mean([t['pnl_percent'] for t in older_trades])
            
            if older_avg == 0:
                return 0.0
                
            improvement = (recent_avg - older_avg) / abs(older_avg)
            
            return float(max(improvement, 0.0))
            
        except Exception as e:
            self.logger.error(f"개선 점수 계산 중 오류: {e}")
            return 0.0
            
    def get_recent_trades(self, symbol: str) -> List[Dict]:
        """최근 거래 데이터 가져오기"""
        try:
            query = """
                SELECT symbol, entry_price, exit_price, quantity, leverage,
                       pnl, pnl_percent, entry_time, exit_time, reason
                FROM trade_log 
                WHERE symbol = ? 
                AND exit_time > datetime('now', '-7 days')
                ORDER BY exit_time DESC
            """
            
            trades = self.recorder.execute_query(query, (symbol,))
            
            trade_data = []
            for trade in trades:
                trade_data.append({
                    'symbol': trade[0],
                    'entry_price': trade[1],
                    'exit_price': trade[2],
                    'quantity': trade[3],
                    'leverage': trade[4],
                    'pnl': trade[5],
                    'pnl_percent': trade[6],
                    'entry_time': datetime.fromisoformat(trade[7]),
                    'exit_time': datetime.fromisoformat(trade[8]),
                    'reason': trade[9]
                })
                
            return trade_data
            
        except Exception as e:
            self.logger.error(f"최근 거래 데이터 가져오기 오류: {e}")
            return []
            
    def save_symbol_optimization(self, symbol: str, optimization_result: Dict):
        """심볼별 최적화 결과 저장"""
        try:
            query = """
                INSERT INTO ai_optimization (symbol, optimization_type, optimization_data, timestamp)
                VALUES (?, ?, ?, ?)
            """
            
            self.recorder.execute_query(query, (
                symbol,
                'PARAMETER_OPTIMIZATION',
                json.dumps(
                    optimization_result,
                    default=lambda value: (
                        value.isoformat()
                        if isinstance(value, datetime)
                        else str(value)
                    ),
                ),
                datetime.now()
            ))
            
            self.logger.info(f"{symbol} 최적화 결과 저장 완료")
            
        except Exception as e:
            self.logger.error(f"최적화 결과 저장 중 오류: {e}")
            
    def save_optimization_results(self, optimization_results: Dict):
        """전체 최적화 결과 저장"""
        try:
            for symbol, result in optimization_results.items():
                self.save_symbol_optimization(symbol, result)
                
            self.logger.info("전체 최적화 결과 저장 완료")
            
        except Exception as e:
            self.logger.error(f"전체 최적화 결과 저장 중 오류: {e}")
            
    def get_optimization_summary(self) -> Dict:
        """최적화 요약 정보"""
        try:
            summary = {
                'total_optimizations': len(self.optimization_history),
                'recent_optimizations': [],
                'performance_improvement': 0.0
            }
            
            # 최근 최적화 결과
            recent_optimizations = [opt for opt in self.optimization_history 
                                  if (datetime.now() - opt.timestamp).days < 7]
            
            summary['recent_optimizations'] = [
                {
                    'symbol': opt.symbol,
                    'type': opt.optimization_type.value,
                    'improvement': opt.improvement_score,
                    'confidence': opt.confidence
                }
                for opt in recent_optimizations
            ]
            
            # 전체 성과 개선도
            if self.optimization_history:
                summary['performance_improvement'] = np.mean([
                    opt.improvement_score for opt in self.optimization_history
                ])
                
            return summary
            
        except Exception as e:
            self.logger.error(f"최적화 요약 정보 가져오기 오류: {e}")
            return {}
    
    # 🔥 AI 캐싱 시스템 메서드들
    def _should_call_ai(self, symbol: str, confidence: float, context: Dict) -> bool:
        """포지션 크기 AI를 호출할지 판단한다.

        신선한 캐시는 신뢰도가 높거나 SHORT라는 이유만으로 우회하지 않는다.
        캐시 만료, 방향 변경, 의미 있는 가격/신뢰도 변화만 재호출 사유다.
        실패 직후에는 짧은 재시도 쿨다운을 두어 장애 시 호출 폭주를 막는다.
        """
        import time

        now = time.time()
        last_attempt = float(self.ai_last_attempt.get(symbol, 0.0) or 0.0)
        if last_attempt and now - last_attempt < self.ai_retry_cooldown_sec:
            return False

        if symbol not in self.ai_cache:
            return True

        cache_data = self.ai_cache[symbol]
        if now - float(cache_data.get('timestamp', 0.0) or 0.0) > self.cache_duration:
            return True

        current_signal = str(context.get('signal') or '').upper()
        cached_signal = str(cache_data.get('signal') or '').upper()
        if current_signal and cached_signal and current_signal != cached_signal:
            return True

        current_price = context.get('current_price', 0)
        cached_price = cache_data.get('price', 0)
        if current_price > 0 and cached_price > 0:
            price_change = abs(current_price - cached_price) / cached_price
            if price_change * 10000.0 >= self.ai_position_price_change_bps:
                return True

        cached_confidence = float(cache_data.get('confidence', confidence) or 0.0)
        confidence_change = abs(float(confidence or 0.0) - cached_confidence)
        if confidence_change + 1e-12 >= self.ai_position_confidence_delta:
            return True

        return False

    def _mark_ai_attempt(self, symbol: str) -> None:
        """성공 여부와 무관하게 호출 시각을 기록해 장애 시 재시도 폭주를 막는다."""
        import time
        self.ai_last_attempt[symbol] = time.time()
    
    def _cache_ai_decision(self, symbol: str, ai_decision: Dict, context: Dict):
        """AI 결정 결과를 캐시에 저장"""
        import time
        
        # 캐시 크기 제한
        if len(self.ai_cache) >= self.max_cache_size:
            # 가장 오래된 항목 제거
            oldest_symbol = min(self.ai_cache.keys(), 
                              key=lambda k: self.ai_cache[k]['timestamp'])
            del self.ai_cache[oldest_symbol]
        
        # AI 결정 결과 캐싱
        self.ai_cache[symbol] = {
            'position_size_factor': ai_decision.get('adjusted_position_size_factor', 1.0),
            'risk_level': ai_decision.get('risk_level', 'MODERATE'),
            'price': context.get('current_price', 0),
            'timestamp': time.time(),
            'confidence': context.get('confidence', 0.5),
            'signal': str(context.get('signal') or '').upper(),
            'last_trade_time': time.time()  # 🔥 거래 시간 기록 추가
        }
        
        self.logger.info(f"[{symbol}] 🚀 AI 결과 캐시 저장 완료")
    
    def _get_cached_ai_decision(self, symbol: str) -> Optional[Dict]:
        """캐시된 AI 결정 결과 가져오기"""
        import time
        if symbol in self.ai_cache:
            cache_data = self.ai_cache[symbol]
            if time.time() - float(cache_data.get('timestamp', 0.0) or 0.0) > self.cache_duration:
                return None
            return {
                'position_size_factor': cache_data['position_size_factor'],
                'risk_level': cache_data['risk_level'],
                'last_trade_time': cache_data.get('last_trade_time', 0)  # 🔥 거래 시간 포함
            }
        return None
    
    def clear_ai_cache(self):
        """AI 캐시 초기화"""
        self.ai_cache.clear()
        self.ai_last_attempt.clear()
        self.logger.info("🚀 AI 캐시 초기화 완료")
    
    def get_ai_cache_status(self) -> Dict:
        """AI 캐시 상태 정보"""
        return {
            'cache_size': len(self.ai_cache),
            'max_cache_size': self.max_cache_size,
            'cache_duration': self.cache_duration,
            'retry_cooldown_sec': self.ai_retry_cooldown_sec,
            'cached_symbols': list(self.ai_cache.keys())
        }
