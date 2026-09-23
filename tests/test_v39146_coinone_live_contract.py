"""Common LIVE policy + native order contract; never sends real orders."""
from unittest.mock import Mock
import pytest

from trading.exchanges.adapters import coinone_spot_adapter as module


@pytest.mark.parametrize('legacy',[None,False,True])
@pytest.mark.parametrize('side,kind',[('buy','MARKET'),('sell','MARKET'),('buy','LIMIT'),('sell','LIMIT')])
def test_order_payload_does_not_require_legacy_e2e_setting(monkeypatch,legacy,side,kind):
    extra={} if legacy is None else {'live_e2e_verified':legacy}
    adapter=module.CoinoneSpotAdapter('fixture-key','fixture-secret',**extra)
    adapter.is_connected=True;adapter.exchange=object()
    monkeypatch.setattr(module,'prepare_ccxt_order_quantity',lambda *a,**kw:{'allowed':True,'quantity':.2,'notional':20000})
    adapter._private_post=Mock(return_value={'result':'success','error_code':'0','order_id':'owned'})
    result=adapter.place_order('BTC/KRW',side,.2,price=100000 if kind=='LIMIT' else None,order_type=kind,client_order_id='fixture-1')
    assert result['status']=='open' and result['id']=='owned'
    assert adapter._private_post.call_count==1
    path,payload=adapter._private_post.call_args.args
    assert path=='/v2.1/order'
    assert payload['side']==side.upper() and payload['type']==kind and payload['user_order_id']=='fixture-1'
    if kind=='MARKET' and side=='buy':
        assert float(payload['amount'])==20000 and 'qty' not in payload
    else: assert float(payload['qty'])==.2 and 'amount' not in payload
    if kind=='LIMIT': assert payload['post_only'] is False and float(payload['price'])==100000
    assert adapter.get_execution_capabilities()['account_e2e_verified'] is False


def test_common_minimum_order_gate_is_not_removed(monkeypatch):
    adapter=module.CoinoneSpotAdapter('fixture','fixture');adapter.is_connected=True;adapter.exchange=object()
    monkeypatch.setattr(module,'prepare_ccxt_order_quantity',lambda *a,**kw:{'allowed':False,'reason':'min_notional'})
    adapter._private_post=Mock()
    assert adapter.place_order('BTC/KRW','buy',.01)['status']=='error'
    adapter._private_post.assert_not_called()


def test_public_connection_is_not_authentication_or_order_permission(monkeypatch):
    adapter=module.CoinoneSpotAdapter('','',live_e2e_verified=True)
    adapter.is_connected=True;adapter.exchange=object();adapter._private_post=Mock()
    assert adapter.place_order('BTC/KRW','sell',1)['error_code']=='credential_required'
    adapter._private_post.assert_not_called()


def test_active_order_endpoint_without_status_remains_open():
    adapter=module.CoinoneSpotAdapter('fixture','fixture')
    adapter._private_post=Mock(return_value={'active_orders':[{'order_id':'owned','target_currency':'BTC',
        'quote_currency':'KRW','original_qty':'1','remain_qty':'.5','executed_qty':'.5'}]})
    assert adapter.get_open_orders()[0]['status']=='open'
