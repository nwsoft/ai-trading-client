"""Read-only support diagnosis plus explicitly isolated PAPER resumption replay.

Usage: .venv/bin/python scripts/verify_teayu_entry_feedback.py DATA_ROOT OUTPUT
No original data, credentials, live connection or trading configuration is changed.
"""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trading.entry_diagnostics import decision_code
from trading.paper_capital import paper_available_funds
from trading.position_sizing_policy import normalize_position_sizing_policy
from trading.opportunity_coordinator import get_opportunity_coordinator, account_scope_for
from web_platform.runtime_bridge import HeadlessRuntimeBridge

VENUES = ('binance','bybit','okx','bitget','upbit','bithumb','coinone')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(8*1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def verify(data, output):
    data, output = data.resolve(), output.resolve()
    if output == data or data in output.parents:
        raise ValueError('output_must_be_outside_support_data')
    output.parent.mkdir(parents=True, exist_ok=True)
    ledger = data/'strategy_paper_outcomes.jsonl'
    originals = [ledger, data/'config/settings.json', data/'trading.db',
                 data/'paper_open_positions_binance.json', data/'paper_open_positions_unified.json']
    before = {str(p.relative_to(data)):digest(p) for p in originals}
    settings_raw = json.loads((data/'config/settings.json').read_text(encoding='utf-8-sig'))
    # Only the simulated equity policy is copied. No credentials/accounts/paths.
    settings = {'paper_trading':True, 'position_sizing_policy':settings_raw.get('position_sizing_policy',{})}
    positions = {}
    for name in ('binance','unified'):
        positions.update(json.loads((data/f'paper_open_positions_{name}.json').read_text(encoding='utf-8-sig'))['venues'])
    report = {'read_only_support':True,'live_orders':0,'ledger_bytes':ledger.stat().st_size,
              'before_sha256':before,'funds':{},'logs':{},'latest_runtime_decisions':{},
              'paper_close_counts':{},'last_paper_close_utc':{}}
    for venue in VENUES:
        quote = 'KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
        initial = normalize_position_sizing_policy(settings,quote_currency=quote)['paper_equity']
        funds = paper_available_funds(initial,positions.get(venue,{}),venue=venue,quote=quote,ledger_file=ledger)
        if funds['capital_basis']=='paper_funds_unverified':
            # The execution guard uses zero spendable funds, which must not be
            # reported as a measured balance in the customer diagnosis.
            funds['available_capital']=None
        report['funds'][venue] = {**funds,'open_positions':len(positions.get(venue,{}))}
    counts, last = collections.Counter(), {}
    with ledger.open() as handle:
        for line in handle:
            row=json.loads(line); venue=row.get('exchange')
            counts[venue]+=1
            last[venue]=max(last.get(venue,''),str(row.get('closed_at') or ''))
    report['paper_close_counts'],report['last_paper_close_utc']=dict(counts),last
    for path in sorted((data/'logs').glob('trading_*.log')):
        versions, blockers = collections.Counter(),collections.Counter()
        first=last=''
        with path.open(errors='replace') as handle:
            for line in handle:
                if line[:10]<'2026-10-06':
                    continue
                first=first or line[:19];last=line[:19]
                versions.update(re.findall(r'\[v(3\.9\.\d+\.\d+)\s',line))
                for marker in ('trading_candidate_catalogue_unavailable','AI 신뢰도 부족','높은 손실률'):
                    if marker in line:
                        blockers[marker]+=1
        report['logs'][path.name]={'first':first,'last':last,'versions':dict(versions),'marker_counts':dict(blockers)}
    conn=sqlite3.connect(f'file:{data/"trading.db"}?mode=ro&immutable=1',uri=True)
    try:
        report['live_table_recent_entries']=list(conn.execute(
            "SELECT exchange,execution_mode,COUNT(*) FROM trade_log WHERE entry_time>='2026-10-04' GROUP BY 1,2"))
        rows=conn.execute('SELECT exchange,execution_mode,decision_type,decision_json,repeat_count FROM ai_decisions ORDER BY id DESC LIMIT 10000')
        grouped=collections.defaultdict(collections.Counter)
        for venue,mode,kind,text,repeats in rows:
            if 'runtime' not in kind or venue not in VENUES:
                continue
            row=json.loads(text)
            code=decision_code(row.get('decision_status') or row.get('status'),row.get('reason'))
            grouped[venue][code]+=max(1,int(repeats or 1))
        report['latest_runtime_decisions']={k:dict(v) for k,v in grouped.items()}
        report['runtime_window']='latest 10000 stored decision rows, weighted by repeat_count'
    finally:
        conn.close()
    # Exercise the actual runtime action and wallet contract on a disposable
    # ledger copy. The real user's session store is never created.
    with tempfile.TemporaryDirectory(prefix='noah-paper-replay-') as temporary:
        temp=Path(temporary);shutil.copy2(ledger,temp/ledger.name)
        for name in ('binance','unified'):
            shutil.copy2(data/f'paper_open_positions_{name}.json',temp/f'paper_open_positions_{name}.json')
        common=dict(settings=settings,recorder=SimpleNamespace(db_path=str(temp/'trading.db')),
                    _opportunity_account='support-replay')
        binance=SimpleNamespace(**common,paper_active_positions=positions['binance'])
        unified=SimpleNamespace(**common,paper_positions={k:v for k,v in positions.items() if k!='binance'})
        bridge=HeadlessRuntimeBridge(account='support-replay')
        bridge._app=SimpleNamespace(settings=settings,trader=binance,unified_trader=unified,
                                   running_crypto_exchanges=lambda:[])
        replay={}
        for venue in VENUES:
            if report['funds'][venue].get('reason') not in {'paper_ledger_currency_unverified','paper_ledger_pnl_unverified'}:
                continue
            action=bridge.start_paper_session(venue)
            owner=binance if venue=='binance' else unified
            funds=owner._last_capital_evidence[(venue,'paper')]
            assert funds['capital_basis']=='paper_reconciled_funds'
            assert action['orders_submitted'] is False and action['trading_started'] is False
            again=bridge.start_paper_session(venue)
            assert again['created'] is False
            coordinator=get_opportunity_coordinator(owner)
            quote=funds['quote_currency']
            auth=coordinator.authorize(policy={},asset_class='crypto',target=venue,
                symbol=f'REPLAY/{quote}'+(':USDT' if quote=='USDT' else ''),direction='LONG',
                quantity=1,price=100,stop_fraction=.01,
                account_scope=account_scope_for(owner,'paper'),capital_guard_enabled=True,
                available_capital=funds['available_capital'],capital_basis=funds['capital_basis'])
            assert auth.allowed
            coordinator.release(auth)
            replay[venue]={'created':action['created'],'repeat_created':again['created'],
                           'historical_pnl_restored':False,'orders_submitted':False,'trading_started':False,
                           'isolated_capital_guard_authorized':True,
                           'capital_basis':funds['capital_basis'],'available_capital':funds['available_capital'],
                           'quote_currency':funds['quote_currency']}
        assert digest(temp/ledger.name)==before[ledger.name]
        report['isolated_new_session_replay']=replay
    report['after_sha256']={str(p.relative_to(data)):digest(p) for p in originals}
    report['originals_unchanged']=report['after_sha256']==before
    assert report['originals_unchanged']
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(output),'originals_unchanged':True,
                      'isolated_resumption_venues':list(replay),'live_orders':0},ensure_ascii=False))


if __name__=='__main__':
    verify(Path(sys.argv[1]),Path(sys.argv[2]))
