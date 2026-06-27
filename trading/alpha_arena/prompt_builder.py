#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 프롬프트 빌더

Alpha Arena 스타일 프롬프트를 생성합니다.
기존 trader.py와 완전히 분리된 독립 모듈입니다.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

try:
    from api.binance_client import BinanceClient
except ImportError:
    BinanceClient = None  # type: ignore


@dataclass
class MarketSnapshot:
    """시장 스냅샷 (3분봉 + 4H 컨텍스트)"""
    symbol: str
    price: float
    spread: float
    volume_24h: float
    funding_rate: float
    trend: str
    # 3분봉 기반 지표
    rsi_7: Optional[float] = None  # RSI7 (3분봉) - 현재값
    rsi_14: Optional[float] = None  # RSI14 (3분봉) - 현재값
    ema_20: Optional[float] = None  # EMA20 (3분봉) - 현재값
    ema_50: Optional[float] = None  # EMA50 (3분봉)
    macd: Optional[float] = None  # MACD (3분봉) - 현재값
    # 4H 컨텍스트 지표
    ema_20_4h: Optional[float] = None  # EMA20 (4H)
    ema_50_4h: Optional[float] = None  # EMA50 (4H)
    atr_3: Optional[float] = None  # ATR3 (4H)
    atr_14: Optional[float] = None  # ATR14 (4H)
    macd_4h: Optional[float] = None  # MACD (4H) - 현재값
    rsi_14_4h: Optional[float] = None  # RSI14 (4H) - 현재값
    # 시계열 데이터 (3분봉 배열)
    candles_3m: Optional[List[Dict[str, Any]]] = None  # 3분봉 배열 (OLDEST → NEWEST)
    ema_20_array: Optional[List[float]] = None  # EMA20 배열 (각 캔들별)
    macd_array: Optional[List[float]] = None  # MACD 배열 (각 캔들별)
    rsi_7_array: Optional[List[float]] = None  # RSI7 배열 (각 캔들별)
    rsi_14_array: Optional[List[float]] = None  # RSI14 배열 (각 캔들별)
    # 4H 컨텍스트 배열
    macd_4h_array: Optional[List[float]] = None  # MACD 배열 (4H, 각 캔들별)
    rsi_14_4h_array: Optional[List[float]] = None  # RSI14 배열 (4H, 각 캔들별)
    # Volume 데이터
    current_volume: Optional[float] = None  # 현재 볼륨 (4H)
    average_volume: Optional[float] = None  # 평균 볼륨 (4H)
    open_interest: Optional[float] = None
    open_interest_avg: Optional[float] = None  # Open Interest 평균


@dataclass
class PositionInfo:
    """포지션 정보"""
    symbol: str
    side: str  # LONG, SHORT
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int


class PromptBuilder:
    """Alpha Arena 프롬프트 빌더"""
    
    # Alpha Arena 고정 심볼
    ARENA_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
    
    # Alpha Arena 벤치마크 초기 자금 (만불 기준)
    INITIAL_CAPITAL_USD = 10000.0
    
    def __init__(self, binance_client: Optional[BinanceClient] = None, settings: Optional[Dict[str, Any]] = None):
        """
        Args:
            binance_client: Binance API 클라이언트 (기존 trader.py 안 거침)
            settings: 설정 딕셔너리
        """
        self.binance_client = binance_client
        self.settings = settings or {}
        self.logger = logging.getLogger(__name__)
        
        # 초기 자금 기준 (설정에서 읽기, 기본값 10000)
        arena_settings = self.settings.get('alpha_arena', {})
        self.initial_capital_benchmark = float(arena_settings.get('initial_capital_benchmark', self.INITIAL_CAPITAL_USD))
        
        # 세션 정보
        self.session_start_time: Optional[datetime] = None
        self.session_id: Optional[str] = None
        
        # 틱 카운터 (invoke_count용)
        self.tick_count: int = 0
        
        # 마지막 주문/에러 기록 (피드백 루프용)
        self.last_orders: List[Dict[str, Any]] = []
        self.last_errors: List[Dict[str, Any]] = []

        # 메트릭 참조 (runner.py에서 set_metrics()로 주입)
        self._metrics: Optional[Any] = None

    def set_metrics(self, metrics: Any) -> None:
        """ArenaMetrics 인스턴스 연결 (runner.py에서 호출)"""
        self._metrics = metrics
    
    def set_session_info(self, session_id: str, start_time: datetime):
        """세션 정보 설정"""
        self.session_id = session_id
        self.session_start_time = start_time
        self.tick_count = 0  # 틱 카운터 리셋
    
    def add_order_result(self, order_result: Dict[str, Any]):
        """주문 결과 추가 (피드백 루프용)"""
        if order_result:
            self.last_orders.append({
                'timestamp': datetime.now().isoformat(),
                'result': order_result
            })
            # 최근 10개만 유지
            if len(self.last_orders) > 10:
                self.last_orders.pop(0)
    
    def add_error(self, error: Dict[str, Any]):
        """에러 추가 (피드백 루프용)"""
        if error:
            self.last_errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': error
            })
            # 최근 10개만 유지
            if len(self.last_errors) > 10:
                self.last_errors.pop(0)
    
    def collect_market_data(self, symbol: str) -> Optional[MarketSnapshot]:
        """시장 데이터 수집 (단일 심볼)"""
        try:
            if not self.binance_client:
                self.logger.warning(f"Binance 클라이언트가 없어 시장 데이터를 수집할 수 없습니다: {symbol}")
                return None
            
            # 24h 티커 데이터
            ticker = self.binance_client.get_24h_ticker(symbol)
            if not ticker:
                return None
            
            price = float(ticker.get('lastPrice', ticker.get('price', 0)))
            if price <= 0:
                return None
            
            # 스프레드 계산 (bid/ask)
            bid_price = float(ticker.get('bidPrice', price))
            ask_price = float(ticker.get('askPrice', price))
            spread = ((ask_price - bid_price) / price) * 100 if price > 0 else 0
            
            # 24h 거래량
            volume_24h = float(ticker.get('quoteVolume', ticker.get('volume', 0)))
            
            # Funding Rate (선물 데이터)
            funding_rate = float(ticker.get('lastFundingRate', 0))
            
            # 지표 계산 (3분봉 + 4H 컨텍스트)
            indicators = self._calculate_indicators(symbol)
            
            # Open Interest (선물 데이터)
            open_interest = float(ticker.get('openInterest', 0))
            # Open Interest 평균 (현재는 현재값과 동일, 향후 여러 틱 평균 계산 가능)
            open_interest_avg = open_interest
            
            # 트렌드 (간단한 추정)
            change_24h = float(ticker.get('priceChangePercent', 0))
            if change_24h > 2:
                trend = "uptrend"
            elif change_24h < -2:
                trend = "downtrend"
            else:
                trend = "neutral"
            
            return MarketSnapshot(
                symbol=symbol,
                price=price,
                spread=spread,
                volume_24h=volume_24h,
                funding_rate=funding_rate,
                trend=trend,
                rsi_7=indicators.get('rsi_7'),
                rsi_14=indicators.get('rsi_14'),
                ema_20=indicators.get('ema_20'),
                ema_50=indicators.get('ema_50'),
                macd=indicators.get('macd'),
                ema_20_4h=indicators.get('ema_20_4h'),
                ema_50_4h=indicators.get('ema_50_4h'),
                atr_3=indicators.get('atr_3'),
                atr_14=indicators.get('atr_14'),
                macd_4h=indicators.get('macd_4h'),
                rsi_14_4h=indicators.get('rsi_14_4h'),
                candles_3m=indicators.get('candles_3m'),
                ema_20_array=indicators.get('ema_20_array'),
                macd_array=indicators.get('macd_array'),
                rsi_7_array=indicators.get('rsi_7_array'),
                rsi_14_array=indicators.get('rsi_14_array'),
                macd_4h_array=indicators.get('macd_4h_array'),
                rsi_14_4h_array=indicators.get('rsi_14_4h_array'),
                current_volume=indicators.get('current_volume'),
                average_volume=indicators.get('average_volume'),
                open_interest=open_interest,
                open_interest_avg=open_interest_avg
            )
            
        except Exception as e:
            self.logger.error(f"시장 데이터 수집 오류 ({symbol}): {e}")
            return None
    
    def _calculate_indicators(self, symbol: str) -> Dict[str, Any]:
        """지표 계산 (3분봉 + 4H 컨텍스트)"""
        result = {}
        try:
            if not self.binance_client:
                return result
            
            # 3분봉 데이터 (최근 200개, OLDEST → NEWEST)
            klines_3m = self.binance_client.get_klines(symbol, '3m', 200)
            # 4H 캔들 데이터 (최근 100개, 컨텍스트용)
            klines_4h = self.binance_client.get_klines(symbol, '4h', 100)
            
            if not klines_3m:
                return result
            
            # 3분봉 Close 가격 추출
            closes_3m = [float(k[4]) for k in klines_3m]
            # 3분봉 캔들 배열 (OLDEST → NEWEST)
            candles_3m = []
            for k in klines_3m:
                candles_3m.append({
                    'time': int(k[0]),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            result['candles_3m'] = candles_3m
            
            # 3분봉 기반 지표 (현재값)
            if len(closes_3m) >= 7:
                result['rsi_7'] = self._calculate_rsi(closes_3m, 7)
            if len(closes_3m) >= 14:
                result['rsi_14'] = self._calculate_rsi(closes_3m, 14)
            if len(closes_3m) >= 20:
                result['ema_20'] = self._calculate_ema(closes_3m, 20)
            if len(closes_3m) >= 50:
                result['ema_50'] = self._calculate_ema(closes_3m, 50)
            if len(closes_3m) >= 26:
                ema_12 = self._calculate_ema(closes_3m, 12)
                ema_26 = self._calculate_ema(closes_3m, 26)
                if ema_12 and ema_26:
                    result['macd'] = ema_12 - ema_26
            
            # 3분봉 배열 지표 (각 캔들별)
            # 주의: 배열 길이는 캔들 길이와 다를 수 있음 (period 이후부터 시작)
            # 예: 200개 캔들 -> EMA20 배열은 180개 (인덱스 20~199에 대응)
            # 프롬프트에서는 각 배열의 마지막 10개를 사용하여 같은 시점의 데이터를 맞춤
            if len(closes_3m) >= 20:
                result['ema_20_array'] = self._calculate_ema_array(closes_3m, 20)
            if len(closes_3m) >= 26:
                result['macd_array'] = self._calculate_macd_array(closes_3m)
            if len(closes_3m) >= 7:
                result['rsi_7_array'] = self._calculate_rsi_array(closes_3m, 7)
            if len(closes_3m) >= 14:
                result['rsi_14_array'] = self._calculate_rsi_array(closes_3m, 14)
            
            # 4H 컨텍스트 지표
            if klines_4h:
                closes_4h = [float(k[4]) for k in klines_4h]
                highs_4h = [float(k[2]) for k in klines_4h]
                lows_4h = [float(k[3]) for k in klines_4h]
                volumes_4h = [float(k[5]) for k in klines_4h]
                
                # 4H 현재값 지표
                if len(closes_4h) >= 20:
                    result['ema_20_4h'] = self._calculate_ema(closes_4h, 20)
                if len(closes_4h) >= 50:
                    result['ema_50_4h'] = self._calculate_ema(closes_4h, 50)
                if len(closes_4h) >= 14:
                    result['rsi_14_4h'] = self._calculate_rsi(closes_4h, 14)
                if len(closes_4h) >= 26:
                    ema_12_4h = self._calculate_ema(closes_4h, 12)
                    ema_26_4h = self._calculate_ema(closes_4h, 26)
                    if ema_12_4h and ema_26_4h:
                        result['macd_4h'] = ema_12_4h - ema_26_4h
                
                # 4H 배열 지표
                if len(closes_4h) >= 26:
                    result['macd_4h_array'] = self._calculate_macd_array(closes_4h)
                if len(closes_4h) >= 14:
                    result['rsi_14_4h_array'] = self._calculate_rsi_array(closes_4h, 14)
                
                # ATR 계산 (4H)
                if len(highs_4h) >= 14 and len(lows_4h) >= 14:
                    result['atr_14'] = self._calculate_atr(highs_4h, lows_4h, closes_4h, 14)
                if len(highs_4h) >= 3 and len(lows_4h) >= 3:
                    result['atr_3'] = self._calculate_atr(highs_4h, lows_4h, closes_4h, 3)
                
                # Volume 데이터 (4H)
                if len(volumes_4h) > 0:
                    result['current_volume'] = volumes_4h[-1]  # 최신 볼륨
                    result['average_volume'] = sum(volumes_4h) / len(volumes_4h)  # 평균 볼륨
            
            return result
            
        except Exception as e:
            self.logger.warning(f"지표 계산 오류 ({symbol}): {e}")
            return result
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """RSI 계산"""
        try:
            if len(prices) < period + 1:
                return None
            
            gains = []
            losses = []
            for i in range(1, len(prices)):
                change = prices[i] - prices[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(-change)
            
            if len(gains) < period:
                return None
            
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            
            if avg_loss == 0:
                return 100.0
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
            
        except Exception:
            return None
    
    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """EMA 계산"""
        try:
            if len(prices) < period:
                return None
            
            # 첫 EMA는 SMA로 시작
            ema = sum(prices[:period]) / period
            
            # 나머지는 EMA 공식 적용
            multiplier = 2 / (period + 1)
            for price in prices[period:]:
                ema = (price * multiplier) + (ema * (1 - multiplier))
            
            return ema
            
        except Exception:
            return None
    
    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> Optional[float]:
        """ATR (Average True Range) 계산"""
        try:
            if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
                return None
            
            # True Range 계산
            true_ranges = []
            for i in range(1, len(highs)):
                tr1 = highs[i] - lows[i]  # High - Low
                tr2 = abs(highs[i] - closes[i-1])  # |High - Prev Close|
                tr3 = abs(lows[i] - closes[i-1])  # |Low - Prev Close|
                true_ranges.append(max(tr1, tr2, tr3))
            
            if len(true_ranges) < period:
                return None
            
            # ATR = True Range의 평균
            atr = sum(true_ranges[-period:]) / period
            return atr
            
        except Exception:
            return None
    
    def _calculate_rsi_array(self, prices: List[float], period: int = 14) -> List[float]:
        """RSI 배열 계산 (각 캔들별 RSI 값)
        
        각 시점 i (period <= i < len(prices))에서 prices[0:i+1]까지의 데이터로 RSI 계산
        """
        try:
            if len(prices) < period + 1:
                return []
            
            rsi_array = []
            for i in range(period, len(prices)):
                # i까지의 데이터로 RSI 계산 (prices[0]부터 prices[i]까지)
                window_prices = prices[:i+1]
                if len(window_prices) < period + 1:
                    rsi_array.append(50.0)  # 기본값
                    continue
                
                # 변화량 계산
                gains = []
                losses = []
                for j in range(1, len(window_prices)):
                    change = window_prices[j] - window_prices[j-1]
                    if change > 0:
                        gains.append(change)
                        losses.append(0)
                    else:
                        gains.append(0)
                        losses.append(-change)
                
                # 최근 period개의 평균 계산
                if len(gains) < period:
                    rsi_array.append(50.0)  # 기본값
                    continue
                
                avg_gain = sum(gains[-period:]) / period
                avg_loss = sum(losses[-period:]) / period
                
                if avg_loss == 0:
                    rsi_array.append(100.0)
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                    rsi_array.append(rsi)
            
            return rsi_array
            
        except Exception:
            return []
    
    def _calculate_ema_array(self, prices: List[float], period: int) -> List[float]:
        """EMA 배열 계산 (각 캔들별 EMA 값)"""
        try:
            if len(prices) < period:
                return []
            
            ema_array = []
            # 첫 EMA는 SMA로 시작
            ema = sum(prices[:period]) / period
            ema_array.append(ema)
            
            # 나머지는 EMA 공식 적용
            multiplier = 2 / (period + 1)
            for i in range(period, len(prices)):
                ema = (prices[i] * multiplier) + (ema * (1 - multiplier))
                ema_array.append(ema)
            
            return ema_array
            
        except Exception:
            return []
    
    def _calculate_macd_array(self, prices: List[float]) -> List[float]:
        """MACD 배열 계산 (각 캔들별 MACD 값 = EMA12 - EMA26)
        
        주의: EMA12 배열은 인덱스 12부터, EMA26 배열은 인덱스 26부터 시작하므로
        MACD 배열은 인덱스 26부터 시작 (더 긴 period 기준)
        """
        try:
            if len(prices) < 26:
                return []
            
            # EMA12, EMA26 배열 계산
            ema_12_array = self._calculate_ema_array(prices, 12)
            ema_26_array = self._calculate_ema_array(prices, 26)
            
            if len(ema_12_array) == 0 or len(ema_26_array) == 0:
                return []
            
            # EMA12 배열은 인덱스 12부터, EMA26 배열은 인덱스 26부터 시작
            # MACD는 EMA26의 시작점(인덱스 26)부터 계산
            # EMA12 배열에서 인덱스 26에 해당하는 부분 찾기
            ema12_start_idx = 26 - 12  # EMA12 배열에서 인덱스 26에 해당하는 위치
            if ema12_start_idx < 0 or ema12_start_idx >= len(ema_12_array):
                return []
            
            # MACD = EMA12 - EMA26 (같은 시점의 값들)
            macd_array = []
            min_len = min(len(ema_12_array) - ema12_start_idx, len(ema_26_array))
            for i in range(min_len):
                macd_array.append(ema_12_array[ema12_start_idx + i] - ema_26_array[i])
            
            return macd_array
            
        except Exception:
            return []
    
    def collect_account_info(self) -> Dict[str, Any]:
        """계좌 정보 수집"""
        try:
            if not self.binance_client:
                return {}
            
            balance = self.binance_client.get_balance()
            account_info = self.binance_client.get_account_info()
            
            # USDT 잔고 추출
            usdt_balance = balance.get('USDT', {})
            wallet_balance = usdt_balance.get('wallet_balance', 0) if isinstance(usdt_balance, dict) else 0
            available_balance = usdt_balance.get('available_balance', 0) if isinstance(usdt_balance, dict) else 0
            unrealized_profit = usdt_balance.get('unrealized_profit', 0) if isinstance(usdt_balance, dict) else 0
            
            return {
                'wallet_balance': wallet_balance,
                'available_balance': available_balance,
                'unrealized_profit': unrealized_profit,
                'total_balance': wallet_balance + unrealized_profit,
                'account_info': account_info
            }
            
        except Exception as e:
            self.logger.error(f"계좌 정보 수집 오류: {e}")
            return {}
    
    def collect_positions(self) -> List[PositionInfo]:
        """포지션 정보 수집"""
        positions = []
        try:
            if not self.binance_client:
                return positions
            
            for symbol in self.ARENA_SYMBOLS:
                try:
                    position_data = self.binance_client.get_position_info(symbol)
                    if not position_data:
                        continue
                    
                    position_amt = float(position_data.get('positionAmt', 0))
                    if abs(position_amt) < 1e-8:  # 포지션 없음
                        continue
                    
                    entry_price = float(position_data.get('entryPrice', 0))
                    leverage = int(position_data.get('leverage', 1))
                    unrealized_pnl = float(position_data.get('unRealizedProfit', 0))
                    
                    # 현재가 조회
                    current_price = self.binance_client.get_current_price(symbol)
                    if current_price <= 0:
                        current_price = entry_price
                    
                    # 포지션 사이드
                    side = 'LONG' if position_amt > 0 else 'SHORT'
                    size = abs(position_amt)
                    
                    positions.append(PositionInfo(
                        symbol=symbol,
                        side=side,
                        size=size,
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        leverage=leverage
                    ))
                    
                except Exception as e:
                    self.logger.warning(f"포지션 정보 수집 오류 ({symbol}): {e}")
                    continue
            
            return positions
            
        except Exception as e:
            self.logger.error(f"포지션 수집 오류: {e}")
            return []
    
    def build_prompt(self) -> str:
        """Alpha Arena 스타일 프롬프트 생성"""
        try:
            if not self.session_start_time:
                self.logger.warning("세션 정보가 설정되지 않았습니다. 기본값 사용")
                self.session_start_time = datetime.now()
            
            # 틱 카운터 증가
            self.tick_count += 1
            
            # 세션 경과 시간 계산
            now = datetime.now()
            elapsed = now - self.session_start_time
            minutes_running = int(elapsed.total_seconds() / 60)
            
            # 시장 데이터 수집 (6개 코인)
            market_snapshots = []
            for symbol in self.ARENA_SYMBOLS:
                snapshot = self.collect_market_data(symbol)
                if snapshot:
                    market_snapshots.append(snapshot)
            
            # 계좌 정보 수집
            account_info = self.collect_account_info()
            
            # 포지션 정보 수집
            positions = self.collect_positions()
            
            # 프롬프트 생성
            prompt = self._format_prompt(
                session_start_time=self.session_start_time,
                minutes_running=minutes_running,
                now=now,
                market_snapshots=market_snapshots,
                account_info=account_info,
                positions=positions
            )
            
            return prompt
            
        except Exception as e:
            self.logger.error(f"프롬프트 생성 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return ""
    
    def _format_prompt(self, 
                      session_start_time: datetime,
                      minutes_running: int,
                      now: datetime,
                      market_snapshots: List[MarketSnapshot],
                      account_info: Dict[str, Any],
                      positions: List[PositionInfo]) -> str:
        """프롬프트 포맷팅 (5개 섹션 고정: Header, Market State, Account & Positions, Rules, Output format)"""
        lines = []
        
        # ===== 1. HEADER =====
        # 🔥 Alpha Arena 벤치마크와 동일한 형식 (실제 프롬프트 샘플 참조)
        lines.append(f"It has been {minutes_running} minutes since you started trading.")
        lines.append(f"The current time is {now.strftime('%Y-%m-%d %H:%M:%S')} and you've been invoked {self.tick_count} times.")
        lines.append("Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha.")
        lines.append("")
        # 🔥 초기 자금 기준 명시 (설정에서 읽은 값 사용)
        lines.append(f"Initial Capital Benchmark: ${self.initial_capital_benchmark:,.0f}")
        lines.append("You should make trading decisions based on this benchmark capital, not necessarily your actual account balance.")
        lines.append("")
        lines.append("ALL OF THE PRICE OR SIGNAL DATA BELOW IS ORDERED: OLDEST → NEWEST")
        lines.append("")
        lines.append("Timeframes note: Unless stated otherwise in a section title, intraday series are provided at 3‑minute intervals. If a coin uses a different interval, it is explicitly stated in that coin's section.")
        lines.append("")
        
        # ===== 2. MARKET STATE =====
        lines.append("CURRENT MARKET STATE FOR ALL COINS")
        lines.append("")
        
        # 🔥 Alpha Arena 벤치마크와 동일한 형식 (실제 프롬프트 샘플 참조)
        for snapshot in market_snapshots:
            # 코인 심볼에서 USDT 제거 (예: BTCUSDT -> BTC)
            coin_symbol = snapshot.symbol.replace('USDT', '')
            lines.append(f"ALL {coin_symbol} DATA")
            lines.append("")
            
            # 현재값 지표
            rsi_7_value = snapshot.rsi_7 if snapshot.rsi_7 is not None else 0.0
            ema20_value = snapshot.ema_20 if snapshot.ema_20 is not None else 0.0
            macd_value = snapshot.macd if snapshot.macd is not None else 0.0
            
            lines.append(f"current_price = {snapshot.price:.4f}, current_ema20 = {ema20_value:.4f}, current_macd = {macd_value:.4f}, current_rsi (7 period) = {rsi_7_value:.3f}")
            lines.append("")
            lines.append("In addition, here is the latest {} open interest and funding rate for perps (the instrument you are trading):".format(coin_symbol))
            lines.append("")
            
            # Open Interest: Latest: {v}  Average: {v}
            oi_latest = snapshot.open_interest if snapshot.open_interest else 0
            oi_avg = snapshot.open_interest_avg if snapshot.open_interest_avg else oi_latest
            lines.append(f"Open Interest: Latest: {oi_latest:,.2f}  Average: {oi_avg:,.2f}")
            lines.append("")
            lines.append(f"Funding Rate: {snapshot.funding_rate:.6f}")
            lines.append("")
            
            # 3분봉 배열 (OLDEST → NEWEST)
            if snapshot.candles_3m:
                lines.append("Intraday series (3‑minute intervals, oldest → latest):")
                lines.append("")
                # 최근 10개 캔들만 사용 (실제 프롬프트 샘플 기준)
                total_candles = len(snapshot.candles_3m)
                recent_candles = snapshot.candles_3m[-10:] if total_candles > 10 else snapshot.candles_3m
                mid_prices = [c['close'] for c in recent_candles]
                lines.append(f"{coin_symbol} mid prices: {mid_prices}")
                lines.append("")
                
                # 각 배열은 period 이후부터 시작하므로, 최근 10개 캔들에 대응하는 배열 인덱스 계산
                # EMA20 배열 (인덱스 20부터 시작)
                if snapshot.ema_20_array:
                    # 최근 10개 캔들에 대응하는 EMA20 배열 인덱스
                    # 캔들 인덱스: [total-10, total-9, ..., total-1]
                    # EMA20 배열 인덱스: [total-10-20, total-9-20, ..., total-1-20] = [total-30, total-29, ..., total-21]
                    # 하지만 배열은 인덱스 0부터 시작하므로: [len(ema20_array)-10, ..., len(ema20_array)-1]
                    ema20_array = snapshot.ema_20_array[-10:] if len(snapshot.ema_20_array) >= 10 else snapshot.ema_20_array
                    lines.append(f"EMA indicators (20‑period): {[round(v, 3) for v in ema20_array]}")
                    lines.append("")
                
                # MACD 배열 (인덱스 26부터 시작)
                if snapshot.macd_array:
                    macd_array = snapshot.macd_array[-10:] if len(snapshot.macd_array) >= 10 else snapshot.macd_array
                    lines.append(f"MACD indicators: {[round(v, 3) for v in macd_array]}")
                    lines.append("")
                
                # RSI7 배열 (인덱스 7부터 시작)
                if snapshot.rsi_7_array:
                    rsi_7_array = snapshot.rsi_7_array[-10:] if len(snapshot.rsi_7_array) >= 10 else snapshot.rsi_7_array
                    lines.append(f"RSI indicators (7‑Period): {[round(v, 3) for v in rsi_7_array]}")
                    lines.append("")
                
                # RSI14 배열 (인덱스 14부터 시작)
                if snapshot.rsi_14_array:
                    rsi_14_array = snapshot.rsi_14_array[-10:] if len(snapshot.rsi_14_array) >= 10 else snapshot.rsi_14_array
                    lines.append(f"RSI indicators (14‑Period): {[round(v, 2) for v in rsi_14_array]}")
                    lines.append("")
            
            # 4H 컨텍스트 지표
            lines.append("Longer‑term context (4‑hour timeframe):")
            lines.append("")
            if snapshot.ema_20_4h is not None and snapshot.ema_50_4h is not None:
                lines.append(f"20‑Period EMA: {snapshot.ema_20_4h:.2f} vs. 50‑Period EMA: {snapshot.ema_50_4h:.2f}")
            if snapshot.atr_3 is not None and snapshot.atr_14 is not None:
                lines.append(f"3‑Period ATR: {snapshot.atr_3:.3f} vs. 14‑Period ATR: {snapshot.atr_14:.3f}")
            # Current Volume vs Average Volume
            if snapshot.current_volume is not None and snapshot.average_volume is not None:
                lines.append(f"Current Volume: {snapshot.current_volume:.3f} vs. Average Volume: {snapshot.average_volume:.3f}")
            # 4H MACD 배열
            if snapshot.macd_4h_array:
                macd_4h_array = snapshot.macd_4h_array[-10:] if len(snapshot.macd_4h_array) >= 10 else snapshot.macd_4h_array
                lines.append(f"MACD indicators: {[round(v, 3) for v in macd_4h_array]}")
            # 4H RSI14 배열
            if snapshot.rsi_14_4h_array:
                rsi_14_4h_array = snapshot.rsi_14_4h_array[-10:] if len(snapshot.rsi_14_4h_array) >= 10 else snapshot.rsi_14_4h_array
                lines.append(f"RSI indicators (14‑Period): {[round(v, 2) for v in rsi_14_4h_array]}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # ===== 3. ACCOUNT & POSITIONS =====
        # 🔥 Alpha Arena 벤치마크와 동일한 형식 (문서 ALPHA_ARENA_MODE.md 섹션 5 참조)
        lines.append("HERE IS YOUR ACCOUNT INFORMATION & PERFORMANCE")
        lines.append("")
        # 🔥 초기 자금 기준 명시 (LLM이 이 기준으로 판단)
        lines.append(f"Initial Capital Benchmark: ${self.initial_capital_benchmark:,.0f}")
        lines.append("")
        # 문서에 명시된 형식: Available Cash, Account Value, Sharpe Ratio
        available_balance = account_info.get('available_balance', 0)
        total_balance = account_info.get('total_balance', 0)
        
        lines.append(f"Available Cash: ${available_balance:.2f}")
        lines.append(f"Account Value: ${total_balance:.2f}")
        # Sharpe Ratio: 메트릭 인스턴스에서 가져오기, 없으면 0.0
        sharpe_ratio = 0.0
        try:
            if self._metrics is not None:
                m = self._metrics
                if hasattr(m, 'current_metrics') and hasattr(m.current_metrics, 'sharpe_ratio'):
                    sharpe_ratio = float(m.current_metrics.sharpe_ratio or 0.0)
                elif hasattr(m, 'calculate_sharpe_ratio'):
                    sharpe_ratio = float(m.calculate_sharpe_ratio() or 0.0)
                elif hasattr(m, 'get_metrics'):
                    sharpe_ratio = float((m.get_metrics() or {}).get('sharpe_ratio', 0.0))
        except Exception:
            sharpe_ratio = 0.0
        lines.append(f"Sharpe Ratio: {sharpe_ratio:.4f}")
        lines.append("")
        lines.append("Current live positions & performance:")
        lines.append("")
        if positions:
            # 🔥 Alpha Arena 벤치마크와 동일한 형식 (문서 ALPHA_ARENA_MODE.md 섹션 5 참조)
            # 문서 형식: {'symbol': 'BTCUSDT', 'quantity': ..., 'entry_price': ..., 'current_price': ..., 
            #            'liquidation_price': ..., 'unrealized_pnl': ..., 'leverage': 10..20,
            #            'exit_plan': {'invalidation_condition': '...', 'profit_target': ..., 'stop_loss': ...},
            #            'confidence': ..., 'risk_usd': ..., 'sl_oid': ..., 'tp_oid': ..., 'wait_for_fill': ..., 'entry_oid': ..., 'notional_usd': ...}
            for pos in positions:
                # 청산가 계산: 유지증거금률(0.5%) 기반 레버리지 공식
                # LONG: liq = entry / (1 + 1/leverage - maintenance_margin_rate)
                # SHORT: liq = entry / (1 - 1/leverage + maintenance_margin_rate)
                try:
                    maintenance_margin_rate = 0.005  # 0.5% (바이낸스 선물 기본)
                    lev = max(1, int(pos.leverage))
                    if str(pos.side).upper() == 'LONG':
                        denom = 1.0 + 1.0 / lev - maintenance_margin_rate
                        liquidation_price = pos.entry_price / denom if denom > 0 else 0.0
                    else:
                        denom = 1.0 - 1.0 / lev + maintenance_margin_rate
                        liquidation_price = pos.entry_price / denom if denom > 0 else 0.0
                except Exception:
                    liquidation_price = 0.0
                # exit_plan은 현재 포지션의 TP/SL 정보 (실제 주문에서 가져오기)
                lines.append(f"{{'symbol': '{pos.symbol}', 'quantity': {pos.size:.4f}, 'entry_price': {pos.entry_price:.4f}, ")
                lines.append(f" 'current_price': {pos.current_price:.4f}, 'liquidation_price': {liquidation_price:.4f}, ")
                lines.append(f" 'unrealized_pnl': {pos.unrealized_pnl:.2f}, 'leverage': {pos.leverage}, ")
                lines.append(f" 'exit_plan': {{'invalidation_condition': 'N/A', 'profit_target': None, 'stop_loss': None}}, ")
                lines.append(f" 'confidence': 0.0, 'risk_usd': 0.0, 'sl_oid': None, 'tp_oid': None, 'wait_for_fill': False, 'entry_oid': None, 'notional_usd': {pos.size * pos.current_price:.2f}}}")
                lines.append("")
        else:
            lines.append("Open Positions: None")
            lines.append("")
        
        # 마지막 주문/에러 (피드백 루프)
        if self.last_orders or self.last_errors:
            lines.append("Recent Orders/Errors:")
            lines.append("")
            if self.last_orders:
                for order in self.last_orders[-3:]:  # 최근 3개만
                    result = order.get('result', {})
                    status = result.get('status', 'UNKNOWN')
                    symbol = result.get('symbol', 'UNKNOWN')
                    if status == 'SUCCESS':
                        order_id = result.get('order_id', 'N/A')
                        lines.append(f"  ✅ [{order.get('timestamp')}] {symbol}: 주문 실행 성공 (ID: {order_id})")
                    elif status == 'SKIPPED':
                        skip_reason = result.get('skip_reason', 'Unknown')
                        # 🔥 TP/SL 누락을 명확히 강조
                        if 'TP/SL' in skip_reason or 'profit_target' in skip_reason or 'stop_loss' in skip_reason:
                            lines.append(f"  ⚠️ [{order.get('timestamp')}] {symbol}: 주문 스킵 - TP/SL 누락!")
                            lines.append(f"     → ENTER_LONG/ENTER_SHORT 신호는 profit_target과 stop_loss 둘 다 필수입니다.")
                        else:
                            lines.append(f"  ⚠️ [{order.get('timestamp')}] {symbol}: 주문 스킵 - {skip_reason}")
                    elif status == 'ERROR':
                        error_msg = result.get('error', 'Unknown error')
                        lines.append(f"  ❌ [{order.get('timestamp')}] {symbol}: 주문 오류 - {error_msg}")
            if self.last_errors:
                for error in self.last_errors[-3:]:  # 최근 3개만
                    error_msg = error.get('error', {})
                    if isinstance(error_msg, dict):
                        error_text = error_msg.get('error', str(error_msg))
                    else:
                        error_text = str(error_msg)
                    # 🔥 TP/SL 누락을 명확히 강조
                    if 'TP/SL' in error_text or 'profit_target' in error_text or 'stop_loss' in error_text:
                        lines.append(f"  ⚠️ [{error.get('timestamp')}] {error_text}")
                        lines.append(f"     → ENTER_LONG/ENTER_SHORT 신호는 profit_target과 stop_loss 둘 다 필수입니다.")
                    else:
                        lines.append(f"  ❌ [{error.get('timestamp')}] {error_text}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # ===== 4. RULES =====
        # 🔥 Alpha Arena 벤치마크와 동일한 형식 (문서 ALPHA_ARENA_MODE.md 섹션 5 참조)
        lines.append("RULES:")
        lines.append("")
        lines.append("Evaluate a decision to maximize risk-adjusted returns.")
        lines.append("")
        lines.append("Rules:")
        lines.append("1. No pyramiding. Do not add to existing positions.")
        lines.append("2. No re-entry into coins you already hold. If you hold a position, use HOLD or CLOSE only.")
        lines.append("3. If invalidation condition is not triggered → HOLD by default.")
        lines.append("4. ⚠️ CRITICAL: For ENTER_LONG or ENTER_SHORT signals, you MUST provide BOTH profit_target AND stop_loss.")
        lines.append("   - If you omit profit_target OR stop_loss, the order will NOT be executed.")
        lines.append("   - The order will be SKIPPED and you will see an error in the next prompt.")
        lines.append("   - You MUST provide BOTH profit_target AND stop_loss for every ENTER_LONG/ENTER_SHORT signal.")
        lines.append("")
        
        # ===== 5. OUTPUT FORMAT =====
        # 🔥 Alpha Arena 벤치마크와 동일한 형식 (문서 ALPHA_ARENA_MODE.md 섹션 5 참조)
        lines.append("OUTPUT FORMAT:")
        lines.append("")
        lines.append("JSON ONLY. NO prose.")
        lines.append("")
        lines.append(f"For each of [{', '.join(self.ARENA_SYMBOLS)}] output this schema:")
        lines.append("")
        lines.append("{")
        lines.append(' "coin": "...", ')
        lines.append(' "signal": "HOLD|CLOSE|ENTER_LONG|ENTER_SHORT",')
        lines.append(" \"quantity\": <number>, ")
        lines.append(" \"leverage\": <10..20>, ")
        lines.append(" \"profit_target\": <number>, ")
        lines.append(" \"stop_loss\": <number>, ")
        lines.append(" \"invalidation_condition\": \"<string>\", ")
        lines.append(" \"risk_usd\": <number>,")
        lines.append(" \"confidence\": <0..1>")
        lines.append("}")
        lines.append("")
        
        return "\n".join(lines)

