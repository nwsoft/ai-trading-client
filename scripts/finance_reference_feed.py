#!/usr/bin/env python3
"""Operator workflow: export reviewed records or recover a client's editorial feed."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.finance_product_intelligence import ProductCatalog
from trading.finance_reference_feed import config,apply,refresh,status,rollback
from trading.insurance_reference_directory import validate,BUNDLED
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,required=True)
    sub=p.add_subparsers(dest='command',required=True)
    export=sub.add_parser('export');export.add_argument('--records',type=Path,required=True);export.add_argument('--source-id',required=True);export.add_argument('--sequence',type=int,required=True);export.add_argument('--output',type=Path,required=True)
    sub.add_parser('status');sub.add_parser('refresh');sub.add_parser('resume')
    roll=sub.add_parser('rollback');roll.add_argument('--revision',required=True)
    args=p.parse_args()
    if args.command=='export':
        rows=validate(json.loads(args.records.read_text()))
        if args.sequence<1:raise ValueError('positive sequence required')
        payload={'schema':'noah-insurance-reference-v1','source_id':args.source_id,'sequence':args.sequence,'published_at':datetime.now(timezone.utc).isoformat(),'products':rows}
        # Never overwrite a previously approved artifact implicitly.
        with args.output.open('x',encoding='utf-8') as stream:json.dump(payload,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'output':str(args.output),'count':len(rows),'uploaded':False}));return
    path=ProductCatalog(args.data_dir/'finance_product_catalog.sqlite3').path
    if args.command=='status':result=status(path)
    elif args.command=='rollback':result=rollback(path,args.revision)
    elif args.command=='resume':
        import sqlite3
        from contextlib import closing
        from filelock import FileLock
        cfg=config(args.data_dir)
        if not cfg:raise ValueError('reviewed feed configuration required')
        with FileLock(str(path)+'.reference-refresh.lock',timeout=2),closing(sqlite3.connect(path)) as db,db:
            row=db.execute('SELECT payload FROM reference_feed_state WHERE id=?',(cfg['id'],)).fetchone()
            if not row:raise ValueError('feed missing')
            state=json.loads(row[0]);state.update(status='reviewed_resume',next_attempt=0,last_attempt=0)
            db.execute('UPDATE reference_feed_state SET payload=? WHERE id=?',(json.dumps(state),cfg['id']))
        result=refresh(path,args.data_dir,True)
    else:result=refresh(path,args.data_dir,True)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
