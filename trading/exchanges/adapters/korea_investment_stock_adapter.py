#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 주식/ETF 어댑터

현재 구현은 KIS REST 계열 공통 경로를 재사용한다.
미래에셋 어댑터와 동일한 REST 호출/파싱 흐름을 사용하되,
브로커 식별자/기본 API 버전/기본 URL을 한국투자증권 기준으로 분리한다.
"""

from .mirae_asset_stock_adapter import MiraeAssetStockAdapter

_KOREA_INVESTMENT_BASE_URL = "https://openapi.koreainvestment.com:9443"
_KOREA_INVESTMENT_SANDBOX_URL = "https://openapivts.koreainvestment.com:29443"


class KoreaInvestmentStockAdapter(MiraeAssetStockAdapter):
    """한국투자증권(KIS) 주식/ETF 어댑터."""

    def __init__(self, user_id: str, password: str, cert_password: str = "", account_no: str = "", **kwargs):
        if "api_type" not in kwargs:
            kwargs["api_type"] = "rest"
        if "api_version" not in kwargs:
            kwargs["api_version"] = "kis"

        super().__init__(user_id, password, cert_password, account_no, **kwargs)

        # 상위 클래스가 세팅한 브로커명을 한국투자증권으로 교체
        self.exchange_name = "koreaInvestment"

        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level="INFO": log_event(
            category, msg, exchange="koreaInvestment", level=level
        )

    def _base_url(self) -> str:
        return _KOREA_INVESTMENT_SANDBOX_URL if self.sandbox else _KOREA_INVESTMENT_BASE_URL
