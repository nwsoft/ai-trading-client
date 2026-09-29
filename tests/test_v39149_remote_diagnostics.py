import json
import time
from types import SimpleNamespace

import pytest

from web_platform.remote_control import RemoteControl, public_reason
from web_platform.remote_monitor import RemoteMonitor
from test_v39142_remote_control import context, command


@pytest.mark.parametrize('reason,expected', [('risk_guardrail_blocked','risk_guardrail_blocked'),
    ('API key SECRET balance 123','execution_failed')])
def test_failure_reason_is_safe_durable_and_does_not_retry(tmp_path, reason, expected):
    calls=[]
    def execute(cmd):
        calls.append(cmd)
        raise RuntimeError(reason)
    control=RemoteControl(tmp_path, context, execute)
    cmd=command();approved={'binance':{'revision':'a'*64,'mode':'paper'}}
    assert control.run(cmd,approved)=='rejected'
    restored=RemoteControl(tmp_path,context,execute)
    assert restored.run(cmd,approved)=='rejected'
    assert restored.reason_for(cmd['id'])==expected and len(calls)==1
    assert 'SECRET' not in control.path.read_text()


def test_connection_status_requires_ack_and_permission_save_invalidates_old_success(tmp_path):
    m=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{})
    assert m.status()['connection_status']=='disabled'
    m.configure(True,'PC')
    assert m.status()['connection_status']=='connecting'
    m.last_sent=time.time();assert m.status()['connection_status']=='connected'
    m.last_sent=time.time()-181;assert m.status()['connection_status']=='stale'
    m.error='failed';assert m.status()['connection_status']=='error'
    m.configure(True,'PC');assert m.status()['connection_status']=='connecting'


def test_ack_burst_preserves_unsent_receipts_and_limits_payload(tmp_path):
    requests=[]
    def post(url,**kwargs):
        requests.append(kwargs['json'])
        return SimpleNamespace(status_code=200,json=lambda:{'accepted':True,'commands':[]})
    m=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{'enabled_sources':['binance']},transport=SimpleNamespace(post=post))
    m.config['enabled']=True;m.token='fixture'
    m.control_acks={f'command-{i:03d}':{'status':'rejected','reason_code':'risk_guardrail_blocked'} for i in range(25)}
    m.tick()
    assert len(requests[0]['acknowledgements'])==20
    assert len(json.dumps(requests[0]))<=8192
    assert len(m.control_acks)==5
    m.tick();assert len(requests[1]['acknowledgements'])==5 and not m.control_acks


def test_failed_upload_retains_ack(tmp_path):
    m=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{},
        transport=SimpleNamespace(post=lambda *a,**k:SimpleNamespace(status_code=500)))
    m.config['enabled']=True;m.token='fixture'
    m.control_acks={'command':{'status':'rejected','reason_code':public_reason('SECRET')}}
    m.tick();assert len(m.control_acks)==1 and m.status()['connection_status']=='error'
