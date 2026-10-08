"""Synthetic PAPER reproduction against a separately selected source tree."""
import sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(source))
sys.path.append(str(Path(__file__).resolve().parents[2]/'tests'))
from test_v3928_close_recovery import fixture
from trading.trader import Position,PositionSide
from trading.paper_position_store import save_positions,load_positions
from trading.paper_capital import paper_available_funds
from trading.paper_strategy_ledger import paper_outcome_calculation_status,read_paper_strategy_outcomes
with tempfile.TemporaryDirectory(prefix='v3928-synthetic-repro-') as folder:
    root=Path(folder);t,p,d=fixture(root);ledger=root/'ledger.jsonl'
    save_positions(t._paper_position_path(),t.paper_positions)
    with patch('trading.paper_strategy_ledger.ledger_path',return_value=ledger):
        with patch('trading.unified_trader.save_positions',side_effect=OSError('injected snapshot failure')):
            success=t._execute_advanced_partial_close_unified('okx',p.symbol,p,110.,d)
        memory_quantity=p.quantity
        disk_quantity=load_positions(t._paper_position_path(),Position,PositionSide)['okx'][p.symbol].quantity
        restarted,_,_=fixture(root);restarted.paper_positions={};restarted._restore_paper_positions()
        q=restarted.paper_positions['okx'][p.symbol]
        restored_quantity=q.quantity;completed=list(q.custom_order_plan_state.get('completed_partial_indices',[]))
        retry=restarted._execute_advanced_partial_close_unified('okx',q.symbol,q,120.,d)
        logged=' '.join(str(c) for c in restarted.logger.mock_calls)
        rows=read_paper_strategy_outcomes(path=ledger)
        raw_rows=[json.loads(line) for line in ledger.read_text().splitlines()]
        close_funds=paper_available_funds(1000,restarted.paper_positions.get('okx',{}),venue='okx',quote='USDT',ledger_file=ledger)
    row=dict(event_id='legacy',exchange='okx',scope='unified',execution_mode='paper',quote_currency='USDT',calculation_status='valid',cost_calculation_status='recorded_contract',entry_price=100,quantity=2,net_pnl=20)
    unknown=root/'unknown.jsonl';unknown.write_text(json.dumps(row)+'\n');original=unknown.read_bytes()
    funds=paper_available_funds(1000,{},venue='okx',quote='USDT',ledger_file=unknown)
    print(json.dumps({'source':str(source),'synthetic_only':True,'live_orders':False,'snapshot_failure':{'returned_success':success,'memory_quantity':memory_quantity,'disk_quantity':disk_quantity,'restored_quantity':restored_quantity,'completed':completed,'retry_other_price_success':retry,'event_conflict_logged':'paper_ledger_event_conflict' in logged,'ledger_rows':len(rows),'raw_ledger_rows':len(raw_rows),'unique_event_ids':len({r['event_id'] for r in raw_rows}),'post_retry_capital_reason':close_funds.get('reason'),'recorded_exit_prices':[r['exit_price'] for r in raw_rows],'closed_quantity':rows[0]['quantity'],'original_exit_price':rows[0]['exit_price']},'missing_contract':{'status':paper_outcome_calculation_status(row),'capital_basis':funds['capital_basis'],'available_capital':funds.get('available_capital'),'reason':funds.get('reason'),'original_preserved':unknown.read_bytes()==original}},indent=2))
