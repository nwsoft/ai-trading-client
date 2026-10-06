#!/usr/bin/env python3
"""Synthetic public-candle CPU/state benchmark; no accounts, inference or orders."""
from pathlib import Path
import sys,json,time,tempfile,resource
from copy import deepcopy
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trading.strategy_scope import runtime_paper_pool,scoped_pool,paper_pool_status
from trading.source_condition_compiler import ConditionCompiler
from trading.custom_strategy_validator import enrich_advanced_indicator_context
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.numeric_strategy_state import NumericStateStore,identity
from scripts.release_source_fingerprint import compute_release_source_fingerprint


def run():
    results=[];started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='noahai-v3926-benchmark-') as work:
        for cap in (10,30):
            for venue in ('binance','bybit','okx','bitget','upbit','bithumb','coinone','kiwoom','shinhan','mirae','kis'):
                stocks=venue in {'kiwoom','shinhan','mirae','kis'};tf='1d' if stocks else '15m'
                base={'decision_timeframe':tf,'executable_entry':{'expression':ConditionCompiler().compile('all_for(close > 0, 3)')},
                      'numeric_state':{'initial':{'counter':0},'updates':{'counter':'counter + 1 if close > 0 else 0'}},
                      'target_scope':f"{'broker' if stocks else 'exchange'}:{venue}"}
                if not stocks:
                    base['executable_entry']['all']=[{'field':{'indicator':'ema','period':17,'timeframe':'1h','source':'close'},'operator':'gt','value':0}]
                pool=[{'rules':deepcopy(base),'strategy_key':f's{i}','version_id':'v1','operation_mode':'paper_validation','priority':5,'target_scope':base['target_scope']} for i in range(cap+5)]
                # Waiting rules deliberately request another frame. If the
                # runtime scopes too late, this would add an unwanted query.
                for row in pool[cap:]:row['rules']['decision_timeframe']='5m'
                owner=SimpleNamespace(current_user_grade='premium' if cap==30 else 'basic',settings={'paper_strategy_evaluation_limit':cap})
                registered=runtime_paper_pool(pool,owner)
                selected=scoped_pool(registered,asset_class='stock' if stocks else 'crypto',target=venue)
                status=paper_pool_status(registered,asset_class='stock' if stocks else 'crypto',target=venue)
                assert len(selected)==cap and status['waiting']==5
                state_path=Path(work)/f'{cap}-{venue}.db';store=NumericStateStore(state_path);counts=[];timings=[];first=None
                for step in ('cold','same_bar','next_bar','restart'):
                    if step=='restart':store=NumericStateStore(state_path)
                    offset=1 if step in {'next_bar','restart'} else 0
                    calls=[]
                    def candles(timeframe,limit):
                        calls.append(timeframe);period={'1d':86400000,'15m':900000,'1h':3600000,'5m':300000}[timeframe]
                        end=1700000000000+offset*period
                        output=[]
                        for i in range(limit):
                            stamp=end-(limit-i)*period;price=100+stamp//period
                            output.append([stamp,price,price+2,price-2,price,20,stamp+period-1])
                        return output
                    before=time.perf_counter()
                    context=enrich_advanced_indicator_context({'exchange':venue,'broker':venue,'symbol':'005930' if stocks else 'BTCUSDT'},selected,candles,
                                state_scope={'venue':venue,'symbol':'005930' if stocks else 'BTCUSDT','mode':'paper'},state_store=store)
                    states=[]
                    for row in selected:
                        key=identity(row['rules'],row);local={**context,'_numeric_state_identity':key}
                        answer=DeclarativeStrategyEngine.evaluate_entry(row['rules'],local)
                        assert answer['allowed'],answer
                        value=context['_numeric_state_results'][key]['values']['counter'];states.append(value)
                    assert '5m' not in calls and len(calls)==len(set(calls))
                    assert all(v==(1 if offset==0 else 2) for v in states)
                    counts.append(len(calls));timings.append(round((time.perf_counter()-before)*1000,2))
                results.append({'cap':cap,'venue':venue,'scope':'synthetic_completed_candles', 'evaluated':cap,'waiting':5,
                                'provider_calls_per_cycle':counts,'cycle_ms':dict(zip(('cold','same_bar','next_bar','restart'),timings)),
                                'same_bar_idempotency':True,'restart_state_preserved':True,'network_calls':0,'orders':0})
    report={'version':'3.9.2.6','source_fingerprint':compute_release_source_fingerprint(ROOT),'scenarios':results,
            'elapsed_seconds':round(time.perf_counter()-started,3),'peak_rss_platform_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'evidence_boundary':'synthetic candle CPU/state contracts; excludes provider/AI latency, live accounts and 24-72h soak',
            'status':'passed'}
    dest=ROOT/'reports/v3926-strategy-pool-benchmark.json';dest.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'passed','scenarios':len(results),'seconds':report['elapsed_seconds'],'report':str(dest)}))

if __name__=='__main__':run()
