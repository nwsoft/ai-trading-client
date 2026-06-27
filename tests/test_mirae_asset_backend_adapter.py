#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
미래에셋증권 Open Trading API 어댑터 테스트 (fake backend)

FakeMiraeAssetBackend 를 주입해 실제 HTTP 없이 로직을 검증합니다.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeMiraeAssetBackend:
    """미래에셋 Open Trading API 를 모사하는 인메모리 fake HTTP client."""

    _mock_token = 'fake-miraeasset-token'

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
        if 'inquire-account-balance' in url:
            return FakeResp({
                'output2': [{
                    'dnca_tot_amt': '1000000',
                    'scts_evlu_amt': '500000',
                    'tot_evlu_amt': '1500000',
                    'evlu_pfls_smtl_amt': '50000',
                    'asst_icdc_erng_rt': '3.45',
                }],
            })
        if 'inquire-balance' in url and 'inquire-account-balance' not in url:
            return FakeResp({'output1': [
                {
                    'pdno': '005930', 'prdt_name': '삼성전자',
                    'hldg_qty': '10', 'pchs_avg_pric': '70000', 'prpr': '75000',
                    'evlu_amt': '750000', 'evlu_pfls_amt': '50000', 'evlu_pfls_rt': '7.14',
                },
                {
                    'pdno': '069500', 'prdt_name': 'KODEX 200',
                    'hldg_qty': '5', 'pchs_avg_pric': '30000', 'prpr': '31000',
                    'evlu_amt': '155000', 'evlu_pfls_amt': '5000', 'evlu_pfls_rt': '3.33',
                },
            ]})
        if 'inquire-psbl-rvsecncl' in url:
            return FakeResp({'output': [
                {
                    'odno': 'ORD001', 'pdno': '005930', 'prdt_name': '삼성전자',
                    'sll_buy_dvsn_cd': '02', 'ord_qty': '5', 'tot_ccld_qty': '0',
                    'psbl_qty': '5', 'ord_unpr': '74000', 'ord_dvsn_name': '정상',
                    'ord_dt': '20260101093000',
                },
            ]})
        if 'inquire-daily-ccld' in url:
            return FakeResp({'output1': [
                {
                    'odno': 'ORD002', 'pdno': '005930', 'prdt_name': '삼성전자',
                    'sll_buy_dvsn_cd': '02', 'ord_qty': '3', 'tot_ccld_qty': '3',
                    'psbl_qty': '0', 'ord_unpr': '73000', 'ord_dvsn_name': '전량체결',
                    'ord_dt': '20260101090500',
                },
            ]})
        if 'inquire-price' in url:
            return FakeResp({'output': {
                'stck_prpr': '75000',
                'prdy_ctrt': '0.67',
                'acml_vol': '1234567',
                'stck_bsop_date': '20260101',
                'prdt_name': '삼성전자',
                'rprs_mrkt_kor_name': 'KOSPI',
                'stck_sdpr': '74500',
            }})
        if 'inquire-daily-itemchartprice' in url:
            return FakeResp({'output': [
                {'stck_shrt_cd': '005930', 'prdt_name': '삼성전자', 'stck_prpr': '75000', 'acml_vol': '1234567'},
                {'stck_shrt_cd': '000660', 'prdt_name': 'SK하이닉스', 'stck_prpr': '120000', 'acml_vol': '987654'},
                # ETF는 is_etf() 필터로 제외
                {'stck_shrt_cd': '069500', 'prdt_name': 'KODEX 200', 'stck_prpr': '31000', 'acml_vol': '500000'},
            ]})
        return FakeResp({})

    def _dispatch_post(self, url: str, json: dict):
        if 'oauth2/token' in url:
            return FakeResp({
                'access_token': self._mock_token,
                'expires_in': 86400,
            })
        if 'order-cash' in url:
            return FakeResp({'rt_cd': '0', 'output': {'odno': 'NEW001'}})
        if 'order-rvsecncl' in url:
            return FakeResp({'rt_cd': '0'})
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
    from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
    fake = FakeMiraeAssetBackend()
    adp = MiraeAssetStockAdapter(
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
    assert o['side'] == 'BUY'


def test_trade_history(adapter):
    """체결 내역 1건 확인."""
    adapter.connect()
    trades = adapter.get_trade_history()
    assert isinstance(trades, list)
    assert len(trades) == 1
    assert trades[0]['filled_quantity'] == 3


def test_place_order_limit_buy(adapter):
    """지정가 매수 주문 성공 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'BUY', 5, price=74000, order_type='LIMIT')
    assert result.get('status') == 'success'
    assert result['order_id'] == 'NEW001'
    assert result['side'] == 'BUY'
    assert result['quantity'] == 5


def test_place_order_invalid_quantity(adapter):
    """수량 0 주문 오류 반환 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'BUY', 0)
    assert result.get('status') == 'error'


def test_is_etf(adapter):
    """ETF 코드 판별 — 105000~115999 범위 포함 확인."""
    assert adapter.is_etf('069500') is True    # KODEX 200
    assert adapter.is_etf('005930') is False   # 삼성전자
    assert adapter.is_etf('110000') is True    # 105000-115999 범위
    assert adapter.is_etf('111999') is True    # 구 범위도 신규 범위에 포함
    assert adapter.is_etf('116000') is False   # 범위 초과


def test_get_account_info(adapter):
    """계좌 정보 반환 확인."""
    adapter.connect()
    info = adapter.get_account_info()
    assert info.get('status') == 'ok'
    assert info['broker'] == 'miraeAsset'
    assert 'account_no' in info


def test_cancel_order(adapter):
    """주문 취소 성공 확인."""
    adapter.connect()
    result = adapter.cancel_order('ORD001', symbol='005930')
    assert result is True


def test_place_order_sell(adapter):
    """매도 시장가 주문 성공 확인."""
    adapter.connect()
    result = adapter.place_order('005930', 'SELL', 3, order_type='MARKET')
    assert result.get('status') == 'success'
    assert result['side'] == 'SELL'
    assert result['order_id'] == 'NEW001'


def test_get_stock_list(adapter):
    """주식 목록 — ETF 제외한 일반 주식만 반환."""
    adapter.connect()
    stocks = adapter.get_stock_list('KOSPI')
    assert isinstance(stocks, list)
    codes = [s['code'] for s in stocks]
    assert '005930' in codes    # 삼성전자
    assert '000660' in codes    # SK하이닉스
    assert '069500' not in codes    # KODEX 200 (ETF) → is_etf() 필터로 제외


def test_get_realtime_price(adapter):
    """실시간 시세 — 핵심 필드 포함 확인."""
    adapter.connect()
    price = adapter.get_realtime_price('005930')
    assert price.get('status') == 'ok'
    assert price['current_price'] == 75000.0
    assert 'change_rate' in price
    assert price['code'] == '005930'


def test_get_stock_info(adapter):
    """종목 정보 — 이름/시장/가격 포함 확인."""
    adapter.connect()
    info = adapter.get_stock_info('005930')
    assert info.get('status') == 'ok'
    assert info['name'] == '삼성전자'
    assert info['current_price'] == 75000.0
    assert info['market'] == 'KOSPI'
    assert info['is_etf'] is False
