import json
import time
from copy import deepcopy
import pytest
from trading.finance_connections import FinanceConnectionError, RecipientRegistry, validate_recipient, api_transport
from trading.finance_handoff import FinanceHandoff
from trading.insurance_workspace import InsuranceWorkspace, InsuranceError

def recipient(mode='api'):
    return {'id':'fixture','name':'Synthetic advisor','organization':'Fixture','role':'상담 담당', 'kinds':['loan','insurance','savings'],
            'mode':mode,'enabled':True,'review_reference':'synthetic tests only','contract_version':'v1','retention_days':30,
            'privacy_url':'https://example.org/privacy','contact_url':'https://example.org/contact',
            'endpoints':{k:'https://example.org/'+k for k in ('submit','status','withdraw')},'token_env':'NOAHAI_FINANCE_TEST_TOKEN'}

@pytest.fixture
def setup(tmp_path):
    (tmp_path/'finance_recipients.json').write_text(json.dumps([recipient()]))
    vault=InsuranceWorkspace(tmp_path,'synthetic-handoff');vault.unlock('synthetic-password-123')
    calls=[]
    def transport(recipient,action,payload,key):
        calls.append((action,deepcopy(payload),key))
        return {'request_id':payload['request_id'],'status':'withdrawn' if action=='withdraw' else 'received','receipt_id':'fixture-123'}
    workflow=FinanceHandoff(vault,transport)
    yield vault,workflow,calls
    vault.lock()

def prepare(w,**kwargs):
    return w.dispatch('prepare',scenario={'kind':'insurance','profile':{'insurance_state':'none','private_health':'NEVER_SHARE'}},
        recipient_id='fixture',scopes=['summary','contact'],contact={'name':'private-name','email':'fixture@example.org'},**kwargs)['request']

def consent(w,r):
    return w.dispatch('consent',request_id=r['id'],confirmed=True,payload_hash=r['payload_hash'])['request']

def unblock(vault,r):
    data=deepcopy(vault._data);data['finance_handoffs'][r['id']]['next_attempt']=0;vault._persist(data)

def test_prepare_does_not_send_and_private_fields_never_implicitly_shared(setup):
    vault,w,calls=setup;r=prepare(w)
    assert not calls and r['state']=='prepared'
    assert 'NEVER_SHARE' not in json.dumps(r) and b'private-name' not in vault.path.read_bytes()
    assert w.recipients()['recipients'][0].get('token_env') is None
    with pytest.raises(FinanceConnectionError):w.dispatch('submit',request_id=r['id'])
    with pytest.raises(FinanceConnectionError):w.dispatch('consent',request_id=r['id'],confirmed=True,payload_hash='bad')

def test_consent_submit_duplicate_status_and_withdraw(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));out=w.dispatch('submit',request_id=r['id'])['request']
    assert out['state']=='received' and out['receipt']['id']=='fixture-123'
    w.dispatch('submit',request_id=r['id']);assert len(calls)==1
    unblock(vault,r);out=w.dispatch('withdraw',request_id=r['id'])['request']
    assert out['state']=='withdrawn' and out['consent'] is None and calls[-1][2].endswith(':withdraw')
    assert w.dispatch('delete',request_id=r['id'],confirmed=True)['external_deletion_confirmed'] is False

def test_timeout_requires_lookup_and_reuses_same_idempotency_key(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));keys=[]
    def timeout(recipient,action,payload,key):keys.append(key);raise TimeoutError()
    w.transport=timeout
    assert w.dispatch('submit',request_id=r['id'])['request']['state']=='delivery_unknown'
    with pytest.raises(FinanceConnectionError):w.dispatch('submit',request_id=r['id'])
    unblock(vault,r)
    w.transport=lambda recipient,action,payload,key:{'request_id':payload['request_id'],'status':'not_found'}
    assert w.dispatch('status',request_id=r['id'])['request']['state']=='consented'
    unblock(vault,r);w.transport=timeout;w.dispatch('submit',request_id=r['id']);assert keys==[r['id'],r['id']]

def test_restart_preserves_submitting_state_no_blind_resend(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));data=deepcopy(vault._data);data['finance_handoffs'][r['id']]['state']='submitting';vault._persist(data)
    vault.lock();vault.unlock('synthetic-password-123')
    with pytest.raises(FinanceConnectionError):w.dispatch('submit',request_id=r['id'])
    assert not calls

def test_manual_package_and_receipt_are_not_api_verified(setup):
    vault,w,calls=setup;w.registry.path.write_text(json.dumps([recipient('manual')]))
    r=consent(w,prepare(w));out=w.dispatch('manual_packet',request_id=r['id'])
    assert out['request']['state']=='package_prepared' and out['download']['receipt_confirmed'] is False
    out=w.dispatch('record_manual_receipt',request_id=r['id'],confirmed=True,receipt_id='manual-ref')['request']
    assert out['state']=='receipt_reported' and out['receipt']['basis']=='user_reported' and not calls
    out=w.dispatch('withdraw',request_id=r['id'])['request'];assert out['state']=='withdrawal_requested'

def test_recipient_change_invalidates_consent(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));changed=recipient();changed['contract_version']='v2';w.registry.path.write_text(json.dumps([changed]))
    with pytest.raises(FinanceConnectionError):w.dispatch('submit',request_id=r['id'])
    assert not calls

def test_wrong_receipt_never_becomes_received(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));w.transport=lambda *args:{'request_id':'wrong','status':'received','receipt_id':'anything'}
    assert w.dispatch('submit',request_id=r['id'])['request']['state']=='delivery_unknown'

def test_locked_and_other_account_cannot_read_consultations(setup):
    vault,w,calls=setup;prepare(w);vault.lock()
    with pytest.raises(InsuranceError):w.dispatch('list')
    other=InsuranceWorkspace(w.directory,'other-account');other.unlock('other-password-123')
    assert FinanceHandoff(other).dispatch('list')['requests']==[];other.lock()

def test_transport_blocks_private_network_before_any_socket_connection(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(FinanceConnectionError,match='not_public'):api_transport(recipient(),'submit',{'request_id':'test'},'test')

@pytest.mark.parametrize('field,value',[('privacy_url','http://example.org'),('mode','email'),('retention_days',0),('token_env','HOME')])
def test_recipient_contract_rejects_unsafe_configuration(field,value):
    r=recipient();r[field]=value
    with pytest.raises(FinanceConnectionError):validate_recipient(r)


def test_immediate_withdraw_persists_and_returns_pending_during_backoff(setup):
    vault,w,calls=setup;r=consent(w,prepare(w));w.dispatch('submit',request_id=r['id'])
    out=w.dispatch('withdraw',request_id=r['id'])['request']
    assert out['state']=='withdrawal_requested' and out['consent'] is None
    assert len(calls)==1
    assert w.dispatch('list')['requests'][0]['state']=='withdrawal_requested'


def test_manual_followup_can_finish_without_claiming_api_or_deletion(setup):
    vault,w,calls=setup;w.registry.path.write_text(json.dumps([recipient('manual')]))
    r=consent(w,prepare(w));w.dispatch('manual_packet',request_id=r['id']);w.dispatch('withdraw',request_id=r['id'])
    out=w.dispatch('record_manual_outcome',request_id=r['id'],outcome='withdrawn',receipt_id='manual-outcome',confirmed=True)['request']
    assert out['state']=='withdrawn' and out['receipt']['basis']=='user_reported'
    assert w.dispatch('delete',request_id=r['id'],confirmed=True)['external_deletion_confirmed'] is False
    assert not calls


def test_returned_quote_is_bound_to_receipt_and_not_auto_confirmed(setup):
    vault,w,calls=setup;r=consent(w,prepare(w))
    from datetime import datetime,timezone,timedelta
    expiry=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    response={'request_id':r['id'],'status':'in_consultation','receipt_id':'bound',
              'result':{'assigned_advisor':'합성 담당자','expected_reply_at':expiry,'quotes':[{'id':'q','name':'시험 견적','provider':'fixture','source_url':'https://example.org/q','valid_until':expiry,'terms':{'annual_rate':3,'fees':0}}]}}
    w.transport=lambda *a:response
    out=w.dispatch('submit',request_id=r['id'])['request']
    assert out['result']['basis']=='recipient_api' and not out['result']['quotes'][0]['terms']['confirmed']
    assert out['result']['assigned_advisor']=='합성 담당자'
    w.dispatch('withdraw',request_id=r['id'])
    with pytest.raises(FinanceConnectionError):w.dispatch('record_result',request_id=r['id'],confirmed=True,result=response['result'])


def test_mismatched_return_request_cannot_replace_result(setup):
    vault,w,calls=setup;r=consent(w,prepare(w))
    w.transport=lambda *a:{'request_id':'other','status':'received','receipt_id':'x','result':{'assigned_advisor':'wrong'}}
    out=w.dispatch('submit',request_id=r['id'])['request']
    assert out['state']=='delivery_unknown' and not out.get('result')
