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


# ─── 증권사별 공식 계약명/구현 드라이버 정본 ───────────────────────────────────
# API 상품명과 Python 구현 드라이버를 섞지 않는다. 예를 들어 pykiwoom은
# 키움 OpenAPI+를 호출하는 드라이버이며, XingAPI는 신한이 아니라 LS증권 API다.

SUPPORTED_API_VERSIONS = {
    "kiwoom": {
        "openapi_plus": {
            "pykiwoom": "키움 OpenAPI+ (pykiwoom 드라이버, Windows 전용)",
        },
        "mock": {
            "mock": "테스트/데모용 Mock (API 없이 동작)",
        },
    },
    "shinhan": {
        "partner_rest": {
            "shinhan_openapi_v2": "신한 Open API v2 (제휴 계약 프로필)",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
    "miraeAsset": {
        "partner_rest": {
            "mirae_partner_profile": "미래에셋증권 제휴 API 계약 프로필",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
    "koreaInvestment": {
        "rest": {
            "kis_openapi_v1": "한국투자증권 KIS Developers Open API (REST)",
        },
        "mock": {
            "mock": "테스트/데모용 Mock",
        },
    },
}


# 문자열 조합 등록, 코드 계약 구현, 배포 환경의 실계정 검증을 서로 분리한다.
# live_order_allowed=True는 영구 차단을 해제한다는 뜻이며 실제 주문 가능 여부는
# 전역/증권사 권한과 어댑터 런타임 준비상태를 AND로 다시 판정한다.
STOCK_API_MATURITY = {
    "kiwoom": {
        ("openapi_plus", "pykiwoom"): {
            "status": "implemented",
            "implemented": True,
            "contract_tested": True,
            "live_verified": False,
            "live_order_allowed": True,
            "message": "키움 OpenAPI+ 조회·주문·취소 구현. Windows/OCX/계좌 준비상태를 실행 직전에 확인합니다.",
        },
    },
    "shinhan": {
        ("partner_rest", "shinhan_openapi_v2"): {
            "status": "partner_profile_required",
            "implemented": True,
            "contract_tested": True,
            "live_verified": False,
            "live_order_allowed": True,
            "message": "신한 제휴 계약에서 발급한 URL·채널·엔드포인트 프로필이 필요합니다.",
        },
    },
    "miraeAsset": {
        ("partner_rest", "mirae_partner_profile"): {
            "status": "partner_profile_required",
            "implemented": True,
            "contract_tested": True,
            "live_verified": False,
            "live_order_allowed": True,
            "message": "미래에셋 제휴 계약에서 발급한 URL·인증·엔드포인트 프로필이 필요합니다.",
        },
    },
    "koreaInvestment": {
        ("rest", "kis_openapi_v1"): {
            "status": "implemented",
            "implemented": True,
            "contract_tested": True,
            "live_verified": False,
            "live_order_allowed": True,
            "message": "KIS 공식 REST 계약 구현. 앱키·계좌·실전/모의 서버 준비상태를 실행 직전에 확인합니다.",
        },
    },
}


def _normalize_stock_broker_key(broker: str) -> str:
    broker_text = str(broker or "").strip()
    broker_lower = broker_text.lower()
    if broker_lower in ("miraeasset", "mirae_asset"):
        return "miraeAsset"
    if broker_lower in ("koreainvestment", "korea_investment", "kis"):
        return "koreaInvestment"
    return broker_lower


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
        
        api_type은 증권사별 공식 계약 정본을 사용한다.
          키움: openapi_plus / pykiwoom
          신한: partner_rest / shinhan_openapi_v2
          미래에셋: partner_rest / mirae_partner_profile
          한국투자: rest / kis_openapi_v1
          테스트: mock / mock
        """
        # mirae_asset / miraeasset → miraeAsset 정규화
        broker_key = _normalize_stock_broker_key(exchange_name)
        
        if broker_key not in cls._stock_adapters:
            raise ValueError(f"지원하지 않는 증권 거래소: {exchange_name}")
        
        # 설정에서 api_type 읽기
        broker_config = settings.get('stock_broker_configs', {}).get(broker_key, {})
        default_combo = {
            'kiwoom': ('openapi_plus', 'pykiwoom'),
            'shinhan': ('partner_rest', 'shinhan_openapi_v2'),
            'miraeAsset': ('partner_rest', 'mirae_partner_profile'),
            'koreaInvestment': ('rest', 'kis_openapi_v1'),
        }[broker_key]
        api_type = str(broker_config.get('api_type') or default_combo[0]).lower()
        api_version = (
            'mock' if api_type == 'mock'
            else str(broker_config.get('api_version') or default_combo[1]).lower()
        )

        # api_type/api_version 조합 방어 검증 (공용 함수 사용)
        ok, err = cls.validate_stock_broker_api_combo(broker_key, api_type, api_version)
        if not ok:
            raise ValueError(err)

        # mock 이면 api_version 자동 채움
        if api_type == 'mock' and not api_version:
            api_version = 'mock'

        maturity = cls.get_stock_broker_api_maturity(broker_key, api_type, api_version)
        if not maturity.get('implemented', False):
            raise ValueError(
                f"{broker_key}: {api_type}/{api_version} 경로 미구현 - "
                f"{maturity.get('message', '사용할 수 없는 API 경로입니다.')}"
            )

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
            sandbox=bool(broker_config.get('sandbox', False)),
            partner_profile=dict(broker_config.get('partner_profile', {}) or {}),
        )
    
    @classmethod
    def get_supported_api_versions(cls, broker: str) -> Dict[str, Any]:
        """증권사별 지원 API 버전 목록 반환"""
        return SUPPORTED_API_VERSIONS.get(_normalize_stock_broker_key(broker), {})

    @classmethod
    def get_stock_broker_api_maturity(
        cls, broker: str, api_type: str, api_version: str
    ) -> Dict[str, Any]:
        """등록 여부와 별개인 증권 API 구현·검증 성숙도 계약을 반환한다."""
        broker_key = _normalize_stock_broker_key(broker)
        api_type_norm = str(api_type or '').strip().lower()
        api_version_norm = str(api_version or '').strip().lower()

        if api_type_norm == 'mock':
            return {
                "status": "test_only",
                "implemented": True,
                "contract_tested": True,
                "live_verified": False,
                "live_order_allowed": False,
                "message": "Mock 테스트/데모 전용이며 실제 주문을 전송하지 않습니다.",
            }

        maturity = STOCK_API_MATURITY.get(broker_key, {}).get(
            (api_type_norm, api_version_norm)
        )
        if maturity is not None:
            return dict(maturity)

        return {
            "status": "unregistered",
            "implemented": False,
            "contract_tested": False,
            "live_verified": False,
            "live_order_allowed": False,
            "message": "등록되거나 검증된 API 성숙도 계약이 없습니다.",
        }

    @classmethod
    def evaluate_stock_live_order_permission(
        cls,
        broker: str,
        api_type: str,
        api_version: str,
        global_live_flag: bool,
        broker_live_flag: bool,
        adapter_ready: Optional[bool] = None,
        adapter_ready_reason: str = '',
    ) -> tuple:
        """대시보드·진단 도구가 공유하는 증권 실주문 실패 폐쇄 게이트."""
        api_type_norm = str(api_type or 'openapi').strip().lower()
        if api_type_norm == 'mock':
            return True, ''

        maturity = cls.get_stock_broker_api_maturity(
            broker, api_type_norm, api_version
        )
        if not maturity.get('live_order_allowed', False):
            status = maturity.get('status', 'unverified')
            detail = maturity.get('message', '실계정 주문 검증 전입니다.')
            return False, f'실주문 차단 [{status}]: {detail}'

        if not bool(global_live_flag):
            return False, '실주문 차단: 전역 enable_stock_live_order가 꺼져 있습니다.'
        if not bool(broker_live_flag):
            return False, f'실주문 차단: {broker} 증권사의 allow_live_order가 꺼져 있습니다.'
        if adapter_ready is False:
            return False, f'실주문 준비 미완료: {adapter_ready_reason or "증권사 API 연결 설정을 확인하세요."}'
        return True, ''
    
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
        broker_key = _normalize_stock_broker_key(broker)

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
