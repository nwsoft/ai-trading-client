"""Import a rights-reviewed complete provider snapshot; never personal records."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.finance_product_intelligence import ProductCatalog

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--snapshot')
    parser.add_argument('--register-feed',action='store_true')
    parser.add_argument('--rollback-revision')
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    store=ProductCatalog(args.database)
    if args.rollback_revision:
        print(json.dumps(store.rollback(args.rollback_revision),ensure_ascii=False));return
    if args.refresh:
        print(json.dumps({'feeds':store.refresh_feeds(force=True)['feeds']},ensure_ascii=False));return
    if not args.snapshot:parser.error('--snapshot is required for import')
    raw=Path(args.snapshot).read_bytes()
    if len(raw)>30*1024*1024: parser.error('snapshot_too_large')
    payload=json.loads(raw)
    result=store.register_feed(payload['source']['id'],args.snapshot) if args.register_feed else store.ingest(payload['source'],payload['products'])
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__': main()
