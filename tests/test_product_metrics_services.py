import json
import threading
from pathlib import Path
from uuid import uuid4
import pytest
from api.product_metrics import ProductMetrics,POLICY
from web_platform.application_services import ApplicationServices
from web_platform.gateway import create_gateway_app
from fastapi.testclient import TestClient

@pytest.fixture
def service(tmp_path,monkeypatch):
    monkeypatch.setattr(ProductMetrics,'start',lambda self:None)
    s=object.__new__(ApplicationServices)
    s.account='synthetic-owner';s.data_dir=tmp_path;s._lock=threading.RLock()
    s._audit=lambda *a,**kw:None
    s.runtime_snapshot=lambda:{}
    s._refresh_runtime_after_strategy_change=lambda:{}
    s.data_dir.joinpath('token.json').write_text(json.dumps({'access_token':'never-persist-in-outbox','user_info':{'id':s.account}}))
    s.data_dir.joinpath('trades-original.json').write_text('[{"original":true}]')
    return s

def actions(service):
    m=service.product_metrics()
    with m.connect() as c:return [json.loads(r['payload'])['action'] for r in c.execute('SELECT payload FROM outbox ORDER BY rowid')]

def test_real_strategy_save_boundary_and_failure_not_counted(service):
    original=service.data_dir.joinpath('trades-original.json').read_bytes()
    service.configure_product_metrics(enabled=True,policy=POLICY)
    saved=service.submit_strategy(scope='binance',name='synthetic',rules={'entry':'RSI < 30'},source_kind='manual')
    assert saved['strategy_key'] and actions(service)==['studio_save']
    # Existing approval safety rejects incomplete strategies before a metric.
    with pytest.raises(ValueError):service.strategy_action(scope='binance',strategy_key=saved['strategy_key'],version_id=saved['version_id'],action='approve')
    assert actions(service)==['studio_save']
    assert service.data_dir.joinpath('trades-original.json').read_bytes()==original
    assert b'never-persist-in-outbox' not in service.product_metrics().path.read_bytes()

def test_local_consent_auth_intent_and_ui_event(service):
    client=TestClient(create_gateway_app(token='x'*40,application_services=service))
    body={'enabled':True,'policy':POLICY}
    assert client.post('/api/v1/product-metrics/consent',json=body).status_code==401
    auth={'Authorization':'Bearer '+'x'*40}
    assert client.post('/api/v1/product-metrics/consent',json=body,headers=auth).status_code==428
    headers={**auth,'X-NoahAI-Intent':'confirmed'}
    assert client.post('/api/v1/product-metrics/consent',json=body,headers={**headers,'Origin':'https://untrusted.example'}).status_code==403
    assert client.post('/api/v1/product-metrics/consent',json=body,headers=headers).json()['enabled']
    event={'action':'studio_open','event_id':str(uuid4())}
    assert client.post('/api/v1/product-metrics/observe',json=event,headers=headers).json()['queued']
    assert actions(service)==['studio_open']
    assert client.post('/api/v1/product-metrics/observe',json={'action':'studio_save','event_id':str(uuid4())},headers=headers).status_code==400
    body['enabled']=False
    assert not client.post('/api/v1/product-metrics/consent',json=body,headers=headers).json()['enabled']
    assert not client.post('/api/v1/product-metrics/observe',json=event,headers=headers).json()['queued']
    assert actions(service)==[]

def test_credentials_bound_to_original_account(service):
    m=service.product_metrics()
    assert m.credentials()=='never-persist-in-outbox'
    service.data_dir.joinpath('token.json').write_text(json.dumps({'access_token':'other-account-token','user_info':{'id':'someone-else'}}))
    assert m.credentials() is None
    service.account='new-owner'
    assert m.credentials() is None

def test_storage_failure_visible_without_failing_real_save(service,monkeypatch):
    def disk_full(*a,**kw):raise OSError('synthetic disk full')
    monkeypatch.setattr(service.product_metrics(),'record',disk_full)
    item=service.submit_strategy(scope='binance',name='saved despite telemetry error',rules={'entry':'RSI < 25'},source_kind='manual')
    assert item['strategy_key']
    assert service.product_metrics_status()['error']=='collection_error'

def test_shutdown_never_restarts_delivery(service,monkeypatch):
    starts=[]
    monkeypatch.setattr(ProductMetrics,'start',lambda self:starts.append(self))
    service._accepting_runtime_commands=False
    assert not service.observe_product('app_open')
    assert not service.product_metrics_status()['enabled']
    assert starts==[]
    with pytest.raises(ValueError,match='shutdown'):service.configure_product_metrics(enabled=True,policy=POLICY)
