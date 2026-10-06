"""Regression cases for actual submission receipts and scoped selection state."""
import threading
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from trading.execution_optimizer import ExecutionOptimizer
from trading.opportunity_coordinator import OpportunityCoordinator, account_scope_for, capture_account_scope
from trading.market_selection_runtime import SelectionSingleFlight, TTLValueCache


def execute(place, **overrides):
    options = dict(order_type='LIMIT', request_price=100., fallback_market=True,
                   max_retries=3, timeout_ms=300, max_slippage_bps=10.)
    options.update(overrides)
    return ExecutionOptimizer().execute_with_quality_control(place, **options)


@pytest.mark.parametrize('status', ['NEW', 'PENDING', 'OPEN', 'FILLED', 'PARTIALLY_FILLED', 'success'])
def test_accepted_slippage_failure_keeps_receipt_without_second_order(status):
    calls = []
    def place(kind, price):
        calls.append(kind)
        return True, {'status':status, 'order_id':'venue-receipt', 'price':103.}, []
    success, receipt, errors, _, _ = execute(place)
    assert success and len(calls) == 1
    assert receipt['status'] == status
    assert receipt['quality_passed'] is False
    assert any('slippage_limit_exceeded' in e for e in errors)


def test_slow_accepted_response_cannot_be_resubmitted():
    with patch('trading.execution_optimizer.time.perf_counter', side_effect=[0., 1.]):
        success, receipt, errors, _, _ = execute(lambda *_:(True, {'status':'NEW'}, []))
    assert success and receipt['quality_passed'] is False
    assert errors == ['timeout:1000.0ms']


@pytest.mark.parametrize('receipt', [{}, {'status':'error'}, {'status':'failed','order_id':'receipt'}])
def test_unknown_receipt_does_not_retry(receipt):
    calls = []
    def place(*_):
        calls.append(1)
        return False, receipt, ['ambiguous response']
    success, result, _, _, _ = execute(place)
    assert not success and len(calls) == 1
    assert result['submission_state'] == 'unknown'
    assert result['reconciliation_required']


def test_transport_error_does_not_retry_or_expose_private_exception():
    def place(*_): raise TimeoutError('private account details')
    success, result, errors, _, _ = execute(place)
    assert not success and result['status'] == 'UNKNOWN'
    assert errors == ['TimeoutError']


def auth(coordinator, *, account='a:live', target='okx', symbol='BTCUSDT', time=1800., **extra):
    return coordinator.authorize(policy={'authorized_targets':['okx','upbit'],
            'max_loss_by_currency':{'USDT':1.1}}, asset_class='crypto', target=target,
            symbol=symbol, direction='LONG', quantity=1., price=100., stop_fraction=.01,
            strategy_version='v1', account_scope=account, signal_time=time, **extra)


def test_two_accounts_cannot_replace_or_release_each_others_reservations():
    c = OpportunityCoordinator()
    a, b = auth(c), auth(c, account='b:live')
    assert a.allowed and b.allowed
    c.record_result(a, status='submitted', order_id='a-order')
    c.record_result(b, status='submitted', order_id='b-order')
    c.release(b)
    snapshot = c.snapshot(a.opportunity_id, account_scope=a.account_scope)
    assert snapshot['reservations']['okx']['idempotency_key'] == a.idempotency_key
    assert snapshot['results']['okx']['order_id'] == 'a-order'
    assert not auth(c).allowed


def test_modes_and_currencies_are_separate():
    c = OpportunityCoordinator()
    a, paper, krw = auth(c), auth(c, account='a:paper'), auth(c, target='upbit', symbol='KRW-BTC')
    assert a.allowed and paper.allowed and krw.allowed
    assert krw.aggregate_notional == 100.
    assert krw.quote_currency == 'KRW'


def test_captured_account_survives_later_login_change():
    owner = SimpleNamespace(settings={})
    with patch('path_utils.get_current_user_account', return_value='first'):
        capture_account_scope(owner)
    before = account_scope_for(owner, 'live')
    with patch('path_utils.get_current_user_account', return_value='second'):
        assert account_scope_for(owner, 'live') == before
    assert account_scope_for(owner, 'paper') != before
    assert 'first' not in before


def test_cache_is_bounded_and_expired_data_evicted():
    c = TTLValueCache(max_entries=2)
    c.set('a', [1]); c.set('b', [2]); c.set('c', [3])
    assert c.get('a', 100) is None
    with patch('trading.market_selection_runtime.time.monotonic', return_value=1e30):
        assert c.get('b', 100) is None
    assert len(c._values) == 1


def test_timed_out_joiner_cannot_receive_expired_candidates():
    f = SelectionSingleFlight()
    f._results['okx'] = (0., [{'symbol':'BTCUSDT'}])
    f._events['okx'] = threading.Event()
    assert f.run('okx', lambda:pytest.fail('duplicate discovery'),
                 cache_ttl=0., wait_timeout=.1, stale_ttl=0.) == []


def test_pending_receipt_survives_restart_and_release_until_provider_reconciles(tmp_path):
    path = tmp_path / 'scope.db'
    c = OpportunityCoordinator(path)
    first = auth(c)
    c.mark_submitting(first)
    c.record_result(first, status='failed', order_id='receipt')
    c.release(first)
    restarted = OpportunityCoordinator(path)
    duplicate = auth(restarted, time=3600.)
    assert not duplicate.allowed and duplicate.reason == 'previous_order_reconciliation_required'
    restarted.reconcile_order_id(account_scope=first.account_scope, target='okx',
                                 order_id='receipt', status='cancelled')
    assert auth(restarted, time=3600.).allowed


def test_cross_process_instances_share_atomic_duplicate_protection(tmp_path):
    path = tmp_path / 'scope.db'
    a, b = OpportunityCoordinator(path), OpportunityCoordinator(path)
    assert auth(a).allowed
    assert not auth(b).allowed


@pytest.mark.parametrize('snapshot,quote,amount', [
    ({'free':{'KRW':500000},'total':{'USDT':100000}},'KRW',500000),
    ({'USDT':{'free':20,'total':200}},'USDT',20),
    ({'total':{'USDT':200}},'USDT',0),
    ({'total_assets':900000,'cash':100000},'KRW',0),
    ({'free':{'USDT':float('nan')}},'USDT',0),
    ({'available_balance':0},'USDT',0),
    ({'status':'error','available_balance':100},'USDT',0),
])
def test_only_verified_currency_funds_can_be_allocated(snapshot,quote,amount):
    from trading.portfolio_orchestrator import available_quote_balance
    assert available_quote_balance(snapshot,quote)[0] == amount


@pytest.mark.parametrize('venue', ['binance','bybit','okx','bitget','upbit','bithumb','coinone'])
@pytest.mark.parametrize('mode', ['paper','learning'])
def test_non_live_allocation_never_reads_real_balance(venue, mode):
    from trading.execution_mode import ExecutionMode
    from trading.trader import Trader
    from trading.unified_trader import UnifiedTrader
    def real_call(*a,**k): pytest.fail('non-LIVE account read')
    if venue == 'binance':
        engine = Trader.__new__(Trader)
        engine.settings = {}
        engine._execution_mode = lambda:ExecutionMode(mode)
        engine.binance_client = SimpleNamespace(get_account_info=real_call, get_futures_balance=real_call)
        result=engine._build_portfolio_allocation_binance('BTCUSDT',{'confidence':.8},
                    {'portfolio_orchestration':{'enabled':True}})
    else:
        engine = UnifiedTrader.__new__(UnifiedTrader)
        engine.settings = {}
        engine._execution_mode = lambda source:ExecutionMode(mode)
        engine.get_exchange_client = real_call
        engine.exchange_manager = SimpleNamespace(get_exchange_balance=real_call)
        result=engine._build_portfolio_allocation_unified(venue,[{'symbol':'QA'}],
                {'QA':{'confidence':.8}}, {'portfolio_orchestration':{'enabled':True}})
    assert result['capital_basis'] == 'paper_virtual_equity'
    assert result['available_capital'] == (1000000 if venue in {'upbit','bithumb','coinone'} else 1000)


def test_live_binance_missing_balance_never_invents_1000():
    from trading.trader import Trader
    from trading.execution_mode import ExecutionMode
    engine=Trader.__new__(Trader);engine.settings={}
    engine._execution_mode=lambda:ExecutionMode.LIVE
    engine.binance_client=SimpleNamespace(get_account_info=lambda:{}, get_futures_balance=lambda:999999)
    result=engine._build_portfolio_allocation_binance('BTCUSDT',{'confidence':.8},
                {'portfolio_orchestration':{'enabled':True}})
    assert result['available_capital'] == 0
    assert result['allocations']['BTCUSDT']['capital'] == 0


def test_atomic_capital_reservations_block_competing_instruments_and_survive_unknown(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path=tmp_path/'capital.db'
    def reserve(symbol):
        return auth(OpportunityCoordinator(path),symbol=symbol,
                    capital_guard_enabled=True,available_capital=150.)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(reserve,['BTCUSDT','ETHUSDT']))
    assert sum(r.allowed for r in results)==1
    winner=next(r for r in results if r.allowed)
    rejected=next(r for r in results if not r.allowed)
    assert rejected.reason=='available_capital_reserved_by_other_orders'
    c=OpportunityCoordinator(path);c.mark_submitting(winner)
    c.record_result(winner,status='unknown')
    c.release(winner)
    assert not auth(OpportunityCoordinator(path),symbol='SOLUSDT',capital_guard_enabled=True,available_capital=150.).allowed
    c.reconcile(winner,status='rejected')
    assert auth(c,symbol='SOLUSDT',capital_guard_enabled=True,available_capital=150.).allowed


@pytest.mark.parametrize('free',[None,float('nan'),float('inf'),-1,0])
def test_unknown_or_zero_available_capital_blocks_new_reservation(free):
    result=auth(OpportunityCoordinator(),capital_guard_enabled=True,available_capital=free)
    assert not result.allowed and result.reserved_capital==0


def test_futures_contract_size_and_margin_not_spot_quantity():
    result=auth(OpportunityCoordinator(),capital_guard_enabled=True,available_capital=10.,leverage=2.,contract_size=.1)
    assert result.allowed and result.estimated_notional==10.
    assert result.reserved_capital==pytest.approx(5.1)


@pytest.mark.parametrize('receipt', [
    {'status':'PENDING','order_id':'own','quantity':10,'price':100},
    {'status':'FILLED','order_id':'own','executed_qty':0,'avg_price':100},
    {'status':'FILLED','order_id':'own','executed_qty':float('nan'),'avg_price':100},
    {'status':'FILLED','executed_qty':1,'avg_price':100},
])
def test_requested_quantity_or_price_cannot_prove_owned_fill(receipt):
    from trading.entry_fill_evidence import owned_entry_fill
    assert owned_entry_fill(receipt) is None


def test_partial_receipt_is_owned_but_does_not_prove_complete_fill():
    from trading.entry_fill_evidence import owned_entry_fill
    result=owned_entry_fill({'status':'PENDING','order_id':'own','executed_qty':.1,'avg_price':100,
                            'order':{'orderId':'own','status':'PARTIALLY_FILLED','executedQty':'.1','avgPrice':'100'}})
    assert result['quantity']==.1 and not result['complete']


@pytest.mark.parametrize('status', ['CANCELED','REJECTED','EXPIRED','EXPIRED_IN_MATCH'])
def test_provider_confirmed_terminal_order_releases_pending_reservation(status):
    from trading.opportunity_coordinator import finish_submission
    c=OpportunityCoordinator(); a=auth(c)
    o=SimpleNamespace(_opportunity_coordinator=c)
    c.mark_submitting(a)
    receipt={'status':'PENDING','order':{'orderId':'own','status':status,'executedQty':'0'}}
    finish_submission(o,a,receipt,confirmed=False)
    assert c.runtime_snapshot(account_scope=a.account_scope,target=a.target)['pending_orders']==1
    finish_submission(o,a,receipt,confirmed=True)
    assert c.runtime_snapshot(account_scope=a.account_scope,target=a.target)['pending_orders']==0


def test_cancelled_partial_fill_still_proves_owned_quantity():
    from trading.entry_fill_evidence import owned_entry_fill
    fill=owned_entry_fill({'order':{'orderId':'own','status':'CANCELED','executedQty':'.1','avgPrice':'100'}})
    assert fill['quantity']==.1 and fill['terminal'] and not fill['complete']


@pytest.mark.parametrize('reply',['not_found','wrong_identity','cancelled','filled'])
def test_unknown_native_order_is_read_only_reconciled_by_durable_client_id(tmp_path,reply):
    from trading.entry_fill_evidence import reconcile_owned_pending_entries
    c=OpportunityCoordinator(tmp_path/'pending.db')
    owner=SimpleNamespace(settings={'account_id':'fixture'},_opportunity_coordinator=c)
    a=c.authorize(policy={'authorized_targets':['binance']},asset_class='crypto',target='binance',symbol='BTCUSDT',direction='LONG',quantity=1.,price=100.,stop_fraction=.01,account_scope=account_scope_for(owner,'live'))
    c.mark_submitting(a);c.record_result(a,status='unknown')
    cid=c.client_order_id(a); calls=[]
    def lookup(**kw):
        calls.append(kw)
        assert kw['origClientOrderId']==cid
        if reply=='not_found':raise TimeoutError('provider read unavailable')
        return {'symbol':'BTCUSDT','orderId':'owned','clientOrderId':cid if reply!='wrong_identity' else 'external',
                'status':'FILLED' if reply=='filled' else 'CANCELED', 'executedQty':'1','avgPrice':'100'}
    owner.binance_client=SimpleNamespace(client=SimpleNamespace(futures_get_order=lookup))
    # Different process/restart finds the same ID from its persisted scope.
    owner._opportunity_coordinator=OpportunityCoordinator(tmp_path/'pending.db')
    reconcile_owned_pending_entries(owner);reconcile_owned_pending_entries(owner)
    assert len(calls)==1
    rows=owner._opportunity_coordinator.pending_submissions(account_scope=a.account_scope,target='binance')
    assert bool(rows)==(reply in {'not_found','wrong_identity'})


def test_pending_lookup_rotation_does_not_starve_later_unknown_orders():
    from trading.entry_fill_evidence import reconcile_owned_pending_entries
    c=OpportunityCoordinator();owner=SimpleNamespace(settings={'account_id':'fixture'},_opportunity_coordinator=c)
    scope=account_scope_for(owner,'live')
    for index in range(4):
        a=c.authorize(policy={'authorized_targets':['binance']},asset_class='crypto',target='binance',symbol=f'COIN{index}USDT',direction='LONG',quantity=1.,price=100.,stop_fraction=.01,account_scope=scope)
        assert a.allowed;c.mark_submitting(a)
    calls=[]
    def lookup(**kwargs):calls.append(kwargs['symbol']);raise TimeoutError('unavailable')
    owner.binance_client=SimpleNamespace(client=SimpleNamespace(futures_get_order=lookup))
    with patch('time.monotonic',side_effect=[0.,31.]):
        reconcile_owned_pending_entries(owner);reconcile_owned_pending_entries(owner)
    assert len(calls)==6 and set(calls)=={f'COIN{i}USDT' for i in range(4)}
    assert c.runtime_snapshot(account_scope=scope,target='binance')['pending_orders']==4


@pytest.mark.parametrize('code,expected',[(-4164,'rejected'),(-2019,'rejected'),(-1111,'rejected'),(-1121,'rejected'),(-1022,'rejected'),(-1006,'unknown'),(-1007,'unknown'),(-4116,'unknown'),(-2010,'unknown'),(-1000,'unknown')])
def test_provider_filter_rejection_is_not_a_permanent_unknown_reservation(code,expected):
    from trading.entry_fill_evidence import binance_submission_error
    error=RuntimeError('private provider detail');error.code=code
    receipt=binance_submission_error(error)
    assert ExecutionOptimizer._submission_state(False,receipt)==expected
    assert 'private provider detail' not in str(receipt)
    c=OpportunityCoordinator();a=auth(c);c.mark_submitting(a)
    from trading.opportunity_coordinator import finish_submission
    finish_submission(SimpleNamespace(_opportunity_coordinator=c),a,receipt)
    assert c.runtime_snapshot(account_scope=a.account_scope,target=a.target)['pending_orders']==(0 if expected=='rejected' else 1)
