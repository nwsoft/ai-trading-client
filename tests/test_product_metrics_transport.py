import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
import requests
from api.product_metrics import ProductMetrics, POLICY

@pytest.fixture
def metrics(tmp_path,monkeypatch):
    monkeypatch.setattr(ProductMetrics,'start',lambda self:None)
    return ProductMetrics(directory=tmp_path,account='alice',credentials=lambda:'test-only-token',
        transport=lambda url,**kw:SimpleNamespace(status_code=200,json=lambda:dict(accepted=True,event_id=kw['json']['event_id'])))

def test_opt_in_payload_and_no_credentials(metrics):
    assert not metrics.path.exists() and not metrics.record('studio_save')
    assert not metrics.path.exists()
    metrics.configure(True,POLICY); assert metrics.deliver_once(); assert metrics.record('studio_save')
    with metrics.connect() as c: value=c.execute('SELECT payload FROM outbox').fetchone()[0]
    assert set(json.loads(value))=={'event_id','action','mode','consent','occurred_at','consent_version','installation_id','consent_revision','client_version'}
    assert b'test-only-token' not in metrics.path.read_bytes()
    assert metrics.deliver_once() and metrics.status()['pending']==0

def test_lost_ack_retries_identical_event_after_restart(metrics):
    seen=[]
    def lost(url,**kw):
        seen.append(kw['json']); raise requests.ConnectionError('lost-ack')
    metrics.configure(True,POLICY); assert metrics.deliver_once()
    metrics.transport=lost
    metrics.record('studio_save')
    assert not metrics.deliver_once() and metrics.status()['pending']==1
    metrics.close()
    second=ProductMetrics(directory=metrics.path.parent.parent,account='alice',credentials=lambda:'new-token')
    def ack(url,**kw):
        seen.append(kw['json']); return SimpleNamespace(status_code=200,json=lambda:dict(accepted=True,event_id=kw['json']['event_id']))
    second.transport=ack
    assert second.deliver_once()
    assert seen[0]==seen[1] and second.status()['pending']==0

def test_revoke_clears_and_remains_off(metrics):
    metrics.configure(True,POLICY); assert metrics.deliver_once(); metrics.record('paper_start','paper')
    metrics.configure(False,POLICY)
    assert metrics.status()['pending']==0 and not metrics.record('studio_save')
    second=ProductMetrics(directory=metrics.path.parent.parent,account='alice',credentials=lambda:'token')
    assert not second.status()['enabled']

def test_auth_failure_pending_and_rejection_visible(metrics):
    metrics.configure(True,POLICY); assert metrics.deliver_once(); metrics.record('app_open')
    metrics.transport=lambda *a,**kw:SimpleNamespace(status_code=401)
    assert not metrics.deliver_once() and metrics.status()['pending']==1
    metrics.transport=lambda *a,**kw:SimpleNamespace(status_code=400)
    assert not metrics.deliver_once() and metrics.status()['rejected']==1
    assert metrics.status()['error']=='observation_rejected'

def test_wrong_receipt_not_deleted(metrics):
    metrics.configure(True,POLICY); assert metrics.deliver_once(); metrics.record('app_open')
    metrics.transport=lambda *a,**kw:SimpleNamespace(status_code=200,json=lambda:{'accepted':True,'event_id':str(uuid4())})
    assert not metrics.deliver_once() and metrics.status()['pending']==1

def test_cross_account_isolation(metrics):
    metrics.configure(True,POLICY); assert metrics.deliver_once(); metrics.record('studio_save')
    bob=ProductMetrics(directory=metrics.path.parent.parent,account='bob',credentials=lambda:'bob-token')
    assert metrics.path!=bob.path and not bob.status()['enabled']
    assert not bob.record('app_open') and metrics.status()['pending']==1

def test_committed_event_survives_hard_exit(tmp_path):
    code='''import os,sys
from api.product_metrics import ProductMetrics,POLICY
ProductMetrics.start=lambda self:None
m=ProductMetrics(directory=sys.argv[1],account='crash-test',credentials=lambda:None)
m.configure(True,POLICY)
assert m.record('studio_save')
os._exit(23)
'''
    done=subprocess.run([sys.executable,'-c',code,str(tmp_path)],cwd=Path(__file__).resolve().parents[1])
    assert done.returncode==23
    m=ProductMetrics(directory=tmp_path,account='crash-test',credentials=lambda:None)
    assert m.status()['pending']==1

def test_shutdown_preserves_offline_outbox(metrics):
    metrics.configure(True,POLICY); assert metrics.deliver_once(); metrics.record('studio_save'); metrics.close()
    assert metrics.status()['pending']==1 and not metrics.record('app_open')

def test_record_does_not_wait_for_network_and_revoke_waits_for_inflight(metrics):
    import threading
    entered=threading.Event();release=threading.Event();revoked=threading.Event()
    def slow(url,**kw):
        entered.set();assert release.wait(3)
        return SimpleNamespace(status_code=200,json=lambda:dict(accepted=True,event_id=kw['json']['event_id']))
    metrics.configure(True,POLICY); assert metrics.deliver_once();metrics.record('app_open');metrics.transport=slow
    sender=threading.Thread(target=metrics.deliver_once);sender.start();assert entered.wait(1)
    # A second durable recording completes while HTTP is deliberately blocked.
    recorded=threading.Event()
    writer=threading.Thread(target=lambda:(metrics.record('studio_save'),recorded.set()));writer.start()
    assert recorded.wait(1)
    revoker=threading.Thread(target=lambda:(metrics.configure(False,POLICY),revoked.set()));revoker.start()
    assert not revoked.wait(.05)
    release.set();sender.join(2);writer.join(2);revoker.join(2)
    assert revoked.is_set() and metrics.status()['pending']==0 and not metrics.status()['enabled']
