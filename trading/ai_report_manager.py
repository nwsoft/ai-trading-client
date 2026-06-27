#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 리포트 매니저
실시간 시장 분석 및 거래 기회 리포트 생성
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from api.kpi_client import emit_kpi_event


@dataclass
class AIMarketReport:
    """AI 시장 분석 리포트"""
    timestamp: datetime
    market_level: str  # LOW, NORMAL, HIGH
    market_score: float
    total_candidates: int
    selected_coins: List[str]
    signal_scores: Dict[str, float]  # 코인별 AI 신호 점수
    trading_opportunities: int  # 거래 기회 개수
    recommendations: List[str]  # AI 추천사항
    risk_assessment: str  # 위험도 평가
    suggested_action: str  # 제안 액션


class AIReportManager:
    """AI 리포트 매니저 - 실시간 분석 및 추천"""
    
    def __init__(self, report_interval: int = 300):  # 5분 간격
        self.logger = logging.getLogger(__name__)
        self.report_interval = report_interval  # 초 단위
        self.last_report_time = datetime.now()
        self.reports_history = []
        self.max_history = 100  # 최대 100개 리포트 저장
        
        # AI 점수 기준 설정
        self.signal_score_thresholds = {
            'conservative': 70,   # 보수적 (기본값)
            'balanced': 60,       # 균형
            'aggressive': 50      # 적극적
        }
        
        # 현재 설정된 모드
        self.current_mode = 'conservative'
        
    def should_generate_report(self) -> bool:
        """리포트 생성 시간인지 확인"""
        return (datetime.now() - self.last_report_time).seconds >= self.report_interval
    
    def generate_market_report(self, market_analysis: Dict, selected_coins: List[Dict], 
                             signal_scores: Dict[str, float]) -> AIMarketReport:
        """AI 시장 분석 리포트 생성"""
        try:
            current_time = datetime.now()
            market_level = market_analysis.get('level', 'NORMAL')
            market_score = market_analysis.get('score', 50.0)
            
            # 거래 기회 분석
            current_threshold = self.signal_score_thresholds[self.current_mode]
            trading_opportunities = sum(1 for score in signal_scores.values() if score >= current_threshold)
            
            # AI 추천사항 생성
            recommendations = self._generate_recommendations(
                market_level, market_score, selected_coins, signal_scores, trading_opportunities
            )
            
            # 위험도 평가
            risk_assessment = self._assess_risk(market_level, market_score, trading_opportunities)
            
            # 제안 액션
            suggested_action = self._suggest_action(
                market_level, trading_opportunities, signal_scores
            )
            
            report = AIMarketReport(
                timestamp=current_time,
                market_level=market_level,
                market_score=market_score,
                total_candidates=len(selected_coins),
                selected_coins=[coin.get('symbol', '') if isinstance(coin, dict) else coin for coin in selected_coins],
                signal_scores=signal_scores,
                trading_opportunities=trading_opportunities,
                recommendations=recommendations,
                risk_assessment=risk_assessment,
                suggested_action=suggested_action
            )
            
            # 리포트 히스토리에 추가
            self._add_to_history(report)
            self.last_report_time = current_time

            emit_kpi_event(
                event_type="ai_market_report_generated",
                category="report",
                asset_class="crypto",
                status="success",
                source="noahai_client_report",
                metric_value=float(trading_opportunities),
                metadata={
                    "market_level": market_level,
                    "market_score": market_score,
                    "total_candidates": len(selected_coins),
                    "mode": self.current_mode,
                },
            )
            
            self.logger.info(f"📊 AI 시장 리포트 생성 완료: {market_level} 시장, {trading_opportunities}개 거래 기회")
            
            return report
            
        except Exception as e:
            self.logger.error(f"AI 리포트 생성 오류: {e}")
            emit_kpi_event(
                event_type="ai_market_report_failed",
                category="report",
                asset_class="crypto",
                status="failed",
                source="noahai_client_report",
                metadata={"error": str(e)},
            )
            return self._create_error_report()
    
    def _generate_recommendations(self, market_level: str, market_score: float, 
                                selected_coins: List, signal_scores: Dict, 
                                trading_opportunities: int) -> List[str]:
        """AI 추천사항 생성"""
        recommendations = []
        
        # 시장 상황별 추천
        if market_level == 'LOW':
            if market_score < 20:
                recommendations.append("🔻 극도로 낮은 시장 활동도 - 대기 권장")
                recommendations.append("📈 변동성 증가 시 거래 기회 모니터링")
            else:
                recommendations.append("⏳ 낮은 시장 활동도 - 신중한 접근 필요")
                
        elif market_level == 'NORMAL':
            recommendations.append("✅ 보통 시장 활동도 - 선별적 거래 가능")
            if trading_opportunities > 0:
                recommendations.append(f"🎯 {trading_opportunities}개 거래 기회 감지됨")
                
        else:  # HIGH
            recommendations.append("🚀 높은 시장 활동도 - 적극적 거래 고려")
            recommendations.append("⚠️ 높은 변동성 주의 필요")
        
        # 거래 기회별 추천
        if trading_opportunities == 0:
            if self.current_mode == 'conservative':
                recommendations.append("💡 더 적극적인 설정 고려 가능 (균형 모드)")
            recommendations.append("🔍 기술적 신호 개선 대기 중")
        elif trading_opportunities >= 3:
            recommendations.append("🎉 다수 거래 기회 - 리스크 분산 권장")
        
        # 신호 점수 기반 추천
        max_score = max(signal_scores.values()) if signal_scores else 0
        if max_score > 0:
            if max_score < 30:
                recommendations.append("📊 약한 신호 강도 - 추가 확인 필요")
            elif max_score >= 50:
                recommendations.append("💪 강한 신호 감지 - 거래 고려")
        
        return recommendations
    
    def _assess_risk(self, market_level: str, market_score: float, 
                    trading_opportunities: int) -> str:
        """위험도 평가"""
        risk_factors = []
        
        # 시장 위험도
        if market_level == 'LOW' and market_score < 20:
            risk_factors.append("매우 낮은 시장 활동도")
        elif market_level == 'HIGH' and market_score > 80:
            risk_factors.append("높은 변동성")
        
        # 거래 기회 위험도
        if trading_opportunities == 0:
            risk_factors.append("거래 기회 부족")
        elif trading_opportunities > 5:
            risk_factors.append("과도한 거래 기회 (선별 필요)")
        
        if not risk_factors:
            return "🟢 낮은 위험도 - 안정적 시장 환경"
        elif len(risk_factors) == 1:
            return f"🟡 보통 위험도 - {risk_factors[0]}"
        else:
            return f"🔴 높은 위험도 - {', '.join(risk_factors)}"
    
    def _suggest_action(self, market_level: str, trading_opportunities: int, 
                       signal_scores: Dict) -> str:
        """제안 액션"""
        if trading_opportunities == 0:
            if market_level == 'LOW':
                return "⏳ 대기 - 시장 활성화 모니터링"
            else:
                return "🔧 설정 조정 고려 - 더 적극적인 모드 검토"
        
        elif trading_opportunities <= 2:
            return "✅ 현재 설정 유지 - 선별적 거래"
        
        elif trading_opportunities <= 5:
            return "🎯 우수한 거래 환경 - 적극적 거래 고려"
        
        else:
            return "⚠️ 과도한 신호 - 보수적 접근 권장"
    
    def _add_to_history(self, report: AIMarketReport):
        """리포트를 히스토리에 추가"""
        self.reports_history.append(asdict(report))
        
        # 최대 개수 제한
        if len(self.reports_history) > self.max_history:
            self.reports_history = self.reports_history[-self.max_history:]
    
    def _create_error_report(self) -> AIMarketReport:
        """오류 시 기본 리포트 생성"""
        return AIMarketReport(
            timestamp=datetime.now(),
            market_level='UNKNOWN',
            market_score=0.0,
            total_candidates=0,
            selected_coins=[],
            signal_scores={},
            trading_opportunities=0,
            recommendations=["❌ 리포트 생성 오류 발생"],
            risk_assessment="🔴 분석 불가",
            suggested_action="🔧 시스템 점검 필요"
        )
    
    def set_trading_mode(self, mode: str):
        """거래 모드 변경"""
        if mode in self.signal_score_thresholds:
            self.current_mode = mode
            self.logger.info(f"거래 모드 변경: {mode} (임계값: {self.signal_score_thresholds[mode]})")
        else:
            self.logger.error(f"잘못된 거래 모드: {mode}")
    
    def get_current_threshold(self) -> int:
        """현재 신호 점수 임계값 반환"""
        return self.signal_score_thresholds[self.current_mode]
    
    def get_recent_reports(self, count: int = 10) -> List[Dict]:
        """최근 리포트 조회"""
        return self.reports_history[-count:] if self.reports_history else []
    
    def get_trading_summary(self) -> Dict:
        """거래 요약 정보"""
        if not self.reports_history:
            return {}
        
        recent_reports = self.reports_history[-10:]  # 최근 10개
        
        total_opportunities = sum(r.get('trading_opportunities', 0) for r in recent_reports)
        avg_market_score = sum(r.get('market_score', 0) for r in recent_reports) / len(recent_reports)
        
        market_levels = [r.get('market_level', 'NORMAL') for r in recent_reports]
        most_common_level = max(set(market_levels), key=market_levels.count)
        
        return {
            'total_opportunities_recent': total_opportunities,
            'avg_market_score': avg_market_score,
            'most_common_market_level': most_common_level,
            'current_mode': self.current_mode,
            'current_threshold': self.get_current_threshold(),
            'report_count': len(self.reports_history)
        }
