"""End-to-end local journal integrity/queue boundaries; no actual providers/orders."""
import hashlib,json,sqlite3,threading,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from trading.paper_ledger_index import index_for,_INDEXES
from trading.paper_capital import paper_available_funds
from trading.paper_position_store import ledger_checkpoint,validate_ledger_checkpoint
from trading.paper_maintenance import MaintenanceQueue
from web_platform.gateway import create_gateway_app


def row(event='one',net=-10):
 return dict(event_id=event,exchange='binance',scope='binance',execution_mode='paper',quote_currency='USDT',net_pnl=net,calculation_status='valid',cost_calculation_status='recorded')

def write(path,rows):path.write_text(''.join(json.dumps(r)+'\n' for r in rows))


def test_append_restart_missing_cache_and_tampered_cache_do_not_restore_spent_cash(tmp_path):
 p=tmp_path/'ledger.jsonl';write(p,[row()]);idx=index_for(p)
 assert idx.wallet('binance','USDT',0)==-10
 with p.open('a') as f:f.write(json.dumps(row('two',-5))+'\n')
 assert idx.wallet('binance','USDT',0)==-15
 _INDEXES.pop(str(p.resolve()))
 idx=index_for(p);assert idx.wallet('binance','USDT',0)==-15
 idx.db_path.unlink()
 assert idx.wallet('binance','USDT',0)==-15
 from contextlib import closing
 with closing(sqlite3.connect(idx.db_path)) as db:
  with db:db.execute('UPDATE events SET net=9999')
 assert idx.wallet('binance','USDT',0)==-15
 # A fresh process also checks derived rows against the verified source chunks.
 with closing(sqlite3.connect(idx.db_path)) as db:
  with db:db.execute('UPDATE events SET net=9999')
 _INDEXES.pop(str(p.resolve()))
 assert index_for(p).wallet('binance','USDT',0)==-15


def test_modified_or_truncated_prefix_cannot_become_new_initial_money(tmp_path):
 p=tmp_path/'ledger.jsonl';write(p,[row()]);cp=ledger_checkpoint(p)
 write(p,[row(net=99)])
 with pytest.raises(ValueError,match='paper_close_recovery_ledger_changed'):validate_ledger_checkpoint(p,cp)
 assert paper_available_funds(1000,{},venue='binance',quote='USDT',ledger_file=p)['capital_basis']=='paper_funds_unverified'


def test_torn_tail_recovered_when_original_append_finishes_without_losing_committed_loss(tmp_path):
 p=tmp_path/'ledger.jsonl';write(p,[row()]);idx=index_for(p);assert idx.wallet('binance','USDT',0)==-10
 line=json.dumps(row('two',-7))+'\n';split=len(line)//2
 with p.open('a') as f:f.write(line[:split])
 with pytest.raises(ValueError,match='torn'):idx.sync()
 with p.open('a') as f:f.write(line[split:])
 assert idx.wallet('binance','USDT',0)==-17


def test_cancellation_resumes_from_verified_chunks(tmp_path,monkeypatch):
 import trading.paper_ledger_index as module
 monkeypatch.setattr(module,'BATCH_BYTES',100)
 p=tmp_path/'ledger.jsonl';write(p,[row(str(n),-1) for n in range(100)])
 event=threading.Event();idx=index_for(p)
 def progress(_):event.set()
 with pytest.raises(ValueError,match='cancelled'):idx.sync(cancel=event,progress=progress)
 event.clear();idx.sync(cancel=event)
 assert idx.wallet('binance','USDT',0)==-100
 assert len(list(module.Rows(idx)))==100


def test_concurrent_same_snapshot_reads_do_not_duplicate_losses(tmp_path):
 p=tmp_path/'ledger.jsonl';write(p,[row(str(n),-1) for n in range(1000)])
 with ThreadPoolExecutor(max_workers=5) as pool:
  assert list(pool.map(lambda _:index_for(p).wallet('binance','USDT',0),range(10)))==[-1000]*10


def wait(queue):
 queue.thread.join(5);assert not queue.thread.is_alive();return queue.status()


def test_queue_is_sequential_isolates_failure_and_hides_private_exception(tmp_path):
 calls=[]
 def runner(source,mode,cancel,progress):
  calls.append((source,mode))
  if source=='okx':raise RuntimeError('PRIVATE-SECRET-response')
  return dict(state='checked',reason='')
 q=MaintenanceQueue(tmp_path,runner);q.start(['binance','okx','upbit'],'paper');state=wait(q)
 assert calls==[('binance','paper'),('okx','paper'),('upbit','paper')]
 assert state['state']=='needs_evidence' and state['items'][1]['reason']=='recovery_check_failed'
 assert 'PRIVATE' not in q.path.read_text()
 assert not state['orders_submitted']


def test_cancel_resume_and_account_process_lock(tmp_path):
 started=threading.Event()
 def runner(source,mode,cancel,progress):
  started.set();cancel.wait(1);return {'state':'paused' if cancel.is_set() else 'checked','reason':''}
 q=MaintenanceQueue(tmp_path,runner);q.start(['binance','upbit'],'paper');assert started.wait(1)
 other=MaintenanceQueue(tmp_path,runner)
 with pytest.raises(RuntimeError,match='already_running'):other.start(['okx'],'paper')
 q.cancel();assert wait(q)['state']=='paused'
 q.runner=lambda *a:{'state':'checked','reason':''}
 q.start(['binance','upbit'],'paper',resume=True);assert wait(q)['state']=='checked'
 assert MaintenanceQueue(tmp_path,q.runner).status()['state']=='checked'


@pytest.mark.parametrize('sources,mode',[(['kis'],'paper'),(['binance','binance'],'paper'),([], 'paper'),(['binance'],'unknown'),(['../secret'],'live')])
def test_queue_rejects_scope_widening_and_ambiguous_modes(tmp_path,sources,mode):
 q=MaintenanceQueue(tmp_path,lambda *a:pytest.fail('must not run'))
 with pytest.raises(ValueError,match='invalid_reconciliation_request'):q.start(sources,mode)


def test_gateway_queue_requires_auth_intent_and_strict_fields():
 calls=[];service=SimpleNamespace(runtime_snapshot=lambda:{},runtime_bridge=SimpleNamespace(reconciliation=lambda **kw:calls.append(kw) or {'state':'running'}))
 with TestClient(create_gateway_app(token='x'*40,application_services=service)) as c:
  path='/api/v1/maintenance/reconciliation';payload=dict(action='start',sources=['binance'],mode='paper')
  assert c.post(path,json=payload).status_code==401
  auth={'Authorization':'Bearer '+'x'*40}
  assert c.post(path,headers=auth,json=payload).status_code==428
  auth['X-NoahAI-Intent']='confirmed'
  assert c.post(path,headers=auth,json={**payload,'start_live':True}).status_code==400
  assert c.post(path,headers=auth,json=payload).status_code==200
  assert calls[-1]==dict(action='start',sources=['binance'],mode='paper')


def test_headless_paper_queue_verifies_files_without_creating_runtime_or_using_credentials(tmp_path,monkeypatch):
 from web_platform.runtime_bridge import HeadlessRuntimeBridge
 p=tmp_path/'strategy_paper_outcomes.jsonl';write(p,[row()])
 monkeypatch.setattr('path_utils.get_db_file_path',lambda:str(tmp_path/'qa.db'))
 bridge=HeadlessRuntimeBridge(account='synthetic',factory=lambda _:pytest.fail('hidden runtime creation'))
 bridge._settings=lambda:{}
 bridge.reconciliation(action='start',sources=['binance','upbit'],mode='paper')
 assert wait(bridge._maintenance_queue)['state']=='checked'
 assert bridge._app is None


def test_steady_state_wallet_event_and_checkpoint_reads_do_not_rebuild_index(tmp_path):
 p=tmp_path/'ledger.jsonl';write(p,[row()]);idx=index_for(p)
 assert idx.wallet('binance','USDT',0)==-10
 original_inode=idx.db_path.stat().st_ino
 for _ in range(5):
  assert idx.wallet('binance','USDT',0)==-10
  assert idx.event('one')['net_pnl']==-10
  validate_ledger_checkpoint(p,ledger_checkpoint(p))
 assert idx.db_path.stat().st_ino==original_inode
 assert not idx.db_path.with_suffix('.rebuild').exists()


def test_index_storage_error_blocks_funds_without_exposing_private_paths(tmp_path,monkeypatch):
 import trading.paper_ledger_index as module
 p=tmp_path/'ledger.jsonl';write(p,[row()])
 def fail(*args,**kwargs):raise sqlite3.OperationalError('PRIVATE-sensitive-path')
 monkeypatch.setattr(module.sqlite3,'connect',fail)
 result=paper_available_funds(1000,{},venue='binance',quote='USDT',ledger_file=p)
 assert result['capital_basis']=='paper_funds_unverified'
 assert result['reason']=='paper_ledger_index_unavailable'
 assert 'PRIVATE' not in json.dumps(result)


def test_structurally_invalid_signed_close_proof_has_specific_finite_reason(tmp_path):
 from trading.paper_strategy_ledger import close_outcome_digest
 from trading.paper_position_store import recovery_digest
 p=tmp_path/'ledger.jsonl';event=row()
 proof={'schema_version':1,'before':[],'after':{},'outcome_sha256':close_outcome_digest(event)}
 event['close_recovery']={**proof,'sha256':recovery_digest(proof)}
 write(p,[event])
 result=paper_available_funds(1000,{},venue='binance',quote='USDT',ledger_file=p)
 assert result['capital_basis']=='paper_funds_unverified'
 assert result['reason']=='paper_close_recovery_evidence_invalid'


@pytest.mark.parametrize('free,warning',[(2*1024**3,False),(1024**2,True)])
def test_disk_warning_is_observational_and_never_deletes_or_blocks(tmp_path,monkeypatch,free,warning):
 import trading.storage_maintenance as module
 monkeypatch.setattr(module.shutil,'disk_usage',lambda _:SimpleNamespace(total=10*1024**3,free=free))
 result=module.disk_capacity(tmp_path)
 assert result['disk_free_bytes']==free and result['disk_low_space_warning'] is warning
 assert list(tmp_path.iterdir())==[]


def test_unknown_disk_space_is_not_reported_as_zero(tmp_path,monkeypatch):
 import trading.storage_maintenance as module
 def fail(_):raise OSError('private-path')
 monkeypatch.setattr(module.shutil,'disk_usage',fail)
 result=module.disk_capacity(tmp_path)
 assert result['disk_free_bytes'] is None and result['disk_low_space_warning'] is None
 assert result['disk_capacity_error']=='disk_capacity_unavailable'


@pytest.mark.parametrize('sources,mode',[(['binance','okx'],'paper'),(['binance'],'live'),(['okx'],'paper')])
def test_resume_cannot_change_persisted_job_scope_or_mode(tmp_path,sources,mode):
 q=MaintenanceQueue(tmp_path,lambda *args:{'state':'needs_evidence','reason':'paper_ledger_pnl_unverified'})
 q.start(['binance'],'paper');before=wait(q)
 with pytest.raises(ValueError,match='invalid_reconciliation_request'):q.start(sources,mode,resume=True)
 assert q.status()==before
