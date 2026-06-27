#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""무키(mock) 기반 증권 고도화 회귀 테스트.

실계정 키 없이도 증권 4사 공통 경로가 정상 동작하는지 검증한다.
"""

from trading.exchanges.exchange_factory import ExchangeFactory
from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter


def _mock_settings_for(broker: str) -> dict:
    return {
        "enabled_stock_brokers": [broker],
        "stock_broker_configs": {
            broker: {
                "enabled": True,
                "api_type": "mock",
                "api_version": "mock",
                "allow_live_order": False,
                "id": "",
                "password": "",
                "cert_password": "",
                "account_no": "",
            }
        },
    }


def test_factory_returns_mock_adapter_for_all_stock_brokers():
    for broker in ("kiwoom", "shinhan", "miraeAsset", "koreaInvestment"):
        adapter = ExchangeFactory.create_stock_exchange(broker, _mock_settings_for(broker))
        assert isinstance(adapter, StockMockAdapter)
        assert adapter.broker_name == broker


def test_mock_adapter_basic_flow_per_broker():
    for broker in ("kiwoom", "shinhan", "miraeAsset", "koreaInvestment"):
        adapter = ExchangeFactory.create_stock_exchange(broker, _mock_settings_for(broker))

        assert adapter.connect() is True

        stocks = adapter.get_stock_list("KOSPI")
        etfs = adapter.get_etf_list()
        balance = adapter.get_balance()

        assert isinstance(stocks, list) and len(stocks) > 0
        assert isinstance(etfs, list) and len(etfs) > 0
        assert isinstance(balance, dict)
        assert balance.get("status") == "ok"

        first = stocks[0]
        order = adapter.place_order(
            symbol=str(first.get("code")),
            side="BUY",
            quantity=1,
            price=float(first.get("current_price") or 10000),
        )
        assert order.get("status") == "filled"
        assert order.get("execution_mode") == "mock"
        assert order.get("broker") == broker
