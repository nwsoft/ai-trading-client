"""Synthetic Binance failures; providers/orders are stubbed."""
import sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
sys.path.append(str(Path(__file__).resolve().parents[2]/'tests'))
from test_v3928_binance_recovery import fixture
from trading.paper_position_store import save_positions,load_positions
from trading.trader import Position,PositionSide
result={}
for fault in ['ledger','snapshot']:
    with tempfile.TemporaryDirectory(prefix='v3928-binance-repro-') as folder:
        root=Path(folder);t,p=fixture(root);save_positions(t._paper_position_path(),{'binance':t.paper_active_positions})
        context=patch('trading.paper_strategy_ledger.record_paper_strategy_outcome',side_effect=OSError('ledger')) if fault=='ledger' else patch('trading.trader.save_positions',side_effect=OSError('snapshot'))
        with patch('trading.paper_strategy_ledger.ledger_path',return_value=t._paper_ledger_path()),patch('trading.trader.emit_position_closed'),context:t._monitor_paper_positions()
        result[fault]={'open_memory':len(t.paper_active_positions),'disk_quantity':load_positions(t._paper_position_path(),Position,PositionSide)['binance'][p.symbol].quantity,'success_statistics_count':t.paper_trade_stats['total_trades'],'recovery_block':t._paper_recovery_error,'ledger_rows':len(t._paper_ledger_path().read_text().splitlines()) if t._paper_ledger_path().exists() else 0}
print(json.dumps({'source':sys.argv[1],'synthetic_only':True,'live_orders':False,'faults':result},indent=2))
