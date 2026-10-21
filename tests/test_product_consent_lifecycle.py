"""The durable control stream must work even with collection disabled."""
import json
from types import SimpleNamespace
import requests
from api.product_metrics import ProductMetrics, POLICY


def make(tmp_path,monkeypatch):
    monkeypatch.setattr(ProductMetrics,'start',lambda self:None)
    return ProductMetrics(directory=tmp_path,account='synthetic-only',credentials=lambda:'token')


def test_offline_withdrawal_survives_restart_and_arrives_before_old_grant(tmp_path,monkeypatch):
    m=make(tmp_path,monkeypatch)
    m.transport=lambda *a,**k:(_ for _ in ()).throw(requests.ConnectionError())
    m.configure(True,POLICY); m.record('studio_open')
    assert not m.deliver_once()
    m.configure(False,POLICY)
    assert not m.status()['enabled'] and m.status()['pending']==0
    assert m.status()['consent_pending']==2
    assert not m.record('app_open')
    m.close()
    m=make(tmp_path,monkeypatch); seen=[]
    def ack(*a,**kw):
        seen.append(kw['json'])
        return SimpleNamespace(status_code=200,json=lambda:dict(accepted=True,event_id=kw['json']['event_id']))
    m.transport=ack
    assert m.deliver_once() and m.deliver_once() and not m.deliver_once()
    assert [e['action'] for e in seen]==['consent_withdrawn','consent_granted']
    assert seen[0]['consent_revision']>seen[1]['consent_revision']
    assert m.status()['consent_pending']==0 and not m.status()['enabled']


def test_upgrade_preserves_queue_without_inventing_consent(tmp_path,monkeypatch):
    m=make(tmp_path,monkeypatch)
    old=dict(event_id='00000000-0000-4000-8000-000000000001',action='studio_open',mode='none',consent=True,consent_version='product-observation-20261018',occurred_at='2026-10-18T00:00:00+00:00')
    with m.connect() as c:
        c.execute('INSERT INTO consent VALUES(1,1,?)',('product-observation-20261018',))
        c.execute('INSERT INTO outbox(id,payload) VALUES(?,?)',(old['event_id'],json.dumps(old)))
    assert m.status()['consent_reconfirmation_required']
    assert not m.status()['enabled'] and not m.record('app_open') and not m.deliver_once()
    with m.connect() as c:
        assert json.loads(c.execute('SELECT payload FROM outbox').fetchone()[0])==old
    m.configure(False,POLICY)
    assert m.status()['pending']==0 and m.status()['consent_pending']==1
