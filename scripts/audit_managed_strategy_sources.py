#!/usr/bin/env python3
"""Offline managed-example roundtrip audit; synthetic contexts/profiles only."""
import argparse
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import random
import socket
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='noah-managed-audit-') as folder:
        import path_utils
        path_utils.get_app_data_dir=lambda:folder
        path_utils.get_config_dir=lambda:str(Path(folder)/'config')
        path_utils.get_log_dir=lambda:str(Path(folder)/'logs')
        for name in ['config','logs']:(Path(folder)/name).mkdir()
        attempts=[]
        previous_connect=socket.socket.connect
        def blocked(*args,**kwargs):
            attempts.append(1);raise OSError('offline_managed_audit')
        socket.socket.connect=blocked
        try:
            return _run(attempts)
        finally:
            socket.socket.connect=previous_connect


def _run(attempts):
    from scripts.export_strategy_presets import payload
    from trading.custom_strategy_presets import get_beginner_preset
    from trading.custom_strategy_mentor import recommend_strategy_candidates
    from trading.strategy_source_ingestor import StrategySourceIngestor
    from trading.declarative_strategy_engine import DeclarativeStrategyEngine as Engine
    from web_platform.application_services import ApplicationServices
    ingestor=StrategySourceIngestor();service=ApplicationServices.__new__(ApplicationServices)
    rng=random.Random(39216);count=0;profiles=0;candidates=0;evaluations=0
    for row in payload()[1:]:
        for asset in ['crypto','stock']:
            text=row['source' if asset=='crypto' else 'stock_source']
            parsed=ingestor.analyze(text,kind='text')
            assert parsed['ready_for_execution'] and service.validate_strategy_draft(rules=parsed['rules'])['ready']
            original=deepcopy(get_beginner_preset(row['key'])['rules_template'])
            original.update(decision_timeframe='15m' if asset=='crypto' else '1d',execution_timeframe='15m' if asset=='crypto' else '1d')
            directions=['LONG','SHORT'] if asset=='crypto' else ['LONG']
            for direction in directions:
                before={**original,'executable_entry':original['independent_entries'][direction]}
                after={**parsed['rules'],'executable_entry':parsed['rules'].get('independent_entries',{}).get(direction,parsed['rules'].get('executable_entry'))}
                for index in range(120):
                    context=dict(current_price=rng.uniform(80,120),ema20=rng.uniform(90,110),ema50=rng.uniform(90,110),ema200=rng.uniform(90,110),rsi=rng.uniform(0,100),volume_ratio=rng.uniform(0,3))
                    context['_previous']={key:rng.uniform(90,110) for key in ['current_price','ema20','ema50','ema200']}
                    if index%10==0:context.pop('_previous')
                    if index%11==0:context.pop('rsi')
                    if index%13==0:context.pop('volume_ratio')
                    scoped={**context,'_closed_bar_contexts':[]}
                    runtime={**context,'_strategy_timeframe_contexts':{original['decision_timeframe']:scoped}}
                    assert Engine.evaluate_entry(before,runtime)['allowed']==Engine.evaluate_entry(after,runtime)['allowed']
                    evaluations+=1
            count+=1
    values=product(['crypto','stock','both'],['small','medium','large'],[0.05,0.5,2.0],['intraday','daily','weekly'],['low','medium','high'],[False,True],['beginner','intermediate','advanced'],[False,True])
    fields=['asset_class','capital_band','max_loss_percent','review_frequency','trade_frequency','leverage_allowed','experience_level','paper_ready']
    for values_row in values:
        profile=dict(zip(fields,values_row));profiles+=1
        for candidate in recommend_strategy_candidates(profile):
            rules=candidate['draft_rules'];parsed=ingestor.analyze(candidate['source_text'],kind='text')
            assert parsed['ready_for_execution'] and service.validate_strategy_draft(rules=parsed['rules'])['ready']
            assert parsed['rules']['engine_settings']==rules['engine_settings']
            assert parsed['rules']['risk_model']==rules['risk_model']
            assert parsed['rules']['decision_timeframe']==rules['decision_timeframe']
            assert parsed['rules'].get('independent_entries',{}).keys()==rules.get('independent_entries',{}).keys()
            candidates+=1
    assert not attempts
    return dict(status='PASS',managed_asset_examples=count,synthetic_entry_comparisons=evaluations,mentor_profiles=profiles,mentor_candidates=candidates,network_attempts=len(attempts),orders_submitted=0,
                scope='four managed prototypes; crypto/stock; finite profile options and 0.05/0.5/2% risk boundaries; no customer data')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=run();text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text)
if __name__=='__main__':main()
