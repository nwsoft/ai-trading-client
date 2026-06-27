#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import unittest
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter


class FakeKiwoomBackend:
    def __init__(self):
        self.connected = False
        self.sent_orders = []

    def CommConnect(self, block=True):
        self.connected = True
        return 0

    def GetConnectState(self):
        return 1 if self.connected else 0

    def GetLoginInfo(self, key):
        data = {
            'ACCNO': '12345678;87654321;',
            'USER_ID': 'kiwoom_user',
        }
        return data.get(key, '')

    def GetCodeListByMarket(self, market_code):
        data = {
            '0': '005930;000660;',
            '10': '035720;',
            '8': '069500;122630;',
            '3': '',
        }
        return data.get(market_code, '')

    def GetMasterCodeName(self, code):
        names = {
            '005930': '삼성전자',
            '000660': 'SK하이닉스',
            '035720': '카카오',
            '069500': 'KODEX 200',
            '122630': 'KODEX 레버리지',
        }
        return names.get(code, code)

    def block_request(self, tr_code, **kwargs):
        if tr_code == 'opt10001':
            return [{
                '종목코드': kwargs.get('종목코드', '005930'),
                '종목명': '삼성전자',
                '현재가': '72000',
                '등락율': '1.25',
                '거래량': '1234567',
                '매수호가': '71900',
                '매도호가': '72100',
                '전일종가': '71100',
            }]
        if tr_code == 'opw00018':
            return {
                'single': {
                    '예수금': '5000000',
                    '총평가금액': '1520000',
                    '총평가손익금액': '120000',
                    '총수익률(%)': '8.57',
                    '추정예탁자산': '6520000',
                },
                'multi': [
                    {
                        '종목번호': '005930',
                        '종목명': '삼성전자',
                        '보유수량': '10',
                        '매입가': '70000',
                        '현재가': '72000',
                        '평가금액': '720000',
                        '평가손익': '20000',
                        '수익률(%)': '2.86',
                    },
                    {
                        '종목번호': '069500',
                        '종목명': 'KODEX 200',
                        '보유수량': '20',
                        '매입가': '40000',
                        '현재가': '41000',
                        '평가금액': '820000',
                        '평가손익': '20000',
                        '수익률(%)': '2.50',
                    },
                ],
            }
        if tr_code == 'opt10075':
            return {
                'multi': [
                    {
                        '주문번호': 'A0001',
                        '종목코드': '005930',
                        '종목명': '삼성전자',
                        '주문구분': '매수',
                        '주문수량': '5',
                        '체결량': '0',
                        '미체결수량': '5',
                        '주문가격': '71000',
                        '주문상태': '접수',
                        '주문시간': '090101',
                    }
                ]
            }
        if tr_code == 'opw00007':
            today = datetime.now().strftime('%Y%m%d')
            return {
                'multi': [
                    {
                        '주문번호': 'B0001',
                        '종목코드': '005930',
                        '종목명': '삼성전자',
                        '매매구분': '매수',
                        '체결수량': '3',
                        '체결단가': '71500',
                        '체결금액': '214500',
                        '실현손익': '5000',
                        '체결시간': f'{today}092000',
                    },
                ]
            }
        return []

    def SendOrder(self, *args):
        self.sent_orders.append(args)
        return 0


class TestKiwoomBackendAdapter(unittest.TestCase):
    def setUp(self):
        self.backend = FakeKiwoomBackend()
        self.adapter = KiwoomStockAdapter(
            user_id='user',
            password='pw',
            cert_password='cert',
            account_no='',
            backend_client=self.backend,
        )

    def test_connect_reads_account_info(self):
        self.assertTrue(self.adapter.connect())
        self.assertEqual(self.adapter.account_no, '12345678')
        self.assertEqual(self.adapter.user_id, 'kiwoom_user')

    def test_get_balance_parses_summary(self):
        self.adapter.connect()
        balance = self.adapter.get_balance()
        self.assertEqual(balance['cash'], 5000000.0)
        self.assertEqual(balance['total_assets'], 6520000.0)
        self.assertEqual(balance['status'], 'ok')

    def test_get_positions_parses_holdings(self):
        self.adapter.connect()
        positions = self.adapter.get_positions()
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0]['code'], '005930')
        self.assertFalse(positions[0]['is_etf'])
        self.assertTrue(any(position['is_etf'] for position in positions))

    def test_get_realtime_price_parses_quote(self):
        self.adapter.connect()
        quote = self.adapter.get_realtime_price('005930')
        self.assertEqual(quote['current_price'], 72000.0)
        self.assertEqual(quote['bid_price'], 71900.0)
        self.assertEqual(quote['ask_price'], 72100.0)

    def test_get_stock_list_and_etf_list(self):
        self.adapter.connect()
        stocks = self.adapter.get_stock_list('ALL')
        etfs = self.adapter.get_etf_list()
        self.assertTrue(any(stock['code'] == '005930' for stock in stocks))
        self.assertTrue(any(etf['code'] == '069500' for etf in etfs))

    def test_open_orders_and_place_order(self):
        self.adapter.connect()
        orders = self.adapter.get_open_orders()
        self.assertEqual(len(orders), 1)
        result = self.adapter.place_order('005930', 'BUY', 3, order_type='MARKET')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(self.backend.sent_orders), 1)

    def test_get_trade_history(self):
        """당일 체결 내역 — opw00007 TR 응답 파싱 확인."""
        self.adapter.connect()
        trades = self.adapter.get_trade_history()
        self.assertIsInstance(trades, list)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t['order_id'], 'B0001')
        self.assertEqual(t['symbol'], '005930')
        self.assertEqual(t['side'], 'BUY')
        self.assertEqual(t['quantity'], 3)

    def test_get_today_trades(self):
        """오늘 체결 내역 — 당일 날짜 필터링 확인."""
        self.adapter.connect()
        today_trades = self.adapter.get_today_trades()
        self.assertIsInstance(today_trades, list)
        # FakeBackend가 오늘 날짜로 체결시간을 설정하므로 1건 포함
        self.assertEqual(len(today_trades), 1)

    def test_get_trading_stats(self):
        """거래 통계 — 필수 키 포함 확인."""
        self.adapter.connect()
        stats = self.adapter.get_trading_stats()
        self.assertEqual(stats['broker'], 'kiwoom')
        self.assertIn('total_trades', stats)
        self.assertIn('buy_count', stats)
        self.assertIn('sell_count', stats)
        self.assertEqual(stats['status'], 'ok')

    def test_cancel_order_with_symbol(self):
        """주문 취소 — symbol 직접 제공 시 SendOrder 호출."""
        self.adapter.connect()
        result = self.adapter.cancel_order('A0001', symbol='005930')
        self.assertTrue(result)
        # SendOrder 가 호출되었는지 확인
        self.assertEqual(len(self.backend.sent_orders), 1)
        order_args = self.backend.sent_orders[0]
        # 3번 인자(주문유형)=3 (취소), 8번 인자(원주문번호)='A0001'
        self.assertEqual(order_args[3], 3)
        self.assertEqual(order_args[8], 'A0001')


if __name__ == '__main__':
    unittest.main(verbosity=2)