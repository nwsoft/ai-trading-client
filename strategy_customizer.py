#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용자 맞춤형 전략 커스터마이저
다양한 전략 조합과 실시간 적용 시스템
"""

import json
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum

class StrategyType(Enum):
    """전략 타입"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    SCALPING = "scalping"
    SWING = "swing"
    CUSTOM = "custom"

class MarketCondition(Enum):
    """시장 조건"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    CALM = "calm"

@dataclass
class TimeBasedStrategy:
    """시간 기반 전략"""
    active_hours: List[tuple]  # [(start_hour, end_hour), ...]
    timezone: str
    weekend_trading: bool
    holiday_trading: bool
    time_specific_params: Dict[str, Dict]

@dataclass
class CoinFilterStrategy:
    """코인 필터 전략"""
    categories: List[str]  # ["defi", "metaverse", "ai", etc.]
    market_cap_min: float
    volume_min: float
    price_range: tuple  # (min_price, max_price)
    excluded_coins: List[str]
    preferred_coins: List[str]

@dataclass
class RiskAdaptiveStrategy:
    """리스크 적응형 전략"""
    base_risk_level: float  # 0.0 ~ 1.0
    emotion_factor: float   # 사용자 감정 상태 반영
    performance_adjustment: bool  # 성과에 따른 자동 조절
    max_consecutive_losses: int
    cooldown_after_loss: int  # 손실 후 대기시간(분)

class StrategyCustomizer:
    """전략 커스터마이저"""
    
    def __init__(self, analyzer, trader, evaluator, risk_manager):
        self.analyzer = analyzer
        self.trader = trader
        self.evaluator = evaluator
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(__name__)
        
        # 사용자 전략 저장소
        self.user_strategies: Dict[str, Dict] = {}
        self.active_strategy_id: Optional[str] = None
        
        # 전략 실행 이력
        self.strategy_performance: Dict[str, Dict] = {}
        
        # 동적 조절 함수들
        self.dynamic_adjusters: Dict[str, Callable] = {
            "market_condition": self._adjust_for_market_condition,
            "time_based": self._adjust_for_time,
            "performance_based": self._adjust_for_performance,
            "emotion_based": self._adjust_for_emotion
        }
        
        self.logger.info("Strategy Customizer 초기화 완료")
    
    def create_custom_strategy(self, strategy_config: Dict) -> str:
        """맞춤형 전략 생성"""
        try:
            strategy_id = f"custom_{int(datetime.now().timestamp())}"
            
            # 기본 전략 구조
            custom_strategy = {
                "id": strategy_id,
                "name": strategy_config.get("name", f"Custom Strategy {strategy_id[-6:]}"),
                "created_at": datetime.now().isoformat(),
                "base_params": strategy_config.get("base_params", {}),
                "filters": strategy_config.get("filters", {}),
                "time_rules": strategy_config.get("time_rules", {}),
                "risk_rules": strategy_config.get("risk_rules", {}),
                "dynamic_adjustments": strategy_config.get("dynamic_adjustments", []),
                "backtesting_results": None,
                "live_performance": {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "avg_profit": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0
                }
            }
            
            # 전략 검증
            validation_result = self._validate_strategy(custom_strategy)
            if not validation_result["valid"]:
                raise ValueError(f"전략 검증 실패: {validation_result['reason']}")
            
            # 전략 저장
            self.user_strategies[strategy_id] = custom_strategy
            
            self.logger.info(f"맞춤형 전략 생성 완료: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            self.logger.error(f"맞춤형 전략 생성 오류: {e}")
            raise
    
    def apply_strategy(self, strategy_id: str) -> bool:
        """전략 적용"""
        try:
            if strategy_id not in self.user_strategies:
                raise ValueError(f"전략을 찾을 수 없습니다: {strategy_id}")
            
            strategy = self.user_strategies[strategy_id]
            
            # 1. 기본 파라미터 적용
            base_params = strategy["base_params"]
            if self.trader:
                trader_settings = {}
                if "leverage" in base_params:
                    trader_settings["default_leverage"] = base_params["leverage"]
                if "tp_percent" in base_params:
                    trader_settings["default_tp"] = base_params["tp_percent"]
                if "sl_percent" in base_params:
                    trader_settings["default_sl"] = base_params["sl_percent"]
                
                self.trader.update_settings(trader_settings)
            
            # 2. 분석기 설정 적용
            if self.analyzer and "signal_threshold" in base_params:
                self.analyzer.set_user_signal_threshold(base_params["signal_threshold"])
            
            # 3. 코인 필터 적용
            if "filters" in strategy and self.evaluator:
                self._apply_coin_filters(strategy["filters"])
            
            # 4. 리스크 규칙 적용
            if "risk_rules" in strategy and self.risk_manager:
                self._apply_risk_rules(strategy["risk_rules"])
            
            # 5. 활성 전략 설정
            self.active_strategy_id = strategy_id
            
            self.logger.info(f"전략 적용 완료: {strategy['name']} ({strategy_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"전략 적용 오류: {e}")
            return False
    
    def _validate_strategy(self, strategy: Dict) -> Dict[str, Any]:
        """전략 검증"""
        try:
            # 필수 필드 확인
            required_fields = ["name", "base_params"]
            for field in required_fields:
                if field not in strategy:
                    return {"valid": False, "reason": f"필수 필드 누락: {field}"}
            
            # 파라미터 범위 확인
            base_params = strategy["base_params"]
            
            # 레버리지 범위 (1x ~ 10x)
            if "leverage" in base_params:
                leverage = base_params["leverage"]
                if not (1 <= leverage <= 10):
                    return {"valid": False, "reason": f"레버리지 범위 초과: {leverage} (1~10x)"}
            
            # 포지션 크기 (1% ~ 50%)
            if "position_size" in base_params:
                position_size = base_params["position_size"]
                if not (0.01 <= position_size <= 0.5):
                    return {"valid": False, "reason": f"포지션 크기 범위 초과: {position_size*100}% (1~50%)"}
            
            # TP/SL 범위 (0.01% ~ 5%)
            for param in ["tp_percent", "sl_percent"]:
                if param in base_params:
                    value = base_params[param]
                    if not (0.01 <= value <= 5.0):
                        return {"valid": False, "reason": f"{param} 범위 초과: {value}% (0.01~5%)"}
            
            # 신호 임계값 (30 ~ 95)
            if "signal_threshold" in base_params:
                threshold = base_params["signal_threshold"]
                if not (30 <= threshold <= 95):
                    return {"valid": False, "reason": f"신호 임계값 범위 초과: {threshold} (30~95)"}
            
            return {"valid": True, "reason": "검증 통과"}
            
        except Exception as e:
            return {"valid": False, "reason": f"검증 오류: {str(e)}"}
    
    def _apply_coin_filters(self, filters: Dict):
        """코인 필터 적용"""
        try:
            # 카테고리 필터
            if "categories" in filters:
                categories = filters["categories"]
                self.logger.info(f"코인 카테고리 필터 적용: {categories}")
                if self.evaluator and hasattr(self.evaluator, 'set_category_filter'):
                    self.evaluator.set_category_filter(categories)
                elif self.evaluator and hasattr(self.evaluator, 'user_category_filter'):
                    self.evaluator.user_category_filter = list(categories)
            
            # 시가총액 필터
            if "market_cap_min" in filters:
                market_cap_min = float(filters["market_cap_min"])
                self.logger.info(f"최소 시가총액 필터: {market_cap_min}")
                if self.evaluator and hasattr(self.evaluator, 'set_market_cap_filter'):
                    self.evaluator.set_market_cap_filter(market_cap_min)
                elif self.evaluator and hasattr(self.evaluator, 'min_market_cap'):
                    self.evaluator.min_market_cap = market_cap_min
            
            # 거래량 필터
            if "volume_min" in filters:
                volume_min = float(filters["volume_min"])
                self.logger.info(f"최소 거래량 필터: {volume_min}")
                if self.evaluator and hasattr(self.evaluator, 'set_volume_filter'):
                    self.evaluator.set_volume_filter(volume_min)
                elif self.evaluator and hasattr(self.evaluator, 'min_volume_24h'):
                    self.evaluator.min_volume_24h = volume_min
            
            # 선호/제외 코인
            if "preferred_coins" in filters:
                preferred = filters["preferred_coins"]
                self.logger.info(f"선호 코인: {preferred}")
                if self.evaluator and hasattr(self.evaluator, 'preferred_symbols'):
                    self.evaluator.preferred_symbols = list(preferred)
            
            if "excluded_coins" in filters:
                excluded = filters["excluded_coins"]
                self.logger.info(f"제외 코인: {excluded}")
                if self.evaluator and hasattr(self.evaluator, 'excluded_symbols'):
                    self.evaluator.excluded_symbols = list(excluded)
                
        except Exception as e:
            self.logger.error(f"코인 필터 적용 오류: {e}")
    
    def _apply_risk_rules(self, risk_rules: Dict):
        """리스크 규칙 적용"""
        try:
            rm = self.risk_manager

            # 일일 손실 한도
            if "daily_loss_limit" in risk_rules:
                daily_limit = float(risk_rules["daily_loss_limit"])
                self.logger.info(f"일일 손실 한도 설정: {daily_limit}%")
                if rm is not None:
                    if hasattr(rm, 'set_daily_loss_limit'):
                        rm.set_daily_loss_limit(daily_limit)
                    elif hasattr(rm, 'daily_loss_limit'):
                        rm.daily_loss_limit = daily_limit

            # 연속 손실 제한
            if "max_consecutive_losses" in risk_rules:
                max_losses = int(risk_rules["max_consecutive_losses"])
                self.logger.info(f"최대 연속 손실: {max_losses}회")
                if rm is not None:
                    if hasattr(rm, 'set_max_consecutive_losses'):
                        rm.set_max_consecutive_losses(max_losses)
                    elif hasattr(rm, 'max_consecutive_losses'):
                        rm.max_consecutive_losses = max_losses

            # 최대 포지션 수
            if "max_positions" in risk_rules:
                max_pos = int(risk_rules["max_positions"])
                self.logger.info(f"최대 동시 포지션 수: {max_pos}")
                if rm is not None and hasattr(rm, 'max_positions'):
                    rm.max_positions = max_pos

            # 감정 기반 조절
            if "emotion_adjustment" in risk_rules:
                emotion_factor = risk_rules["emotion_adjustment"]
                self.logger.info(f"감정 기반 리스크 조절: {emotion_factor}")
                if rm is not None and hasattr(rm, 'emotion_factor'):
                    rm.emotion_factor = float(emotion_factor)

        except Exception as e:
            self.logger.error(f"리스크 규칙 적용 오류: {e}")
    
    def apply_dynamic_adjustment(self, adjustment_type: str, context: Dict) -> bool:
        """동적 조절 적용"""
        try:
            if adjustment_type in self.dynamic_adjusters:
                adjuster_func = self.dynamic_adjusters[adjustment_type]
                result = adjuster_func(context)
                
                if result:
                    self.logger.info(f"동적 조절 적용 완료: {adjustment_type}")
                    return True
                else:
                    self.logger.warning(f"동적 조절 실패: {adjustment_type}")
                    return False
            else:
                self.logger.warning(f"알 수 없는 조절 타입: {adjustment_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"동적 조절 오류: {e}")
            return False
    
    def _adjust_for_market_condition(self, context: Dict) -> bool:
        """시장 상황 기반 조절"""
        try:
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            market_condition = context.get("market_condition", "NORMAL")
            
            # 시장 상황별 파라미터 조절
            adjustments = {}
            
            if market_condition == "HIGH_VOLATILITY":
                # 고변동성: 보수적 접근
                adjustments = {
                    "leverage": max(1, strategy["base_params"].get("leverage", 1) - 1),
                    "position_size": strategy["base_params"].get("position_size", 0.1) * 0.8,
                    "sl_percent": strategy["base_params"].get("sl_percent", 0.2) * 0.8
                }
            elif market_condition == "LOW_VOLATILITY":
                # 저변동성: 적극적 접근
                adjustments = {
                    "leverage": min(3, strategy["base_params"].get("leverage", 1) + 1),
                    "position_size": strategy["base_params"].get("position_size", 0.1) * 1.2,
                    "tp_percent": strategy["base_params"].get("tp_percent", 0.18) * 0.8
                }
            
            # 조절사항 적용
            if adjustments and self.trader:
                trader_settings = {}
                if "leverage" in adjustments:
                    trader_settings["default_leverage"] = adjustments["leverage"]
                if "tp_percent" in adjustments:
                    trader_settings["default_tp"] = adjustments["tp_percent"]
                if "sl_percent" in adjustments:
                    trader_settings["default_sl"] = adjustments["sl_percent"]
                
                self.trader.update_settings(trader_settings)
                
                self.logger.info(f"시장 상황 조절 적용: {market_condition} -> {adjustments}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"시장 상황 조절 오류: {e}")
            return False
    
    def _adjust_for_time(self, context: Dict) -> bool:
        """시간 기반 조절"""
        try:
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            time_rules = strategy.get("time_rules", {})
            
            current_time = datetime.now().time()
            current_hour = current_time.hour
            
            # 시간대별 활성화 체크
            active_hours = time_rules.get("active_hours", [(0, 23)])
            is_active_time = any(start <= current_hour <= end for start, end in active_hours)
            
            if not is_active_time:
                self.logger.info(f"비활성 시간대: {current_hour}시 — 거래 일시 중단")
                if self.trader and hasattr(self.trader, 'pause_trading'):
                    self.trader.pause_trading(reason=f'비활성 시간대({current_hour}시)')
                elif self.trader and hasattr(self.trader, 'set_monitoring_mode'):
                    self.trader.set_monitoring_mode(True)
                return True
            
            # 시간대별 파라미터 조절
            time_specific_params = time_rules.get("time_specific_params", {})
            
            if "morning" in time_specific_params and 6 <= current_hour <= 12:
                params = time_specific_params["morning"]
            elif "afternoon" in time_specific_params and 12 <= current_hour <= 18:
                params = time_specific_params["afternoon"]
            elif "evening" in time_specific_params and 18 <= current_hour <= 24:
                params = time_specific_params["evening"]
            else:
                return True  # 기본 설정 유지
            
            # 시간대별 설정 적용
            if params and self.trader:
                trader_settings = {}
                for key, value in params.items():
                    if key == "aggressiveness":
                        # 공격성 수준에 따른 파라미터 조절
                        if value == "high":
                            trader_settings["default_leverage"] = min(3, strategy["base_params"].get("leverage", 1) * 1.5)
                        elif value == "low":
                            trader_settings["default_leverage"] = max(1, strategy["base_params"].get("leverage", 1) * 0.8)
                
                if trader_settings:
                    self.trader.update_settings(trader_settings)
                    self.logger.info(f"시간대 조절 적용: {current_hour}시 -> {params}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"시간 기반 조절 오류: {e}")
            return False
    
    def _adjust_for_performance(self, context: Dict) -> bool:
        """성과 기반 조절"""
        try:
            if not self.active_strategy_id:
                return False
            
            performance_data = context.get("performance", {})
            recent_win_rate = performance_data.get("recent_win_rate", 0.5)
            consecutive_losses = performance_data.get("consecutive_losses", 0)
            
            strategy = self.user_strategies[self.active_strategy_id]
            adjustments = {}
            
            # 연속 손실 시 보수적 조절
            if consecutive_losses >= 3:
                adjustments = {
                    "leverage": 1,  # 최소 레버리지
                    "position_size": strategy["base_params"].get("position_size", 0.1) * 0.5,
                    "signal_threshold": min(90, strategy["base_params"].get("signal_threshold", 70) + 10)
                }
                self.logger.warning(f"연속 손실 감지 ({consecutive_losses}회) - 보수적 모드 전환")
            
            # 높은 승률 시 적극적 조절
            elif recent_win_rate > 0.7:
                adjustments = {
                    "leverage": min(3, strategy["base_params"].get("leverage", 1) + 1),
                    "position_size": min(0.2, strategy["base_params"].get("position_size", 0.1) * 1.2),
                }
                self.logger.info(f"높은 승률 감지 ({recent_win_rate:.1%}) - 적극적 모드 전환")
            
            # 조절사항 적용
            if adjustments:
                if self.trader:
                    trader_settings = {}
                    if "leverage" in adjustments:
                        trader_settings["default_leverage"] = adjustments["leverage"]
                    if "position_size" in adjustments:
                        pos_size = float(adjustments["position_size"])
                        trader_settings["position_size"] = pos_size
                        # 직접 속성 지원 시 함께 갱신
                        if hasattr(self.trader, 'position_size'):
                            self.trader.position_size = pos_size
                        elif hasattr(self.trader, 'set_position_size'):
                            self.trader.set_position_size(pos_size)
                    
                    if trader_settings:
                        self.trader.update_settings(trader_settings)
                
                if self.analyzer and "signal_threshold" in adjustments:
                    self.analyzer.set_user_signal_threshold(adjustments["signal_threshold"])
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"성과 기반 조절 오류: {e}")
            return False
    
    def _adjust_for_emotion(self, context: Dict) -> bool:
        """감정 기반 조절"""
        try:
            emotion_state = context.get("emotion", "neutral")
            stress_level = context.get("stress_level", 0.5)  # 0.0 ~ 1.0
            
            if not self.active_strategy_id:
                return False
            
            strategy = self.user_strategies[self.active_strategy_id]
            
            # 스트레스 수준에 따른 조절
            if stress_level > 0.7 or emotion_state in ["stressed", "anxious"]:
                # 고스트레스: 매우 보수적
                adjustments = {
                    "leverage": 1,
                    "position_size": strategy["base_params"].get("position_size", 0.1) * 0.3,
                    "sl_percent": strategy["base_params"].get("sl_percent", 0.2) * 0.7,
                    "signal_threshold": min(90, strategy["base_params"].get("signal_threshold", 70) + 15)
                }
                self.logger.info(f"고스트레스 상태 감지 - 안전 모드 적용: {emotion_state}")
                
            elif stress_level < 0.3 and emotion_state in ["confident", "happy"]:
                # 저스트레스 + 긍정적: 약간 적극적
                adjustments = {
                    "leverage": min(2, strategy["base_params"].get("leverage", 1) + 0.5),
                    "position_size": min(0.15, strategy["base_params"].get("position_size", 0.1) * 1.1),
                }
                self.logger.info(f"긍정적 상태 감지 - 균형 모드 적용: {emotion_state}")
                
            else:
                return True  # 중립 상태, 변경 없음
            
            # 조절사항 적용
            if self.trader:
                trader_settings = {}
                if "leverage" in adjustments:
                    trader_settings["default_leverage"] = adjustments["leverage"]
                if "sl_percent" in adjustments:
                    trader_settings["default_sl"] = adjustments["sl_percent"]
                
                if trader_settings:
                    self.trader.update_settings(trader_settings)
            
            if self.analyzer and "signal_threshold" in adjustments:
                self.analyzer.set_user_signal_threshold(adjustments["signal_threshold"])
            
            return True
            
        except Exception as e:
            self.logger.error(f"감정 기반 조절 오류: {e}")
            return False
    
    def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """전략 성과 조회"""
        try:
            if strategy_id not in self.user_strategies:
                return {}
            
            strategy = self.user_strategies[strategy_id]
            return strategy.get("live_performance", {})
            
        except Exception as e:
            self.logger.error(f"전략 성과 조회 오류: {e}")
            return {}
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """전략 목록 조회"""
        try:
            return [
                {
                    "id": strategy_id,
                    "name": strategy["name"],
                    "created_at": strategy["created_at"],
                    "active": strategy_id == self.active_strategy_id,
                    "performance": strategy.get("live_performance", {})
                }
                for strategy_id, strategy in self.user_strategies.items()
            ]
            
        except Exception as e:
            self.logger.error(f"전략 목록 조회 오류: {e}")
            return []
    
    def backup_strategy(self, strategy_id: str) -> bool:
        """전략 백업"""
        try:
            if strategy_id not in self.user_strategies:
                return False
            
            strategy = self.user_strategies[strategy_id]
            backup_data = {
                "strategy": strategy,
                "backup_time": datetime.now().isoformat(),
                "backup_reason": "user_request"
            }
            
            # 백업 파일 저장
            backup_filename = f"strategy_backup_{strategy_id}_{int(datetime.now().timestamp())}.json"
            with open(backup_filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"전략 백업 완료: {backup_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"전략 백업 오류: {e}")
            return False
