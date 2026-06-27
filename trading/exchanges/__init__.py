#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래소 모듈 패키지
"""

"""
주의: 이 패키지의 __init__에서 무거운 의존성을 강제 임포트하지 않습니다.
python-binance(모듈명 'binance') 미설치 환경에서도 어댑터/인터페이스 임포트가 가능해야 합니다.
필요 시 각 모듈에서 직접 임포트하세요.
"""

__all__ = [
    'BaseExchange',
]
