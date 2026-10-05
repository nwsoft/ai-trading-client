#!/usr/bin/env python3
"""Local Korean journey contract evaluation. Does not call or benchmark AI models.

A real-provider acceptance report must separately include responses, model/version,
source versions, latency, token usage/cost and reviewed grounding/abstention marks.
"""
import json,sys,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trading.finance_discovery import discover

def evaluate():
    cases=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/v3925_finance_journey_eval.json').read_text());rows=[]
    for c in cases:
        started=time.perf_counter();r=discover({'kind':c['kind'],'question':c['question']});p=r['profile']
        checks={'goal':p['discovery_goal']==c['goal'],'preparation':r['can_prepare'],'no_provider_call':r['decision']['provider_called'] is False}
        if 'state' in c:checks['state']=p['insurance_state']==c['state']
        if 'purpose' in c:checks['purpose']=p['loan_purpose']==c['purpose']
        if 'amount' in c:checks['amount']=float(p.get('amount',0))==c['amount']
        rows.append({'id':c['id'],'pass':all(checks.values()),'checks':checks,'local_elapsed_ms':round((time.perf_counter()-started)*1000,3)})
    return {'scope':'local_contract_only','provider_calls':0,'model_quality_verified':False,'cases':rows,'passed':sum(r['pass'] for r in rows),'total':len(rows)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);args=p.parse_args();r=evaluate()
    raw=json.dumps(r,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(raw+'\n')
    print(raw);sys.exit(0 if r['passed']==r['total'] else 1)
