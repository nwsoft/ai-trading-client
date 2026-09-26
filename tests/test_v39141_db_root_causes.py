from datetime import datetime
from types import SimpleNamespace
import sqlite3
import logging
import threading

import pytest

from test_v39139_pnl_audit import setup_trade
from trading.binance_close_evidence import BinanceCloseEvidence
from trading.daily_risk_basis import load_or_create, credential_scope
from trading.risk_manager import RiskManager
from trading.trader import Trader
from api.binance_client import BinanceClient
from trading.pnl_evidence import verified_live_samples


def protection():
    return {'order': {'algoId': 123, 'symbol': 'BTCUSDT', 'side': 'SELL'}}


def service(tmp_path):
    recorder, tid, fill = setup_trade(tmp_path, exit_id=None)
    fill.update(order_id='456', order='456')
    client = SimpleNamespace(
        get_algo_order_evidence=lambda _: {'algoId':123,'actualOrderId':'456','symbol':'BTCUSDT','side':'SELL'},
        get_recent_trades=lambda **kw: [fill],
    )
    evidence = BinanceCloseEvidence(recorder, client)
    evidence.remember('entry-1','BTCUSDT','SELL',[protection()])
    return evidence, recorder, tid, client, fill


def test_owned_algo_actual_order_recovers_and_restart_is_idempotent(tmp_path):
    e,r,tid,c,fill = service(tmp_path)
    assert e.sync(now=100)['linked'] == 1
    row=r.execute_query('SELECT exit_order_id,net_pnl,reconciliation_status FROM trade_log WHERE id=?',(tid,))[0]
    assert row == ('456',pytest.approx(-10.2),'exchange_confirmed')
    assert BinanceCloseEvidence(r,c).sync(now=140)['linked'] == 0
    assert r.execute_query('SELECT count(*) FROM exchange_execution_log')[0][0] == 1


@pytest.mark.parametrize('corrupt', ('algo','symbol','side','fill_order','partial','untriggered','timeout'))
def test_bad_or_incomplete_evidence_cannot_certify_exit(tmp_path, corrupt):
    e,r,tid,c,fill = service(tmp_path)
    response=c.get_algo_order_evidence('123')
    if corrupt=='algo': response['algoId']=789
    if corrupt=='symbol': response['symbol']='OTHERUSDT'
    if corrupt=='side': response['side']='BUY'
    if corrupt=='untriggered': response['actualOrderId']=''
    if corrupt=='fill_order': fill.update(order_id='other',order='other')
    if corrupt=='partial': fill['amount']=1
    if corrupt=='timeout':
        def query(_): raise TimeoutError('fixture')
        c.get_algo_order_evidence=query
    else: c.get_algo_order_evidence=lambda _:response
    assert e.sync(now=100)['linked']==0
    assert r.execute_query('SELECT exit_order_id FROM trade_log WHERE id=?',(tid,))[0][0] is None


def test_delayed_fill_recovers_without_new_order_or_new_entry(tmp_path):
    e,r,tid,c,fill=service(tmp_path)
    c.get_recent_trades=lambda **kw:[]
    assert e.sync(now=100)['linked']==0
    c.get_recent_trades=lambda **kw:[fill]
    assert e.sync(now=110)['checked']==0
    assert e.sync(now=131)['linked']==1


def test_no_submission_proof_never_adopts_manual_close(tmp_path):
    r,tid,fill=setup_trade(tmp_path,exit_id=None)
    c=SimpleNamespace(get_recent_trades=lambda **kw:pytest.fail('unowned API query'))
    assert BinanceCloseEvidence(r,c).sync(now=100)['checked']==0
    assert r.execute_query('SELECT exit_order_id FROM trade_log WHERE id=?',(tid,))[0][0] is None


def test_77_zombie_lots_do_not_become_current_unrealized_loss():
    ledger=SimpleNamespace(get_open_managed_trades=lambda *a,**k:[
        {'symbol':'OLDUSDT','side':'SELL','quantity':100,'entry_price':1,'execution_mode':'live'}]*77)
    client=SimpleNamespace(get_positions_result=lambda:{'status':'success','positions':[]})
    risk=RiskManager(client,ledger)
    result = risk._managed_unrealized_pnl('binance')
    assert result[:2] == (False,0)
    assert '대조 필요' in result[2]  # Flat is not proof of the missing realized result.
    client.get_positions_result=lambda:{'status':'error','positions':[]}
    assert risk._managed_unrealized_pnl('binance')[0] is False


def test_live_quantity_mismatch_never_scales_zombie_losses():
    ledger=SimpleNamespace(get_open_managed_trades=lambda *a,**k:[
        {'symbol':'OLDUSDT','side':'SELL','quantity':100,'entry_price':1,'execution_mode':'live'}]*2)
    client=SimpleNamespace(get_positions_result=lambda:{'status':'success','positions':[
        {'symbol':'OLDUSDT','side':'SHORT','size':100,'unrealized_pnl':-2}]})
    risk=RiskManager(client,ledger)
    assert risk._managed_unrealized_pnl('binance')[0] is False


def test_basis_survives_restart_and_isolates_day_venue_account(tmp_path):
    db=str(tmp_path/'basis.db')
    def get(day='2026-09-19',venue='binance',scope='account-a',value=115.98):
        return load_or_create(db,day,venue,'USDT',scope,value)
    assert get()==115.98
    assert get(value=129.48)==115.98
    assert get(scope='account-b',value=200)==200
    assert get(venue='bybit',value=300)==300
    assert get(day='2026-09-20',value=400)==400
    scope=credential_scope({'binance_api_key':'fixture-key'},object(),'binance')
    assert 'fixture-key' not in scope and len(scope)==64


def test_basis_storage_failure_or_invalid_value_never_resets(tmp_path):
    with pytest.raises(ValueError):
        load_or_create(str(tmp_path/'basis.db'),'today','binance','USDT','a',float('nan'))
    with pytest.raises(sqlite3.OperationalError):
        load_or_create(str(tmp_path/'missing'/'basis.db'),'today','binance','USDT','a',100)


def test_risk_evaluation_keeps_denominator_across_process_restart(tmp_path, monkeypatch):
    r,_,_=setup_trade(tmp_path)
    def risk(equity,pnl):
        manager=RiskManager(object(),r,settings={'binance_api_key':'fixture-key'})
        manager._get_live_equity_snapshot=lambda _: {'valid':True,'equity':equity}
        manager._today_live_trades=lambda _:[]
        manager._managed_unrealized_pnl=lambda _: (True,pnl,'')
        return manager
    from trading import notifications
    monkeypatch.setattr(notifications,'publish_notification',lambda *a,**k:True)
    first=risk(98.92,-17.06).evaluate_daily_loss_limit(execution_mode='live')
    second=risk(98.24,-31.24).evaluate_daily_loss_limit(execution_mode='live')
    assert first.initial_equity==pytest.approx(115.98)
    assert second.initial_equity==first.initial_equity
    assert second.loss_rate==pytest.approx(31.24/115.98*100)


@pytest.mark.parametrize('payload',(None,{},[{}]))
def test_invalid_position_response_is_not_confirmed_flat(payload):
    client=object.__new__(BinanceClient)
    client.client=SimpleNamespace(futures_position_information=lambda **kw:payload)
    client.config=SimpleNamespace(recv_window=5000)
    client.logger=logging.getLogger('fixture')
    client._has_api_keys=lambda:True
    client.get_synced_timestamp=lambda:123
    assert client.get_positions_result()['status']=='error'


def test_unknown_position_does_not_cancel_protection_or_close_ledger(monkeypatch):
    trader=object.__new__(Trader)
    stop=threading.Event()
    trader.binance_client=SimpleNamespace(ensure_ws_for=lambda _:True)
    trader.active_positions={'TEST':object()}
    trader.monitoring_flags={'TEST':stop}
    trader.price_data_points={}
    trader.log_event=lambda *a,**k:None
    trader.logger=logging.getLogger('fixture')
    trader._get_position_info_with_retry=lambda _:None
    monkeypatch.setattr(stop, 'wait', lambda _:stop.set())
    trader.start_realtime_monitoring('TEST',trader.active_positions['TEST'])
    assert 'TEST' in trader.active_positions  # no cancel/read/write methods exist on fixture


def test_native_summary_preserves_rebate_and_persists_actual_fill(tmp_path):
    r,_,_=setup_trade(tmp_path)
    trader=object.__new__(Trader)
    trader.recorder=r
    requests=[]
    def history(**kw):
        requests.append(kw)
        return [{'id':'f','order_id':'456','symbol':'BTCUSDT','side':'SELL',
                 'quantity':2,'price':95,'realized_pnl':-10,'commission':-0.1,
                 'commission_asset':'USDT','time':int(datetime.now().timestamp()*1000)}]
    trader.binance_client=SimpleNamespace(get_recent_trades=history)
    result=trader._get_binance_order_fill_summary('BTCUSDT','456',attempts=1)
    assert result['confirmed'] and result['fees']==-0.1
    assert requests[0]['order_id']=='456'
    assert r.execute_query('SELECT fee FROM exchange_execution_log')[0][0]==-0.1


@pytest.mark.parametrize('missing',('realized_pnl','commission','commission_asset'))
def test_native_summary_does_not_invent_missing_cost_or_pnl(missing):
    fill={'order_id':'456','quantity':1,'price':1,'commission':0.1,'realized_pnl':0.2,'commission_asset':'USDT'}
    fill.pop(missing)
    trader=object.__new__(Trader)
    trader.binance_client=SimpleNamespace(get_recent_trades=lambda **kw:[fill])
    assert trader._get_binance_order_fill_summary('TEST','456',attempts=1)['confirmed'] is False


def test_submission_wrapper_persists_provenance_before_position_is_registered(tmp_path):
    r,_,_=setup_trade(tmp_path,exit_id=None)
    trader=object.__new__(Trader)
    trader.recorder=r
    trader.active_positions={}
    trader.binance_client=SimpleNamespace(place_tp_sl_orders=lambda **kw:(protection(),{}))
    trader.log_event=lambda *a,**k:None
    trader._place_owned_binance_protection(entry_order_id='entry-1',symbol='BTCUSDT',position_side='LONG')
    assert r.execute_query('SELECT entry_order_id,protection_id FROM binance_close_evidence')==[('entry-1','123')]


@pytest.mark.parametrize('venue', ('binance','bybit','okx','bitget','upbit','bithumb','coinone','kis','kiwoom','mirae','shinhan'))
def test_optional_learning_uses_net_and_rejects_incomplete_window(venue):
    row={'exchange':venue,'execution_mode':'live','entry_price':100,'quantity':1,
         'performance_evidence_ready':True,'net_pnl':-1,'pnl':10,'pnl_percent':10}
    ready=verified_live_samples([row],venue)
    assert ready[0]['pnl']==-1 and ready[0]['pnl_percent']==-1
    assert verified_live_samples([row,{**row,'performance_evidence_ready':False}],venue)==[]
    assert len(verified_live_samples([row,{**row,'execution_mode':'paper','performance_evidence_ready':False}],venue))==1
    assert verified_live_samples([{**row,'exchange':'other'}],venue)==[]
