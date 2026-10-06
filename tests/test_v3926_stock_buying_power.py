from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from trading.portfolio_orchestrator import live_stock_available_funds
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy


def kis(output):
    adapter = KoreaInvestmentStockAdapter.__new__(KoreaInvestmentStockAdapter)
    adapter.account_no = '0000000001'; adapter.is_connected = True; adapter.sandbox = False
    adapter._get = Mock(return_value={'rt_cd':'0', 'output':output})
    return adapter


def test_kis_reads_official_cash_only_buying_power_without_margin_cma_or_overseas():
    adapter = kis({'ord_psbl_cash':'100000', 'nrcvb_buy_amt':'80000', 'max_buy_amt':'999999'})
    result = adapter.get_orderable_cash(symbol='005930', price=70000, order_type='MARKET')
    assert result['orderable_cash'] == 80000
    path = adapter._get.call_args.args[0]; params = adapter._get.call_args.kwargs['params']
    assert path.endswith('/inquire-psbl-order')
    assert params['PDNO'] == '005930' and params['ORD_DVSN'] == '01'
    assert params['CMA_EVLU_AMT_ICLD_YN'] == params['OVRS_ICLD_YN'] == 'N'
    assert adapter._tr_id(path, method='GET') == 'TTTC8908R'
    adapter.sandbox = True
    assert adapter._tr_id(path, method='GET') == 'VTTC8908R'


@pytest.mark.parametrize('output', [{}, {'ord_psbl_cash':'100000'}, {'ord_psbl_cash':'nan','nrcvb_buy_amt':'99999'},
                                  {'ord_psbl_cash':'-1','nrcvb_buy_amt':'99999'}])
def test_kis_unknown_cash_does_not_fall_back_to_maximum_margin(output):
    adapter = kis(output)
    result = adapter.get_orderable_cash(symbol='005930', price=70000)
    assert result['status'] == 'error' and 'orderable_cash' not in result


def test_kis_zero_is_a_confirmed_zero_and_limit_uses_matching_order_kind():
    adapter = kis({'ord_psbl_cash':'0', 'nrcvb_buy_amt':'100000'})
    assert adapter.get_orderable_cash(symbol='005930',price=70000,order_type='LIMIT')['orderable_cash'] == 0
    assert adapter._get.call_args.kwargs['params']['ORD_DVSN'] == '00'
    adapter._get.reset_mock()
    assert adapter.get_orderable_cash(symbol='QA',price=70000)['status'] == 'error'
    adapter._get.assert_not_called()


@pytest.mark.parametrize('record,expected', [({'예수금':'999999'}, None), ({'주문가능금액':'0'},0), ({'주문가능금액':'50000'},50000)])
def test_kiwoom_reads_deposit_detail_but_requires_actual_orderable_field(record, expected):
    adapter = KiwoomStockAdapter.__new__(KiwoomStockAdapter)
    adapter.is_connected=True;adapter.account_no='qa';adapter.account_password=''
    adapter._call_block_request=Mock(return_value={'single':record})
    result=adapter.get_orderable_cash(symbol='005930',price=70000)
    assert result.get('orderable_cash') == expected
    assert result['status'] == ('ok' if expected is not None else 'error')
    assert adapter._call_block_request.call_args.args[0] == 'opw00001'


def test_kiwoom_x86_read_is_proxied_as_an_interruptible_get_without_order():
    proxy = KiwoomProcessProxy.__new__(KiwoomProcessProxy);proxy._call=Mock(return_value={'orderable_cash':10})
    assert proxy.get_orderable_cash(symbol='005930',price=70000)['orderable_cash'] == 10
    proxy._call.assert_called_once_with('get_orderable_cash',symbol='005930',price=70000,order_type='MARKET')


def test_reading_buying_power_is_not_an_order_and_error_never_restores_deposits():
    adapter = SimpleNamespace(get_orderable_cash=Mock(return_value={'status':'error'}),
            get_balance=Mock(return_value={'cash':999999}),place_order=Mock())
    assert live_stock_available_funds(adapter,'005930',70000)[0] == 0
    adapter.get_balance.assert_not_called();adapter.place_order.assert_not_called()


def test_partner_reported_orderable_zero_stays_zero_and_deposit_alone_is_unknown():
    for snapshot, amount in [({'cash':999999},0),({'orderable_cash':0,'cash':999999},0),({'orderable_cash':80000},80000)]:
        adapter = SimpleNamespace(get_balance=lambda:snapshot)
        assert live_stock_available_funds(adapter,'005930',70000)[0] == amount
