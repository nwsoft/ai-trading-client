#!/usr/bin/env python3
"""Offline explicit PAPER snapshot-copy audit; never provider calls or source writes.

Compare .17 with an independent public16 replay reference whose *reader only*
ignores the old lifetime cap. This is not proof that unmodified .16 can run the
snapshot. Reports contain aggregate states, never amounts, IDs or raw records.
"""
from pathlib import Path
import argparse
import contextlib
import io
import json
import re


def run(snapshot,output,baseline_ref):
    import ast,subprocess,copy,math,contextlib,hashlib,io,json,logging,shutil,socket,tempfile,sys,time
    from pathlib import Path
    from types import SimpleNamespace
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));source=Path(snapshot).resolve()
    output=Path(output).resolve()
    if output.is_relative_to(source):raise ValueError('output_must_be_outside_snapshot')
    files=[source/name for name in ['strategy_paper_outcomes.jsonl','paper_funds_sessions.json','paper_open_positions_binance.json','paper_open_positions_unified.json']]
    if any(not p.is_file() or p.is_symlink() for p in files):raise ValueError('snapshot_files_missing_or_symlink')
    identities={p:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns,p.stat().st_mode) for p in files}
    network=[]
    def blocked(*a,**kw):network.append(1);raise OSError('offline copy only')
    socket.socket.connect=blocked;logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix='noah17-shared-paper-upgrade-') as directory:
     folder=Path(directory)
     for p in files:shutil.copy2(p,folder/p.name)
     import path_utils
     path_utils.get_db_dir=lambda:str(folder);path_utils.get_db_file_path=lambda:str(folder/'qa.db')
     path_utils.get_app_data_dir=lambda:str(folder/'app');path_utils.get_config_dir=lambda:str(folder/'app/config');path_utils.get_log_dir=lambda:str(folder/'app/logs')
     for d in ['app/config','app/logs']:(folder/d).mkdir(parents=True,exist_ok=True)
     with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
      from trading.paper_ledger_index import index_for,Rows
      from trading.trader import Trader
      from trading.unified_trader import UnifiedTrader
      from trading.paper_capital import paper_funds_for
      ledger=folder/'strategy_paper_outcomes.jsonl';start=time.monotonic();idx=index_for(ledger);idx.sync();index_time=time.monotonic()-start
      owners=[];recoveries=[]
      from trading.paper_position_store import load_positions
      from trading.trader import Position,PositionSide
      def state_hash(stores):
       return hashlib.sha256(json.dumps({v:{s:vars(p) for s,p in ps.items()} for v,ps in stores.items()},sort_keys=True,default=str).encode()).hexdigest()
      prior_stores={kind:load_positions(folder/f'paper_open_positions_{kind}.json',Position,PositionSide,ledger_file=ledger) for kind in ['binance','unified']}
      prior={kind:state_hash(stores) for kind,stores in prior_stores.items()}
      import trading.paper_position_store as store_module
      import trading.paper_strategy_ledger as ledger_module
      tree=ast.parse(subprocess.check_output(['git','show',baseline_ref+':trading/paper_position_store.py'],text=True))
      function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='reconcile_close_events')
      namespace=dict(vars(store_module));exec(compile(ast.Module(body=[function],type_ignores=[]),'<public16-independent-replay-reference>','exec'),namespace)
      references=copy.deepcopy(prior_stores)
      original_reader=ledger_module.read_close_ledger
      ledger_module.read_close_ledger=lambda path:[json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]
      try:
       for kind,stores in references.items():namespace['reconcile_close_events'](stores,ledger,execution_scope=kind)
      finally:ledger_module.read_close_ledger=original_reader
      for cls,kind in [(Trader,'binance'),(UnifiedTrader,'unified')]:
       owner=cls.__new__(cls);owner.settings={};owner.recorder=SimpleNamespace(db_path=str(folder/'qa.db'))
       owner._paper_position_store_file=folder/f'paper_open_positions_{kind}.json'
       owner._paper_position_persistence_enabled=True;owner._paper_recovery_error='paper_close_recovery_budget';owner._paper_restore_failed=True
       owner.paper_active_positions={};owner.paper_positions={};owner.logger=SimpleNamespace(error=lambda *a:None);owner.log_event=lambda *a,**kw:None
       ok=owner._recover_paper_closes(restore=True)
       current={'binance':owner.paper_active_positions} if kind=='binance' else owner.paper_positions
       differences={}
       for v,ps in prior_stores[kind].items():
        for symbol,p in ps.items():
         now=current.get(v,{}).get(symbol)
         if now is None:differences['confirmed_closed_position']=differences.get('confirmed_closed_position',0)+1;continue
         for key,val in vars(p).items():
          if val!=vars(now).get(key):differences[key]=differences.get(key,0)+1
       before_count=sum(len(x) for x in prior_stores[kind].values());after_count=sum(len(x) for x in current.values())
       recoveries.append(dict(engine=kind,success=ok,reason=owner._paper_recovery_error,raw_snapshot_equals_replayed_state=not differences and before_count==after_count,raw_saved_positions=before_count,recovered_positions=after_count,independent_public16_replay_fields_equal=state_hash(current)==state_hash(references[kind]),changed_field_counts=differences,empty_venue_groups_added=sum(not p for v,p in current.items() if v not in prior_stores[kind])))
       owners.append(owner)
      wallets=[]
      from trading.paper_funds_session import read_session
      from trading.paper_strategy_ledger import normalize_paper_outcome_costs
      from trading.strategy_scope import canonical_venue
      for v in ['binance','upbit','bithumb','coinone','bybit','okx','bitget']:
       owner=owners[0 if v=='binance' else 1];positions=owner.paper_active_positions if v=='binance' else owner.paper_positions.get(v,{})
       funds=paper_funds_for(owner,1000,positions,venue=v,quote='KRW' if v in {'upbit','bithumb','coinone'} else 'USDT')
       session=read_session(ledger,venue=v,quote='KRW' if v in {'upbit','bithumb','coinone'} else 'USDT')
       offset=session['ledger_offset'] if session else 0
       independent={}
       with ledger.open('rb') as stream:
        stream.seek(offset)
        for raw in stream:
         if not raw.strip():continue
         event=json.loads(raw)
         if event.get('execution_mode')!='paper' or canonical_venue(event.get('exchange',''))!=v or event.get('cost_calculation_status')=='parallel_paper_recorded_contract':continue
         event=normalize_paper_outcome_costs(event)
         independent.setdefault(event['event_id'],float(event['net_pnl']))
       assert math.isclose(funds['realized_net_pnl'],sum(independent.values()),rel_tol=1e-12,abs_tol=1e-8)
       wallets.append(dict(independent_pnl_sum_equal=True,source=v,basis=funds['capital_basis'],reason=funds.get('reason'),preserved_positions=len(positions)))
      counts=dict(unique_indexed_paper_events=len(Rows(idx)),raw_lines=sum(1 for _ in ledger.open('rb')))
     report=dict(status='PASS' if all(x['success'] and x['independent_public16_replay_fields_equal'] for x in recoveries) and all(x['basis']=='paper_reconciled_funds' for x in wallets) else 'NEEDS_REVIEW',snapshot='explicit_snapshot',baseline_commit=baseline_ref,original_ledger_bytes=ledger.stat().st_size,old64MiB_limit_exceeded_by=ledger.stat().st_size-64*1024*1024,initial_index_seconds=round(index_time,3),counts=counts,engine_recovery=recoveries,wallets=wallets,ledger_copy_bytes_unchanged=hashlib.sha256(ledger.read_bytes()).hexdigest()==identities[source/ledger.name][0],original_bytes_mtime_permissions_unchanged=all(identities[p]==(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns,p.stat().st_mode) for p in files),network_attempts=len(network),orders_submitted=0)
     output.parent.mkdir(parents=True,exist_ok=True)
     output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
     assert all(x['independent_public16_replay_fields_equal'] for x in recoveries)
     assert report['status']=='PASS' and report['original_bytes_mtime_permissions_unchanged'] and report['ledger_copy_bytes_unchanged']

    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--baseline-ref',default='8b4f62b24df04cfe427d46eb2f55dfef24ff1b28')
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.baseline_ref):parser.error('baseline_ref_must_be_full_commit')
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            report=run(args.snapshot,args.output,args.baseline_ref)
    except Exception:
        print(json.dumps({'status':'FAIL','reason':'isolated_paper_copy_audit_failed','private_output_suppressed':True}))
        return 1
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
