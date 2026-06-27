#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 대화형 전략 시스템
사용자와의 실시간 대화를 통한 전략 커스터마이징
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

class ChatIntentType(Enum):
    """대화 의도 분류"""
    MARKET_ANALYSIS = "market_analysis"
    STRATEGY_CHANGE = "strategy_change"
    PARAMETER_ADJUST = "parameter_adjust"
    RISK_MANAGEMENT = "risk_management"
    PERFORMANCE_REVIEW = "performance_review"
    GENERAL_QUESTION = "general_question"

@dataclass
class ChatMessage:
    """채팅 메시지"""
    timestamp: datetime
    user_id: str
    message: str
    intent: ChatIntentType
    response: str
    action_taken: Optional[Dict] = None

@dataclass 
class StrategyPreset:
    """전략 프리셋"""
    name: str
    description: str
    parameters: Dict[str, Any]
    risk_level: str  # CONSERVATIVE, BALANCED, AGGRESSIVE
    expected_return: float
    max_drawdown: float

class AITradingChatbot:
    """AI 거래 챗봇"""
    
    def __init__(self, analyzer, trader, risk_manager):
        self.analyzer = analyzer
        self.trader = trader
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(__name__)
        
        # 대화 이력
        self.chat_history: List[ChatMessage] = []
        
        # 전략 프리셋
        self.strategy_presets = self._initialize_strategy_presets()
        
        # 현재 설정 백업
        self.default_settings_backup = None
        self.custom_settings_history = []
        
        self.logger.info("AI Trading Chatbot 초기화 완료")
    
    def _initialize_strategy_presets(self) -> Dict[str, StrategyPreset]:
        """전략 프리셋 초기화"""
        return {
            "conservative": StrategyPreset(
                name="안전 우선",
                description="낮은 리스크, 안정적 수익 추구",
                parameters={
                    "leverage": 1,
                    "position_size": 0.05,  # 5%
                    "tp_percent": 0.12,
                    "sl_percent": 0.15,
                    "signal_threshold": 80
                },
                risk_level="CONSERVATIVE",
                expected_return=0.8,
                max_drawdown=0.3
            ),
            "balanced": StrategyPreset(
                name="균형 전략",
                description="중간 리스크, 균형잡힌 수익",
                parameters={
                    "leverage": 1,
                    "position_size": 0.10,  # 10%
                    "tp_percent": 0.18,
                    "sl_percent": 0.20,
                    "signal_threshold": 70
                },
                risk_level="BALANCED", 
                expected_return=1.2,
                max_drawdown=0.5
            ),
            "aggressive": StrategyPreset(
                name="적극 공격",
                description="높은 리스크, 높은 수익 추구",
                parameters={
                    "leverage": 2,
                    "position_size": 0.15,  # 15%
                    "tp_percent": 0.25,
                    "sl_percent": 0.25,
                    "signal_threshold": 60
                },
                risk_level="AGGRESSIVE",
                expected_return=2.0,
                max_drawdown=1.0
            )
        }
    
    async def process_user_message(self, user_message: str, user_id: str = "default") -> Dict[str, Any]:
        """사용자 메시지 처리"""
        try:
            # 1. 의도 분석
            intent = self._analyze_intent(user_message)
            
            # 2. 응답 생성
            response_data = await self._generate_response(user_message, intent)
            
            # 3. 채팅 이력 저장
            chat_message = ChatMessage(
                timestamp=datetime.now(),
                user_id=user_id,
                message=user_message,
                intent=intent,
                response=response_data["text"],
                action_taken=response_data.get("action")
            )
            self.chat_history.append(chat_message)
            
            return {
                "response": response_data["text"],
                "intent": intent.value,
                "suggested_actions": response_data.get("suggested_actions", []),
                "requires_confirmation": response_data.get("requires_confirmation", False),
                "action_data": response_data.get("action")
            }
            
        except Exception as e:
            self.logger.error(f"메시지 처리 오류: {e}")
            return {
                "response": "죄송합니다. 메시지 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                "intent": "error",
                "suggested_actions": [],
                "requires_confirmation": False
            }
    
    def _analyze_intent(self, message: str) -> ChatIntentType:
        """메시지 의도 분석"""
        message_lower = message.lower()
        
        # 키워드 기반 의도 분류
        if any(word in message_lower for word in ["시장", "상황", "분석", "어때", "현재"]):
            return ChatIntentType.MARKET_ANALYSIS
            
        elif any(word in message_lower for word in ["공격적", "적극적", "안전", "보수적", "전략"]):
            return ChatIntentType.STRATEGY_CHANGE
            
        elif any(word in message_lower for word in ["레버리지", "포지션", "손절", "익절", "설정"]):
            return ChatIntentType.PARAMETER_ADJUST
            
        elif any(word in message_lower for word in ["손실", "위험", "리스크", "안전하게"]):
            return ChatIntentType.RISK_MANAGEMENT
            
        elif any(word in message_lower for word in ["수익", "성과", "결과", "성능"]):
            return ChatIntentType.PERFORMANCE_REVIEW
            
        else:
            return ChatIntentType.GENERAL_QUESTION
    
    async def _generate_response(self, message: str, intent: ChatIntentType) -> Dict[str, Any]:
        """응답 생성"""
        try:
            if intent == ChatIntentType.MARKET_ANALYSIS:
                return await self._handle_market_analysis_request()
                
            elif intent == ChatIntentType.STRATEGY_CHANGE:
                return await self._handle_strategy_change_request(message)
                
            elif intent == ChatIntentType.PARAMETER_ADJUST:
                return await self._handle_parameter_adjust_request(message)
                
            elif intent == ChatIntentType.RISK_MANAGEMENT:
                return await self._handle_risk_management_request(message)
                
            elif intent == ChatIntentType.PERFORMANCE_REVIEW:
                return await self._handle_performance_review_request()
                
            else:
                return await self._handle_general_question(message)
                
        except Exception as e:
            self.logger.error(f"응답 생성 오류: {e}")
            return {
                "text": "응답 생성 중 오류가 발생했습니다.",
                "suggested_actions": []
            }
    
    async def _handle_market_analysis_request(self) -> Dict[str, Any]:
        """시장 분석 요청 처리"""
        try:
            # 현재 시장 상황 분석
            if self.analyzer:
                market_conditions = self.analyzer._analyze_current_market_conditions()
                market_level = market_conditions.get('level', 'NORMAL')
                market_score = market_conditions.get('score', 0)
                
                # 시장 상황에 따른 응답 생성
                if market_level == 'HIGH':
                    emoji = "🔥"
                    status = "매우 활발한 상태"
                    recommendation = "적극적인 거래 기회가 많습니다"
                elif market_level == 'LOW':
                    emoji = "😴"
                    status = "조용한 상태"
                    recommendation = "신중한 진입을 권장합니다"
                else:
                    emoji = "📊"
                    status = "보통 상태"
                    recommendation = "균형잡힌 거래가 적합합니다"
                
                response_text = f"""
{emoji} **현재 시장 분석**

📈 **시장 활동도**: {status} (점수: {market_score:.1f})
🎯 **추천사항**: {recommendation}

💡 **AI 분석 결과**:
• 변동성: {market_level} 수준
• 거래 기회: {'높음' if market_level == 'HIGH' else '중간' if market_level == 'NORMAL' else '낮음'}
• 권장 전략: {'적극적' if market_level == 'HIGH' else '균형' if market_level == 'NORMAL' else '보수적'}

더 자세한 분석이 필요하시면 말씀해주세요! 🤖
                """.strip()
                
                return {
                    "text": response_text,
                    "suggested_actions": [
                        "전략 변경하기",
                        "파라미터 조정하기", 
                        "코인 선택 기준 변경하기"
                    ]
                }
            else:
                return {
                    "text": "죄송합니다. 현재 시장 분석 기능을 사용할 수 없습니다.",
                    "suggested_actions": []
                }
                
        except Exception as e:
            self.logger.error(f"시장 분석 처리 오류: {e}")
            return {
                "text": "시장 분석 중 오류가 발생했습니다.",
                "suggested_actions": []
            }
    
    async def _handle_strategy_change_request(self, message: str) -> Dict[str, Any]:
        """전략 변경 요청 처리"""
        try:
            message_lower = message.lower()
            
            # 전략 타입 식별
            if any(word in message_lower for word in ["공격적", "적극적", "aggressive"]):
                strategy_key = "aggressive"
            elif any(word in message_lower for word in ["안전", "보수적", "conservative"]):
                strategy_key = "conservative"
            else:
                strategy_key = "balanced"
            
            strategy = self.strategy_presets[strategy_key]
            current_settings = self._get_current_settings()
            
            # 변경사항 계산
            changes = self._calculate_strategy_changes(current_settings, strategy.parameters)
            
            response_text = f"""
🎯 **{strategy.name} 전략**으로 변경하시겠습니까?

📋 **전략 정보**:
• 설명: {strategy.description}
• 리스크 수준: {strategy.risk_level}
• 예상 수익률: {strategy.expected_return}%/일
• 최대 손실: {strategy.max_drawdown}%

🔄 **변경사항**:
{self._format_changes(changes)}

⚠️ **예상 효과**:
• 수익률: {'+' if strategy.expected_return > 1.0 else ''}{(strategy.expected_return - 1.0) * 100:+.0f}%
• 리스크: {'+' if strategy.max_drawdown > 0.5 else ''}{(strategy.max_drawdown - 0.5) * 100:+.0f}%

적용하시겠습니까?
            """.strip()
            
            return {
                "text": response_text,
                "requires_confirmation": True,
                "action": {
                    "type": "strategy_change",
                    "strategy_key": strategy_key,
                    "parameters": strategy.parameters
                },
                "suggested_actions": ["적용하기", "다른 전략 보기", "취소하기"]
            }
            
        except Exception as e:
            self.logger.error(f"전략 변경 처리 오류: {e}")
            return {
                "text": "전략 변경 처리 중 오류가 발생했습니다.",
                "suggested_actions": []
            }
    
    def _get_current_settings(self) -> Dict[str, Any]:
        """현재 설정 조회"""
        if self.trader:
            return {
                "leverage": self.trader.settings.get('default_leverage', 1),
                "position_size": 0.10,  # 기본값
                "tp_percent": self.trader.settings.get('default_tp', 0.18),
                "sl_percent": self.trader.settings.get('default_sl', 0.20),
                "signal_threshold": getattr(self.analyzer, 'user_signal_threshold', 70) if self.analyzer else 70
            }
        return {}
    
    def _calculate_strategy_changes(self, current: Dict, target: Dict) -> Dict[str, tuple]:
        """전략 변경사항 계산"""
        changes = {}
        for key, new_value in target.items():
            if key in current:
                old_value = current[key]
                if old_value != new_value:
                    changes[key] = (old_value, new_value)
        return changes
    
    def _format_changes(self, changes: Dict[str, tuple]) -> str:
        """변경사항 포맷팅"""
        if not changes:
            return "• 변경사항 없음"
        
        formatted = []
        labels = {
            "leverage": "레버리지",
            "position_size": "포지션 크기",
            "tp_percent": "익절 목표",
            "sl_percent": "손절 라인",
            "signal_threshold": "신호 임계값"
        }
        
        for key, (old, new) in changes.items():
            label = labels.get(key, key)
            if key == "position_size":
                formatted.append(f"• {label}: {old*100:.0f}% → {new*100:.0f}%")
            elif key in ["tp_percent", "sl_percent"]:
                formatted.append(f"• {label}: {old:.2f}% → {new:.2f}%")
            else:
                formatted.append(f"• {label}: {old} → {new}")
        
        return "\n".join(formatted)
    
    async def _handle_parameter_adjust_request(self, message: str) -> Dict[str, Any]:
        """파라미터 조정 요청 처리"""
        # 구체적인 파라미터 조정 로직 구현
        return {
            "text": "파라미터 조정 기능은 구현 중입니다.",
            "suggested_actions": ["전략 프리셋 사용하기"]
        }
    
    async def _handle_risk_management_request(self, message: str) -> Dict[str, Any]:
        """리스크 관리 요청 처리"""
        try:
            # 현재 리스크 상황 분석
            response_text = """
🛡️ **안전 모드로 전환**합니다

🔒 **적용될 보안 설정**:
• 레버리지: 1x (고정)
• 포지션 크기: 5% (축소)
• 손절라인: 0.15% (강화)
• 신호 임계값: 80점 (엄격)

📊 **예상 효과**:
• 손실 리스크: -60% 감소
• 수익 기회: -20% 감소
• 안정성: +80% 향상

현재 설정을 백업하고 안전 모드를 적용하시겠습니까?
            """.strip()
            
            return {
                "text": response_text,
                "requires_confirmation": True,
                "action": {
                    "type": "safety_mode",
                    "parameters": self.strategy_presets["conservative"].parameters
                },
                "suggested_actions": ["안전 모드 적용", "설정 유지", "다른 옵션 보기"]
            }
            
        except Exception as e:
            self.logger.error(f"리스크 관리 처리 오류: {e}")
            return {
                "text": "리스크 관리 설정 중 오류가 발생했습니다.",
                "suggested_actions": []
            }
    
    async def _handle_performance_review_request(self) -> Dict[str, Any]:
        """성과 검토 요청 처리"""
        # 성과 분석 로직 구현
        return {
            "text": "성과 분석 기능은 구현 중입니다.",
            "suggested_actions": ["거래 이력 보기"]
        }
    
    async def _handle_general_question(self, message: str) -> Dict[str, Any]:
        """일반 질문 처리"""
        return {
            "text": f"질문해주셔서 감사합니다! 더 구체적으로 도움이 필요한 부분을 말씀해주세요.\n\n💡 **이런 것들을 도와드릴 수 있어요**:\n• 현재 시장 상황 분석\n• 거래 전략 조정\n• 리스크 관리 설정\n• 성과 분석 및 개선",
            "suggested_actions": [
                "시장 분석 요청",
                "전략 변경하기", 
                "리스크 관리",
                "성과 검토"
            ]
        }
    
    def apply_strategy_changes(self, action_data: Dict) -> bool:
        """전략 변경사항 적용"""
        try:
            # 현재 설정 백업
            if not self.default_settings_backup:
                self.default_settings_backup = self._get_current_settings()
            
            action_type = action_data.get("type")
            parameters = action_data.get("parameters", {})
            
            if action_type in ["strategy_change", "safety_mode"]:
                # 트레이더 설정 업데이트
                if self.trader:
                    new_settings = {}
                    if "leverage" in parameters:
                        new_settings["default_leverage"] = parameters["leverage"]
                    if "tp_percent" in parameters:
                        new_settings["default_tp"] = parameters["tp_percent"]
                    if "sl_percent" in parameters:
                        new_settings["default_sl"] = parameters["sl_percent"]
                    
                    self.trader.update_settings(new_settings)
                
                # 분석기 설정 업데이트
                if self.analyzer and "signal_threshold" in parameters:
                    self.analyzer.set_user_signal_threshold(parameters["signal_threshold"])
                
                # 변경 이력 저장
                self.custom_settings_history.append({
                    "timestamp": datetime.now(),
                    "action_type": action_type,
                    "parameters": parameters,
                    "user_message": f"Applied {action_type}"
                })
                
                self.logger.info(f"전략 변경 적용 완료: {action_type}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"전략 변경 적용 오류: {e}")
            return False
    
    def restore_default_settings(self) -> bool:
        """기본 설정 복원"""
        try:
            if not self.default_settings_backup:
                self.logger.warning("백업된 기본 설정이 없습니다")
                return False
            
            # 기본 설정 복원
            if self.trader:
                restore_settings = {}
                if "leverage" in self.default_settings_backup:
                    restore_settings["default_leverage"] = self.default_settings_backup["leverage"]
                if "tp_percent" in self.default_settings_backup:
                    restore_settings["default_tp"] = self.default_settings_backup["tp_percent"]
                if "sl_percent" in self.default_settings_backup:
                    restore_settings["default_sl"] = self.default_settings_backup["sl_percent"]
                
                self.trader.update_settings(restore_settings)
            
            if self.analyzer and "signal_threshold" in self.default_settings_backup:
                self.analyzer.set_user_signal_threshold(self.default_settings_backup["signal_threshold"])
            
            self.logger.info("기본 설정 복원 완료")
            return True
            
        except Exception as e:
            self.logger.error(f"기본 설정 복원 오류: {e}")
            return False
    
    def get_chat_history(self, limit: int = 10) -> List[Dict]:
        """채팅 이력 조회"""
        try:
            recent_chats = self.chat_history[-limit:] if limit > 0 else self.chat_history
            return [
                {
                    "timestamp": chat.timestamp.isoformat(),
                    "message": chat.message,
                    "response": chat.response,
                    "intent": chat.intent.value,
                    "action_taken": chat.action_taken
                }
                for chat in recent_chats
            ]
        except Exception as e:
            self.logger.error(f"채팅 이력 조회 오류: {e}")
            return []
