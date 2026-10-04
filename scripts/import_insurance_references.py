"""Update reviewed product discovery metadata without an app release.

Input is a JSON list matching insurance_reference_directory.BUNDLED. No prices
or personal information; use the licensed catalog importer for actual feeds.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.insurance_reference_directory import import_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--snapshot',required=True)
    args=parser.parse_args()
    with Path(args.snapshot).open('rb') as source:
        raw=source.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:parser.error('snapshot_too_large')
    print(json.dumps(import_rows(args.database,json.loads(raw)),ensure_ascii=False))


if __name__=='__main__':main()
