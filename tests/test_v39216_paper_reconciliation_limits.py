"""Reproduce published .16 limits. These passing assertions certify defects exist,
not that lifetime limits/PAPER maintenance have been fixed. Synthetic data only.
"""
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
def test_published16_all_venues_switch_to_generic_funds_block_at_shared_size_limit(boundary_ledgers,venue):
    before,after=boundary_ledgers
    quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
    assert paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=before)['capital_basis']=='paper_reconciled_funds'
    funds=paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=after)
    assert funds['capital_basis']=='paper_funds_unverified'
    assert funds['reason']=='paper_ledger_reconciliation_budget'
    visible=entry_health({'capital':funds})
    assert visible['label']=='가상 자금 대조 필요'
    assert '거래 기록 점검' in visible['action']
    assert visible['code']=='paper_funds_unverified'  # actual budget cause lost from headline


def test_close_checkpoint_and_replay_also_stop_at_same_lifetime_bytes(boundary_ledgers):
    before,after=boundary_ledgers
    checkpoint=ledger_checkpoint(before)
    assert checkpoint['offset']==LIMIT
    validate_ledger_checkpoint(before,checkpoint)
    with pytest.raises(ValueError,match='paper_close_recovery_budget'):ledger_checkpoint(after)
    with pytest.raises(ValueError,match='paper_close_recovery_budget'):read_close_ledger(after)


@pytest.mark.parametrize('venue',VENUES)
def test_unrelated_parallel_or_blank_history_counts_toward_wallet_line_limit(tmp_path,venue):
    path=tmp_path/'synthetic.jsonl'
    # No actual trades or money discrepancy: blank lines are supported, but
    # lifetime line count is checked before venue/mode/observation filtering.
    path.write_bytes(b'\n'*100_001)
    quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT'
    assert paper_available_funds(1000,{},venue=venue,quote=quote,ledger_file=path)['reason']=='paper_ledger_reconciliation_budget'
    with pytest.raises(ValueError,match='paper_close_recovery_budget'):read_close_ledger(path)


def test_old_checkpoint_still_valid_after_append_but_new_checkpoint_cannot_be_written(boundary_ledgers):
    from hashlib import sha256
    _,after=boundary_ledgers
    with after.open('rb') as stream:prefix=stream.readline()
    checkpoint=dict(schema_version=1,offset=len(prefix),sha256=sha256(prefix).hexdigest())
    validate_ledger_checkpoint(after,checkpoint)
    with pytest.raises(ValueError,match='paper_close_recovery_budget'):ledger_checkpoint(after)


@pytest.mark.parametrize('venue',VENUES)
def test_real_recovery_method_propagates_shared_lifetime_limit_to_all_wallets(boundary_ledgers,tmp_path,venue):
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
    assert owner._recover_paper_closes() is False
    assert owner._paper_recovery_error=='paper_close_recovery_budget'
    funds=paper_funds_for(owner,1000,{},venue=venue,quote='KRW' if venue in {'upbit','bithumb','coinone'} else 'USDT')
    assert funds['reason']=='paper_close_recovery_budget'
    assert entry_health({'capital':funds})['label']=='가상 자금 대조 필요'
    assert not owner.paper_positions and not owner.paper_active_positions
