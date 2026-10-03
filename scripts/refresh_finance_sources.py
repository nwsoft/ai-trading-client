"""Refresh reviewed product snapshot APIs (suitable for an operator scheduler)."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.finance_product_intelligence import ProductCatalog
from trading.finance_source_connector import refresh_sources, read_sources

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-directory',required=True)
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--resume-source')
    args=parser.parse_args();directory=Path(args.data_directory)
    configs=read_sources(directory/'finance_product_sources.json')
    if args.validate_only:
        print(json.dumps({'validated_sources':len(configs),'network_called':False}));return
    store=ProductCatalog(directory/'finance_product_catalog.sqlite3')
    if args.resume_source:
        if args.resume_source not in {r['id'] for r in configs if r['enabled']}:parser.error('source_not_enabled')
        from contextlib import closing
        with closing(sqlite3.connect(store.path)) as db,db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_sources'").fetchone():
                db.execute("UPDATE remote_sources SET status='ready',next_attempt=0 WHERE source_id=?",(args.resume_source,))
            db.execute("UPDATE source_feeds SET status='ready',next_attempt=0 WHERE source_id=?",(args.resume_source,))
    result=refresh_sources(store,directory,force=args.force)
    print(json.dumps({'current_count':result['current_count'],'feeds':result['feeds']},ensure_ascii=False))

if __name__=='__main__':main()
