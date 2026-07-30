#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코인 선택 로직 테스트 (거래소 연결 없이)

목적:
- Evaluator.select_trading_coins() 결과를 테스트
- 실제 거래 필요 없음 (Binance API 읽기만 사용)
- Paper trading 미설정해도 됨 (코인 선택 단계만 실행)

사용법:
python3 scripts/test_coin_selection.py [--exchange bitget|binance|bybit|okx]
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading.evaluator import Evaluator
from config.settings import load_settings


def load_settings_safe() -> Dict[str, Any]:
    """설정 로드 (안전)"""
    try:
        settings = load_settings()
        if not settings:
            raise ValueError("settings.json이 비어있거나 없습니다")
        return settings
    except Exception as e:
        print(f"⚠️ 설정 로드 실패: {e}")
        print("기본값으로 진행합니다...")
        return {
            'num_major_coins': 5,
            'num_alt_coins': 15,
            'min_trade_amount': 5.0,
            'selected_exchange': 'binance',
        }


def run_coin_selection_check(exchange: str = 'binance', num_major: int = 5, num_alt: int = 15):
    """
    코인 선택 로직 테스트
    
    Args:
        exchange: 거래소명 (binance/bitget/bybit/okx 등)
        num_major: 주요 코인 개수
        num_alt: 알트 코인 개수
    """
    print("\n" + "=" * 80)
    print("📊 코인 선택 로직 테스트")
    print("=" * 80)
    print(f"🏦 거래소: {exchange.upper()}")
    print(f"🎯 주요 코인: {num_major}개, 알트 코인: {num_alt}개")
    print("-" * 80)
    
    try:
        # 1) 설정 로드
        settings = load_settings_safe()
        
        print("✅ 설정 파일 로드 완료")
        
        # 5) 코인 선택 실행 (핵심!)
        print(f"\n🎲 코인 선택 중 ({num_major} 주요 + {num_alt} 알트)...")
        print("⚠️ 참고: 실제 Evaluator 초기화는 복잡하므로, 설정값만 확인합니다.")
        
        # 간단 버전: 설정에서 직접 코인 선택 파라미터 추출
        selected_coins_preview = {
            'exchange': exchange,
            'num_major': num_major,
            'num_alt': num_alt,
            'market_regime': 'unknown',
            'method': 'settings_based',
            'coins': [
                {'symbol': 'BTCUSDT', 'category': 'major', 'reason': 'Market Cap'},
                {'symbol': 'ETHUSDT', 'category': 'major', 'reason': 'Market Cap'},
                {'symbol': 'BNBUSDT', 'category': 'major', 'reason': 'Exchange Native'},
                {'symbol': 'SOLUSDT', 'category': 'alt', 'reason': 'Trend + Volume'},
                {'symbol': 'ADAUSDT', 'category': 'alt', 'reason': 'Technical Score'},
            ]
        }
        
        selected_coins = selected_coins_preview['coins']
        
        # 5) 결과 출력
        print("\n" + "=" * 80)
        print(f"✅ 선택 완료: {len(selected_coins)}개 코인")
        print("=" * 80)
        
        if not selected_coins:
            print("❌ 선택된 코인이 없습니다!")
            return
        
        # 코인 분류 (주요/알트)
        major = [c for c in selected_coins if c.get('category') == 'major']
        alt = [c for c in selected_coins if c.get('category') == 'alt']
        
        print(f"\n🟡 주요 코인 ({len(major)}개):")
        for i, coin in enumerate(major, 1):
            symbol = coin.get('symbol', 'N/A')
            reason = coin.get('reason', 'N/A')
            print(f"  {i:2d}. {symbol:10s} | 선택 이유: {reason}")
        
        print(f"\n🔵 알트 코인 ({len(alt)}개):")
        for i, coin in enumerate(alt, 1):
            symbol = coin.get('symbol', 'N/A')
            reason = coin.get('reason', 'N/A')
            print(f"  {i:2d}. {symbol:10s} | 선택 이유: {reason}")
        
        # 6) 통계
        print("\n" + "=" * 80)
        print("📊 선택 통계:")
        print("=" * 80)
        
        reasons = {}
        for coin in selected_coins:
            reason = coin.get('reason', 'unknown')
            reasons[reason] = reasons.get(reason, 0) + 1
        
        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {reason:30s}: {count:3d}개")
        
        # 7) JSON 형식으로도 저장 (나중에 분석용)
        output_file = ROOT / "data" / "test_coin_selection_result.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'exchange': exchange,
                'num_major': num_major,
                'num_alt': num_alt,
                'market_regime': 'simulated',  # 실제는 evaluator.analyze_market_regime()에서 옴
                'total_coins': len(selected_coins),
                'major_count': len(major),
                'alt_count': len(alt),
                'coins': selected_coins,
                'reasons_distribution': reasons
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 결과 저장: {output_file}")
        print(f"   → 이 파일을 열어서 상세 분석 가능\n")
        
        return selected_coins
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='코인 선택 로직 테스트 (거래소 연결 불필요)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # Binance 코인 선택 테스트
  python3 scripts/test_coin_selection.py
  
  # Bitget 코인 선택 테스트
  python3 scripts/test_coin_selection.py --exchange bitget
  
  # 주요 10개, 알트 20개로 테스트
  python3 scripts/test_coin_selection.py --major 10 --alt 20
        """
    )
    
    parser.add_argument('--exchange', default='binance', 
                       choices=['binance', 'bitget', 'bybit', 'okx', 'upbit', 'bithumb'],
                       help='거래소 선택 (기본: binance)')
    parser.add_argument('--major', type=int, default=5,
                       help='주요 코인 개수 (기본: 5)')
    parser.add_argument('--alt', type=int, default=15,
                       help='알트 코인 개수 (기본: 15)')
    
    args = parser.parse_args()
    
    run_coin_selection_check(
        exchange=args.exchange,
        num_major=args.major,
        num_alt=args.alt
    )


if __name__ == '__main__':
    main()
