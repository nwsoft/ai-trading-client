#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
통합 거래소 팩토리 클래스
"""

from typing import Dict, Any, Optional
from .interfaces.exchange_interface import ExchangeInterface
from .interfaces.futures_exchange import FuturesExchange
from .interfaces.spot_exchange import SpotExchange
from .interfaces.stock_exchange import StockExchange
from .adapters.binance_futures_adapter import BinanceFuturesAdapter
from .adapters.bybit_futures_adapter import BybitFuturesAdapter
from .adapters.okx_futures_adapter import OkxFuturesAdapter
from .adapters.bitget_futures_adapter import BitgetFuturesAdapter
from .adapters.upbit_spot_adapter import UpbitSpotAdapter
from .adapters.bithumb_spot_adapter import BithumbSpotAdapter
from .adapters.kiwoom_stock_adapter import KiwoomStockAdapter
from .adapters.shinhan_stock_adapter import ShinhanStockAdapter
from .adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
from .adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
from .adapters.stock_mock_adapter import StockMockAdapter


# ─── 증권사별 지원 API 버전 정의 ────────────────────────────────────────────────
# api_type/api_version은 settings.json > stock_broker_configs.[broker].api_type 에서 읽음
#
# 키움증권:
#   openapi  / pykiwoom    - pykiwoom 라이브러리 (PyQt5 기반, Windows 전용)
#   openapi  / kiwoom_api  - kiwoom-api 라이브러리 (비공식 래퍼)
#   openapi  / cybos       - 대신증권 CYBOS Plus (별도)
#   mock                   - 테스트/데모용 Mock
#
# 신한증권:
#   openapi  / solapi      - SolAPI (REST 기반)
#   openapi  / xingapi     - LS증권 XingAPI 호환
#   mock                   - 테스트/데모용 Mock
#
# 미래에셋:
#   openapi  / miraemts    - 미래에셋 MTS OpenAPI
#   openapi  / kis         - 한국투자증권 KIS Developers (REST)
#   mock                   - 테스트/데모용 Mock
#
# 한국투자증권:
#   rest     / kis         - 한국투자증권 KIS Developers (REST)
#   openapi  / kis         - 내부 통일 표기(실제 REST 처리)
#   mock                   - 테스트/데모용 Mock

SUPPORTED_API_VERSIONS = {
    "kiwoom": {
        "openapi": {
            "pykiwoom":   "pykiwoom 라이브러리 (PyQt5 기반, Windows 전용)",
            "kiwoom_api": "kiwoom-api 비공식 래퍼",
        },
        "mock": {
            "mock": "테스트/데모용 Mock (API 없이 동작)",
        },
    },
    "shinhan": {
        "openapi": {
            "solapi":   "신한금융투자 SolAPI (REST)",
            "xingapi":  "LS증권 XingAPI 호환 모드",
        },
        "rest": {
            "solapi_rest": "신한금융투자 SolAPI REST v2",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
    "miraeAsset": {
        "openapi": {
            "miraemts":  "미래에셋 MTS OpenAPI",
            "miraedaas": "미래에셋 DaaS OpenAPI",
            "kis": "KIS REST 호환 경로(레거시 호환)",
        },
        "rest": {
            "kis": "한국투자증권 KIS Developers (REST, 미래에셋 계열)",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
    "koreaInvestment": {
        "rest": {
            "kis": "한국투자증권 KIS Developers (REST)",
        },
        "openapi": {
            "kis": "내부 통일 표기(실제 REST 처리)",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
}


class ExchangeFactory:
    """통합 거래소 팩토리 클래스"""
    
    _futures_adapters = {
        'binance': BinanceFuturesAdapter,
        'bybit': BybitFuturesAdapter,
        'okx': OkxFuturesAdapter,
        'bitget': BitgetFuturesAdapter,
    }
    
    _spot_adapters = {
        'upbit': UpbitSpotAdapter,
        'bithumb': BithumbSpotAdapter,
    }
    
    _stock_adapters = {
        'kiwoom': KiwoomStockAdapter,
        'shinhan': ShinhanStockAdapter,
        'miraeAsset': MiraeAssetStockAdapter,
        'koreaInvestment': KoreaInvestmentStockAdapter,
    }
    
    @classmethod
    def create_futures_exchange(cls, exchange_name: str, settings: Dict[str, Any]) -> Optional[FuturesExchange]:
        """선물 거래소 생성"""
        if exchange_name not in cls._futures_adapters:
            raise ValueError(f"지원하지 않는 선물 거래소: {exchange_name}")
        
        adapter_class = cls._futures_adapters[exchange_name]
        api_key = settings.get(f'{exchange_name}_api_key', '')
        secret_key = settings.get(f'{exchange_name}_secret_key', '')
        
        if exchange_name == 'binance':
            testnet = settings.get('use_testnet', False)
            return adapter_class(api_key, secret_key, testnet=testnet)
        elif exchange_name == 'okx':
            passphrase = settings.get('okx_passphrase', '')
            return adapter_class(api_key, secret_key, passphrase)
        elif exchange_name == 'bitget':
            password = settings.get('bitget_password', '')
            return adapter_class(api_key, secret_key, password)
        else:
            return adapter_class(api_key, secret_key)
    
    @classmethod
    def create_spot_exchange(cls, exchange_name: str, settings: Dict[str, Any]) -> Optional[SpotExchange]:
        """현물 거래소 생성"""
        if exchange_name not in cls._spot_adapters:
            raise ValueError(f"지원하지 않는 현물 거래소: {exchange_name}")
        
        adapter_class = cls._spot_adapters[exchange_name]
        api_key = settings.get(f'{exchange_name}_api_key', '')
        secret_key = settings.get(f'{exchange_name}_secret_key', '')
        
        return adapter_class(api_key, secret_key)
    
    @classmethod
    def create_stock_exchange(cls, exchange_name: str, settings: Dict[str, Any]) -> Optional[StockExchange]:
        """
        증권 거래소 생성 (주식/ETF)
        
        api_type 우선순위:
          1. settings.stock_broker_configs.[broker].api_type
          2. 기본값 = "openapi"
        
        api_type 값:
          "mock"    → StockMockAdapter (API 없이 테스트/데모)
          "openapi" → 각 증권사 실제 어댑터 (API 필요)
          "rest"    → REST 기반 어댑터 (각 증권사별)
        """
        # mirae_asset / miraeasset → miraeAsset 정규화
        broker_key = exchange_name
        exchange_name_lower = exchange_name.lower()
        if exchange_name_lower in ('miraeasset', 'mirae_asset'):
            broker_key = 'miraeAsset'
        elif exchange_name_lower in ('koreainvestment', 'korea_investment', 'kis'):
            broker_key = 'koreaInvestment'
        
        if broker_key not in cls._stock_adapters:
            raise ValueError(f"지원하지 않는 증권 거래소: {exchange_name}")
        
        # 설정에서 api_type 읽기
        broker_config = settings.get('stock_broker_configs', {}).get(broker_key, {})
        api_type = broker_config.get('api_type', 'openapi').lower()
        api_version = broker_config.get('api_version', '')

        # api_type/api_version 조합 방어 검증 (공용 함수 사용)
        ok, err = cls.validate_stock_broker_api_combo(broker_key, api_type, api_version)
        if not ok:
            raise ValueError(err)

        # mock 이면 api_version 자동 채움
        if api_type == 'mock' and not api_version:
            api_version = 'mock'

        user_id      = broker_config.get('id', '')
        password     = broker_config.get('password', '')
        cert_password = broker_config.get('cert_password', '')
        account_no   = broker_config.get('account_no', '')
        # REST 계열 증권사는 app_key/app_secret 우선, 없으면 기존 id/password를 폴백으로 사용한다.
        app_key = broker_config.get('app_key', '') or user_id
        app_secret = broker_config.get('app_secret', '') or password
        
        # ── Mock 모드 ──────────────────────────────────────────────────────────
        if api_type == 'mock':
            return StockMockAdapter(
                broker_name=broker_key,
                user_id=user_id,
                password=password,
                cert_password=cert_password,
                account_no=account_no,
                api_type=api_type,
                api_version=api_version,
            )
        
        # ── 실제 어댑터 (openapi / rest) ────────────────────────────────────────
        adapter_class = cls._stock_adapters[broker_key]
        return adapter_class(
            user_id,
            password,
            cert_password,
            account_no,
            api_type=api_type,
            api_version=api_version,
            app_key=app_key,
            app_secret=app_secret,
        )
    
    @classmethod
    def get_supported_api_versions(cls, broker: str) -> Dict[str, Any]:
        """증권사별 지원 API 버전 목록 반환"""
        return SUPPORTED_API_VERSIONS.get(broker, {})
    
    @classmethod
    def create_exchange(cls, exchange_name: str, trading_type: str, settings: Dict[str, Any]) -> Optional[ExchangeInterface]:
        """거래소 생성 (자동 타입 감지)"""
        if trading_type == 'futures':
            return cls.create_futures_exchange(exchange_name, settings)
        elif trading_type == 'spot':
            return cls.create_spot_exchange(exchange_name, settings)
        elif trading_type == 'stock':
            return cls.create_stock_exchange(exchange_name, settings)
        else:
            raise ValueError(f"지원하지 않는 거래 유형: {trading_type}")
    
    @classmethod
    def get_supported_exchanges(cls) -> Dict[str, list]:
        """지원하는 거래소 목록 반환"""
        return {
            'futures': list(cls._futures_adapters.keys()),
            'spot': list(cls._spot_adapters.keys()),
            'stock': list(cls._stock_adapters.keys())
        }
        
    @classmethod
    def validate_exchange_settings(cls, exchange_name: str, trading_type: str, settings: Dict[str, Any]) -> bool:
        """거래소 설정 유효성 검증"""
        exchange_name = exchange_name.lower()
        
        if exchange_name == 'binance':
            return bool(settings.get('binance_api_key') and settings.get('binance_secret_key'))
        elif exchange_name == 'upbit':
            return bool(settings.get('upbit_api_key') and settings.get('upbit_secret_key'))
        elif exchange_name == 'bithumb':
            return bool(settings.get('bithumb_api_key') and settings.get('bithumb_secret_key'))
            
        return False

    @classmethod
    def validate_stock_broker_api_combo(
        cls, broker: str, api_type: str, api_version: str
    ) -> tuple:
        """증권사 api_type/api_version 조합 검증.

        Returns:
            (ok: bool, error_message: str)  — ok=True 이면 error_message는 빈 문자열
        """
        # broker 정규화
        broker_key = broker
        if broker.lower() in ('miraeasset', 'mirae_asset'):
            broker_key = 'miraeAsset'
        elif broker.lower() in ('koreainvestment', 'korea_investment', 'kis'):
            broker_key = 'koreaInvestment'

        supported_types = SUPPORTED_API_VERSIONS.get(broker_key)
        if not supported_types:
            return False, f"'{broker_key}'는 등록되지 않은 증권사입니다."

        api_type_norm = (api_type or '').strip().lower()
        supported_versions = supported_types.get(api_type_norm)
        if not isinstance(supported_versions, dict):
            supported = ', '.join(sorted(supported_types.keys()))
            return False, (
                f"{broker_key}: api_type '{api_type_norm}' 미지원 (지원: {supported})"
            )

        # mock 이면 api_version 자동 채움 허용
        if api_type_norm == 'mock':
            return True, ""

        api_version_norm = (api_version or '').strip().lower()
        if not api_version_norm:
            supported_v = ', '.join(sorted(supported_versions.keys()))
            return False, (
                f"{broker_key}: api_version 누락 "
                f"(api_type={api_type_norm}, 지원: {supported_v})"
            )

        if api_version_norm not in supported_versions:
            supported_v = ', '.join(sorted(supported_versions.keys()))
            return False, (
                f"{broker_key}: api_version '{api_version_norm}' 미지원 "
                f"(api_type={api_type_norm}, 지원: {supported_v})"
            )

        return True, ""
