#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장 심리·거래량 지표 분석기
현재 사용 중인 python-binance 기반으로 시장 심리 데이터를 수집하고 분석
"""

import logging
import numpy as np
import pandas as pd
import requests
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class SentimentLevel(Enum):
    """시장 심리 수준"""
    EXTREME_FEAR = "극도의 공포"
    FEAR = "공포"
    NEUTRAL = "중립"
    GREED = "탐욕"
    EXTREME_GREED = "극도의 탐욕"


@dataclass
class VolumeAnalysis:
    """거래량 분석 결과"""
    current_volume: float
    avg_volume_24h: float
    volume_ratio: float
    volume_trend: str  # "증가", "감소", "안정"
    volume_spike: bool  # 급등 여부
    

@dataclass
class FundingRateData:
    """펀딩비 데이터"""
    symbol: str
    current_rate: float
    avg_rate_7d: float
    next_funding_time: datetime
    rate_trend: str  # "상승", "하락", "안정"


@dataclass
class OpenInterestData:
    """미체결약정 데이터"""
    symbol: str
    current_oi: float
    oi_change_24h: float
    oi_change_percent: float
    oi_trend: str


@dataclass
class LongShortRatio:
    """롱/숏 비율 데이터"""
    symbol: str
    long_ratio: float
    short_ratio: float
    account_ratio: float  # 계정별 롱/숏 비율
    top_trader_ratio: float  # 상위 트레이더 롱/숏 비율
    

@dataclass
class MarketSentimentData:
    """종합 시장 심리 데이터"""
    symbol: str
    timestamp: datetime
    sentiment_score: float  # -100 ~ 100
    sentiment_level: SentimentLevel
    volume_analysis: VolumeAnalysis
    funding_rate: FundingRateData
    open_interest: Optional[OpenInterestData]
    long_short_ratio: Optional[LongShortRatio]
    fear_greed_index: Optional[float]


class MarketSentimentAnalyzer:
    """시장 심리·거래량 지표 분석기 (python-binance 기반)"""
    
    def __init__(self, binance_client, logger: Optional[logging.Logger] = None):
        self.binance_client = binance_client  # python-binance Client 객체
        self.logger = logger or logging.getLogger(__name__)
        self.sentiment_cache = {}
        self.cache_duration = 300  # 5분 캐시
        
    def analyze_market_sentiment(self, symbol: str, exchange_name: str = 'binance') -> MarketSentimentData:
        """종합 시장 심리 분석"""
        try:
            # 캐시 확인
            cache_key = f"{exchange_name}_{symbol}"
            if self._is_cache_valid(cache_key):
                return self.sentiment_cache[cache_key]['data']
            
            # 1. 거래량 분석
            volume_analysis = self.analyze_volume_patterns(symbol, exchange_name)
            
            # 2. 펀딩비 분석
            funding_rate = self.get_funding_rate_analysis(symbol, exchange_name)
            
            # 3. 미체결약정 분석 (선물만)
            open_interest = self.get_open_interest_analysis(symbol, exchange_name)
            
            # 4. 롱/숏 비율 분석
            long_short_ratio = self.get_long_short_ratio(symbol, exchange_name)
            
            # 5. 종합 심리 점수 계산
            sentiment_score = self._calculate_sentiment_score(
                volume_analysis, funding_rate, open_interest, long_short_ratio
            )
            
            sentiment_level = self._score_to_level(sentiment_score)
            
            result = MarketSentimentData(
                symbol=symbol,
                timestamp=datetime.now(),
                sentiment_score=sentiment_score,
                sentiment_level=sentiment_level,
                volume_analysis=volume_analysis,
                funding_rate=funding_rate,
                open_interest=open_interest,
                long_short_ratio=long_short_ratio,
                fear_greed_index=None  # 추후 외부 API 연동 시 구현
            )
            
            # 캐시 저장
            self.sentiment_cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"시장 심리 분석 오류 ({symbol}): {e}")
            return self._get_default_sentiment_data(symbol)
    
    def analyze_volume_patterns(self, symbol: str, exchange_name: str = 'binance') -> VolumeAnalysis:
        """거래량 패턴 분석 (python-binance 기반)"""
        try:
            if not self.binance_client:
                raise ValueError("바이낸스 클라이언트가 초기화되지 않음")
            
            # 24시간 티커 데이터
            ticker = self.binance_client.get_ticker(symbol=symbol)
            current_volume = float(ticker['volume'])
            
            # 과거 7일간 일봉 데이터
            klines = self.binance_client.get_historical_klines(symbol, '1d', '7 days ago UTC')
            volumes = [float(kline[5]) for kline in klines[:-1]]  # 마지막 미완성 캔들 제외
            avg_volume_24h = float(np.mean(volumes)) if volumes else current_volume
            
            volume_ratio = current_volume / avg_volume_24h if avg_volume_24h > 0 else 1.0
            
            # 거래량 트렌드 분석
            volume_trend = "안정"
            volume_spike = False
            
            if volume_ratio > 3.0:
                volume_trend = "급증"
                volume_spike = True
            elif volume_ratio > 1.5:
                volume_trend = "증가"
            elif volume_ratio < 0.5:
                volume_trend = "감소"
                
            return VolumeAnalysis(
                current_volume=current_volume,
                avg_volume_24h=avg_volume_24h,
                volume_ratio=volume_ratio,
                volume_trend=volume_trend,
                volume_spike=volume_spike
            )
            
        except Exception as e:
            self.logger.error(f"거래량 분석 오류 ({symbol}): {e}")
            return VolumeAnalysis(0, 0, 1.0, "안정", False)
    
    def get_funding_rate_analysis(self, symbol: str, exchange_name: str = 'binance') -> FundingRateData:
        """펀딩비 분석 (python-binance 기반)"""
        try:
            if not self.binance_client:
                return FundingRateData(symbol, 0.0, 0.0, datetime.now(), "안정")
            
            # 현재 펀딩비 (선물만 지원)
            try:
                funding_rate_info = self.binance_client.futures_funding_rate(symbol=symbol, limit=1)
                if funding_rate_info:
                    current_rate = float(funding_rate_info[0]['fundingRate'])
                    funding_time = funding_rate_info[0]['fundingTime']
                    next_funding_time = datetime.fromtimestamp(funding_time / 1000) + timedelta(hours=8)
                else:
                    current_rate = 0.0
                    next_funding_time = datetime.now() + timedelta(hours=8)
            except:
                # 현물인 경우 펀딩비 없음
                return FundingRateData(symbol, 0.0, 0.0, datetime.now(), "안정")
            
            # 과거 펀딩비 히스토리 (7일)
            try:
                funding_history = self.binance_client.futures_funding_rate(symbol=symbol, limit=21)  # 8시간마다, 7일
                if funding_history:
                    rates = [float(rate['fundingRate']) for rate in funding_history]
                    avg_rate_7d = float(np.mean(rates))
                else:
                    avg_rate_7d = current_rate
            except:
                avg_rate_7d = current_rate
            
            # 펀딩비 트렌드
            rate_trend = "안정"
            if current_rate > avg_rate_7d * 1.5:
                rate_trend = "상승"
            elif current_rate < avg_rate_7d * 0.5:
                rate_trend = "하락"
                
            return FundingRateData(
                symbol=symbol,
                current_rate=current_rate,
                avg_rate_7d=avg_rate_7d,
                next_funding_time=next_funding_time,
                rate_trend=rate_trend
            )
            
        except Exception as e:
            self.logger.error(f"펀딩비 분석 오류 ({symbol}): {e}")
            return FundingRateData(symbol, 0.0, 0.0, datetime.now(), "안정")
    
    def get_open_interest_analysis(self, symbol: str, exchange_name: str = 'binance') -> Optional[OpenInterestData]:
        """미체결약정 분석 (바이낸스 REST API 직접 호출)"""
        try:
            if not self.binance_client:
                return None
                
            # 바이낸스 선물 미체결약정 API 호출
            return self._get_binance_open_interest(symbol)
            
        except Exception as e:
            self.logger.error(f"미체결약정 분석 오류 ({symbol}): {e}")
            return None
    
    def get_long_short_ratio(self, symbol: str, exchange_name: str = 'binance') -> Optional[LongShortRatio]:
        """롱/숏 비율 분석 (바이낸스 REST API 직접 호출)"""
        try:
            if not self.binance_client:
                return None
                
            # 바이낸스 롱/숏 비율 API 호출
            return self._get_binance_long_short_ratio(symbol)
            
        except Exception as e:
            self.logger.error(f"롱/숏 비율 분석 오류 ({symbol}): {e}")
            return None
    
    def _get_binance_open_interest(self, symbol: str) -> Optional[OpenInterestData]:
        """바이낸스 미체결약정 조회 (python-binance 직접 호출)"""
        try:
            if not self.binance_client:
                return None
                
            # 현재 미체결약정
            oi_data = self.binance_client.futures_open_interest(symbol=symbol)
            current_oi = float(oi_data['openInterest'])
            
            # 미체결약정 히스토리 (24시간 변화)
            try:
                oi_history = self.binance_client.futures_open_interest_hist(
                    symbol=symbol, 
                    period="5m", 
                    limit=288  # 24시간 (5분 단위)
                )
                if len(oi_history) >= 2:
                    old_oi = float(oi_history[0]['sumOpenInterest'])
                    oi_change_24h = current_oi - old_oi
                    oi_change_percent = (oi_change_24h / old_oi * 100) if old_oi > 0 else 0
                else:
                    oi_change_24h = 0
                    oi_change_percent = 0
            except:
                oi_change_24h = 0
                oi_change_percent = 0
            
            # 트렌드 분석
            oi_trend = "안정"
            if oi_change_percent > 10:
                oi_trend = "급증"
            elif oi_change_percent > 5:
                oi_trend = "증가"
            elif oi_change_percent < -10:
                oi_trend = "급감"
            elif oi_change_percent < -5:
                oi_trend = "감소"
            
            return OpenInterestData(
                symbol=symbol,
                current_oi=current_oi,
                oi_change_24h=oi_change_24h,
                oi_change_percent=oi_change_percent,
                oi_trend=oi_trend
            )
            
        except Exception as e:
            self.logger.error(f"바이낸스 미체결약정 조회 오류: {e}")
            return None
    
    def _get_binance_long_short_ratio(self, symbol: str) -> Optional[LongShortRatio]:
        """바이낸스 롱/숏 비율 조회 (python-binance 직접 호출)"""
        try:
            if not self.binance_client:
                return None
                
            # 전체 계정 롱/숏 비율
            account_ratio_data = self.binance_client.futures_global_longshort_ratio(
                symbol=symbol, period="5m", limit=1
            )
            
            # 상위 트레이더 롱/숏 비율  
            top_trader_data = self.binance_client.futures_top_longshort_ratio(
                symbol=symbol, period="5m", limit=1
            )
            
            if account_ratio_data and top_trader_data:
                account_long_ratio = float(account_ratio_data[0]['longShortRatio'])
                account_short_ratio = 1.0 - account_long_ratio
                
                top_long_ratio = float(top_trader_data[0]['longShortRatio'])
                top_short_ratio = 1.0 - top_long_ratio
                
                return LongShortRatio(
                    symbol=symbol,
                    long_ratio=(account_long_ratio + top_long_ratio) / 2,
                    short_ratio=(account_short_ratio + top_short_ratio) / 2,
                    account_ratio=account_long_ratio,
                    top_trader_ratio=top_long_ratio
                )
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"바이낸스 롱/숏 비율 조회 오류: {e}")
            return None
    
    def _calculate_sentiment_score(
        self, 
        volume: VolumeAnalysis, 
        funding: FundingRateData,
        oi: Optional[OpenInterestData],
        ls_ratio: Optional[LongShortRatio]
    ) -> float:
        """종합 심리 점수 계산 (-100 ~ 100)"""
        score = 0.0
        
        # 1. 거래량 기여도 (30%)
        volume_score = 0.0
        if volume.volume_ratio > 3.0:
            volume_score = 30.0  # 극도로 높은 거래량 = 강한 관심
        elif volume.volume_ratio > 2.0:
            volume_score = 20.0
        elif volume.volume_ratio > 1.5:
            volume_score = 10.0
        elif volume.volume_ratio < 0.5:
            volume_score = -20.0  # 낮은 거래량 = 관심 부족
        
        # 2. 펀딩비 기여도 (25%)
        funding_score = 0.0
        if funding.current_rate > 0.001:  # 0.1% 이상
            funding_score = -25.0  # 높은 펀딩비 = 과도한 롱 포지션 = 위험
        elif funding.current_rate > 0.0005:
            funding_score = -15.0
        elif funding.current_rate < -0.001:
            funding_score = 25.0  # 음수 펀딩비 = 숏 포지션 과다 = 반등 가능성
        elif funding.current_rate < -0.0005:
            funding_score = 15.0
        
        # 3. 미체결약정 기여도 (20%)
        oi_score = 0.0
        if oi:
            if oi.oi_change_percent > 10:
                oi_score = 15.0  # OI 급증 = 새로운 포지션 유입
            elif oi.oi_change_percent > 5:
                oi_score = 10.0
            elif oi.oi_change_percent < -10:
                oi_score = -15.0  # OI 급감 = 청산 압박
        
        # 4. 롱/숏 비율 기여도 (25%)
        ls_score = 0.0
        if ls_ratio:
            if ls_ratio.long_ratio > 0.7:
                ls_score = -25.0  # 과도한 롱 = 위험
            elif ls_ratio.long_ratio > 0.6:
                ls_score = -15.0
            elif ls_ratio.long_ratio < 0.3:
                ls_score = 25.0  # 과도한 숏 = 반등 기회
            elif ls_ratio.long_ratio < 0.4:
                ls_score = 15.0
        
        total_score = volume_score + funding_score + oi_score + ls_score
        return max(-100, min(100, total_score))
    
    def _score_to_level(self, score: float) -> SentimentLevel:
        """점수를 심리 수준으로 변환"""
        if score >= 60:
            return SentimentLevel.EXTREME_GREED
        elif score >= 20:
            return SentimentLevel.GREED
        elif score <= -60:
            return SentimentLevel.EXTREME_FEAR
        elif score <= -20:
            return SentimentLevel.FEAR
        else:
            return SentimentLevel.NEUTRAL
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """캐시 유효성 확인"""
        if cache_key not in self.sentiment_cache:
            return False
        
        cache_time = self.sentiment_cache[cache_key]['timestamp']
        return (datetime.now() - cache_time).seconds < self.cache_duration
    
    def _get_default_sentiment_data(self, symbol: str) -> MarketSentimentData:
        """기본 심리 데이터 반환"""
        return MarketSentimentData(
            symbol=symbol,
            timestamp=datetime.now(),
            sentiment_score=0.0,
            sentiment_level=SentimentLevel.NEUTRAL,
            volume_analysis=VolumeAnalysis(0, 0, 1.0, "안정", False),
            funding_rate=FundingRateData(symbol, 0.0, 0.0, datetime.now(), "안정"),
            open_interest=None,
            long_short_ratio=None,
            fear_greed_index=None
        )
    
    def get_market_overview(self, symbols: List[str], exchange_name: str = 'binance') -> Dict[str, MarketSentimentData]:
        """여러 심볼의 시장 개요"""
        overview = {}
        for symbol in symbols:
            try:
                overview[symbol] = self.analyze_market_sentiment(symbol, exchange_name)
            except Exception as e:
                self.logger.error(f"시장 개요 조회 오류 ({symbol}): {e}")
                overview[symbol] = self._get_default_sentiment_data(symbol)
        
        return overview
    
    def clear_cache(self):
        """캐시 초기화"""
        self.sentiment_cache.clear()
        self.logger.info("시장 심리 분석 캐시 초기화 완료")