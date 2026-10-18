"""Synthetic failure/restart contracts. Never uses an exchange or customer folder."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
import pytest
from trading.parallel_strategy_paper import ParallelStrategyPaperEngine
import trading.parallel_strategy_paper as module


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'get_app_data_dir', lambda: tmp_path)
    settings = {'paper_trading':False, 'parallel_strategy_paper_validation':{'enabled':True}}
    engine = ParallelStrategyPaperEngine(settings_provider=lambda: settings)
    pos = dict(position_id='fixture-position', strategy_key='fixture-strategy', version_id='fixture-version',
        strategy_scope='unified', rules={}, target='binance', symbol='TESTUSDT', asset_class='crypto',
        side='SHORT', entry_price=100., quantity=5., contract_size=1., tp_fraction=.014, sl_fraction=.008,
        round_trip_fee_rate=.0008, round_trip_slippage_rate=.0006, quote_currency='USDT', leverage=5,
        opened_at=datetime.now(timezone.utc).isoformat(), last_observed_at=datetime.now(timezone.utc).isoformat(),
        observation_status='continuous', position_sizing={'account_equity':1000.})
    engine._positions[engine._identity(pos,'binance','TESTUSDT')]=pos
    engine._save()
    return engine, settings, tmp_path


def tick(engine, price=101., mode='live'):
    return engine.observe(target='binance',symbol='TESTUSDT',asset_class='crypto',primary_execution_mode=mode,
        context={'current_price':price},strategy_pool=[],market_regime='range')


def ledger(path):
    p=path/'strategy_paper_outcomes.jsonl'
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_failed_commit_freezes_price_time_and_pnl_across_restart_mode_change(seeded, monkeypatch):
    engine,settings,path=seeded; real=module.record_paper_strategy_outcome
    def fail(**kw): raise OSError('disk unavailable')
    monkeypatch.setattr(module,'record_paper_strategy_outcome',fail)
    assert tick(engine)['closed']==0
    pending=json.loads((path/'parallel_strategy_paper_positions.json').read_text())
    frozen=next(iter(pending.values()))['pending_close']
    assert frozen['exit_price']==101. and engine.status()['pending_closes']==1
    settings['paper_trading']=True;settings['parallel_strategy_paper_validation']['enabled']=False
    engine=ParallelStrategyPaperEngine(settings_provider=lambda:settings)
    monkeypatch.setattr(module,'record_paper_strategy_outcome',real)
    assert tick(engine,202.85,mode='paper')['closed']==1
    row=ledger(path)[0]
    assert row['exit_price']==101. and row['closed_at']==frozen['closed_at']
    assert row['net_pnl']==frozen['net_pnl'] and len(ledger(path))==1
    assert engine.status()['open_positions']==0


def test_lost_commit_ack_and_snapshot_restart_do_not_duplicate_or_reprice(seeded, monkeypatch):
    engine,settings,path=seeded;real=module.record_paper_strategy_outcome
    def lost_ack(**kw): real(**kw);raise OSError('ack lost')
    monkeypatch.setattr(module,'record_paper_strategy_outcome',lost_ack)
    assert tick(engine)['closed']==0 and len(ledger(path))==1
    original=(path/'strategy_paper_outcomes.jsonl').read_bytes()
    engine=ParallelStrategyPaperEngine(settings_provider=lambda:settings)
    monkeypatch.setattr(module,'record_paper_strategy_outcome',real)
    assert tick(engine,300.)['closed']==1
    assert (path/'strategy_paper_outcomes.jsonl').read_bytes()==original
    assert tick(engine,300.)['closed']==0


def test_intent_save_failure_does_not_commit_or_drop_position(seeded,monkeypatch):
    engine,_,path=seeded;called=[]
    monkeypatch.setattr(module,'record_paper_strategy_outcome',lambda **kw:called.append(kw))
    monkeypatch.setattr(engine,'_save',lambda:(_ for _ in ()).throw(OSError('disk full')))
    assert tick(engine)['closed']==0 and not called and len(engine.snapshot())==1
    assert engine.snapshot()[0]['pending_close']['exit_price']==101.


def test_post_commit_snapshot_failure_is_recoverable_without_ledger_change(seeded,monkeypatch):
    engine,_,path=seeded;save=engine._save;calls=0
    def save_then_fail():
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('snapshot flush failed')
        save()
    monkeypatch.setattr(engine,'_save',save_then_fail)
    assert tick(engine)['closed']==0 and len(engine.snapshot())==1 and len(ledger(path))==1
    original=(path/'strategy_paper_outcomes.jsonl').read_bytes()
    monkeypatch.setattr(engine,'_save',save)
    assert tick(engine,400.)['closed']==1
    assert (path/'strategy_paper_outcomes.jsonl').read_bytes()==original


def test_independent_watch_handles_unselected_position_while_paper_or_disabled(seeded):
    engine,settings,path=seeded
    settings['paper_trading']=True;settings['parallel_strategy_paper_validation']['enabled']=False
    assert engine.service_exits(lambda *_:101.)['closed']==1
    assert ledger(path)[0]['validation_path']=='parallel_validation'
    assert ledger(path)[0]['capital_reference']==1000.


def test_missing_quote_keeps_position_and_shows_actionable_status(seeded):
    engine,_,path=seeded
    assert engine.service_exits(lambda *_:0.)['closed']==0
    assert engine.status()['state']=='needs_attention'
    assert engine.status()['reason_code']=='parallel_paper_quote_unavailable'
    assert not ledger(path)


def test_concurrent_watch_and_analysis_commit_exactly_once(seeded):
    engine,_,path=seeded
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(lambda _:tick(engine),range(12)))
    assert sum(v['closed'] for v in results)==1 and len(ledger(path))==1


def test_legacy_gap_is_visible_and_loss_is_not_capped_or_deleted(seeded):
    engine,_,path=seeded;next(iter(engine._positions.values())).pop('last_observed_at')
    assert tick(engine,203.)['closed']==1
    row=ledger(path)[0]
    assert row['observation_status']=='legacy_observation_gap' and row['net_pnl_percent'] < -100


def test_statistics_separate_paths_and_capital_without_changing_history(tmp_path):
    from web_platform.application_services import ApplicationServices
    now=datetime.now(timezone.utc).isoformat()
    base=dict(exchange='binance',scope='binance',symbol='TESTUSDT',execution_mode='paper',calculation_status='valid',
        quote_currency='USDT',entry_price=10.,quantity=1.,contract_size=2.,fees=.1,opened_at=now,closed_at=now)
    rows=[dict(base,event_id='a',net_pnl=2),dict(base,event_id='b',net_pnl=-500,exit_policy_source='custom_strategy_parallel_paper'),
          dict(base,event_id='c',net_pnl=1,validation_path='parallel_validation',capital_basis='independent_strategy_virtual_equity',capital_reference=1000.,observation_status='continuous')]
    p=tmp_path/'strategy_paper_outcomes.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in rows));before=p.read_bytes()
    service=object.__new__(ApplicationServices);service.data_dir=tmp_path
    stats=service._paper_statistics_snapshot(asset_class='crypto',source='binance',period='all')
    assert stats['closed_count']==3 and stats['pnl_by_currency']['USDT']==-497
    assert len(stats['groups'])==3 and stats['notional_by_currency']['USDT']==60.
    assert {g['validation_path'] for g in stats['groups']}=={'runtime_paper','parallel_validation'}
    assert sum(g['capital_reference'] is None for g in stats['groups'])==2
    assert p.read_bytes()==before


@pytest.mark.parametrize('requested,ack,allowed',[('CROSS',True,True),('ISOLATED',False,False),('BAD',True,False)])
def test_entry_margin_is_normalized_and_fail_closed(requested,ack,allowed):
    from trading.entry_margin_policy import confirm_entry_margin
    calls=[];client=SimpleNamespace(set_margin_type=lambda symbol,mode:calls.append((symbol,mode)) or ack)
    assert confirm_entry_margin(client,'TESTUSDT',{'default_margin_type':requested}) is allowed
    if requested=='CROSS':assert calls==[('TESTUSDT','CROSSED')]


def test_live_capacity_uses_membership_and_keeps_risk_default():
    from trading.strategy_scope import runtime_applied_pool,scoped_pool
    rows=[{'version_id':str(i),'target_scope':'asset:crypto','priority':i,'operation_mode':'standard'} for i in range(40)]
    for grade,requested,expected in [('premium',30,30),('premium',10,10),('general',30,10)]:
        pool=runtime_applied_pool(rows,SimpleNamespace(current_user_grade=grade,settings={'live_strategy_evaluation_limit':requested}))
        assert len(scoped_pool(pool,asset_class='crypto',target='binance'))==expected


def test_pending_commit_recovers_before_any_quote_network_read(seeded, monkeypatch):
    engine, settings, path = seeded
    real = module.record_paper_strategy_outcome
    monkeypatch.setattr(module, 'record_paper_strategy_outcome', lambda **kw: (_ for _ in ()).throw(OSError('offline storage')))
    assert tick(engine)['closed'] == 0
    monkeypatch.setattr(module, 'record_paper_strategy_outcome', real)
    settings['paper_trading'] = True
    calls=[]
    def unavailable(*args):
        calls.append(1)
        raise AssertionError('must not request a quote for a frozen exit')
    assert engine.service_exits(unavailable)['closed'] == 1
    assert calls == [] and ledger(path)[0]['exit_price'] == 101.


def test_unavailable_ledger_index_still_freezes_observed_exit(seeded, monkeypatch):
    from trading.paper_ledger_index import index_for
    engine, _, path = seeded
    index = index_for(path / 'strategy_paper_outcomes.jsonl')
    monkeypatch.setattr(index, 'event', lambda *a: (_ for _ in ()).throw(ValueError('paper_ledger_index_unavailable')))
    assert tick(engine)['closed'] == 0
    saved=json.loads((path/'parallel_strategy_paper_positions.json').read_text())
    assert next(iter(saved.values()))['pending_close']['exit_price'] == 101.
    assert engine.status()['pending_closes'] == 1
