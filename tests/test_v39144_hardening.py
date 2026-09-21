import gzip
import json
import sqlite3
from contextlib import closing
from enum import Enum
from types import SimpleNamespace

import pytest

from tests.test_v39144_storage import decisions, entry
from trading.decision_storage import save
from trading.learning_storage import LearningStore


@pytest.mark.parametrize('kind,owner,payload', [
    ('trade_runtime::okx','okx',{'exchange':'binance','execution_mode':'live'}),
    ('stock_auto_trade_symbol','kiwoom',{'broker':'kis','execution_mode':'live'}),
    ('stock_auto_trade_symbol','kiwoom',{'broker':'kiwoom','execution_mode':'live','validation':{'execution_mode':'paper'}}),
    ('trade_runtime::binance','binance',{'execution_mode':'nonsense'}),
    ('trade_runtime::binance','binance',{}),
])
def test_new_conflicts_retained_but_not_admitted(tmp_path,kind,owner,payload):
    with closing(decisions(tmp_path/'trading.db')) as conn, conn:
        result=save(conn,'BTC',kind,payload,exchange=owner)
        assert result['storage_status']=='quarantined'
        assert conn.execute('SELECT count(*) FROM ai_decisions').fetchone()[0]==0
        original=json.loads(conn.execute('SELECT original_json FROM contract_rejections').fetchone()[0])
        assert original['decision']==payload
        save(conn,'BTC',kind,payload,exchange=owner)
        assert conn.execute('SELECT occurrences FROM contract_rejections').fetchone()[0]==2


@pytest.mark.parametrize('venue',['binance','upbit','bithumb','bybit','okx','bitget','coinone','kiwoom','kis','mirae','shinhan'])
@pytest.mark.parametrize('mode',['paper','live','learning'])
def test_normal_contract_all_venues_modes(tmp_path,venue,mode):
    with closing(decisions(tmp_path/'trading.db')) as conn, conn:
        result=save(conn,'TEST','trade_runtime::'+venue,{'exchange':venue,'execution_mode':mode,'status':'hold','reason':'neutral'},exchange=venue)
        assert result['exchange']==venue and result['execution_mode']==mode
        assert conn.execute('SELECT count(*) FROM ai_decisions').fetchone()[0]==1


def test_mode_enum_and_legacy_aliases():
    from trading.event_contract import execution_mode_key,input_issues
    class Mode(Enum): LIVE='live'
    assert execution_mode_key(Mode.LIVE)=='live'
    assert not input_issues('stock_auto_trade_symbol',{'broker':'koreainvestment','execution_mode':'live_api','validation':{'execution_mode':'live'}},'kis')


def test_shared_stock_recorder_owner_not_mutated_and_timeout_not_false_order():
    from unittest.mock import MagicMock
    from trading.stock_analysis_service import StockAnalysisService
    recorder=MagicMock(exchange='binance')
    service=StockAnalysisService(MagicMock(api_type='real'), broker_name='kiwoom', recorder=recorder)
    service._get_recorder()
    assert recorder.exchange=='binance'
    service._persist_xai_decision('069500','stock_auto_trade_symbol',{
        'broker':'kis','execution_mode':'live_api','is_etf':True,'action':'BUY',
        'validation':{'success':False,'errors':['TimeoutError']}})
    saved=recorder.save_ai_decision.call_args.args[2]
    assert saved['broker']=='kis'  # conflict remains visible to the boundary
    assert saved['actual_order'] is None
    assert recorder.save_ai_decision.call_args.kwargs['exchange']=='kiwoom'


def test_learning_conflict_cannot_be_hidden_by_manager(tmp_path,monkeypatch):
    import path_utils
    from trading.exchange_learning_manager import get_exchange_learning_manager
    monkeypatch.setattr(path_utils,'get_app_data_dir',lambda:str(tmp_path))
    manager=get_exchange_learning_manager('okx')
    original=entry('binance',1)
    assert manager.add_learning_data(original) is False
    assert original['exchange']=='binance'
    assert manager._store.count()==0
    with closing(manager._store.connect()) as conn:
        assert json.loads(conn.execute('SELECT original_json FROM contract_rejections').fetchone()[0])==original


def test_store_rejects_direct_conflicting_mode(tmp_path):
    store=LearningStore(tmp_path)
    assert store.append('okx',{**entry('okx',1),'validation':{'execution_mode':'live'}}) is False
    assert store.count()==0


def rotated(root,content=b'closed event\n'*100):
    folder=root/'logs';folder.mkdir(exist_ok=True)
    path=folder/'trading_okx.2026-09-21_01-02-03_123456.log'
    path.write_bytes(content)
    return path


def test_compaction_verified_preserves_active_and_resumes(tmp_path,monkeypatch):
    from log_system import storage_policy as p
    monkeypatch.setattr(p,'schedule_log_compaction',lambda root:None)
    path=rotated(tmp_path);body=path.read_bytes()
    active=tmp_path/'logs'/'trading_okx.log';active.write_bytes(b'active')
    unrelated=tmp_path/'logs'/'customer.log';unrelated.write_bytes(b'other')
    p.write_policy(tmp_path,{'log_budget_bytes':1000})
    record={'level':SimpleNamespace(no=20),'message':'test'}
    assert not p.diagnostic_filter(tmp_path,record)
    assert p.compact_logs(tmp_path)==1
    assert not path.exists()
    packed=list((tmp_path/'log_archives').glob('*.gz'))
    assert len(packed)==1 and gzip.decompress(packed[0].read_bytes())==body
    assert active.read_bytes()==b'active' and unrelated.read_bytes()==b'other'
    assert p.diagnostic_filter(tmp_path,record)
    assert p.compact_logs(tmp_path,force=True)==0
    assert p.disk_usage(tmp_path)['log_archive_bytes']>0


def test_compaction_failure_keeps_source_and_retry(tmp_path,monkeypatch):
    from log_system import storage_policy as p
    path=rotated(tmp_path);body=path.read_bytes()
    replace=p.os.replace
    def fail_archive(src,dst):
        if str(dst).endswith('.gz'): raise OSError('simulated disk failure')
        return replace(src,dst)
    monkeypatch.setattr(p.os,'replace',fail_archive)
    assert p.compact_logs(tmp_path,force=True)==0
    assert path.read_bytes()==body
    assert p.read_policy(tmp_path)['log_archive_error']=='OSError'
    monkeypatch.setattr(p.os,'replace',replace)
    assert p.compact_logs(tmp_path,force=True)==1
    assert p.read_policy(tmp_path)['log_archive_error'] is None


def test_compaction_never_follows_symlink(tmp_path):
    from log_system import storage_policy as p
    outside=tmp_path/'external';outside.mkdir()
    target=outside/'evidence';target.write_bytes(b'keep')
    logs=tmp_path/'logs';logs.mkdir()
    try:
        (logs/'trading.2026-09-21_01-02-03_123456.log').symlink_to(target)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Windows symbolic-link privilege is unavailable')
        raise
    assert p.compact_logs(tmp_path,force=True)==0
    assert target.read_bytes()==b'keep'


def test_rejection_status_visible_and_maintenance_not_relabel(tmp_path):
    from trading.storage_maintenance import StorageMaintenance
    with closing(decisions(tmp_path/'trading.db')) as conn, conn:
        save(conn,'BTC','trade_runtime::okx',{'exchange':'binance','execution_mode':'paper'},exchange='okx')
    service=StorageMaintenance(tmp_path)
    assert service.status()['contract_rejected_records']==1
    service.run()
    assert service.status()['contract_rejected_records']==1
    assert service.status()['trade_records_deleted'] is False
