import base64
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_v39146_customer_write_recovery import recorder, entry
from trading import recorder_write_queue as queue


@pytest.mark.parametrize('venue',['binance','okx','bybit','bitget','upbit','bithumb','coinone','kiwoom','shinhan','mirae','kis'])
def test_partial_replay_preserves_quantity_cost_and_strategy(recorder,venue):
    tid=entry(recorder,'entry',venue)
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("UPDATE trade_log SET strategy_key='s',strategy_version_id='v',entry_fee=1,entry_fee_asset='USDT',settlement_currency='USDT' WHERE id=?",(tid,))
    args=dict(symbol='BTCUSDT',exchange=venue,entry_order_id='entry',exit_order_id='exit',closed_quantity=.25,
        exit_price=104,gross_pnl=1,exit_fee=.1,fee_asset='USDT',reason='partial',pnl_source='exchange',reconciliation_status='exchange_confirmed')
    token=queue.enqueue(recorder,'record_partial_trade_close',args)
    assert recorder.record_partial_trade_close(**args,_write_token=token)
    assert queue.drain(recorder)==1
    assert recorder.record_partial_trade_close(**args)
    with sqlite3.connect(recorder.db_path) as db:
        rows=db.execute('SELECT quantity,entry_fee,strategy_key,strategy_version_id FROM trade_log ORDER BY id').fetchall()
    assert rows==[(.75,.75,'s','v'),(.25,.25,'s','v')]


@pytest.mark.parametrize('method,payload,table',[('log_risk_event',dict(symbol='BTC',risk_type='guard',risk_level='warning',description='fixture',impact_score=1),'risk_log'),
    ('save_stock_execution_metric',{'metric':{'broker':'kis','symbol':'005930','success':True}},'stock_execution_metrics')])
def test_auxiliary_write_commit_before_ack(recorder,method,payload,table):
    token=queue.enqueue(recorder,method,payload)
    getattr(recorder,method)(**payload,_write_token=token)
    assert queue.drain(recorder)==1
    with sqlite3.connect(recorder.db_path) as db: assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==1


@pytest.mark.parametrize('broker',['kiwoom','shinhan','mirae','kis'])
@pytest.mark.parametrize('missing_fee',[False,True])
def test_broker_exact_order_recovery_to_pnl(recorder,broker,missing_fee):
    from trading.record_recovery_adapters import RecoveryResolver
    tid=entry(recorder,'buy-owned',broker)
    stamp=datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("UPDATE trade_log SET exit_time=?,exit_order_id='sell-owned',settlement_currency='KRW',entry_fee=NULL,reconciliation_status='legacy_unverified' WHERE id=?",(stamp,tid))
        db.row_factory=sqlite3.Row
        trade=dict(db.execute('SELECT * FROM trade_log WHERE id=?',(tid,)).fetchone())
    def fetch(symbol,order,epoch):
        buy=order=='buy-owned'
        return [{'id':order,'order':order,'symbol':symbol,'side':'buy' if buy else 'sell','amount':1,
            'price':100 if buy else 110,'fee':{'cost':None if missing_fee else 1,'currency':'KRW'},'timestamp':stamp}]
    result=RecoveryResolver(recorder,SimpleNamespace(get_recovery_order_fills=fetch),broker)(broker,trade)
    with sqlite3.connect(recorder.db_path) as db: net=db.execute('SELECT net_pnl FROM trade_log WHERE id=?',(tid,)).fetchone()[0]
    assert (result!='')==missing_fee
    assert net is None if missing_fee else net==8


def test_bundle_extraction_hash_duplicates_and_truncation(tmp_path):
    from trading.strategy_source_ingestor import StrategySourceIngestor
    from trading.strategy_source_bundle import extract_bundle
    a=tmp_path/'a.md';a.write_text('RSI 30 이하 LONG '+ 'a'*100)
    b=tmp_path/'b.md';b.write_text('a'*70000)
    result=extract_bundle(StrategySourceIngestor(),[{'value':str(a)},{'value':str(a)},{'value':str(b)}])
    assert result.evidence['sources'][1]['duplicate']
    assert result.evidence['sources'][2]['truncated']
    assert not result.evidence['coverage_complete']
    assert len(result.text)<60000


@pytest.mark.parametrize('suffix',['.xlsx','.docx'])
def test_office_extraction(tmp_path,suffix):
    from trading.strategy_source_bundle import office_text
    path=tmp_path/('source'+suffix)
    with zipfile.ZipFile(path,'w') as z:
        if suffix=='.xlsx':z.writestr('xl/worksheets/sheet1.xml','<sheet xmlns="x"><row><c r="A1" t="inlineStr"><is><t>RSI 30</t></is></c></row></sheet>')
        else:z.writestr('word/document.xml','<document xmlns="x"><p><r><t>RSI 30</t></r></p></document>')
    assert 'RSI 30' in office_text(path)


def test_bundle_web_service_preserves_manifest_and_cleans_uploads(tmp_path,monkeypatch):
    from web_platform import application_services as module
    monkeypatch.setattr(module,'get_app_data_dir',lambda:str(tmp_path))
    monkeypatch.setattr(module,'set_current_user_account',lambda _:None)
    monkeypatch.setattr(module,'load_settings',lambda **kw:{})
    service=module.ApplicationServices(account='fixture')
    files=[{'name':'rules.md','value':base64.b64encode('RSI 30 이하 LONG, RSI 55 이상 청산, 손절 1%, 익절 2%, 포지션 5%, 횡보장 Binance'.encode()).decode()},
           {'name':'risk.txt','value':base64.b64encode('수익 보장 없음'.encode()).decode()}]
    result=service.analyze_strategy_source(source_kind='auto',value='selected-files',files=files)
    assert len(result['source_manifest'])==2
    assert not list((tmp_path/'cache'/'strategy_uploads').glob('*'))
    assert 'bundle_' not in json.dumps(result,ensure_ascii=False)


@pytest.mark.parametrize('status,expected',[('LIVE','open'),('FILLED','closed'),('PARTIALLY_FILLED','open'),('PARTIALLY_CANCELED','canceled'),('CANCELED_LIMIT_PRICE_EXCEED','canceled')])
def test_coinone_partial_status_and_missing_fee(status,expected):
    from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
    result=CoinoneSpotAdapter._normalize_native_order({'status':status,'order_id':'a','executed_qty':'.5','original_qty':'1','average_executed_price':'100'},'BTC/KRW')
    assert result['status']==expected
    assert result['filled']==.5
    assert result['fee'] is None


def test_coinone_timeout_never_reposts(monkeypatch):
    from trading.exchanges.adapters import coinone_spot_adapter as m
    a=m.CoinoneSpotAdapter('fixture','fixture',live_e2e_verified=True);a.is_connected=True;a.exchange=object()
    monkeypatch.setattr(m,'prepare_ccxt_order_quantity',lambda *a,**k:{'allowed':True,'quantity':1,'notional':100})
    a._private_post=Mock(side_effect=TimeoutError())
    result=a.place_order('BTC/KRW','buy',1,client_order_id='fixture-1')
    assert result['status']=='unknown' and not result['retry_safe']
    assert a._private_post.call_count==1


def test_group_close_replay_keeps_event_time_and_does_not_certify_estimate(recorder):
    entry(recorder,'a');entry(recorder,'b')
    args=dict(symbol='BTCUSDT',exchange='binance',entry_order_ids=['a','b'],exit_price=103,
        reason='fixture',fees=.1,slippage=.1,exit_order_id='exit',closed_at='2026-09-20 01:00:00')
    token=queue.enqueue(recorder,'_close_managed_entry_group',args)
    assert recorder._close_managed_entry_group(**args,_write_token=token)
    assert queue.drain(recorder)==1
    assert queue.drain(recorder)==0
    with sqlite3.connect(recorder.db_path) as db:
        rows=db.execute('SELECT exit_time,net_pnl,reconciliation_status FROM trade_log').fetchall()
    assert rows==[('2026-09-20 01:00:00',None,'pending_exchange_reconciliation')]*2


def test_order_command_late_retry_cannot_erase_confirmed_order(recorder):
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("INSERT INTO crypto_order_commands(command_id,exchange,symbol,side,intent_type,status) VALUES ('cmd','binance','BTCUSDT','buy','entry','pending')")
    args=dict(command_id='cmd',status='submitting',increment_attempt=True)
    token=queue.enqueue(recorder,'update_crypto_order_command',args)
    assert recorder.update_crypto_order_command('cmd',status='confirmed',exchange_order_id='owned')
    assert queue.drain(recorder)==1
    with sqlite3.connect(recorder.db_path) as db:
        assert db.execute('SELECT status,exchange_order_id,attempts FROM crypto_order_commands').fetchone()==('confirmed','owned',0)


def test_log_cleanup_preserves_financial_and_risk_history(recorder):
    tid=entry(recorder,'old')
    recorder.log_risk_event(symbol='BTC',risk_type='guard',risk_level='warning',description='old',impact_score=1)
    with sqlite3.connect(recorder.db_path) as db:
        db.execute("UPDATE trade_log SET exit_time='2000-01-01' WHERE id=?",(tid,))
        db.execute("UPDATE risk_log SET timestamp='2000-01-01'")
    recorder.cleanup_old_logs(90)
    with sqlite3.connect(recorder.db_path) as db:
        assert db.execute('SELECT count(*) FROM trade_log').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM risk_log').fetchone()[0]==1


def test_partial_unknown_entry_fee_remains_unknown(recorder):
    tid=entry(recorder,'entry')
    with sqlite3.connect(recorder.db_path) as db: db.execute('UPDATE trade_log SET entry_fee=NULL WHERE id=?',(tid,))
    assert recorder.record_partial_trade_close(symbol='BTCUSDT',exchange='binance',entry_order_id='entry',
        exit_order_id='exit',closed_quantity=.2,exit_price=105,gross_pnl=1,exit_fee=.1,fee_asset='USDT',
        reason='fixture',pnl_source='exchange',reconciliation_status='exchange_confirmed')
    with sqlite3.connect(recorder.db_path) as db:
        assert db.execute('SELECT net_pnl,entry_fee FROM trade_log WHERE exit_time IS NOT NULL').fetchone()==(None,None)


def test_partial_paper_retry_does_not_block_live(recorder):
    tid=entry(recorder,'paper')
    with sqlite3.connect(recorder.db_path) as db: db.execute("UPDATE trade_log SET execution_mode='paper' WHERE id=?",(tid,))
    queue.enqueue(recorder,'record_partial_trade_close',{'exchange':'binance','symbol':'BTCUSDT','entry_order_id':'paper'})
    assert queue.unresolved_closes(recorder.db_path,'binance')==0
    queue.enqueue(recorder,'_close_managed_entry_group',{'exchange':'binance','symbol':'BTCUSDT','entry_order_ids':['paper']})
    assert queue.unresolved_closes(recorder.db_path,'binance')==0
    queue.enqueue(recorder,'_close_managed_entry_group',{'exchange':'binance','symbol':'BTCUSDT','entry_order_ids':['unknown']})
    assert queue.unresolved_closes(recorder.db_path,'binance')==1


@pytest.mark.parametrize('field',['fee','fee_currency','is_ask'])
def test_coinone_native_recovery_preserves_missing_evidence(field):
    from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
    a=CoinoneSpotAdapter('fixture','fixture')
    row=dict(trade_id='fill',order_id='owned',target_currency='BTC',quote_currency='KRW',is_ask=True,
             qty='1',price='100',timestamp=1700000000000,fee='1',fee_currency='KRW')
    row.pop(field)
    a._private_post=Mock(return_value={'completed_orders':[row]})
    if field=='is_ask':
        with pytest.raises(RuntimeError,match='side_missing'):a.get_recovery_order_fills('BTC/KRW','owned',1700000000)
    else:
        result=a.get_recovery_order_fills('BTC/KRW','owned',1700000000)
        assert result[0]['fee']['cost' if field=='fee' else 'currency'] is None


def test_coinone_native_history_pagination_and_foreign_order_filter():
    from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
    a=CoinoneSpotAdapter('fixture','fixture')
    foreign=[{'trade_id':f'f{i}','order_id':'manual'} for i in range(100)]
    owned=dict(trade_id='fill',order_id='owned',target_currency='BTC',quote_currency='KRW',is_ask=True,
             qty='1',price='100',timestamp=1700000000000,fee='1',fee_currency='KRW')
    a._private_post=Mock(side_effect=[{'completed_orders':foreign},{'completed_orders':[owned]}])
    result=a.get_recovery_order_fills('BTC/KRW','owned',1700000000)
    assert len(result)==1 and result[0]['id']=='fill'
    assert a._private_post.call_args.args[1]['to_trade_id']=='f99'


def test_coinone_failed_open_order_query_is_not_empty():
    from trading.exchanges.adapters.coinone_spot_adapter import CoinoneSpotAdapter
    a=CoinoneSpotAdapter('fixture','fixture');a._private_post=Mock(side_effect=TimeoutError())
    assert a.get_open_orders_result()['orders'] is None
    with pytest.raises(RuntimeError):a.get_open_orders()


@pytest.mark.parametrize('broker',['kis','kiwoom','shinhan','mirae'])
def test_broker_native_history_never_uses_order_limit_price(broker):
    from trading.stock_history_recovery import order_fills
    raw=dict(order_id='owned',price=900,fee=1,tax=0)
    a=SimpleNamespace(is_connected=True,account_no='fixture01',account_password='',exchange_name=broker,
        partner_profile={'recovery_history':{'date_parameter':'date','path':'/history','rows_key':'rows'}},
        _normalize_symbol=lambda v:v,_parse_order=lambda _:dict(order_id='owned',symbol='005930',side='buy',filled_quantity=1,price=900,timestamp='20260101'),
        _parse_trade_record=lambda _:dict(order_id='owned',symbol='005930',side='buy',quantity=1,filled_price=900,timestamp='120000'),
        _get=lambda *args,**kw:{'rows':[raw],'output1':[raw]},_call_block_request=lambda *args,**kw:{'multi':[raw]})
    assert order_fills(a,'005930','owned',1767225600)==[]
    raw['체결단가']=100;raw['ord_tmd']='120000'
    assert order_fills(a,'005930','owned',1767225600)[0]['price']==100


def test_low_storage_blocks_entries_but_not_stock_protection(tmp_path,monkeypatch):
    from trading import remote_entry_pause as module
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:SimpleNamespace(free=1024))
    gate=module.EntryPause(tmp_path)
    monkeypatch.setattr(module,'gate',lambda:gate)
    with gate.permit('binance') as allowed: assert not allowed
    assert gate.last_block_reason['binance']=='storage_free_space_low'
    class Broker:
        broker_name='kis'
        @module.entry_submission('',stock=True)
        def order(self,*,side):return 'called'
    assert Broker().order(side='BUY')==(False,{},['storage_free_space_low'])
    assert Broker().order(side='SELL')=='called'


def test_truncated_bundle_cannot_be_execution_ready(tmp_path):
    from trading.strategy_source_bundle import extract_bundle
    from trading.strategy_source_ingestor import StrategySourceIngestor
    source=tmp_path/'large.md'
    source.write_text('RSI 30 이하 LONG, RSI 55 이상 청산, 손절 1%, 익절 2%, 포지션 5%, 횡보장 Binance\n'+'a'*70000)
    ingestor=StrategySourceIngestor()
    bundle=extract_bundle(ingestor,[{'value':str(source)}])
    result=ingestor.analyze('selected-files',extracted_source=bundle)
    assert not result['ready_for_execution']
    assert 'source_coverage_incomplete' in result['rules']['compiler_issues']


def test_conflicting_source_rules_are_not_implicitly_merged(tmp_path):
    from trading.strategy_source_bundle import extract_bundle
    from trading.strategy_source_ingestor import StrategySourceIngestor
    a=tmp_path/'a.md';b=tmp_path/'b.md'
    a.write_text('RSI 30 이하 LONG, 손절 1%', encoding='utf-8')
    b.write_text('RSI 20 이하 LONG, 손절 3%', encoding='utf-8')
    result=extract_bundle(StrategySourceIngestor(),[{'value':str(a)},{'value':str(b)}])
    assert not result.evidence['coverage_complete']
    assert any('조건이 다릅니다' in w for w in result.warnings)
