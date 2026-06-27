"""
프로젝트 로깅 모듈
🔥 주의: 이 폴더명이 Python 표준 라이브러리 'logging'과 충돌하지 않도록 처리
"""

# Python 표준 logging 모듈을 명시적으로 import하여 다른 곳에서도 사용 가능하게
import sys
import logging as stdlib_logging  # 표준 라이브러리를 별칭으로 저장

# 표준 logging 모듈을 다시 export (다른 모듈에서 사용 가능하도록)
__all__ = ['log_adapter', 'log_stream']