"""Regression: previously reproduced .16 lifetime limits are removed in .17."""
import json
from pathlib import Path
import pytest
from trading.paper_capital import paper_available_funds
from trading.paper_position_store import ledger_checkpoint,validate_ledger_checkpoint
from trading.paper_strategy_ledger import read_close_ledger
from trading.entry_diagnostics import entry_health

LIMIT=64*1024*1024
VENUES=['binance','upbit','bithumb','coinone','bybit','okx','bitget']


def write_valid_bounded_ledger(path,size):
    row=dict(event_id='synthetic-only',exchange='binance',scope='binance',execution_mode='paper',
             quote_currency='USDT',calculation_status='valid',net_pnl=0,cost_calculation_status='recorded')
    line=(json.dumps(row)+'\n').encode()
    with path.open('wb') as output:
        output.write(line)
        remaining=size-len(line)
        blank=b' '*1023+b'\n'
        while remaining>1024:
            output.write(blank);remaining-=1024
        output.write(b' '*(remaining-1)+b'\n')
    assert path.stat().st_size==size


@pytest.fixture(scope='module')
def boundary_ledgers(tmp_path_factory):
    folder=tmp_path_factory.mktemp('synthetic-lifetime-limit')
    before=folder/'boundary.jsonl';after=folder/'over.jsonl'
    write_valid_bounded_ledger(before,LIMIT)
    write_valid_bounded_ledger(after,LIMIT+1)
    return before,after


@pytest.mark.parametrize('venue',VENUES)
def test_all_venues_keep_verified_funds_above_previous_shared_size_limit(boundary_ledgers,venue):
    before,after=boundary_ledgers
    quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
    assert paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=before)['capital_basis']=='paper_reconciled_funds'
    funds=paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=after)
    assert funds['capital_basis']=='paper_reconciled_funds'
    assert funds['available_capital']==1000


def test_close_checkpoint_and_replay_support_growth_above_old_limit(boundary_ledgers):
    before,after=boundary_ledgers
    checkpoint=ledger_checkpoint(before)
    assert checkpoint['offset']==LIMIT
    validate_ledger_checkpoint(before,checkpoint)
    assert ledger_checkpoint(after)['offset']==LIMIT+1
    assert len(read_close_ledger(after))==1


@pytest.mark.parametrize('venue',VENUES)
def test_blank_history_has_no_lifetime_line_limit(tmp_path,venue):
    path=tmp_path/'synthetic.jsonl'
    # No actual trades or money discrepancy: blank lines are supported, but
    # lifetime line count is checked before venue/mode/observation filtering.
    path.write_bytes(b'\n'*100_001)
    quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
    assert paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=path)['capital_basis']=='paper_reconciled_funds'
    assert len(read_close_ledger(path))==0


def test_old_and_new_checkpoints_both_validate_after_growth(boundary_ledgers):
    from hashlib import sha256
    _,after=boundary_ledgers
    with after.open('rb') as stream:prefix=stream.readline()
    checkpoint=dict(schema_version=1,offset=len(prefix),sha256=sha256(prefix).hexdigest())
    validate_ledger_checkpoint(after,checkpoint)
    validate_ledger_checkpoint(after,ledger_checkpoint(after))


@pytest.mark.parametrize('venue',VENUES)
def test_real_recovery_method_recovers_all_wallets_after_old_size_limit(boundary_ledgers,tmp_path,venue):
    from types import SimpleNamespace
    from trading.trader import Trader
    from trading.unified_trader import UnifiedTrader
    from trading.paper_capital import paper_funds_for
    _,ledger=boundary_ledgers
    owner=Trader.__new__(Trader) if venue=='binance' else UnifiedTrader.__new__(UnifiedTrader)
    owner.settings={}
    owner.recorder=SimpleNamespace(db_path=str(tmp_path/'private.db'))
    owner._paper_ledger_path=lambda:ledger
    owner._paper_position_store_file=tmp_path/'positions.json'
    owner._paper_recovery_error=''
    owner.paper_active_positions={};owner.paper_positions={}
    owner.logger=SimpleNamespace(error=lambda *a:None)
    owner.log_event=lambda *a,**k:None
    assert owner._recover_paper_closes() is True
    assert owner._paper_recovery_error==''
    funds=paper_funds_for(owner,1000,{},venue=venue,quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT')
    assert funds['capital_basis']=='paper_reconciled_funds'
    assert not owner.paper_positions and not owner.paper_active_positions


def test_real_durable_writer_crosses_old_limit_and_retry_is_idempotent(boundary_ledgers,tmp_path):
    import shutil
    from trading.paper_strategy_ledger import record_paper_strategy_outcome
    before,_=boundary_ledgers
    path=tmp_path/'growing.jsonl';shutil.copyfile(before,path)
    checkpoint=ledger_checkpoint(path)
    arguments=dict(scope='binance',exchange='binance',symbol='SYNTHETICUSDT',strategy_key='',version_id='',
        opened_at='2026-10-17T00:00:00+00:00',closed_at='2026-10-17T01:00:00+00:00',
        net_pnl=-2,gross_pnl=-2,fees=0,quote_currency='USDT',cost_calculation_status='recorded',
        position_id='synthetic-boundary-close',ledger_file=path)
    first=record_paper_strategy_outcome(**arguments)
    size=path.stat().st_size;assert size>LIMIT
    assert record_paper_strategy_outcome(**arguments)['event_id']==first['event_id']
    assert path.stat().st_size==size
    validate_ledger_checkpoint(path,checkpoint)
    assert ledger_checkpoint(path)['offset']==size
    funds=paper_available_funds(1000,{},venue='binance',quote='USDT',ledger_file=path)
    assert funds['capital_basis']=='paper_reconciled_funds' and funds['realized_net_pnl']==-2
    assert funds['available_capital']==998
