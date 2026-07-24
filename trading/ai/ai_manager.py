#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 매니저: 손절/익절 분석, 패턴 유사성 검증, 진입 전 검증, 최적화 적용 요청
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import logging
import math
import os

from .openai_client import OpenAIClient


class AIManager:
    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None, settings: Optional[Dict[str, Any]] = None):
        self.api_key = api_key
        # 🔥 설정 파일에서 모델을 받아오므로 하드코딩 제거
        self.model = model or "gpt-4o-mini"  # 기본값은 fallback용
        self.client = OpenAIClient(api_key=api_key, model=self.model, base_url=base_url)
        # 역할별 모델 배치를 위한 settings 저장
        self._settings: Dict[str, Any] = settings or {}
        # 로거 초기화
        self.logger = logging.getLogger(__name__)
        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='global', level=level)
        
        # 🔥 모델 정보 로깅 추가
        self.log_event('analysis', f'AI Manager 초기화 완료 - 모델: {self.model}')

    def _get_model_for_role(self, role: str) -> str:
        """역할(task type)에 맞는 모델 반환 - ai_model_roles 설정 기반 비용 최적화

        Tier 구분:
          frequent_cheap  → 빈번 호출(신호분석·패턴·포지션 크기): 기본 gpt-4o-mini
          standard        → 중요 분석(손익 분석·일일 리포트): 기본 gpt-4o
          premium         → 정밀 분석(진단·파라미터 최적화): 기본 gpt-4o
        """
        _role_to_tier: Dict[str, str] = {
            'signal_analysis': 'frequent_cheap',
            'pattern_similarity': 'frequent_cheap',
            'pre_entry': 'frequent_cheap',
            'position_sizing': 'frequent_cheap',
            'loss_analysis': 'standard',
            'profit_analysis': 'standard',
            'daily_report': 'standard',
            'diagnosis': 'premium',
            'parameter_optimization': 'premium',
        }
        tier = _role_to_tier.get(role, 'standard')
        roles_cfg = self._settings.get('ai_model_roles', {})
        return roles_cfg.get(tier) or self.model

    def enabled(self) -> bool:
        """AI 기능 활성화 여부"""
        return bool(self.api_key) and self.client.is_ready()

    def analyze_market_conditions(self, symbol: str, market_data: List, indicators: Dict) -> Dict[str, Any]:
        """시장 상황 분석 및 동적 설정 제안"""
        try:
            if not self.enabled():
                return self._get_default_analysis()

            def _read(value: Any, key: str, default: float = 0.0) -> float:
                try:
                    raw = value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)
                    return float(raw)
                except Exception:
                    return float(default)

            closes = [_read(row, "close") for row in (market_data or [])[-30:]]
            closes = [value for value in closes if value > 0]
            returns = [
                (closes[index] / closes[index - 1]) - 1.0
                for index in range(1, len(closes))
                if closes[index - 1] > 0
            ]
            if len(returns) > 1:
                mean_return = sum(returns) / len(returns)
                volatility = math.sqrt(
                    sum((value - mean_return) ** 2 for value in returns) / len(returns)
                )
            else:
                volatility = 0.0
            volume_ratio = _read(indicators, "volume_ratio", 0.0)
            
            system = "You are an expert cryptocurrency trading analyst. Analyze market conditions and provide optimal trading parameters."
            
            prompt = f"""
Symbol: {symbol}

Market Data Analysis:
- Current Price: {closes[-1] if closes else 0}
- RSI: {_read(indicators, 'rsi', 0)}
- MACD: {_read(indicators, 'macd', 0)}
- Realized Volatility (fraction): {volatility}
- Volume Ratio vs moving average: {volume_ratio}

Provide JSON response:
{{
  "entry_confidence": 0.0-1.0,
  "optimal_entry_price": float,
  "tp_percent": 0.0005-0.05,
  "sl_percent": 0.0005-0.03,
  "leverage": 1-10,
  "signal": "LONG/SHORT/HOLD",
  "reason": "string",
  "market_volatility": "LOW/NORMAL/HIGH",
  "trend_strength": "WEAK/MEDIUM/STRONG"
}}
tp_percent and sl_percent MUST be fractions: 0.001 means 0.1%, not 1%.
"""
            
            use_model = self._get_model_for_role('signal_analysis')
            result = self.client.chat_json(system, prompt, temperature=0.3, max_tokens=320,
                                             model=use_model)
            if isinstance(result, dict):
                result["entry_confidence"] = max(
                    0.0, min(float(result.get("entry_confidence", result.get("confidence", 0.5)) or 0.5), 1.0)
                )
                for key, maximum in (("tp_percent", 0.05), ("sl_percent", 0.03)):
                    value = float(result.get(key, self._get_default_analysis()[key]) or 0.0)
                    if value > maximum:
                        value /= 100.0
                    result[key] = max(0.0005, min(value, maximum))
                result["leverage"] = max(1, min(int(float(result.get("leverage", 1) or 1)), 10))
                result["_ai_model"] = use_model
                result["_ai_usage"] = self.client.get_last_usage()
            return result if result else self._get_default_analysis()
            
        except Exception as e:
            self.logger.error(f"시장 상황 분석 오류: {e}")
            return self._get_default_analysis()

    def analyze_loss_trade(self, symbol: str, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """손절 거래 분석"""
        try:
            if not self.enabled():
                return None
                
            system = "You are an expert cryptocurrency trading analyst. Analyze loss patterns and provide specific recommendations for future trades."
            prompt = self._compose_loss_prompt(symbol, trade_data)
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=800,
                                             model=self._get_model_for_role('loss_analysis'))
            if result:
                self.logger.info(f"{symbol} 손절 분석 완료: {result.get('loss_cause', 'Unknown')}")
            return result
            
        except Exception as e:
            self.logger.error(f"손절 분석 오류: {e}")
            return None

    def analyze_profit_trade(self, symbol: str, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """익절 거래 분석"""
        try:
            if not self.enabled():
                return None
                
            system = "You are an expert cryptocurrency trading analyst. Analyze profit patterns and provide specific recommendations for future trades."
            prompt = self._compose_profit_prompt(symbol, trade_data)
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=800,
                                             model=self._get_model_for_role('profit_analysis'))
            if result:
                self.logger.info(f"{symbol} 익절 분석 완료: {result.get('profit_cause', 'Unknown')}")
            return result
            
        except Exception as e:
            self.logger.error(f"익절 분석 오류: {e}")
            return None

    def analyze_pattern_similarity(self, symbol: str, current_signal_data: Dict[str, Any], recent_patterns: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """패턴 유사성 분석 (진입 전 검증)"""
        try:
            if not self.enabled() or not recent_patterns:
                return None
                
            system = "You are an expert cryptocurrency trading pattern analyzer. Compare current signals with past patterns and make trading decisions."
            prompt = self._compose_similarity_prompt(symbol, current_signal_data, recent_patterns)
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=600,
                                             model=self._get_model_for_role('pattern_similarity'))
            if result:
                action = result.get('action', 'PROCEED')
                self.logger.info(f"{symbol} 패턴 분석: {action} - {result.get('reason', '')}")
            return result
            
        except Exception as e:
            self.logger.error(f"패턴 유사성 분석 오류: {e}")
            return None

    def generate_daily_report(self, days: int = 1) -> Dict[str, Any]:
        """일일/주간/월간 리포트 생성"""
        try:
            if not self.enabled():
                return {"error": "AI 기능이 비활성화되어 있습니다."}
            
            system = "You are an expert cryptocurrency trading analyst. Generate comprehensive trading reports with actionable insights."
            
            # 거래 데이터 수집
            trade_data = self._collect_trade_data(days)
            performance_data = self._analyze_performance(days)
            market_data = self._collect_market_data(days)
            
            prompt = f"""
Generate a comprehensive {days}-day trading report based on the following data:

TRADING PERFORMANCE:
{json.dumps(performance_data, ensure_ascii=False, indent=2)}

TRADE HISTORY:
{json.dumps(trade_data, ensure_ascii=False, indent=2)}

MARKET CONDITIONS:
{json.dumps(market_data, ensure_ascii=False, indent=2)}

Provide a detailed report in JSON format:
{{
  "summary": {{
    "period": "{days}일",
    "total_trades": number,
    "win_rate": "percentage",
    "total_pnl": "amount",
    "best_performing_coin": "coin_name",
    "worst_performing_coin": "coin_name"
  }},
  "performance_analysis": {{
    "strengths": ["list of strengths"],
    "weaknesses": ["list of weaknesses"],
    "opportunities": ["list of opportunities"],
    "threats": ["list of threats"]
  }},
  "ai_learning_progress": {{
    "patterns_learned": number,
    "accuracy_improvement": "percentage",
    "key_insights": ["list of key insights"]
  }},
  "recommendations": {{
    "immediate_actions": ["list of immediate actions"],
    "parameter_adjustments": {{
      "tp_percent": "increase/decrease/keep",
      "sl_percent": "increase/decrease/keep",
      "leverage": "increase/decrease/keep",
      "signal_threshold": "increase/decrease/keep"
    }},
    "coin_selection": {{
      "add_coins": ["list of coins to add"],
      "remove_coins": ["list of coins to remove"],
      "reason": "explanation"
    }}
  }},
  "risk_assessment": {{
    "current_risk_level": "LOW/MEDIUM/HIGH",
    "risk_factors": ["list of risk factors"],
    "mitigation_strategies": ["list of strategies"]
  }},
  "next_period_forecast": {{
    "expected_performance": "description",
    "market_outlook": "description",
    "confidence_level": "HIGH/MEDIUM/LOW"
  }}
}}
"""
            
            result = self.client.chat_json(system, prompt, temperature=0.3, max_tokens=1500,
                                             model=self._get_model_for_role('daily_report'))
            if result:
                self.logger.info(f"{days}일 리포트 생성 완료")
            return result if result else {"error": "리포트 생성 실패"}
            
        except Exception as e:
            self.logger.error(f"리포트 생성 오류: {e}")
            return {"error": f"리포트 생성 오류: {str(e)}"}

    def diagnose_trading_issues(self, hours_without_trades: int = 1) -> Dict[str, Any]:
        """거래 부재 문제 진단"""
        try:
            if not self.enabled():
                return {"error": "AI 기능이 비활성화되어 있습니다."}
            
            system = "You are an expert cryptocurrency trading system diagnostician. Analyze why no trades are occurring and provide solutions."
            
            # 시스템 상태 데이터 수집
            system_data = self._collect_system_status()
            market_conditions = self._collect_current_market_conditions()
            recent_signals = self._collect_recent_signals()
            
            prompt = f"""
Diagnose why no trades have occurred in the last {hours_without_trades} hours:

SYSTEM STATUS:
{json.dumps(system_data, ensure_ascii=False, indent=2)}

CURRENT MARKET CONDITIONS:
{json.dumps(market_conditions, ensure_ascii=False, indent=2)}

RECENT SIGNALS:
{json.dumps(recent_signals, ensure_ascii=False, indent=2)}

Provide diagnosis and solutions in JSON format:
{{
  "diagnosis": {{
    "primary_issue": "main reason for no trades",
    "secondary_issues": ["list of secondary issues"],
    "severity": "LOW/MEDIUM/HIGH/CRITICAL"
  }},
  "root_causes": {{
    "signal_generation": {{
      "issue": "description of signal generation problem",
      "current_settings": "current parameter values",
      "recommended_changes": "specific parameter adjustments"
    }},
    "coin_selection": {{
      "issue": "description of coin selection problem",
      "current_coins": ["list of current coins"],
      "recommended_coins": ["list of recommended coins"]
    }},
    "market_conditions": {{
      "issue": "description of market condition problem",
      "current_market_state": "description",
      "adaptation_needed": "required adaptations"
    }},
    "risk_management": {{
      "issue": "description of risk management problem",
      "current_risk_settings": "current settings",
      "recommended_adjustments": "specific adjustments"
    }}
  }},
  "solutions": {{
    "immediate_fixes": ["list of immediate fixes"],
    "parameter_adjustments": {{
      "signal_confidence_threshold": "new_value",
      "volatility_threshold": "new_value",
      "rsi_oversold_threshold": "new_value",
      "rsi_overbought_threshold": "new_value",
      "trend_strength_threshold": "new_value",
      "volume_threshold": "new_value"
    }},
    "coin_list_updates": {{
      "add": ["coins to add"],
      "remove": ["coins to remove"],
      "prioritize": ["coins to prioritize"]
    }},
    "market_adaptation": {{
      "strategy_adjustments": ["list of strategy changes"],
      "timeframe_adjustments": ["list of timeframe changes"]
    }}
  }},
  "implementation_plan": {{
    "steps": ["ordered list of implementation steps"],
    "expected_outcome": "description of expected results",
    "monitoring_metrics": ["list of metrics to monitor"]
  }},
  "confidence": "HIGH/MEDIUM/LOW"
}}
"""
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=1200,
                                             model=self._get_model_for_role('diagnosis'))
            if result:
                self.logger.info(f"거래 부재 문제 진단 완료: {result.get('diagnosis', {}).get('primary_issue', 'Unknown')}")
            return result if result else {"error": "진단 실패"}
            
        except Exception as e:
            self.logger.error(f"문제 진단 오류: {e}")
            return {"error": f"진단 오류: {str(e)}"}

    def auto_optimize_parameters(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """진단 결과를 바탕으로 자동 파라미터 최적화"""
        try:
            if not self.enabled():
                return {"error": "AI 기능이 비활성화되어 있습니다."}
            
            system = "You are an expert trading system optimizer. Apply the diagnosis results to optimize trading parameters."
            
            prompt = f"""
Based on the following diagnosis, provide specific parameter optimizations:

DIAGNOSIS:
{json.dumps(diagnosis, ensure_ascii=False, indent=2)}

Provide optimized parameters in JSON format:
{{
  "optimized_parameters": {{
    "signal_generation": {{
      "confidence_threshold": "new_value (0.0-1.0)",
      "rsi_oversold": "new_value (0-50)",
      "rsi_overbought": "new_value (50-100)",
      "volatility_min": "new_value (0.0-1.0)",
      "trend_strength_min": "new_value (0.0-1.0)",
      "volume_ratio_min": "new_value (0.0-1.0)"
    }},
    "risk_management": {{
      "default_tp": "new_value (0.1-1.0)",
      "default_sl": "new_value (0.1-1.0)",
      "max_leverage": "new_value (1-10)",
      "position_size_percent": "new_value (1-100)"
    }},
    "coin_selection": {{
      "max_coins": "new_value (1-10)",
      "min_market_cap": "new_value",
      "min_volume": "new_value",
      "exclude_coins": ["list of coins to exclude"]
    }},
    "market_adaptation": {{
      "update_frequency": "new_value (seconds)",
      "market_regime_threshold": "new_value",
      "volatility_adjustment": "new_value"
    }}
  }},
  "implementation_priority": {{
    "high_priority": ["list of high priority changes"],
    "medium_priority": ["list of medium priority changes"],
    "low_priority": ["list of low priority changes"]
  }},
  "expected_improvements": {{
    "trade_frequency": "expected change",
    "win_rate": "expected change",
    "risk_reduction": "expected change",
    "profitability": "expected change"
  }},
  "rollback_plan": {{
    "trigger_conditions": ["conditions to rollback"],
    "original_parameters": "original parameter values",
    "rollback_steps": ["steps to rollback"]
  }}
}}
"""
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=1000,
                                             model=self._get_model_for_role('parameter_optimization'))
            if result:
                self.logger.info("파라미터 최적화 완료")
            return result if result else {"error": "최적화 실패"}
            
        except Exception as e:
            self.logger.error(f"파라미터 최적화 오류: {e}")
            return {"error": f"최적화 오류: {str(e)}"}

    def _get_default_analysis(self) -> Dict[str, Any]:
        """기본 분석 결과"""
        return {
            "entry_confidence": 0.5,
            "optimal_entry_price": 0,
            "tp_percent": 0.0018,
            "sl_percent": 0.0020,
            "leverage": 1,
            "signal": "HOLD",
            "reason": "기본 설정",
            "market_volatility": "NORMAL",
            "trend_strength": "MEDIUM"
        }

    def _compose_loss_prompt(self, symbol: str, trade: Dict[str, Any]) -> str:
        """손절 분석 프롬프트"""
        return f"""
Coin: {symbol}

Losing Trade Analysis:
- Entry Price: {trade.get('entry_price', 0)}
- Exit Price: {trade.get('exit_price', 0)}
- Loss: {trade.get('realized_pnl', 0)} USDT
- Signal Type: {trade.get('signal_type', 'UNKNOWN')}
- Signal Reason: {trade.get('signal_reason', 'UNKNOWN')}
- 15m RSI: {trade.get('rsi_15m', 0)}
- 1h RSI: {trade.get('rsi_1h', 0)}
- Market Trend: {trade.get('market_trend', 'UNKNOWN')}
- Volatility: {trade.get('volatility', 0)}
- TP Setting: {trade.get('tp_setting', 0)}
- SL Setting: {trade.get('sl_setting', 0)}
- Monitoring Points: {trade.get('monitoring_points', 0)}
- Price Movement Pattern: {trade.get('price_movement_pattern', 'UNKNOWN')}

Analyze the loss and provide recommendations. Respond in JSON:
{{
  "loss_cause": "detailed explanation of why the trade failed",
  "loss_pattern": "QUICK_LOSS/STEADY_LOSS/VOLATILE_LOSS/SIGNAL_FAILURE/MARKET_REVERSAL",
  "volatility_issue": "LOW_VOLATILITY/HIGH_VOLATILITY/NORMAL",
  "signal_accuracy": "CORRECT/INCORRECT/UNCLEAR",
  "tp_sl_issue": "YES/NO",
  "timing_issue": "EARLY_EXIT/LATE_EXIT/OPTIMAL",
  "recommended_action": "ADJUST_TP_SL/REVERSE_SIGNAL/SKIP_TRADE/NO_CHANGE",
  "specific_adjustments": {{
    "profit_target_adjustment": "INCREASE/DECREASE/KEEP",
    "loss_limit_adjustment": "INCREASE/DECREASE/KEEP",
    "leverage_adjustment": "INCREASE/DECREASE/KEEP",
    "position_size_adjustment": "INCREASE/DECREASE/KEEP"
  }},
  "confidence": "HIGH/MEDIUM/LOW",
  "learning_points": ["key lessons learned from this loss"]
}}
"""

    def _compose_profit_prompt(self, symbol: str, trade: Dict[str, Any]) -> str:
        """익절 분석 프롬프트"""
        profit_rate = 0.0
        try:
            ep = float(trade.get('entry_price', 0) or 0)
            xp = float(trade.get('exit_price', 0) or 0)
            if ep > 0:
                profit_rate = (xp - ep) / ep * 100
        except Exception:
            profit_rate = 0.0
            
        return f"""
Coin: {symbol}

Profit Trade Analysis:
- Entry Price: {trade.get('entry_price', 0)}
- Exit Price: {trade.get('exit_price', 0)}
- Profit: {trade.get('realized_pnl', 0)} USDT
- Profit Rate: {profit_rate:.4f}%
- Signal Type: {trade.get('signal_type', 'UNKNOWN')}
- Signal Reason: {trade.get('signal_reason', 'UNKNOWN')}
- 15m RSI: {trade.get('rsi_15m', 0)}
- 1h RSI: {trade.get('rsi_1h', 0)}
- Market Trend: {trade.get('market_trend', 'UNKNOWN')}
- Volatility: {trade.get('volatility', 0)}
- TP Setting: {trade.get('tp_setting', 0)}
- SL Setting: {trade.get('sl_setting', 0)}
- Monitoring Points: {trade.get('monitoring_points', 0)}
- Price Movement Pattern: {trade.get('price_movement_pattern', 'UNKNOWN')}

Analyze the profit and provide recommendations. Respond in JSON:
{{
  "profit_cause": "detailed explanation of why the trade succeeded",
  "profit_pattern": "QUICK_PROFIT/STEADY_PROFIT/VOLATILE_PROFIT/SIGNAL_SUCCESS/MARKET_MOMENTUM",
  "signal_accuracy": "CORRECT/INCORRECT/UNCLEAR",
  "tp_sl_effectiveness": "OPTIMAL/TOO_TIGHT/TOO_LOOSE",
  "timing_quality": "EXCELLENT/GOOD/AVERAGE/POOR",
  "recommended_action": "REPEAT_PATTERN/ADJUST_PARAMETERS/NO_CHANGE",
  "specific_adjustments": {{
    "profit_target_adjustment": "INCREASE/DECREASE/KEEP",
    "loss_limit_adjustment": "INCREASE/DECREASE/KEEP",
    "leverage_adjustment": "INCREASE/DECREASE/KEEP",
    "position_size_adjustment": "INCREASE/DECREASE/KEEP"
  }},
  "confidence": "HIGH/MEDIUM/LOW",
  "success_factors": ["key factors that led to success"]
}}
"""

    def _compose_similarity_prompt(self, symbol: str, current: Dict[str, Any], patterns: List[Dict[str, Any]]) -> str:
        """패턴 유사성 분석 프롬프트"""
        patterns_summary = []
        for i, pattern in enumerate(patterns[:5]):  # 최근 5개 패턴만
            patterns_summary.append(f"""
Pattern {i+1}:
- Result: {pattern.get('result', 'UNKNOWN')}
- Signal Type: {pattern.get('signal_type', 'UNKNOWN')}
- RSI: {pattern.get('rsi', 0)}
- Volatility: {pattern.get('volatility', 0)}
- Loss Cause: {pattern.get('loss_cause', 'UNKNOWN')}
""")
        
        return f"""
Coin: {symbol}

Current Signal:
- Signal Type: {current.get('signal_type', 'UNKNOWN')}
- Signal Reason: {current.get('signal_reason', 'UNKNOWN')}
- RSI 15m: {current.get('rsi_15m', 0)}
- RSI 1h: {current.get('rsi_1h', 0)}
- Market Trend: {current.get('market_trend', 'UNKNOWN')}
- Volatility: {current.get('volatility', 0)}

Recent Loss Patterns:
{''.join(patterns_summary)}

Compare current signal with recent loss patterns and decide. Respond in JSON:
{{
  "action": "PROCEED/SKIP/ADJUST",
  "reason": "detailed explanation",
  "similarity_score": 0.0-1.0,
  "risk_level": "LOW/MEDIUM/HIGH",
  "recommended_adjustments": {{
    "tp_adjustment": "INCREASE/DECREASE/KEEP",
    "sl_adjustment": "INCREASE/DECREASE/KEEP",
    "leverage_adjustment": "INCREASE/DECREASE/KEEP",
    "position_size_adjustment": "INCREASE/DECREASE/KEEP"
  }},
  "confidence": "HIGH/MEDIUM/LOW"
}}
"""

    def _collect_trade_data(self, days: int) -> Dict[str, Any]:
        """거래 데이터 수집"""
        try:
            from trading.recorder import Recorder
            recorder = Recorder()
            trades = recorder.get_trade_history(days=days) or []

            total_trades = len(trades)
            winning = [t for t in trades if float(t.get('pnl') or 0) > 0]
            losing = [t for t in trades if float(t.get('pnl') or 0) < 0]
            pnls = [float(t.get('pnl') or 0) for t in trades]

            return {
                "total_trades": total_trades,
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "total_pnl": float(sum(pnls)),
                "avg_trade_duration": 0,
                "best_trade": float(max(pnls)) if pnls else 0.0,
                "worst_trade": float(min(pnls)) if pnls else 0.0,
            }
        except Exception as e:
            self.logger.error(f"거래 데이터 수집 오류: {e}")
            return {}

    def _analyze_performance(self, days: int) -> Dict[str, Any]:
        """성과 분석"""
        try:
            from trading.recorder import Recorder
            recorder = Recorder()
            stats = recorder.get_performance_stats(days=days) or {}
            return {
                "win_rate": float(stats.get("win_rate", 0.0)),
                "profit_factor": float(stats.get("profit_factor", 0.0)),
                "max_drawdown": float(stats.get("max_drawdown", 0.0)),
                "sharpe_ratio": float(stats.get("sharpe_ratio", 0.0)),
                "avg_profit_per_trade": float(stats.get("avg_win", 0.0)),
                "avg_loss_per_trade": float(stats.get("avg_loss", 0.0)),
            }
        except Exception as e:
            self.logger.error(f"성과 분석 오류: {e}")
            return {}

    def _collect_market_data(self, days: int) -> Dict[str, Any]:
        """시장 데이터 수집"""
        try:
            return {
                "market_volatility": 0.0,
                "trend_direction": "NEUTRAL",
                "volume_trend": "NEUTRAL",
                "market_regime": "NORMAL"
            }
        except Exception as e:
            self.logger.error(f"시장 데이터 수집 오류: {e}")
            return {}

    def _collect_system_status(self) -> Dict[str, Any]:
        """시스템 상태 수집"""
        try:
            return {
                "is_trading_active": True,
                "active_positions": 0,
                "last_trade_time": "2024-01-01 00:00:00",
                "signal_generation_status": "ACTIVE",
                "coin_selection_status": "ACTIVE"
            }
        except Exception as e:
            self.logger.error(f"시스템 상태 수집 오류: {e}")
            return {}

    def _collect_current_market_conditions(self) -> Dict[str, Any]:
        """현재 시장 상황 수집"""
        try:
            return {
                "overall_volatility": 0.0,
                "market_trend": "NEUTRAL",
                "volume_conditions": "NORMAL",
                "liquidity_conditions": "NORMAL"
            }
        except Exception as e:
            self.logger.error(f"시장 상황 수집 오류: {e}")
            return {}

    def _collect_recent_signals(self, days: int = 1) -> Dict[str, Any]:
        """최근 신호 수집"""
        try:
            from trading.recorder import Recorder
            recorder = Recorder()

            # 최근 AI 의사결정을 신호 프록시로 활용
            decisions = recorder.get_ai_decisions(limit=200) or []
            total_signals = len(decisions)

            feedback_items = [d for d in decisions if (d.get('user_feedback') or '').strip()]
            successful = sum(1 for d in feedback_items if 'good' in str(d.get('user_feedback', '')).lower() or '정확' in str(d.get('user_feedback', '')))
            failed = sum(1 for d in feedback_items if 'bad' in str(d.get('user_feedback', '')).lower() or '부정확' in str(d.get('user_feedback', '')))

            quality = 'UNKNOWN'
            if feedback_items:
                ratio = successful / max(len(feedback_items), 1)
                if ratio >= 0.7:
                    quality = 'GOOD'
                elif ratio >= 0.4:
                    quality = 'NORMAL'
                else:
                    quality = 'POOR'

            return {
                "total_signals": total_signals,
                "successful_signals": successful,
                "failed_signals": failed,
                "signal_quality": quality,
            }
        except Exception as e:
            self.logger.error(f"최근 신호 수집 오류: {e}")
            return {}

    def optimize_position_size(self, ai_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """AI 기반 포지션 크기 최적화 (사용자 성향 조절 가능)"""
        try:
            if not self.enabled():
                return None
            
            # 🔥 사용자 성향 설정 로드 (settings에서)
            user_preference = self._load_user_trading_preference(ai_context.get('settings', {}))
            
            system = """You are an expert cryptocurrency trading risk manager. 
            Analyze the trading context and determine the optimal position size factor.
            Consider user's risk tolerance, available balance, and market conditions.
            
            User Trading Preference: {user_preference}
            
            Provide JSON response with detailed reasoning:
            {{
                "adjusted_position_size_factor": float (0.1-10.0),
                "risk_reasoning": "string explaining the decision",
                "balance_utilization_percent": float (5.0-50.0),
                "risk_level": "CONSERVATIVE/MODERATE/AGGRESSIVE",
                "recommendations": ["string", "string"],
                "max_loss_amount": float,
                "position_size_explanation": "string"
            }}"""
            
            prompt = f"""
Trading Context:
- Symbol: {ai_context.get('symbol', 'UNKNOWN')}
- Available Balance: {ai_context.get('available_balance', 0):.2f} USDT
- Current Price: {ai_context.get('current_price', 0):.4f}
- Signal: {ai_context.get('signal', 'UNKNOWN')}
- Confidence: {ai_context.get('confidence', 0):.2f}
- Base Position Size Factor: {ai_context.get('position_size_factor', 1.0):.2f}
- Min Trade Amount: {ai_context.get('min_trade_amount', 5):.2f} USDT

Market Analysis:
- Signal indicates: {ai_context.get('signal', 'UNKNOWN')} with {ai_context.get('confidence', 0):.1%} confidence
- Price volatility and market conditions should be considered

Risk Management Rules:
1. Never risk more than 50% of available balance
2. Conservative: 5-15% of balance, Moderate: 15-30%, Aggressive: 30-50%
3. Consider signal confidence and market conditions
4. Adjust position size based on user preference
5. NEVER suggest trades below min_trade_amount (5 USDT)
6. Always ensure trade amount >= min_trade_amount

Please provide optimal position sizing with detailed reasoning.
"""
            
            result = self.client.chat_json(system, prompt, temperature=0.2, max_tokens=800,
                                             model=self._get_model_for_role('position_sizing'))
            
            if result:
                self.logger.info(f"AI 포지션 크기 최적화 완료: {result.get('risk_level', 'UNKNOWN')} 접근")
                # 🔥 AI 판단 결과를 사용자 설정에 저장
                self._save_ai_decision(ai_context.get('symbol', 'UNKNOWN'), result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"AI 포지션 크기 최적화 오류: {e}")
            return None
    
    def _load_user_trading_preference(self, settings: Dict[str, Any]) -> str:
        """사용자 거래 성향 설정 로드 (settings.json에서)"""
        try:
            # 🔥 settings.json에서 AI 거래 성향 설정 로드
            ai_prefs = settings.get('ai_trading_preferences', {})
            return ai_prefs.get('risk_tolerance', 'CONSERVATIVE')
        except Exception as e:
            self.logger.warning(f"사용자 거래 성향 로드 실패: {e}")
            return "CONSERVATIVE"
    
    def _save_ai_decision(self, symbol: str, decision: Dict[str, Any]):
        """AI 판단 결과를 데이터베이스에 저장"""
        try:
            # 🔥 AI 판단 결과를 데이터베이스에 저장
            from trading.recorder import Recorder
            recorder = Recorder()
            recorder.save_ai_decision(
                symbol=symbol,
                decision_type="POSITION_SIZE",
                decision_data=decision,
                user_feedback=None
            )
                
            self.logger.info(f"[{symbol}] AI 판단 결과 저장 완료")
            
        except Exception as e:
            self.logger.warning(f"AI 판단 결과 저장 실패: {e}")
    
    def update_user_preference(self, new_preference: Dict[str, Any]):
        """사용자 거래 성향 설정 업데이트"""
        try:
            # 🔥 사용자가 AI 어시스턴트를 통해 거래 성향 조절
            preference_file = "user_trading_preference.json"
            current_preference = {}
            
            if os.path.exists(preference_file):
                with open(preference_file, 'r', encoding='utf-8') as f:
                    current_preference = json.load(f)
            
            current_preference.update(new_preference)
            
            with open(preference_file, 'w', encoding='utf-8') as f:
                json.dump(current_preference, f, indent=2, ensure_ascii=False)
                
            self.logger.info(f"사용자 거래 성향 설정 업데이트: {new_preference}")
            
        except Exception as e:
            self.logger.error(f"사용자 거래 성향 설정 업데이트 실패: {e}")

    def chat_completion(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs) -> str:
        """AI 채팅 완성 - 대시보드 AI 채팅 기능용"""
        try:
            # 🔥 상세한 디버그 로그 추가 (빌드 환경 문제 진단용)
            if not self.enabled():
                error_msg = "AI 기능이 비활성화되어 있습니다. API 키를 확인해주세요."
                self.logger.warning(f"{error_msg} (api_key 존재: {bool(self.api_key)}, client ready: {self.client.is_ready() if self.client else False})")
                return error_msg
            
            # 사용할 모델 결정
            use_model = model or self.model
            self.logger.debug(f"AI 채팅 요청: 모델={use_model}, 메시지 수={len(messages)}")
            
            # 시스템 메시지와 사용자 메시지 분리
            system_message = ""
            user_messages = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                elif msg.get("role") == "user":
                    user_messages.append(msg.get("content", ""))
            
            # 사용자 메시지 결합
            user_message = "\n".join(user_messages) if user_messages else ""
            
            if not user_message:
                self.logger.warning("AI 채팅 요청 실패: 사용자 메시지가 없습니다.")
                return "사용자 메시지가 없습니다."
            
            # OpenAI API 호출 (지정된 모델 사용)
            self.logger.debug(f"OpenAI API 호출 시작: 모델={use_model}, 시스템 메시지 길이={len(system_message)}, 사용자 메시지 길이={len(user_message)}")
            response = self.client.chat(system_message, user_message, model=use_model, **kwargs)
            
            if response:
                self.logger.info(f"AI 채팅 응답 생성 완료 (모델: {use_model}, 응답 길이: {len(response)})")
                return response
            else:
                error_msg = "AI 응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
                detailed_error = f"{error_msg} (모델: {use_model}, API 키 존재: {bool(self.api_key)}, API 키 길이: {len(self.api_key) if self.api_key else 0}, 클라이언트 준비: {self.client.is_ready() if self.client else False})"
                self.logger.error(detailed_error)
                # 빌드 환경에서도 확인 가능하도록 print도 출력
                if os.getenv('NOAHAI_DEBUG_AI') == '1':
                    print(f"[ERROR] {detailed_error}")
                return error_msg
                
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.logger.error(f"AI 채팅 완성 오류: {e}")
            self.logger.error(f"상세 오류 정보:\n{error_detail}")
            return f"AI 응답 생성 중 오류가 발생했습니다: {str(e)}"
