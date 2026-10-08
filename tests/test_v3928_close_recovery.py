import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from trading.trader import Position, PositionSide
from trading.unified_trader import UnifiedTrader
from trading.execution_mode import ExecutionMode
from trading.paper_position_store import save_positions, load_positions
from trading.paper_strategy_ledger import paper_outcome_calculation_status, read_paper_strategy_outcomes
from trading.paper_capital import paper_available_funds
from trading.custom_strategy_order_plan import evaluate_order_plan


def fixture(tmp_path, contract=.01, side=PositionSide.LONG):
    p=Position(symbol='QA/USDT:USDT', side=side, entry_price=100., current_price=110., quantity=10., leverage=5,
        unrealized_pnl=0., unrealized_pnl_percent=0., entry_time=datetime(2026,10,8,tzinfo=timezone.utc),
        position_id='recovery-position', position_owner='noahai', execution_mode='paper',
        entry_evidence={'position_sizing':{'contract_size':contract}})
    t=UnifiedTrader.__new__(UnifiedTrader);t.settings={};t.logger=MagicMock();t.recorder=None
    t.paper_positions={'okx':{p.symbol:p}};t._execution_mode=lambda venue:ExecutionMode.PAPER
    t._position_store=lambda venue:t.paper_positions.setdefault(venue,{})
    t._paper_position_persistence_enabled=True;t._paper_position_path=lambda:tmp_path/'positions.json'
    t._is_order_success=lambda result:result.get('status')=='success'
    t._update_trade_stats_unified=MagicMock();t.position_sizing_snapshots={}
    t.get_exchange_client=lambda *a:(_ for _ in ()).throw(AssertionError('no provider allowed'))
    decision=evaluate_order_plan({'partial_take_profits':[{'target_percent':1.,'close_fraction':.4}]},None,pnl_percent=10.,current_quantity=10.)
    return t,p,decision


def test_snapshot_failure_recovers_committed_partial_once(tmp_path):
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        with patch('trading.unified_trader.save_positions',side_effect=OSError('snapshot full')):
            assert not t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
        restarted,_,_=fixture(tmp_path);restarted.paper_positions={}
        restarted._restore_paper_positions()
        q=restarted.paper_positions['okx'][p.symbol]
        assert q.quantity==6 and q.custom_order_plan_state['completed_partial_indices']==[0]
        assert not restarted._execute_advanced_partial_close_unified('okx',q.symbol,q,120.,d)
        restarted._restore_paper_positions()
        assert restarted.paper_positions['okx'][p.symbol].quantity==6
        assert len(read_paper_strategy_outcomes(path=ledger))==1


def test_missing_contract_does_not_become_verified_funds(tmp_path):
    row=dict(event_id='legacy',exchange='okx',scope='unified',execution_mode='paper',quote_currency='USDT',
        calculation_status='valid',cost_calculation_status='recorded_contract',entry_price=100,quantity=2,net_pnl=20)
    ledger=tmp_path/'ledger.jsonl';ledger.write_text(json.dumps(row)+'\n');original=ledger.read_bytes()
    assert paper_outcome_calculation_status(row)=='legacy_unverified'
    funds=paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=ledger)
    assert funds['capital_basis']=='paper_funds_unverified'
    assert ledger.read_bytes()==original


@pytest.mark.parametrize('partial',[True,False])
@pytest.mark.parametrize('fault',['ledger','snapshot','crash','fsync'])
def test_close_failure_matrix(tmp_path,partial,fault):
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    def close(t,p,price):
        return t._execute_advanced_partial_close_unified('okx',p.symbol,p,price,d) if partial else t._close_position_unified('okx',p.symbol,p,price)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger),patch('trading.unified_trader.emit_position_closed'):
        if fault=='ledger':
            context=patch('trading.unified_trader.record_paper_strategy_outcome',side_effect=OSError('ledger fail'))
        elif fault=='snapshot':
            context=patch('trading.unified_trader.save_positions',side_effect=OSError('snapshot fail'))
        elif fault=='fsync':
            context=patch('trading.paper_strategy_ledger.os.fsync',side_effect=OSError('fsync fail'))
        else:
            context=patch.object(t,'_paper_close_commit_hook',side_effect=SystemExit('process terminated'))
        with context:
            if fault=='crash':
                with pytest.raises(SystemExit):close(t,p,110.)
            else:assert not close(t,p,110.)
        assert load_positions(t._paper_position_path(),Position,PositionSide)['okx'][p.symbol].quantity==10
        assert not t._update_trade_stats_unified.called
        restarted,_,_=fixture(tmp_path);restarted.paper_positions={};restarted._restore_paper_positions()
        assert not restarted._paper_recovery_error
        if fault=='ledger':
            q=restarted.paper_positions['okx'][p.symbol];assert q.quantity==10
            assert close(restarted,q,120.)
        elif partial:
            q=restarted.paper_positions['okx'][p.symbol];assert q.quantity==6
            for price in [110.,120.]:assert not close(restarted,q,price)
        else:
            assert not restarted.paper_positions.get('okx')
            for price in [110.,120.]:assert not close(restarted,p,price)
        for _ in range(3):restarted._restore_paper_positions()
        rows=read_paper_strategy_outcomes(path=ledger)
        assert len(rows)==1 and rows[0]['quantity']==(4 if partial else 10)
        positions=restarted.paper_positions.get('okx',{})
        funds=paper_available_funds(1000,positions,venue='okx',quote='USDT',ledger_file=ledger)
        assert funds['capital_basis']=='paper_reconciled_funds'
        expected_margin=(6*100*.01/5*1.02) if partial else 0.
        assert funds['open_margin']==pytest.approx(expected_margin)
        assert funds['available_capital']==pytest.approx(1000+rows[0]['net_pnl']-expected_margin)


@pytest.mark.parametrize('contract',[.01,.1,1.,10.,100.,1000.,100000.])
@pytest.mark.parametrize('side',[PositionSide.LONG,PositionSide.SHORT])
@pytest.mark.parametrize('prices',[(110.,120.),(90.,80.)])
def test_actual_close_matrix_and_restart(tmp_path,contract,side,prices):
    t,p,d=fixture(tmp_path,contract,side);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger),patch('trading.unified_trader.emit_position_closed'):
        assert t._execute_advanced_partial_close_unified('okx',p.symbol,p,prices[0],d)
        t._restore_paper_positions();p=t.paper_positions['okx'][p.symbol]
        assert p.quantity==6
        assert t._close_position_unified('okx',p.symbol,p,prices[1])
        t._restore_paper_positions();assert not t.paper_positions['okx']
    rows=read_paper_strategy_outcomes(path=ledger)
    assert [r['quantity'] for r in rows]==[4.,6.]
    gross=((prices[0]-100)*4+(prices[1]-100)*6)*contract*(1 if side==PositionSide.LONG else -1)
    assert sum(r['gross_pnl'] for r in rows)==pytest.approx(gross)
    assert sum(r['fees'] for r in rows)==pytest.approx(.4*contract)
    assert sum(r['estimated_slippage'] for r in rows)==pytest.approx(.2*contract)
    assert sum(r['net_pnl'] for r in rows)==pytest.approx(gross-.6*contract)
    assert len(set(r['event_id'] for r in rows))==2


@pytest.mark.parametrize('partial',[True,False])
def test_real_process_exit_between_commits(tmp_path,partial):
    import subprocess,sys
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    script="""import os,sys;from pathlib import Path;from unittest.mock import patch
sys.path.insert(0,'tests')
from test_v3928_close_recovery import fixture
folder=Path(sys.argv[1]);t,p,d=fixture(folder)
t._paper_close_commit_hook=lambda:os._exit(73)
with patch('trading.paper_strategy_ledger.ledger_path',return_value=folder/'ledger.jsonl'):
 if sys.argv[2]=='True':t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
 else:t._close_position_unified('okx',p.symbol,p,110.)
"""
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path),str(partial)],capture_output=True)
    assert result.returncode==73,result.stderr
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        t._restore_paper_positions();assert not t._paper_recovery_error
        if partial:assert t.paper_positions['okx'][p.symbol].quantity==6
        else:assert not t.paper_positions['okx']
        t._restore_paper_positions()
    assert len(read_paper_strategy_outcomes(path=ledger))==1


@pytest.mark.parametrize('kind',['legacy','torn','tampered','conflict','outcome','event'])
def test_insufficient_recovery_proof_preserves_and_blocks(tmp_path,kind):
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        with patch.object(t,'_paper_close_commit_hook',side_effect=SystemExit):
            with pytest.raises(SystemExit):t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
    row=json.loads(ledger.read_text())
    if kind=='legacy':row.pop('close_recovery')
    if kind=='tampered':row['close_recovery']['after']['quantity']=7
    if kind=='outcome':row['net_pnl']=1000
    if kind=='event':row['event_id']='unbound-event'
    data=json.dumps(row)+'\n'
    if kind=='torn':data=data[:-2]
    if kind=='conflict':data+=json.dumps({**row,'net_pnl':1000})+'\n'
    ledger.write_text(data);original=ledger.read_bytes();snapshot=t._paper_position_path().read_bytes()
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        t._restore_paper_positions();assert t._paper_recovery_error
        assert not t._execute_advanced_partial_close_unified('okx',p.symbol,p,120.,d)
    assert ledger.read_bytes()==original and t._paper_position_path().read_bytes()==snapshot


@pytest.mark.parametrize('venue',['okx','bybit','bitget'])
@pytest.mark.parametrize('notional',[None,200,2])
def test_legacy_unit_cannot_be_inferred_from_valid_or_notional(venue,notional):
    from trading.paper_strategy_ledger import summarize_paper_outcomes
    row=dict(exchange=venue,scope='unified',execution_mode='paper',quote_currency='USDT',
        calculation_status='valid',cost_calculation_status='recorded_contract',entry_price=100,quantity=2,net_pnl=20)
    if notional is not None:row['sizing_final_notional']=notional
    original=json.dumps(row)
    assert paper_outcome_calculation_status(row)=='legacy_unverified'
    summary=summarize_paper_outcomes([row],default_currency='USDT')
    assert summary['closed_count']==0 and summary['win_rate'] is None
    assert json.dumps(row)==original
    assert paper_outcome_calculation_status({**row,'contract_size':.01})=='valid'
    for spot in ['upbit','coinone','bithumb','binance']:
        assert paper_outcome_calculation_status({**row,'exchange':spot})=='valid'


@pytest.mark.parametrize('partial',[True,False])
def test_checkpoint_detects_removed_or_rewritten_committed_ledger(tmp_path,partial):
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger),patch('trading.unified_trader.emit_position_closed'):
        if partial:assert t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
        else:assert t._close_position_unified('okx',p.symbol,p,110.)
        original=ledger.read_bytes();snapshot=t._paper_position_path().read_bytes()
        ledger.write_bytes(b'')
        t._restore_paper_positions();assert t._paper_recovery_error=='paper_close_recovery_ledger_changed'
        assert t._paper_position_path().read_bytes()==snapshot
        ledger.write_bytes(original)
        t._restore_paper_positions();assert not t._paper_recovery_error


def test_same_process_retry_after_snapshot_failure_uses_original_close_price(tmp_path):
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        with patch('trading.unified_trader.save_positions',side_effect=OSError('disk')):
            assert not t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
        assert p.quantity==10
        assert not t._execute_advanced_partial_close_unified('okx',p.symbol,p,120.,d)
        assert p.quantity==6
    rows=read_paper_strategy_outcomes(path=ledger)
    assert len(rows)==1 and rows[0]['exit_price']==110.


def test_recovery_error_blocks_new_evaluation_even_if_memory_is_empty(tmp_path):
    from types import SimpleNamespace
    from web_platform.runtime_bridge import HeadlessRuntimeBridge
    t,p,d=fixture(tmp_path);t.paper_positions={};t._paper_recovery_error='paper_close_recovery_required'
    t._opportunity_account='copied';t.settings={'paper_trading':True};t.recorder=SimpleNamespace(db_path=str(tmp_path/'trading.db'))
    bridge=HeadlessRuntimeBridge(account='copied');bridge._app=SimpleNamespace(unified_trader=t,settings=t.settings)
    with pytest.raises(RuntimeError,match='paper_close_recovery_required'):bridge.start_paper_session('okx')


@pytest.mark.parametrize('partial',[True,False])
@pytest.mark.parametrize('fault',['replace','directory_sync'])
def test_snapshot_atomic_boundaries_recover_once(tmp_path,partial,fault):
    from pathlib import Path
    from trading.paper_position_store import fsync_parent
    t,p,d=fixture(tmp_path);ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    replace=Path.replace
    def fail_replace(path,target):
        if path==t._paper_position_path().with_suffix('.json.tmp'):raise OSError('replace failed')
        return replace(path,target)
    def fail_directory(path):
        if path==t._paper_position_path():raise OSError('directory sync failed after replace')
        return fsync_parent(path)
    context=patch.object(Path,'replace',fail_replace) if fault=='replace' else patch('trading.paper_position_store.fsync_parent',fail_directory)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger),patch('trading.unified_trader.emit_position_closed'):
        with context:
            result=t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d) if partial else t._close_position_unified('okx',p.symbol,p,110.)
            assert not result and t._paper_recovery_error
        for _ in range(3):
            t._restore_paper_positions();assert not t._paper_recovery_error
            if partial:
                q=t.paper_positions['okx'][p.symbol];assert q.quantity==6
                assert not t._execute_advanced_partial_close_unified('okx',q.symbol,q,120.,d)
            else:
                assert not t.paper_positions['okx']
                assert not t._close_position_unified('okx',p.symbol,p,120.)
        assert len(read_paper_strategy_outcomes(path=ledger))==1


@pytest.mark.parametrize('venue',['upbit','bithumb','coinone','binance'])
@pytest.mark.parametrize('partial',[True,False])
def test_intrinsic_base_quantity_closes_do_not_require_foreign_contract_evidence(tmp_path,venue,partial):
    t,p,d=fixture(tmp_path);p.entry_evidence={}
    p.symbol='QA/KRW' if venue!='binance' else 'QAUSDT'
    t.paper_positions={venue:{p.symbol:p}}
    ledger=tmp_path/'ledger.jsonl';save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger),patch('trading.unified_trader.emit_position_closed'):
        result=t._execute_advanced_partial_close_unified(venue,p.symbol,p,110.,d) if partial else t._close_position_unified(venue,p.symbol,p,110.)
        assert result
        t._restore_paper_positions();assert not t._paper_recovery_error
        if partial:assert t.paper_positions[venue][p.symbol].quantity==6
        else:assert not t.paper_positions[venue]
    rows=read_paper_strategy_outcomes(path=ledger)
    assert len(rows)==1 and paper_outcome_calculation_status(rows[0])=='valid'
    assert rows[0]['gross_pnl']==pytest.approx(40 if partial else 100)


@pytest.mark.parametrize('engine',['unified','binance'])
def test_failed_restore_cannot_overwrite_corrupt_disk_with_empty_memory(tmp_path,engine):
    if engine=='unified':t,p,_=fixture(tmp_path);stores={'okx':{p.symbol:p}}
    else:
        from test_v3928_binance_recovery import fixture as binance_fixture
        t,p=binance_fixture(tmp_path);stores={'binance':{p.symbol:p}}
    path=t._paper_position_path();save_positions(path,stores);healthy=path.read_bytes();path.write_bytes(b'{incomplete')
    t.paper_positions={} if engine=='unified' else None
    if engine=='binance':t.paper_active_positions={}
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=tmp_path/'ledger.jsonl'):
        t._restore_paper_positions();assert t._paper_restore_failed and t._paper_recovery_error
        for _ in range(3):assert not t._recover_paper_closes()
        with pytest.raises(ValueError):t._persist_paper_positions()
        assert path.read_bytes()==b'{incomplete'
        path.write_bytes(healthy)
        assert t._recover_paper_closes() and not t._paper_restore_failed
        positions=t.paper_positions['okx'] if engine=='unified' else t.paper_active_positions
        assert positions[p.symbol].quantity==10
