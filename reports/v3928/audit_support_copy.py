"""Aggregate-only audit on a disposable clone of the accepted support backup."""
import json,shutil,tempfile,hashlib,importlib.util
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import sys,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.append(str(Path(__file__).resolve().parents[2]/'tests'))
from test_v3928_close_recovery import fixture
from trading.paper_strategy_ledger import paper_outcome_calculation_status,read_close_ledger
from trading.paper_position_store import load_positions
from trading.trader import Position,PositionSide
parser=argparse.ArgumentParser();parser.add_argument('--source-backup',type=Path,required=True);parser.add_argument('--baseline-tree',type=Path,required=True);args=parser.parse_args()
source=args.source_backup.resolve()
spec=importlib.util.spec_from_file_location('public7_calculation',args.baseline_tree/'trading/paper_strategy_ledger.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
result={'support_copy_only':True,'providers_or_live_orders':False,'normalizes_history':False}
with tempfile.TemporaryDirectory(prefix='v3928-support-replay-') as folder:
    root=Path(folder)
    for name in ['strategy_paper_outcomes.jsonl','paper_open_positions_unified.json','paper_open_positions_binance.json']:shutil.copyfile(source/name,root/name)
    ledger=root/'strategy_paper_outcomes.jsonl';before=hashlib.sha256(ledger.read_bytes()).hexdigest()
    raw=[json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    result['raw_outcome_rows']=len(raw);result['before_status_counts']=dict(Counter(old.paper_outcome_calculation_status(r) for r in raw));result['after_status_counts']=dict(Counter(paper_outcome_calculation_status(r) for r in raw));result['valid_to_unverified']=sum(old.paper_outcome_calculation_status(r)=='valid' and paper_outcome_calculation_status(r)!='valid' for r in raw)
    try:result['strict_ledger_rows']=len(read_close_ledger(ledger));result['ledger_block_reason']=''
    except Exception as e:result['ledger_block_reason']=str(e)
    t,_,_=fixture(root);t._paper_position_path=lambda:root/'paper_open_positions_unified.json';t._paper_ledger_path=lambda:ledger;t.paper_positions={}
    snapshot_before=t._paper_position_path().read_bytes();t._restore_paper_positions()
    result['unified_restore_block_reason']=t._paper_recovery_error
    result['restored_position_counts']={venue:len(positions) for venue,positions in t.paper_positions.items()}
    result['ledger_prefix_unchanged']=before==hashlib.sha256(ledger.read_bytes()).hexdigest()
    result['positions_original_preserved_on_block']=not t._paper_recovery_error or snapshot_before==t._paper_position_path().read_bytes()
    from test_v3928_binance_recovery import fixture as binance_fixture
    b,_=binance_fixture(root);b._paper_position_path=lambda:root/'paper_open_positions_binance.json';b._paper_ledger_path=lambda:ledger;b.paper_active_positions={}
    binance_before=b._paper_position_path().read_bytes();b._restore_paper_positions()
    result['binance_restore_block_reason']=b._paper_recovery_error
    result['binance_restored_position_count']=len(b.paper_active_positions)
    result['binance_positions_original_preserved_on_block']=not b._paper_recovery_error or binance_before==b._paper_position_path().read_bytes()
print(json.dumps(result,ensure_ascii=False,indent=2))
