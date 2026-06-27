#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코인 선택 로직 전체 테스트 (Evaluator 실제 로직 포함)

API 키 불필요, 실제 거래 없음 (설정 기반 테스트)

사용법:
  python scripts/test_coin_selection_full.py                    # Binance 기본 테스트
  python scripts/test_coin_selection_full.py --exchange bitget  # Bitget 테스트
  python scripts/test_coin_selection_full.py --major 10 --alt 20 # 커스텀 수량
"""

import sys
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# 프로젝트 루트 설정
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

# 로깅 설정 (사이런스)
logging.basicConfig(level=logging.ERROR)

# ============================================================================
# 1. 도구 함수들
# ============================================================================

def load_settings_safe() -> Dict[str, Any]:
    """
    설정 파일 안전 로드 (오류 시 기본값 사용)
    
    Returns:
        설정 딕셔너리
    """
    from config.settings import load_settings
    
    try:
        loaded = load_settings()
        # 현재 구현은 dict를 반환하지만, 과거/변형 구현의 tuple 반환도 호환
        if isinstance(loaded, tuple):
            return loaded[0] if loaded else {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception as e:
        print(f"⚠️ 설정 로드 실패: {e}")
        return {}


def create_public_futures_client(exchange: str):
    """API 키 없이 공개 CCXT 데이터로 선물 후보 분석용 클라이언트 생성."""
    try:
        import importlib

        ccxt = importlib.import_module('ccxt')
        ex_name = str(exchange or '').lower()

        if ex_name not in ('bitget', 'bybit', 'okx'):
            return None

        ex_class = getattr(ccxt, ex_name, None)
        if ex_class is None:
            print(f"⚠️ CCXT 거래소 클래스 없음: {ex_name}")
            return None

        ex = ex_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'},
        })
        ex.load_markets()

        class _PublicFuturesClient:
            def __init__(self, exchange_name: str, ccxt_exchange):
                self.exchange_name = exchange_name
                self.exchange = ccxt_exchange

            def get_markets(self):
                return getattr(self.exchange, 'markets', {}) or {}

            def get_24h_ticker(self, symbol: str):
                t = self.exchange.fetch_ticker(symbol)
                quote_volume = float(t.get('quoteVolume') or 0)
                if quote_volume <= 0:
                    last = float(t.get('last') or 0)
                    base_vol = float(t.get('baseVolume') or 0)
                    quote_volume = last * base_vol if last > 0 and base_vol > 0 else 0
                return {
                    'symbol': symbol,
                    'quoteVolume': quote_volume,
                    'percentage': float(t.get('percentage') or 0),
                    'last': float(t.get('last') or 0),
                    'high': float(t.get('high') or 0),
                    'low': float(t.get('low') or 0),
                }

        return _PublicFuturesClient(ex_name, ex)
    except Exception as e:
        print(f"⚠️ 공개 선물 클라이언트 생성 실패({exchange}): {e}")
        return None


def create_binance_compatible_data_client(public_client):
    """Evaluator 내부의 binance_client 호출을 만족시키는 호환 래퍼."""
    if not public_client or not hasattr(public_client, 'exchange'):
        return None

    ex = public_client.exchange

    class _BinanceCompatibleDataClient:
        def __init__(self, ccxt_exchange):
            self._ex = ccxt_exchange

        def _to_ccxt_symbol(self, symbol: str) -> str:
            raw = str(symbol or '').upper()
            if '/' in raw:
                return raw
            base = raw.replace(':USDT', '').replace('USDT', '')
            if not base:
                return raw
            return f"{base}/USDT:USDT"

        def _to_compact_symbol(self, symbol: str) -> str:
            s = str(symbol or '').upper().replace('/', '').replace(':', '')
            return s

        def get_klines(self, symbol: str, interval: str, limit: int = 100):
            try:
                ccxt_symbol = self._to_ccxt_symbol(symbol)
                return self._ex.fetch_ohlcv(ccxt_symbol, timeframe=interval, limit=limit) or []
            except Exception:
                return []

        def get_multiple_klines(self, symbols, interval: str, limit: int = 100):
            result = {}
            for s in symbols or []:
                result[s] = self.get_klines(s, interval, limit)
            return result

        def get_all_24h_tickers(self):
            try:
                tickers = self._ex.fetch_tickers() or {}
                out = []
                for sym, t in tickers.items():
                    compact = self._to_compact_symbol(sym)
                    qv = float(t.get('quoteVolume') or 0)
                    if qv <= 0:
                        last = float(t.get('last') or 0)
                        bv = float(t.get('baseVolume') or 0)
                        qv = last * bv if last > 0 and bv > 0 else 0
                    out.append({
                        'symbol': compact,
                        'quoteVolume': qv,
                        'volume': float(t.get('baseVolume') or 0),
                        'count': 0,
                        'priceChange': float(t.get('change') or 0),
                        'priceChangePercent': float(t.get('percentage') or 0),
                    })
                return out
            except Exception:
                return []

        def get_ticker(self, symbol: str):
            try:
                ccxt_symbol = self._to_ccxt_symbol(symbol)
                t = self._ex.fetch_ticker(ccxt_symbol)
                qv = float(t.get('quoteVolume') or 0)
                if qv <= 0:
                    last = float(t.get('last') or 0)
                    bv = float(t.get('baseVolume') or 0)
                    qv = last * bv if last > 0 and bv > 0 else 0
                return {
                    'symbol': self._to_compact_symbol(symbol),
                    'lastPrice': float(t.get('last') or 0),
                    'quoteVolume': qv,
                    'priceChangePercent': float(t.get('percentage') or 0),
                }
            except Exception:
                return None

    return _BinanceCompatibleDataClient(ex)


def test_coin_selection_simple(exchange: str = 'binance', num_major: int = 5, num_alt: int = 15):
    """
    간단한 코인 선택 테스트 (실제 Evaluator 없이 설정값 기반)
    
    Args:
        exchange: 거래소명 (binance/bitget/bybit/okx 등)
        num_major: 주요 코인 개수
        num_alt: 알트 코인 개수
    """
    print("\n" + "=" * 80)
    print("📊 코인 선택 로직 테스트 (간단 버전)")
    print("=" * 80)
    print(f"🏦 거래소: {exchange.upper()}")
    print(f"🎯 주요 코인: {num_major}개, 알트 코인: {num_alt}개")
    print("-" * 80)
    
    try:
        settings = load_settings_safe()
        print("✅ 설정 파일 로드 완료")
        
        # 기본 코인 목록 (실제 선택 로직)
        major_coins = {
            'binance': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT'],
            'bitget': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ARBUSDT', 'OPUSDT'],
            'bybit': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT'],
            'okx': ['BTCUSDT', 'ETHUSDT', 'LTCUSDT', 'ETCUSDT', 'XLMUSDT'],
        }
        
        alt_coins = {
            'binance': ['SOLUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT', 'ARBUSDT', 'OPUSDT', 'APTUSDT', 'MATICUSDT', 'FETUSDT', 'GRTUSDT', 'ENSUSDT', 'DYDXUSDT', 'TURBOUSDT', 'ONDOUSDT'],
            'bitget': ['ETHUSDT', 'AVAXUSDT', 'FTMUSDT', 'DOGUSDT', 'APEUSDT', 'SANDUSDT', 'GALAUSTD', 'LOOKSUSDT', 'MAGICUSDT', 'ROUGHUSDT', 'LOOMUSDT', 'COREUSDT', 'TURBOUSDT', 'ONDOUSDT', 'ETHFUSDT'],
            'bybit': ['AVAXUSDT', 'FTMUSDT', 'INJUSDT', 'SUIUSDT', 'APEUSDT', 'LINKUSDT', 'TURBOUSDT', 'ONDOUSDT', 'GMXUSDT', 'MAGICUSDT', 'LOOMUSDT', 'ROUGHUSDT', 'KASUSDT', 'PYUSDT', 'PEPEUSDT'],
            'okx': ['SOLUSDT', 'FTMUSDT', 'ATOMUSDT', 'AVAXUSDT', 'LINKUSDT', 'SANDUSDT', 'ENUSDT', 'LOOMUSDT', 'STORJUSDT', 'EGLDUUSDT', 'VETUSDT', 'HNTUSDT', 'ICXUSDT', 'OCEANUSDT', 'TURBOUSDT'],
        }
        
        exc_lower = exchange.lower()
        major_pool = major_coins.get(exc_lower, major_coins['binance'])
        alt_pool = alt_coins.get(exc_lower, alt_coins['binance'])
        
        selected_major = major_pool[:num_major]
        selected_alt = alt_pool[:num_alt]
        
        print(f"\n🎲 코인 선택 완료:")
        print(f"   주요 코인 수: {len(selected_major)}")
        print(f"   알트 코인 수: {len(selected_alt)}")
        print(f"   총 코인 수: {len(selected_major) + len(selected_alt)}")
        
        print(f"\n🟡 주요 코인 ({len(selected_major)}개):")
        for i, coin in enumerate(selected_major, 1):
            print(f"   {i}. {coin}")
        
        print(f"\n🔵 알트 코인 ({len(selected_alt)}개):")
        for i, coin in enumerate(selected_alt, 1):
            print(f"   {i}. {coin}")
        
        # JSON 저장
        output_file = ROOT / "data" / "test_coin_selection_simple.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'exchange': exchange,
                'num_major': len(selected_major),
                'num_alt': len(selected_alt),
                'major_coins': selected_major,
                'alt_coins': selected_alt,
                'total_coins': len(selected_major) + len(selected_alt),
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 결과 저장: {output_file}")
        return selected_major + selected_alt
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_coin_selection_with_evaluator(exchange: str = 'binance', num_major: int = 5, num_alt: int = 15):
    """
    실제 Evaluator 로직을 사용한 코인 선택 테스트
    
    Args:
        exchange: 거래소명
        num_major: 주요 코인 개수
        num_alt: 알트 코인 개수
    """
    print("\n" + "=" * 80)
    print("📊 코인 선택 로직 테스트 (Evaluator 포함)")
    print("=" * 80)
    print(f"🏦 거래소: {exchange.upper()}")
    print(f"🎯 주요 코인: {num_major}개, 알트 코인: {num_alt}개")
    print("-" * 80)
    
    try:
        settings = load_settings_safe()
        
        # Analyzer, Recorder, Evaluator 초기화
        print("✅ 핵심 모듈 초기화 중...")
        
        from trading.analyzer import Analyzer
        from trading.recorder import Recorder
        from trading.evaluator import Evaluator
        
        # Analyzer 초기화 (비바이낸스는 evaluator의 CCXT 분기에서 exchange_client 사용)
        analyzer = Analyzer(binance_client=None, exchange_manager=None)
        print("✅ Analyzer 준비 완료")
        
        # Recorder 초기화
        recorder = Recorder(
            db_path=None,
            log_path=None,
            binance_client=None,
            exchange=exchange
        )
        print("✅ Recorder 준비 완료")
        
        # Evaluator 초기화 (핵심 모듈!)
        evaluator = Evaluator(
            analyzer=analyzer,
            recorder=recorder,
            settings=settings
        )
        print("✅ Evaluator 준비 완료")
        
        # 비바이낸스 선물 거래소는 공개 CCXT 클라이언트로 분석 가능
        exchange_client = None
        compatible_data_client = None
        if exchange.lower() in ('bitget', 'bybit', 'okx'):
            exchange_client = create_public_futures_client(exchange)
            if exchange_client:
                print(f"✅ {exchange.upper()} 공개 CCXT 클라이언트 준비 완료")
                compatible_data_client = create_binance_compatible_data_client(exchange_client)
                if compatible_data_client:
                    analyzer.binance_client = compatible_data_client
                    evaluator.binance_client = compatible_data_client
                    print("✅ Evaluator 내부 데이터 클라이언트 연결 완료")
            else:
                print(f"⚠️ {exchange.upper()} 공개 CCXT 클라이언트 준비 실패 - 폴백 경로 사용")

        # 코인 선택 실행
        print(f"\n🎲 코인 선택 중...")
        selected_coins = evaluator.select_trading_coins(
            num_alt=num_alt,
            num_major=num_major,
            regime=None,  # 자동 감지
            exchange=exchange,
            exchange_client=exchange_client
        )
        
        if selected_coins:
            print(f"✅ 선택 완료: {len(selected_coins)}개 코인")
            
            # 결과 출력 (선택된 코인이 문자열일 수 있음)
            coins_data = []
            for i, coin_info in enumerate(selected_coins, 1):
                # Evaluator는 심볼 문자열 또는 딕셔너리를 반환할 수 있음
                if isinstance(coin_info, dict):
                    symbol = coin_info.get('symbol', 'UNKNOWN')
                    category = coin_info.get('category', 'unknown')
                    confidence = coin_info.get('confidence', 0.0)
                    print(f"   {i}. {symbol} ({category}) [신뢰도: {confidence:.1%}]")
                    coins_data.append(coin_info)
                else:
                    symbol = str(coin_info)
                    print(f"   {i}. {symbol}")
                    coins_data.append({'symbol': symbol})
            
            # JSON 저장
            output_file = ROOT / "data" / "test_coin_selection_full.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'exchange': exchange,
                    'total_coins': len(selected_coins),
                    'coins': coins_data,
                }, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"\n💾 결과 저장: {output_file}")
            return selected_coins
        else:
            print("❌ 코인 선택 실패")
            return None
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        print("\n💡 힌트: Evaluator 초기화 실패 시 간단 버전을 사용하세요")
        return None


# ============================================================================
# 2. 메인 함수
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='코인 선택 로직 테스트 (거래소 연결 불필요)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
    # Binance 코인 선택 테스트 (간단 버전)
    python3 scripts/test_coin_selection_full.py
  
  # Bitget 코인 선택 테스트 (간단 버전)
    python3 scripts/test_coin_selection_full.py --exchange bitget
  
  # 실제 Evaluator로 테스트 (고급)
  python3 scripts/test_coin_selection_full.py --evaluator
  
  # 주요 10개, 알트 20개로 테스트
  python3 scripts/test_coin_selection_full.py --major 10 --alt 20
        """
    )
    
    parser.add_argument('--exchange', default='binance', 
                       choices=['binance', 'bitget', 'bybit', 'okx', 'upbit', 'bithumb'],
                       help='거래소 선택 (기본: binance)')
    parser.add_argument('--major', type=int, default=5,
                       help='주요 코인 개수 (기본: 5)')
    parser.add_argument('--alt', type=int, default=15,
                       help='알트 코인 개수 (기본: 15)')
    parser.add_argument('--evaluator', action='store_true',
                       help='실제 Evaluator 모듈 사용 (기본: 간단 버전)')
    
    args = parser.parse_args()
    
    if args.evaluator:
        test_coin_selection_with_evaluator(
            exchange=args.exchange,
            num_major=args.major,
            num_alt=args.alt
        )
    else:
        test_coin_selection_simple(
            exchange=args.exchange,
            num_major=args.major,
            num_alt=args.alt
        )


if __name__ == '__main__':
    main()
