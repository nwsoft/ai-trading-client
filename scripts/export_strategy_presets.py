#!/usr/bin/env python3
"""Export/check browser prototypes from the same managed template catalogue."""
import argparse
import json
from copy import deepcopy
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trading.custom_strategy_presets import list_beginner_presets, render_preset_source


def payload():
    rows = []
    for item in list_beginner_presets():
        row = dict(key=item['key'], label=item['name'], name=item['name'],
                   source=item.get('source_text', item['summary']))
        if item.get('executable_template'):
            rules = deepcopy(item['rules_template'])
            rules['executable_entry'] = rules['independent_entries']['LONG']
            rules.pop('independent_entries')
            rules['entry_signal'] = 'LONG'
            rules['decision_timeframe'] = '1d'
            rules['engine_settings']['leverage'] = 1
            row['stock_source'] = render_preset_source(item['name'], rules)
        else: row['stock_source'] = row['source']
        rows.append(row)
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    path=ROOT/'webui/src/generated/strategy-presets.json'
    expected=json.dumps(payload(),ensure_ascii=False,indent=2)+'\n'
    if args.check:
        if not path.is_file() or path.read_text(encoding='utf-8') != expected:
            raise SystemExit('Strategy prototype catalogue drift')
        print('Strategy prototype catalogue PASS');return
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(expected,encoding='utf-8',newline='\n');print(path)
if __name__=='__main__':main()
