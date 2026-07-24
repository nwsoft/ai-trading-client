#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 대화형 전략 시스템
사용자와의 실시간 대화를 통한 전략 커스터마이징
"""

import json
import logging
import math
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

class ChatIntentType(Enum):
    """대화 의도 분류"""
    MARKET_ANALYSIS = "market_analysis"
    STRATEGY_CHANGE = "strategy_change"
    PARAMETER_ADJUST = "parameter_adjust"
    RISK_MANAGEMENT = "risk_management"
    PERFORMANCE_REVIEW = "performance_review"
    DAILY_REPORT = "daily_report"
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
            
        elif any(word in message_lower for word in ["일일", "데일리", "브리프", "리포트", "아침", "저녁"]):
            return ChatIntentType.DAILY_REPORT

        elif any(word in message_lower for word in ["수익", "성과", "결과", "성능", "복기", "건강도", "샤프", "mdd", "포트폴리오", "분산", "편중", "현금비율"]):
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

            elif intent == ChatIntentType.DAILY_REPORT:
                return await self._handle_daily_report_request()
                
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
                "tp_percent": float(self.trader.settings.get('default_tp', 0.0018)) * 100.0,
                "sl_percent": float(self.trader.settings.get('default_sl', 0.0020)) * 100.0,
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
        try:
            trades = self._collect_trade_history(limit=120)
            if not trades:
                return {
                    "text": "최근 거래 데이터가 없어 복기를 생성할 수 없습니다. 거래가 1건 이상 쌓이면 계좌 건강도와 개선 포인트를 자동으로 보여드립니다.",
                    "suggested_actions": ["거래 이력 보기", "시장 분석 요청"]
                }

            metrics = self._build_health_metrics(trades)
            review_points = self._build_trade_review_points(metrics)
            portfolio = self._build_portfolio_diagnosis()

            response_text = (
                "📋 계좌 건강도 + 거래 복기\n\n"
                f"• 건강도 점수: {metrics['health_score']}/100 ({metrics['health_grade']})\n"
                f"• 총 거래: {metrics['total_trades']}건 | 승률: {metrics['win_rate']:.1f}%\n"
                f"• 순손익: {metrics['net_pnl']:+.2f} | Profit Factor: {metrics['profit_factor']:.2f}\n"
                f"• Sharpe: {metrics['sharpe']:.2f} | MDD: {metrics['mdd']*100:.2f}%\n\n"
                "📦 포트폴리오 진단\n"
                f"• 포지션 수: {portfolio['position_count']} | 포지션 노출: {portfolio['exposure']:.2f}\n"
                f"• 현금 비율: {portfolio['cash_ratio']:.1f}% | 최대 편중: {portfolio['top_symbol']} {portfolio['top_concentration']:.1f}%\n"
                f"• 포트폴리오 상태: {portfolio['summary']}\n\n"
                "🔎 거래 복기\n"
                + "\n".join([f"• {point}" for point in review_points])
            )

            return {
                "text": response_text,
                "suggested_actions": ["리스크 관리", "전략 변경하기", "시장 분석 요청"],
                "action": {
                    "type": "performance_review",
                    "metrics": metrics,
                    "portfolio_diagnosis": portfolio,
                },
            }
        except Exception as e:
            self.logger.error(f"성과 검토 처리 오류: {e}")
            return {
                "text": "성과 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "suggested_actions": ["거래 이력 보기"]
            }

    async def _handle_daily_report_request(self) -> Dict[str, Any]:
        """S-3 일일 리포트 요청 처리"""
        try:
            trades = self._collect_trade_history(limit=120)
            if not trades:
                return {
                    "text": "📄 AI 일일 리포트\n\n❌ 거래 데이터가 없어 일일 리포트를 생성할 수 없습니다.\n\n• 거래 데이터가 1건 이상 쌓이면 자동으로 일일 요약을 제공합니다.",
                    "suggested_actions": ["시장 분석 요청", "거래 이력 보기"],
                }

            metrics = self._build_health_metrics(trades)
            portfolio = self._build_portfolio_diagnosis()
            total_fees = sum(self._extract_trade_fee(t) for t in trades)
            avg_fee = (total_fees / len(trades)) if trades else 0.0
            fee_impact = (total_fees / abs(metrics["net_pnl"]) * 100.0) if abs(metrics["net_pnl"]) > 0 else 0.0

            response_text = (
                "📄 AI 일일 리포트\n\n"
                "🌅 아침 브리프\n"
                f"• 포트폴리오 상태: {portfolio['summary']}\n"
                f"• 현금 비율: {portfolio['cash_ratio']:.1f}% | 최대 편중: {portfolio['top_symbol']} {portfolio['top_concentration']:.1f}%\n"
                f"• 리스크 레벨: {'주의' if metrics['mdd'] > 0.25 else '안정'}\n\n"
                "🌙 저녁 복기\n"
                f"• 총 거래: {metrics['total_trades']}건 | 승률: {metrics['win_rate']:.1f}%\n"
                f"• 누적PnL: {metrics['net_pnl']:+.2f} | Profit Factor: {metrics['profit_factor']:.2f}\n"
                f"• 누적Fee: {total_fees:.2f} | 평균Fee: {avg_fee:.4f} | Fee/PnL: {fee_impact:.2f}%\n"
                f"• 건강도: {metrics['health_score']}/100 ({metrics['health_grade']})"
            )

            return {
                "text": response_text,
                "suggested_actions": ["성과 검토", "리스크 관리", "전략 변경하기"],
                "action": {
                    "type": "daily_report",
                    "metrics": metrics,
                    "portfolio_diagnosis": portfolio,
                    "cost": {
                        "total_fees": float(total_fees),
                        "avg_fee": float(avg_fee),
                        "fee_impact_percent": float(fee_impact),
                    },
                },
            }
        except Exception as e:
            self.logger.error(f"일일 리포트 처리 오류: {e}")
            return {
                "text": "일일 리포트 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "suggested_actions": ["성과 검토", "시장 분석 요청"],
            }

    def _collect_trade_history(self, limit: int = 120) -> List[Dict[str, Any]]:
        """트레이더/레코더에서 최근 거래 이력을 수집한다."""
        candidates: List[Any] = []

        if not self.trader:
            return []

        # 1) 메모리 기반 후보
        for attr in ("trade_history", "closed_trades", "recent_trades", "trades"):
            value = getattr(self.trader, attr, None)
            if isinstance(value, list):
                candidates.extend(value)

        # 2) 레코더 기반 후보
        recorder = getattr(self.trader, "recorder", None)
        if recorder:
            for method_name in ("get_recent_trades", "get_trade_history", "load_recent_trades"):
                method = getattr(recorder, method_name, None)
                if callable(method):
                    try:
                        result = method(limit)  # type: ignore[misc]
                        if isinstance(result, list):
                            candidates.extend(result)
                            break
                    except Exception:
                        continue

        normalized: List[Dict[str, Any]] = []
        for item in candidates:
            if isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "__dict__"):
                normalized.append(dict(item.__dict__))

        # 중복 제거(동일 timestamp + symbol + pnl 기준)
        uniq: Dict[str, Dict[str, Any]] = {}
        for trade in normalized:
            key = "|".join(
                [
                    str(trade.get("timestamp") or trade.get("closed_at") or trade.get("time") or ""),
                    str(trade.get("symbol") or trade.get("ticker") or ""),
                    str(trade.get("pnl") or trade.get("profit") or trade.get("realized_pnl") or ""),
                ]
            )
            uniq[key] = trade

        trades = list(uniq.values())
        return trades[-limit:] if limit > 0 else trades

    def _extract_trade_pnl(self, trade: Dict[str, Any]) -> float:
        """거래 객체에서 손익 값을 추출한다."""
        for key in ("pnl", "profit", "realized_pnl", "net_pnl", "profit_loss"):
            value = trade.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def _extract_trade_fee(self, trade: Dict[str, Any]) -> float:
        """거래 객체에서 수수료 값을 추출한다."""
        for key in ("fees", "fee", "commission"):
            value = trade.get(key)
            if value is not None:
                try:
                    return abs(float(value))
                except (TypeError, ValueError):
                    continue
        return 0.0

    def _build_health_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        pnls = [self._extract_trade_pnl(t) for t in trades]
        total = len(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total * 100.0) if total else 0.0
        net_pnl = float(sum(pnls))
        avg_win = float(sum(wins) / win_count) if win_count else 0.0
        avg_loss = float(sum(losses) / loss_count) if loss_count else 0.0

        total_gain = float(sum(wins))
        total_loss_abs = abs(float(sum(losses)))
        profit_factor = total_gain / total_loss_abs if total_loss_abs > 0 else (9.99 if total_gain > 0 else 0.0)

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                drawdown = (peak - equity) / peak
                max_drawdown = max(max_drawdown, drawdown)

        returns = [pnl for pnl in pnls if pnl != 0]
        if len(returns) >= 2:
            mean_ret = statistics.mean(returns)
            std_ret = statistics.pstdev(returns)
            sharpe = (mean_ret / std_ret) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        health_score = 50
        health_score += min(20, int(win_rate / 5))
        health_score += min(15, int(max(0.0, min(profit_factor, 3.0)) * 5))
        health_score += min(10, int(max(-1.0, min(sharpe, 2.0)) * 5))
        health_score += min(5, max(0, int((0.25 - max_drawdown) * 20)))
        health_score = int(max(0, min(100, health_score)))

        if health_score >= 80:
            grade = "매우 양호"
        elif health_score >= 65:
            grade = "양호"
        elif health_score >= 50:
            grade = "주의"
        else:
            grade = "위험"

        return {
            "total_trades": total,
            "win_rate": win_rate,
            "net_pnl": net_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "sharpe": float(sharpe),
            "mdd": float(max_drawdown),
            "health_score": health_score,
            "health_grade": grade,
        }

    def _build_trade_review_points(self, metrics: Dict[str, Any]) -> List[str]:
        """핵심 지표 기준의 복기 코멘트를 생성한다."""
        points: List[str] = []

        if metrics["win_rate"] < 45:
            points.append("승률이 낮아 진입 필터를 강화하고 신호 임계값 상향을 권장합니다.")
        else:
            points.append("승률 흐름은 유지 가능한 수준입니다. 과도한 매매 빈도만 주의하세요.")

        if metrics["profit_factor"] < 1.2:
            points.append("손익비가 약합니다. 익절/손절 비율을 재점검해 평균 손실을 줄이세요.")
        else:
            points.append("손익비가 양호합니다. 현재 손절 규칙을 유지하되 급변 구간만 보수적으로 대응하세요.")

        if metrics["mdd"] > 0.25:
            points.append("최대 낙폭이 높습니다. 포지션 크기 축소와 레버리지 제한이 필요합니다.")
        else:
            points.append("최대 낙폭은 통제 범위입니다. 리스크 한도를 유지하세요.")

        if metrics["sharpe"] < 0.5:
            points.append("변동성 대비 성과가 낮습니다. 신호 품질이 높은 구간 위주로 거래를 압축하세요.")
        else:
            points.append("리스크 대비 성과(Sharpe)가 안정 구간입니다.")

        return points

    def _build_portfolio_diagnosis(self) -> Dict[str, Any]:
        """현재 포지션/현금 기준 포트폴리오 진단을 생성한다."""
        try:
            positions = self._collect_active_positions()
            cash_value = self._collect_cash_value()

            exposures: List[Tuple[str, float]] = []
            total_exposure = 0.0
            for symbol, pos in positions.items():
                exposure = self._estimate_position_exposure(pos)
                if exposure <= 0:
                    continue
                total_exposure += exposure
                exposures.append((symbol, exposure))

            portfolio_total = total_exposure + max(0.0, cash_value)
            cash_ratio = (cash_value / portfolio_total * 100.0) if portfolio_total > 0 else 0.0

            top_symbol = "N/A"
            top_concentration = 0.0
            if exposures and total_exposure > 0:
                top_symbol, top_value = max(exposures, key=lambda item: item[1])
                top_concentration = (top_value / total_exposure) * 100.0

            if len(exposures) == 0:
                summary = "포지션 없음 (대기 상태)"
            elif top_concentration >= 55.0:
                summary = "편중 위험 높음"
            elif top_concentration >= 40.0:
                summary = "편중 주의"
            else:
                summary = "분산 양호"

            return {
                "position_count": len(exposures),
                "exposure": float(total_exposure),
                "cash": float(cash_value),
                "cash_ratio": float(cash_ratio),
                "top_symbol": str(top_symbol),
                "top_concentration": float(top_concentration),
                "summary": summary,
            }
        except Exception:
            return {
                "position_count": 0,
                "exposure": 0.0,
                "cash": 0.0,
                "cash_ratio": 0.0,
                "top_symbol": "N/A",
                "top_concentration": 0.0,
                "summary": "진단 데이터 부족",
            }

    def _collect_active_positions(self) -> Dict[str, Any]:
        """트레이더에서 활성 포지션 딕셔너리를 추출한다."""
        if not self.trader:
            return {}

        positions = getattr(self.trader, "active_positions", None)
        if isinstance(positions, dict):
            # unified 형태(exchange -> dict(symbol -> position)) 평탄화
            if positions and all(isinstance(v, dict) for v in positions.values()):
                flattened: Dict[str, Any] = {}
                for value in positions.values():
                    for k, v in value.items():
                        flattened[str(k)] = v
                if flattened:
                    return flattened
            return positions

        return {}

    def _collect_cash_value(self) -> float:
        """트레이더의 현금성 값(USDT/KRW/현금)을 추정한다."""
        if not self.trader:
            return 0.0

        for attr in ("available_balance", "current_balance", "account_balance", "usdt_balance", "cash"):
            value = getattr(self.trader, attr, None)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def _estimate_position_exposure(self, pos: Any) -> float:
        """포지션 한 건의 노출 금액을 추정한다."""
        def _g(obj: Any, key: str, default: Any = None) -> Any:
            try:
                if isinstance(obj, dict):
                    return obj.get(key, default)
                if hasattr(obj, key):
                    return getattr(obj, key)
            except Exception:
                pass
            return default

        qty = _g(pos, "quantity", _g(pos, "size", _g(pos, "contracts", 0.0)))
        entry_price = _g(pos, "entry_price", _g(pos, "entryPrice", _g(pos, "price", 0.0)))
        amount = _g(pos, "amount", None)

        try:
            if amount is not None:
                amount_f = float(amount)
                if amount_f > 0:
                    return amount_f
        except (TypeError, ValueError):
            pass

        try:
            q = abs(float(qty or 0.0))
            p = abs(float(entry_price or 0.0))
            return q * p
        except (TypeError, ValueError):
            return 0.0
    
    async def _handle_general_question(self, message: str) -> Dict[str, Any]:
        """S-4 대화형 투자비서 고도화: 일반 질문에도 계좌 기반 조언을 제공한다."""
        try:
            message_lower = message.lower()
            focus = "균형 점검"
            if any(k in message_lower for k in ["리스크", "위험", "손실", "드로우다운"]):
                focus = "리스크 관리"
            elif any(k in message_lower for k in ["전략", "설정", "최적화", "개선"]):
                focus = "전략 조정"
            elif any(k in message_lower for k in ["수익", "성과", "복기", "수익률"]):
                focus = "성과 개선"

            trades = self._collect_trade_history(limit=120)
            portfolio = self._build_portfolio_diagnosis()

            if trades:
                metrics = self._build_health_metrics(trades)
                total_fees = sum(self._extract_trade_fee(t) for t in trades)
                fee_impact = (total_fees / abs(metrics["net_pnl"]) * 100.0) if abs(metrics["net_pnl"]) > 0 else 0.0

                brief_lines: List[str] = [
                    "💬 AI 투자비서 브리핑",
                    "",
                    f"• 현재 포커스: {focus}",
                    f"• 건강도: {metrics['health_score']}/100 ({metrics['health_grade']})",
                    f"• 승률/손익: {metrics['win_rate']:.1f}% / {metrics['net_pnl']:+.2f}",
                    f"• 포트폴리오: {portfolio['summary']} (현금 {portfolio['cash_ratio']:.1f}%)",
                    f"• 비용 영향: 누적Fee {total_fees:.2f}, Fee/PnL {fee_impact:.2f}%",
                    "",
                    "🎯 다음 액션 제안",
                ]

                if focus == "리스크 관리":
                    brief_lines.append("• 포지션 노출 상한과 손절 규칙을 우선 재점검하세요.")
                elif focus == "전략 조정":
                    brief_lines.append("• 최근 승률/손익 기준으로 전략 프리셋을 재선택해보세요.")
                elif focus == "성과 개선":
                    brief_lines.append("• 손익비가 낮은 구간을 복기하고 진입 필터를 강화하세요.")
                else:
                    brief_lines.append("• 일일 리포트와 성과 검토를 순서대로 확인하세요.")

                return {
                    "text": "\n".join(brief_lines),
                    "suggested_actions": [
                        "일일 리포트",
                        "성과 검토",
                        "리스크 관리",
                        "전략 변경하기",
                        "시장 분석 요청",
                    ],
                    "action": {
                        "type": "investment_assistant",
                        "focus": focus,
                        "metrics": metrics,
                        "portfolio_diagnosis": portfolio,
                    },
                }

            # 거래 데이터가 없더라도 동작 가이드를 제공
            return {
                "text": (
                    "💬 AI 투자비서 브리핑\n\n"
                    "현재는 거래 데이터가 부족해 정량 브리핑을 계산할 수 없습니다.\n"
                    "먼저 1~3건 이상 거래 이력을 만든 뒤 성과 검토/일일 리포트를 실행하면"
                    " 계좌 기반 조언을 자동으로 제공합니다."
                ),
                "suggested_actions": [
                    "시장 분석 요청",
                    "일일 리포트",
                    "성과 검토",
                    "전략 변경하기",
                ],
                "action": {
                    "type": "investment_assistant",
                    "focus": focus,
                },
            }
        except Exception as e:
            self.logger.error(f"투자비서 응답 처리 오류: {e}")
            return {
                "text": "투자비서 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "suggested_actions": ["시장 분석 요청", "성과 검토"],
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
