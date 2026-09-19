import json
import threading
import time
from types import SimpleNamespace
import pytest
from trading.remote_entry_pause import gate, VENUES
from web_platform.remote_control import RemoteControl
from web_platform.remote_monitor import RemoteMonitor
from web_platform.application_services import ApplicationServices


def context(source='binance',mode='paper',running=False,revision='a'*64):
    return {'revision':revision,'sources':[{'source':source,'mode':mode,'running':running}]}


def command(source='binance',mode='paper',action='start',revision='a'*64):
    return {'id':'remote-command-0123456789','source':source,'mode':mode,'action':action,'revision':revision,'expires':time.time()+120}


@pytest.mark.parametrize('source',sorted(VENUES))
@pytest.mark.parametrize('mode',['paper','live'])
@pytest.mark.parametrize('action',['start','resume'])
def test_scoped_control_is_durable_and_idempotent(tmp_path,source,mode,action):
    calls=[]; snapshot=context(source,mode)
    if action=='resume':gate(tmp_path).set(source,True)
    approved={source:{'revision':snapshot['revision'],'mode':mode}}
    control=RemoteControl(tmp_path,lambda:snapshot,lambda cmd:calls.append(cmd))
    cmd=command(source,mode,action)
    assert control.run(cmd,approved)=='completed'
    assert RemoteControl(tmp_path,lambda:snapshot,lambda cmd:calls.append(cmd)).run(cmd,approved)=='completed'
    assert len(calls)==1


@pytest.mark.parametrize('change',[{'revision':'b'*64},{'mode':'live'},{'expires':0},{'action':'stop'},{'source':'unknown'}])
def test_invalid_context_never_executes(tmp_path,change):
    calls=[];control=RemoteControl(tmp_path,context,lambda cmd:calls.append(cmd))
    with pytest.raises(ValueError):control.run({**command(),**change},{'binance':{'revision':'a'*64,'mode':'paper'}})
    assert not calls


def test_reserved_crash_does_not_retry_and_failure_preserves_pause(tmp_path):
    cmd=command();approved={'binance':{'revision':'a'*64,'mode':'paper'}}
    class Crash(BaseException):pass
    def crash(cmd):raise Crash()
    with pytest.raises(Crash):RemoteControl(tmp_path,context,crash).run(cmd,approved)
    calls=[]
    assert RemoteControl(tmp_path,context,lambda c:calls.append(c)).run(cmd,approved)=='uncertain'
    assert not calls
    def denied(cmd):raise RuntimeError('risk_data_unavailable')
    assert RemoteControl(tmp_path,context,denied).run({**cmd,'id':'different-id'},approved)=='rejected'
    assert gate(tmp_path).state('binance')['paused']


def test_reapproval_rotates_authorization_and_settings_changes_remove_readiness(tmp_path):
    state=context();runtime=lambda:{'enabled_sources':['binance'],'execution_modes':{'binance':'paper'}}
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=runtime,control_context=lambda:state,control_execute=lambda c:None)
    assert not monitor.status()['allow_control']
    monitor.configure(True,'PC',True,True,False)
    first=monitor.config['approved']['binance']['revision']
    monitor.configure(True,'PC',True,True,False)
    assert first!=monitor.config['approved']['binance']['revision']
    state['revision']='c'*64
    assert monitor.approval_context()['revision']!=monitor.config['approved']['binance']['revision']
    assert 'password' not in monitor.path.read_text()


def test_opt_out_does_not_expand_legacy_permission(tmp_path):
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{})
    monitor.configure(True,'PC',True)
    assert not monitor.config['allow_control'] and not monitor.config['share_details']


def test_disabling_remote_never_depends_on_strategy_or_runtime_readiness(tmp_path):
    def unavailable():raise OSError('strategy file unavailable')
    monitor=RemoteMonitor(account='alice',data_dir=tmp_path,snapshot=lambda:{},control_context=unavailable,control_execute=lambda c:None)
    monitor.config.update(enabled=True,allow_control=True)
    monitor.configure(False,'PC',True,True,False)
    assert not monitor.config['enabled'] and monitor.config['approved']=={}


@pytest.mark.parametrize('blocked',['membership','risk','settings','expired','permission','shutdown','account'])
def test_application_rejects_before_start_and_never_resets_risk(tmp_path,blocked):
    calls=[];state=context(mode='live');cmd=command(mode='live')
    monitor=SimpleNamespace(account='alice',config={'enabled':True,'allow_control':True,'approved':{'binance':{'revision':'a'*64,'mode':'live'}}},stop_event=threading.Event(),approval_context=lambda:state)
    risk=SimpleNamespace(evaluate_daily_loss_limit=lambda **kwargs:SimpleNamespace(blocked=blocked=='risk'))
    app=SimpleNamespace(assert_command_allowed=lambda s:None,risk_manager=risk)
    service=SimpleNamespace(account='alice',data_dir=tmp_path,_remote_monitor=monitor,
        refresh_membership_status=lambda **k:{'status':'temporary_check_failure' if blocked=='membership' else 'active','active':True},
        runtime_bridge=SimpleNamespace(_ensure_app=lambda:app,snapshot=lambda:{'running_sources':['binance']}),
        execute_runtime_command=lambda **kw:calls.append(kw))
    if blocked=='settings':state['revision']='b'*64
    if blocked=='expired':cmd['expires']=time.time()-1
    if blocked=='permission':monitor.config['allow_control']=False
    if blocked=='shutdown':monitor.stop_event.set()
    if blocked=='account':service.account='bob'
    with pytest.raises(RuntimeError):ApplicationServices.execute_remote_control(service,cmd,expected_account='alice')
    assert not calls


def test_application_starts_via_existing_command_with_entries_fenced(tmp_path):
    cmd=command();state=context();calls=[]
    monitor=SimpleNamespace(account='alice',config={'enabled':True,'allow_control':True,'approved':{'binance':{'revision':'a'*64,'mode':'paper'}}},stop_event=threading.Event(),approval_context=lambda:state)
    monitor.lock=threading.RLock()
    def execute(**kw):
        assert gate(tmp_path).state('binance')['paused']
        calls.append(kw)
    service=SimpleNamespace(account='alice',data_dir=tmp_path,_remote_monitor=monitor,
        refresh_membership_status=lambda **k:{'status':'active','active':True},
        runtime_bridge=SimpleNamespace(_ensure_app=lambda:SimpleNamespace(assert_command_allowed=lambda s:None),snapshot=lambda:{'running_sources':['binance']}),execute_runtime_command=execute)
    ApplicationServices.execute_remote_control(service,cmd,expected_account='alice')
    assert calls[0]['command']=='trading.start' and calls[0]['payload']['live_confirmation'] is False
    assert not gate(tmp_path).state('binance')['paused']


def test_corrupt_receipt_store_fails_closed(tmp_path):
    path=tmp_path/'remote_control_receipts.json';path.write_text('{broken')
    calls=[]
    with pytest.raises(ValueError):RemoteControl(tmp_path,context,lambda c:calls.append(c)).run(command(),{'binance':{'revision':'a'*64,'mode':'paper'}})
    assert not calls


def test_receipt_completion_disk_failure_fences_running_entries(tmp_path,monkeypatch):
    control=RemoteControl(tmp_path,context,lambda c:None)
    original=control._save
    def fail_completion(receipts):
        if any(r['status']=='completed' for r in receipts.values()):raise OSError('disk full')
        original(receipts)
    monkeypatch.setattr(control,'_save',fail_completion)
    with pytest.raises(OSError):control.run(command(),{'binance':{'revision':'a'*64,'mode':'paper'}})
    assert gate(tmp_path).state('binance')['paused']
    assert json.loads(control.path.read_text())[command()['id']]['status']=='uncertain'


def test_permission_revoked_during_preflight_never_starts(tmp_path):
    calls=[];state=context(mode='live');cmd=command(mode='live')
    monitor=SimpleNamespace(account='alice',config={'enabled':True,'allow_control':True,'approved':{'binance':{'revision':'a'*64,'mode':'live'}}},stop_event=threading.Event(),approval_context=lambda:state)
    def preflight(**kwargs):
        monitor.config['allow_control']=False
        return SimpleNamespace(blocked=False)
    app=SimpleNamespace(assert_command_allowed=lambda s:None,risk_manager=SimpleNamespace(evaluate_daily_loss_limit=preflight))
    service=SimpleNamespace(account='alice',data_dir=tmp_path,_remote_monitor=monitor,
        refresh_membership_status=lambda **k:{'status':'active','active':True},
        runtime_bridge=SimpleNamespace(_ensure_app=lambda:app),execute_runtime_command=lambda **kw:calls.append(kw))
    with pytest.raises(RuntimeError):ApplicationServices.execute_remote_control(service,cmd,expected_account='alice')
    assert not calls


@pytest.mark.parametrize('source',['kiwoom','kis','mirae','shinhan'])
def test_stock_context_never_approves_stale_paper_mode(tmp_path,monkeypatch,source):
    import web_platform.application_services as module
    monkeypatch.setattr(module,'load_settings',lambda **k:{'paper_trading':False})
    service=SimpleNamespace(data_dir=tmp_path,_strategy_filename=lambda scope:scope+'_private.json',
        runtime_bridge=SimpleNamespace(_app=None,snapshot=lambda:{'enabled_sources':[source],'execution_modes':{source:'paper'}}))
    assert ApplicationServices.remote_control_context(service)['sources'][0]['mode']=='learning'
