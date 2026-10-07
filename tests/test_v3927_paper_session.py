import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from trading.paper_capital import paper_available_funds
from trading.paper_funds_session import start_session
from trading.opportunity_coordinator import OpportunityCoordinator
from web_platform.runtime_bridge import HeadlessRuntimeBridge


def legacy(venue='okx', quote='USDT'):
    return dict(event_id='old', exchange=venue, execution_mode='paper',scope='unified',net_pnl=0.)


def make_ledger(tmp_path, row=None):
    ledger=tmp_path/'strategy_paper_outcomes.jsonl'
    ledger.write_text(json.dumps(row or legacy())+'\n')
    return ledger


def start(ledger, **changes):
    args=dict(venue='okx',quote='USDT',initial_equity=1000.,positions={},stopped=True,pending_orders=0)
    args.update(changes)
    return start_session(ledger, **args)


def test_explicit_new_session_preserves_history_and_survives_restart_without_resetting_losses(tmp_path):
    ledger=make_ledger(tmp_path)
    original=ledger.read_bytes()
    assert paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)['capital_basis']=='paper_funds_unverified'
    session=start(ledger)
    assert session['created']
    assert hashlib.sha256(original).hexdigest()==session['preserved_sha256']
    with ledger.open('a') as f:
        f.write(json.dumps(dict(event_id='new',exchange='okx',execution_mode='paper',scope='unified',
            quote_currency='USDT',calculation_status='valid',contract_size=.01,net_pnl=-75.))+'\n')
    funds=paper_available_funds(2000,{},venue='okx',quote='USDT',ledger_file=ledger)
    assert funds['initial_capital']==1000 and funds['available_capital']==925
    assert funds['paper_session_id']==session['session_id'] and funds['historical_pnl_restored'] is False
    assert start(ledger,initial_equity=3000)['created'] is False
    assert ledger.read_bytes().startswith(original)
    from trading.paper_strategy_ledger import read_paper_strategy_outcomes
    rows=read_paper_strategy_outcomes(path=ledger)
    assert len(rows)==2 and rows[0]['net_pnl']==0. and 'contract_size' not in rows[0]


@pytest.mark.parametrize('change,reason',[
    ({'stopped':False},'paper_session_stop_required'),
    ({'positions':{'QA':{}}},'paper_session_flat_required'),
    ({'pending_orders':1},'paper_session_pending_orders'),
    ({'pending_orders':None},'paper_session_pending_orders'),
    ({'initial_equity':float('nan')},'initial_equity_unverified'),
    ({'initial_equity':True},'initial_equity_unverified')])
def test_new_session_cannot_bypass_positions_reservations_or_unknown_capital(tmp_path,change,reason):
    ledger=make_ledger(tmp_path)
    with pytest.raises(ValueError,match=reason):start(ledger,**change)
    assert not (tmp_path/'paper_funds_sessions.json').exists()


def test_verified_loss_wallet_and_conflicting_history_cannot_be_reset(tmp_path):
    row={**legacy(), 'calculation_status':'valid','quote_currency':'USDT','net_pnl':-2000}
    ledger=make_ledger(tmp_path,row)
    with pytest.raises(ValueError,match='paper_session_legacy_block_required'):start(ledger)
    with ledger.open('a') as f:f.write(json.dumps({**row,'net_pnl':10})+'\n')
    with pytest.raises(ValueError,match='paper_session_legacy_block_required'):start(ledger)


@pytest.mark.parametrize('change',['truncate','edit','corrupt_state'])
def test_preserved_boundary_corruption_blocks_new_capital(tmp_path,change):
    ledger=make_ledger(tmp_path);start(ledger)
    if change=='truncate':ledger.write_bytes(b'')
    elif change=='edit':ledger.write_text(ledger.read_text().replace('0.0','1.0'))
    else:(tmp_path/'paper_funds_sessions.json').write_text('broken')
    result=paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)
    assert result['capital_basis']=='paper_funds_unverified' and result['realized_net_pnl'] is None


def test_account_venue_currency_and_parallel_observations_stay_separate(tmp_path):
    ledger=make_ledger(tmp_path);start(ledger)
    assert paper_available_funds(1000,{},venue='bybit',quote='USDT',ledger_file=ledger)['available_capital']==1000
    other=tmp_path/'other';other.mkdir()
    with ledger.open('a') as f:
        for row in [dict(event_id='shadow',exchange='okx',execution_mode='paper',cost_calculation_status='parallel_paper_recorded_contract',net_pnl=99999),
                    dict(event_id='krw',exchange='upbit',execution_mode='paper',quote_currency='KRW',calculation_status='valid',net_pnl=8000)]:
            f.write(json.dumps(row)+'\n')
    assert paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)['available_capital']==1000
    assert paper_available_funds(10000,{},venue='upbit',quote='KRW',ledger_file=ledger)['available_capital']==18000
    assert 'paper_session_id' not in paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=other/'strategy_paper_outcomes.jsonl')


def bridge(tmp_path):
    owner=SimpleNamespace(settings={'paper_trading':True},recorder=SimpleNamespace(db_path=str(tmp_path/'trading.db')),
        _opportunity_account='qa',paper_positions={'okx':{}},_opportunity_coordinator=OpportunityCoordinator(tmp_path/'runtime.db'))
    app=SimpleNamespace(unified_trader=owner,settings=owner.settings,running_crypto_exchanges=lambda:[])
    obj=HeadlessRuntimeBridge(account='qa');obj._app=app
    return obj,owner,app


def test_runtime_rechecks_memory_persisted_positions_and_orders_without_api_or_start(tmp_path):
    ledger=make_ledger(tmp_path);obj,owner,app=bridge(tmp_path)
    owner.paper_positions['okx']={'QA':{}}
    with pytest.raises(RuntimeError,match='paper_session_flat_required'):obj.start_paper_session('okx')
    owner.paper_positions['okx']={}
    disk=tmp_path/'paper_open_positions_unified.json'
    disk.write_text(json.dumps({'execution_mode':'paper','venues':{'okx':{'QA':{}}}}))
    with pytest.raises(RuntimeError,match='paper_session_flat_required'):obj.start_paper_session('okx')
    disk.unlink();app.running_crypto_exchanges=lambda:['okx']
    with pytest.raises(RuntimeError,match='paper_session_stop_required'):obj.start_paper_session('okx')
    app.running_crypto_exchanges=lambda:[]
    result=obj.start_paper_session('okx')
    assert result['created'] and result['orders_submitted'] is False and result['trading_started'] is False
    assert owner._last_capital_evidence[('okx','paper')]['paper_session_id']==result['session_id']
    assert json.loads(ledger.read_text())==legacy()


def test_runtime_refuses_live_and_account_switch(tmp_path):
    make_ledger(tmp_path);obj,owner,app=bridge(tmp_path)
    owner.settings['paper_trading']=False
    with pytest.raises(RuntimeError,match='paper_session_mode_required'):obj.start_paper_session('okx')
    owner.settings['paper_trading']=True;owner._opportunity_account='different'
    with pytest.raises(RuntimeError,match='paper_account_scope_changed'):obj.start_paper_session('okx')


def test_runtime_checks_persisted_reservations_at_action_time(tmp_path):
    from trading.opportunity_coordinator import account_scope_for
    make_ledger(tmp_path);obj,owner,app=bridge(tmp_path)
    coordinator=owner._opportunity_coordinator
    auth=coordinator.authorize(policy={},asset_class='crypto',target='okx',symbol='QA/USDT:USDT',
        direction='LONG',quantity=1,price=100,stop_fraction=.01,
        account_scope=account_scope_for(owner,'paper'),signal_time=1800)
    assert auth.allowed
    owner._opportunity_coordinator=OpportunityCoordinator(tmp_path/'runtime.db')
    with pytest.raises(RuntimeError,match='paper_session_pending_orders'):obj.start_paper_session('okx')
    assert not (tmp_path/'paper_funds_sessions.json').exists()


def test_gateway_requires_auth_intent_acknowledgement_and_reports_real_action(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.application_services import ApplicationServices
    from web_platform.gateway import create_gateway_app
    import web_platform.application_services as services_module
    monkeypatch.setattr(services_module,'get_app_data_dir',lambda:str(tmp_path))
    monkeypatch.setattr(services_module,'set_current_user_account',lambda account:None)
    monkeypatch.setattr(services_module,'load_settings',lambda *args,**kwargs:{'paper_trading':True})
    make_ledger(tmp_path);obj,owner,app=bridge(tmp_path)
    services=ApplicationServices(account='qa',runtime_bridge=obj)
    token='local-test-token-which-is-at-least-32-characters'
    client=TestClient(create_gateway_app(token=token,application_services=services))
    endpoint='/api/v1/maintenance/paper-session';payload={'source':'okx','new_baseline_acknowledged':True}
    auth={'Authorization':f'Bearer {token}'};intent={**auth,'X-NoahAI-Intent':'confirmed'}
    assert client.post(endpoint,json=payload).status_code==401
    assert client.post(endpoint,headers=auth,json=payload).status_code==428
    assert client.post(endpoint,headers=intent,json={'source':'okx'}).status_code==400
    response=client.post(endpoint,headers=intent,json=payload)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['created'] and result['historical_pnl_restored'] is False and result['trading_started'] is False
    assert client.post(endpoint,headers=intent,json=payload).json()['created'] is False



def test_missing_session_basis_and_boolean_initial_capital_fail_closed(tmp_path):
    ledger=make_ledger(tmp_path);start(ledger)
    path=tmp_path/'paper_funds_sessions.json';original=json.loads(path.read_text())
    for change in [{'basis':None},{'initial_capital':True}]:
        row=json.loads(json.dumps(original));row['sessions']['okx:USDT'].update(change);path.write_text(json.dumps(row))
        funds=paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)
        assert funds['capital_basis']=='paper_funds_unverified' and funds['realized_net_pnl'] is None


def test_runtime_storage_failure_has_a_finite_nonprivate_reason(tmp_path):
    make_ledger(tmp_path);obj,owner,app=bridge(tmp_path)
    with patch('trading.paper_funds_session.start_session',side_effect=OSError('private path')):
        with pytest.raises(RuntimeError,match='^paper_session_save_failed$'):obj.start_paper_session('okx')
