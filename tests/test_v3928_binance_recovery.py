"""Binance's base-quantity PAPER engine uses the same commit/replay protection."""
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import pytest
from trading.trader import Trader,Position,PositionSide
from trading.execution_mode import ExecutionMode
from trading.paper_position_store import save_positions,load_positions
from trading.paper_strategy_ledger import read_paper_strategy_outcomes
from trading.paper_capital import paper_available_funds


def fixture(tmp_path,price=110.,side=PositionSide.LONG):
    t=Trader.__new__(Trader);t.settings={};t.recorder=None;t.log_event=MagicMock()
    t._execution_mode=lambda:ExecutionMode.PAPER;t._paper_position_persistence_enabled=True
    t._paper_position_path=lambda:tmp_path/'binance.json';t._paper_ledger_path=lambda:tmp_path/'ledger.jsonl'
    t._paper_recovery_error=''
    t.binance_client=SimpleNamespace(get_current_price=lambda symbol:price,create_order=MagicMock(side_effect=AssertionError('no orders')))
    p=Position(symbol='QAUSDT',side=side,entry_price=100.,current_price=price,quantity=10.,leverage=5,
        unrealized_pnl=0.,unrealized_pnl_percent=0.,entry_time=datetime(2026,10,8,tzinfo=timezone.utc),
        position_id='binance-position',execution_mode='paper',position_owner='noahai',tp_price=105. if side==PositionSide.LONG else 95.,sl_price=95. if side==PositionSide.LONG else 105.)
    t.paper_active_positions={p.symbol:p};t.paper_trade_stats={'total_trades':0,'total_pnl':0.,'winning_trades':0,'losing_trades':0}
    return t,p


@pytest.mark.parametrize('fault',['ledger','snapshot','crash','fsync'])
def test_binance_full_close_fault_recovery_and_price_changed_retry(tmp_path,fault):
    t,p=fixture(tmp_path);save_positions(t._paper_position_path(),{'binance':t.paper_active_positions})
    if fault=='ledger':context=patch('trading.paper_strategy_ledger.record_paper_strategy_outcome',side_effect=OSError('ledger'))
    elif fault=='snapshot':context=patch('trading.trader.save_positions',side_effect=OSError('snapshot'))
    elif fault=='fsync':context=patch('trading.paper_strategy_ledger.os.fsync',side_effect=OSError('fsync'))
    else:context=patch.object(t,'_paper_close_commit_hook',side_effect=SystemExit)
    with patch('trading.trader.emit_position_closed') as emitted:
        with context:
            if fault=='crash':
                with pytest.raises(SystemExit):t._monitor_paper_positions()
            else:t._monitor_paper_positions()
        assert p.quantity==10 and t.paper_active_positions[p.symbol] is p
        assert t.paper_trade_stats['total_trades']==0 and not emitted.called
        assert load_positions(t._paper_position_path(),Position,PositionSide)['binance'][p.symbol].quantity==10
        restarted,_=fixture(tmp_path,price=120.);restarted.paper_active_positions={};restarted._restore_paper_positions()
        assert not restarted._paper_recovery_error
        if fault=='ledger':assert p.symbol in restarted.paper_active_positions
        else:assert not restarted.paper_active_positions
        restarted._monitor_paper_positions()
        for _ in range(3):restarted._restore_paper_positions();restarted._monitor_paper_positions()
    rows=read_paper_strategy_outcomes(path=t._paper_ledger_path())
    assert len(rows)==1 and rows[0]['quantity']==10
    assert rows[0]['exit_price']==(120. if fault=='ledger' else 110.)
    funds=paper_available_funds(1000,restarted.paper_active_positions,venue='binance',quote='USDT',ledger_file=t._paper_ledger_path())
    assert funds['open_margin']==0 and funds['available_capital']==pytest.approx(1000+rows[0]['net_pnl'])
    assert not t.binance_client.create_order.called


@pytest.mark.parametrize('side',[PositionSide.LONG,PositionSide.SHORT])
@pytest.mark.parametrize('price',[90.,110.])
def test_binance_base_quantity_cost_contract_is_unchanged(tmp_path,side,price):
    t,p=fixture(tmp_path,price,side);save_positions(t._paper_position_path(),{'binance':t.paper_active_positions})
    with patch('trading.trader.emit_position_closed'):t._monitor_paper_positions()
    row=read_paper_strategy_outcomes(path=t._paper_ledger_path())[0]
    gross=(price-100)*10*(1 if side==PositionSide.LONG else -1)
    assert row['gross_pnl']==pytest.approx(gross)
    assert row['fees']==pytest.approx(.4) and row['estimated_slippage']==pytest.approx(.3)
    assert row['net_pnl']==pytest.approx(gross-.7)
    assert t.paper_trade_stats['total_trades']==1 and not t.paper_active_positions


def test_binance_real_process_exit_between_ledger_and_snapshot(tmp_path):
    import subprocess,sys
    t,p=fixture(tmp_path);save_positions(t._paper_position_path(),{'binance':t.paper_active_positions})
    script="""import sys,os
from pathlib import Path
sys.path.insert(0,'tests')
from test_v3928_binance_recovery import fixture
t,p=fixture(Path(sys.argv[1]));t._paper_close_commit_hook=lambda:os._exit(73)
t._monitor_paper_positions()
"""
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True)
    assert result.returncode==73,result.stderr
    t.paper_active_positions={};t._restore_paper_positions();assert not t._paper_recovery_error and not t.paper_active_positions
    t._restore_paper_positions();assert len(read_paper_strategy_outcomes(path=t._paper_ledger_path()))==1


def test_binance_live_mode_does_not_run_paper_close_recovery(tmp_path):
    t,p=fixture(tmp_path);t._execution_mode=lambda:ExecutionMode.LIVE
    t.binance_client.get_current_price=MagicMock(side_effect=AssertionError('no LIVE provider calls'))
    t._monitor_paper_positions()
    assert not t.binance_client.get_current_price.called
    assert t.paper_active_positions[p.symbol] is p and not t._paper_ledger_path().exists()
