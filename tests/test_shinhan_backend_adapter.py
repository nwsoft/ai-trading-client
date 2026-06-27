#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
신한증권 SOL Trading Open API 어댑터 테스트 (fake backend)

FakeShinhanBackend 를 주입해 실제 HTTP 없이 로직을 검증합니다.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeShinhanBackend:
    """신한증권 REST API 를 모사하는 인메모리 fake HTTP client."""

    _mock_token = 'fake-shinhan-token'

    def __init__(self):
        self.headers = {'Authorization': f'Bearer {self._mock_token}'}
        self._last_request: dict = {}

    def get(self, url: str, params=None, timeout=10):
        self._last_request = {'method': 'GET', 'url': url, 'params': params or {}}
        return self._dispatch_get(url, params or {})

    def post(self, url: str, json=None, timeout=10):
        self._last_request = {'method': 'POST', 'url': url, 'json': json or {}}
        return self._dispatch_post(url, json or {})

    def _dispatch_get(self, url: str, params: dict):
        if 'account/domestic/list' in url:
            return FakeResp({'accounts': [{'accountNo': '12345678901'}], 'status': 'ok'})
        if 'account/domestic/balance' in url:
            return FakeResp({
                'cash': 1000000.0,
                'stock_eval': 500000.0,
                'total_assets': 1500000.0,
                'profit_loss': 50000.0,
                'profit_rate': 3.45,
                'status': 'ok',
            })
        if 'account/domestic/holdings' in url:
            return FakeResp({'holdings': [
                {
                    'isuSrtCd': '005930', 'isuNm': '삼성전자',
                    'holdCnt': '10', 'pcsPric': '70000', 'crntPric': '75000',
                    'evluAmt': '750000', 'evluPfls': '50000', 'pfrlRt': '7.14',
                },
                {
                    'isuSrtCd': '069500', 'isuNm': 'KODEX 200',
                    'holdCnt': '5', 'pcsPric': '30000', 'crntPric': '31000',
                    'evluAmt': '155000', 'evluPfls': '5000', 'pfrlRt': '3.33',
                },
            ]})
        if 'order/domestic/open-orders' in url or 'market/domestic/open-orders' in url:
            return FakeResp({'orders': [
                {
                    'ordNo': 'ORD001', 'isuSrtCd': '005930', 'isuNm': '삼성전자',
                    'buySellDvCd': '1', 'ordQty': '5', 'execQty': '0',
                    'unExecQty': '5', 'ordPrc': '74000', 'ordStsCd': '정상',
                    'ordDt': '20260101093000',
                },
            ]})
        if 'order/domestic/history' in url:
            return FakeResp({'orders': [
                {
                    'ordNo': 'ORD002', 'isuSrtCd': '005930', 'isuNm': '삼성전자',
                    'buySellDvCd': '2', 'ordQty': '3', 'execQty': '3',
                    'unExecQty': '0', 'ordPrc': '74500', 'ordStsCd': '전량체결',
                    'ordDt': '20260101090500',
                },
            ]})
        if 'market/domestic/stock-list' in url:
            return FakeResp({'stocks': [
                {'isuSrtCd': '005930', 'isuNm': '삼성전자', 'clsprc': '75000', 'acmlVol': '1234567'},
                {'isuSrtCd': '000660', 'isuNm': 'SK하이닉스', 'clsprc': '120000', 'acmlVol': '987654'},
                # ETF 는 is_etf() 필터로 제외됨
                {'isuSrtCd': '069500', 'isuNm': 'KODEX 200', 'clsprc': '31000', 'acmlVol': '500000'},
            ]})
        if 'market/domestic/price' in url:
            return FakeResp({
                'stckPrpr': '75000',
                'prdy_ctrt': '0.67',
                'acmlVol': '1234567',
                'bidPrc': '74900',
                'askPrc': '75100',
                'stckBsopDt': '20260101',
            })
        if 'market/domestic/stock-info' in url:
            return FakeResp({
                'isuNm': '삼성전자',
                'mktNm': 'KOSPI',
                'clsprc': '75000',
                'prevClsprc': '74500',
                'flucRt': '0.67',
                'acmlVol': '1234567',
            })
        return FakeResp({})

    def _dispatch_post(self, url: str, json: dict):
        if 'oauth/token' in url:
            return FakeResp({
                'access_token': self._mock_token,
                'expires_in': 86400,
            })
        if 'order/domestic/buy' in url or 'order/domestic/sell' in url:
            return FakeResp({'ordNo': 'NEW001', 'rt_cd': '0', 'status': 'success'})
        if 'order/domestic/cancel' in url:
            return FakeResp({'ordNo': 'ORD001', 'rt_cd': '0', 'result': 'ok'})
        return FakeResp({})

    def update(self, headers: dict):
        self.headers.update(headers)


class FakeResp:
    def __init__(self, data: dict):
        self._data = data

    def json(self):
        return self._data


# ------------------------------------------------------------------
# 테스트
# ------------------------------------------------------------------

@pytest.fixture
def adapter():
    from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
    fake = FakeShinhanBackend()
    adp = ShinhanStockAdapter(
        user_id='testuser', password='testpw',
        account_no='12345678901',
        app_key='test-app-key', app_secret='test-app-secret',
        backend_client=fake,
    )
    return adp


def test_connect(adapter):
    """mock token 주입으로 연결 성공 확인."""
    result = adapter.connect()
    assert result is True
    assert adapter.is_connected is True


def test_balance(adapter):
    """잔고 조회 - 필수 키 포함 확인."""
    adapter.connect()
    bal = adapter.get_balance()
    assert bal.get('status') == 'ok'
    assert 'cash' in bal
    assert 'total_assets' in bal
    assert bal['cash'] >= 0
    assert bal['total_assets'] >= 0


def test_positions(adapter):
    """보유 종목 2개 (주식 1 + ETF 1) 확인."""
    adapter.connect()
    positions = adapter.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 2

    samsung = next((p for p in positions if p['code'] == '005930'), None)
    assert samsung is not None
    assert samsung['quantity'] == 10
    assert samsung['is_etf'] is False

    etf = next((p for p in positions if p['code'] == '069500'), None)
    assert etf is not None
    assert etf['is_etf'] is True


def test_open_orders(adapter):
    """미체결 주문 1건 확인."""
    adapter.connect()
    orders = adapter.get_open_orders()
    assert isinstance(orders, list)
    assert len(orders) == 1
    o = orders[0]
    assert o['order_id'] == 'ORD001'
    assert o['symbol'] == '005930'
    assert o['side'] in ('BUY', 'SELL')


def test_place_order_buy(adapter):
    """매수 주문 성공 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'BUY', 5, price=74000, order_type='LIMIT')
    assert result.get('status') == 'success'
    assert 'order_id' in result


def test_place_order_invalid_quantity(adapter):
    """수량 0 주문 오류 반환 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'BUY', 0)
    assert result.get('status') == 'error'


def test_is_etf(adapter):
    """ETF 코드 판별."""
    assert adapter.is_etf('069500') is True   # KODEX 200
    assert adapter.is_etf('005930') is False  # 삼성전자
    assert adapter.is_etf('105000') is True   # ETF 범위


def test_get_account_info(adapter):
    """계좌 정보 반환 확인."""
    adapter.connect()
    info = adapter.get_account_info()
    assert info.get('status') == 'ok'
    assert 'account_no' in info
    assert 'broker' in info


def test_cancel_order_success(adapter):
    """주문 취소 — symbol 직접 제공 시 성공."""
    adapter.connect()
    result = adapter.cancel_order('ORD001', symbol='005930')
    assert result is True


def test_cancel_order_via_open_orders(adapter):
    """주문 취소 — symbol 없이 취소 시 미체결 조회 후 symbol 자동 매핑."""
    adapter.connect()
    result = adapter.cancel_order('ORD001')
    assert result is True


def test_get_trade_history(adapter):
    """체결 내역 — 체결 수량 > 0 인 건만 반환."""
    adapter.connect()
    trades = adapter.get_trade_history()
    assert isinstance(trades, list)
    assert len(trades) == 1
    t = trades[0]
    assert t['order_id'] == 'ORD002'
    assert t['filled_quantity'] == 3
    assert t['side'] == 'SELL'


def test_get_stock_list(adapter):
    """주식 목록 — ETF 제외한 일반 주식만 반환."""
    adapter.connect()
    stocks = adapter.get_stock_list('KOSPI')
    assert isinstance(stocks, list)
    codes = [s['code'] for s in stocks]
    assert '005930' in codes   # 삼성전자
    assert '000660' in codes   # SK하이닉스
    assert '069500' not in codes   # KODEX 200 (ETF) → is_etf() 필터로 제외


def test_get_realtime_price(adapter):
    """실시간 시세 — 핵심 필드 포함 확인."""
    adapter.connect()
    price = adapter.get_realtime_price('005930')
    assert price.get('status') == 'ok'
    assert price['current_price'] == 75000.0
    assert 'change_rate' in price
    assert 'bid_price' in price
    assert 'ask_price' in price


def test_get_stock_info(adapter):
    """종목 정보 — 이름/시장/가격 포함 확인."""
    adapter.connect()
    info = adapter.get_stock_info('005930')
    assert info.get('status') == 'ok'
    assert info['name'] == '삼성전자'
    assert info['current_price'] == 75000.0
    assert info['is_etf'] is False


def test_place_order_sell(adapter):
    """매도 시장가 주문 성공 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'SELL', 3, order_type='MARKET')
    assert result.get('status') == 'success'
    assert result['side'] == 'SELL'
    assert result['order_id'] == 'NEW001'
