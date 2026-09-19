import json
import threading
import time
from types import SimpleNamespace
import pytest
from api.telemetry_batch import TelemetryBatcher
from trading import remote_entry_pause
from web_platform.remote_monitor import RemoteMonitor, public_snapshot


def test_telemetry_aggregation_preserves_counts_mean_and_account_boundary():
    batcher=TelemetryBatcher()
    def item(value,user='alice',event='ai_inference_completed'):
        return {'url':'https://test.invalid','headers':{'Authorization':'Bearer '+user},'payload':{
            'event_type':event,'status':'success','category':'learning','asset_class':'crypto',
            'user_id':user,'session_id':'session','source':'test','metric_value':value,
            'metadata':{'exchange':'binance','symbol':'BTCUSDT','secret':'must-not-survive'}}}
    assert batcher.add(item(100)) and batcher.add(item(300))
    assert batcher.add(item(900,'bob'))
    assert not batcher.add(item(1,event='trade_position_closed'))
    batches=batcher.ready(force=True)
    assert len(batches)==2
    alice=next(b['payload'] for b in batches if b['payload']['user_id']=='alice')
    assert alice['metric_value']==200 and alice['metadata']['_count']==2
    assert 'secret' not in alice['metadata']
    assert not batcher.add(batches[0])


@pytest.mark.parametrize('venue',sorted(remote_entry_pause.VENUES))
def test_pause_drains_inflight_and_persists_without_touching_exits(tmp_path,venue):
    gate=remote_entry_pause.EntryPause(tmp_path)
    with gate.permit(venue) as allowed:
        assert allowed
        assert gate.set(venue,True)['status']=='draining'
        with gate.permit(venue) as next_allowed:assert not next_allowed
    assert gate.state(venue)['status']=='paused'
    assert remote_entry_pause.EntryPause(tmp_path).state(venue)['paused']
    assert gate.set(venue,False)['status']=='enabled'


def test_pause_command_replay_cannot_undo_local_resume(tmp_path):
    gate=remote_entry_pause.EntryPause(tmp_path)
    args={'command_id':'command-01234567890123456789','expires':time.time()+120}
    gate.set('binance',True,**args);gate.set('binance',False)
    restored=remote_entry_pause.EntryPause(tmp_path)
    result=restored.set('binance',True,**args)
    assert result['already_applied'] and not result['paused']


@pytest.mark.parametrize('venue',['kiwoom','kis','mirae','shinhan'])
def test_real_stock_submission_boundary_blocks_buy_but_allows_exit(tmp_path,monkeypatch,venue):
    from trading.stock_analysis_service import StockAnalysisService
    gate=remote_entry_pause.EntryPause(tmp_path);gate.set(venue,True)
    monkeypatch.setattr(remote_entry_pause,'gate',lambda:gate)
    calls=[]
    svc=object.__new__(StockAnalysisService);svc.broker_name=venue
    svc.adapter=SimpleNamespace(place_order=lambda **kwargs:(calls.append(kwargs) or {'status':'success'}))
    order={'symbol':'005930','quantity':1,'price':50000,'order_type':'market'}
    assert svc._place_stock_order(side='BUY',**order)==(False,{},['remote_entries_paused'])
    assert not calls
    assert svc._place_stock_order(side='SELL',**order)[0]
    assert len(calls)==1 and calls[0]['side']=='SELL'


def test_remote_monitor_minimal_snapshot_no_secret_fields():
    runtime={'enabled_sources':['binance','kis'],'running_sources':['kis'],
        'execution_modes':{'binance':'live','kis':'paper'},'api_key':'SECRET','positions':[{'balance':100}]}
    result=public_snapshot(runtime)
    assert 'SECRET' not in json.dumps(result) and 'positions' not in result
    assert result['sources'][1]=={'source':'kis','running':True,'mode':'paper'}


def test_remote_monitor_register_pause_ack_and_revocation(tmp_path,monkeypatch):
    (tmp_path/'token.json').write_text(json.dumps({'access_token':'account-token','user_info':{'id':'alice','session_id':'session'}}))
    calls=[];responses=[{'device_token':'device-secret'},
        {'accepted':True,'commands':[{'id':'command-01234567890123456789','action':'pause_entries','source':'kis','expires':time.time()+100}]},
        {'accepted':True,'commands':[]},{}]
    codes=iter([200,200,200,401])
    def post(url,**kwargs):
        calls.append((url,kwargs));data=responses.pop(0);return SimpleNamespace(status_code=next(codes),json=lambda:data)
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{'enabled_sources':['kis'],'execution_modes':{'kis':'paper'}},transport=SimpleNamespace(post=post))
    monitor.configure(True,'Alice PC',True);monitor.tick()
    assert monitor.pause_states()['kis']['paused']
    assert monitor.status()['last_sent']
    assert 'device-secret' not in monitor.path.read_text()
    monitor.tick()
    assert calls[-1][1]['json']['acknowledgements'][0]['status']=='paused'
    monitor.tick()
    assert not monitor.status()['enabled']


def test_remote_slow_network_never_blocks_local_status_or_disable(tmp_path):
    entered=threading.Event();release=threading.Event()
    (tmp_path/'token.json').write_text(json.dumps({'access_token':'account-token','user_info':{'id':'alice','session_id':'session'}}))
    def post(*args,**kwargs):
        entered.set();release.wait(2)
        return SimpleNamespace(status_code=200,json=lambda:{'device_token':'old-token'})
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{},transport=SimpleNamespace(post=post))
    monitor.configure(True,'PC')
    worker=threading.Thread(target=monitor.tick);worker.start();assert entered.wait(1)
    begin=time.monotonic();monitor.configure(False,'PC');assert not monitor.status()['enabled']
    assert time.monotonic()-begin<.2
    release.set();worker.join(2);assert monitor.token==''


def test_old_server_never_receives_aggregated_payload(monkeypatch):
    from api import kpi_client
    monkeypatch.setattr(kpi_client, '_batch_capability_cache', {})
    calls=[]
    monkeypatch.setattr(kpi_client.requests,'get',lambda *a,**k:(calls.append(a) or SimpleNamespace(status_code=200,json=lambda:{})))
    item={'url':'https://fixture.invalid/auth/kpi/event','headers':{'Authorization':'Bearer test'},'payload':{'event_type':'ai_inference_completed'}}
    assert not kpi_client._supports_telemetry_batch(item)
    assert not kpi_client._supports_telemetry_batch(item)
    assert len(calls)==1


def test_flush_waits_for_periodic_batch_in_transit():
    from api import kpi_client
    with kpi_client._batch_delivery_lock:
        assert not kpi_client.flush_kpi_events(timeout=.01)


def test_binance_actual_entry_methods_are_gated(tmp_path,monkeypatch):
    from trading.trader import Trader
    gate=remote_entry_pause.EntryPause(tmp_path);gate.set('binance',True)
    monkeypatch.setattr(remote_entry_pause,'gate',lambda:gate)
    bot=object.__new__(Trader)
    assert bot.execute_single_trade() is False
    assert bot._execute_paper_trade() is False


def test_remote_rename_rotates_registration_and_keeps_pause(tmp_path):
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{})
    monitor.configure(True,'Old PC',True)
    monitor.token='old-device-token'
    remote_entry_pause.gate(tmp_path).set('kis',True)
    monitor.configure(True,'New PC',True)
    assert monitor.token=='' and monitor.status()['name']=='New PC'
    assert monitor.status()['entry_pauses']['kis']['paused']
