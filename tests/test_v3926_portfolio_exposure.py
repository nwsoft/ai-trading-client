from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import time
import pytest
from trading.opportunity_coordinator import OpportunityCoordinator
from trading.portfolio_exposure import collect_exposure, position_gross, normalize_exposure_snapshot


def snapshot(gross, *, checked=None, started=None, fx=None):
    stamp = checked or time.time()
    return {'status':'verified','started_at':started or stamp,'checked_at':stamp,'gross_by_currency':gross,'fx':fx}


def policy(venues, **changes):
    return {'portfolio_exposure': {'enabled':True,'venues':venues,'max_gross_usdt':1000,'max_gross_krw':1000000, **changes}}


def auth(coordinator, *, venue='binance', symbol='BTCUSDT', scope='qa:live', amount=100, observed=None, config=None):
    return coordinator.authorize(policy=config or policy([venue]), asset_class='stock' if venue=='kis' else 'crypto',
        target=venue, symbol=symbol, direction='BUY', quantity=1, price=amount, stop_fraction=.01,
        account_scope=scope, exposure_snapshot=observed, strategy_version=symbol)


def test_cross_venue_positions_and_all_signals_are_aggregated_and_restart_safe(tmp_path):
    path=tmp_path/'risk.db'; first=OpportunityCoordinator(path); second=OpportunityCoordinator(path)
    config=policy(['binance','okx'])
    assert auth(first, observed=snapshot({'USDT':400}), config=config).reason=='portfolio_exposure_unverified'
    allowed=auth(second,venue='okx',symbol='ETH/USDT:USDT',observed=snapshot({'USDT':400}),config=config)
    assert allowed.allowed
    first.mark_submitting(allowed)
    blocked=auth(OpportunityCoordinator(path),symbol='SOLUSDT',observed=snapshot({'USDT':400}),amount=101,config=config)
    assert not blocked.allowed and blocked.reason=='portfolio_gross_cap_exceeded:USDT'
    assert blocked.portfolio_exposure['gross_by_currency']['USDT']==1001
    assert auth(first,symbol='SOLUSDT',scope='other:live',observed=snapshot({'USDT':0}),config=config).reason=='portfolio_exposure_unverified'
    assert auth(first,symbol='SOLUSDT',scope='qa:paper',observed=snapshot({'USDT':0}),config=config).reason=='portfolio_exposure_unverified'


def test_competing_process_instances_cannot_both_consume_remaining_global_cap(tmp_path):
    path=tmp_path/'risk.db'; config=policy(['binance'])
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda symbol: auth(OpportunityCoordinator(path),symbol=symbol,amount=100,
            observed=snapshot({'USDT':850}),config=config), ['BTCUSDT','ETHUSDT']))
    assert sum(r.allowed for r in results)==1


def test_fill_or_partial_cancel_counts_until_a_later_full_positions_read(tmp_path):
    coordinator=OpportunityCoordinator(tmp_path/'risk.db')
    before=time.time(); result=auth(coordinator,observed=snapshot({'USDT':800},checked=before),amount=150)
    assert result.allowed
    coordinator.reconcile(result,status='cancelled',order_id='fixture-own')
    coordinator.release(result)
    assert not auth(coordinator,symbol='ETHUSDT',observed=snapshot({'USDT':800},checked=before),amount=100).allowed
    assert auth(coordinator,symbol='SOLUSDT',observed=snapshot({'USDT':850}),amount=100).allowed


@pytest.mark.parametrize('gross', [{'USDT':float('nan')},{'USDT':-1},{'USD':100}, {}, {'USDT':True}])
def test_invalid_snapshot_is_not_persisted_as_confirmed_zero(gross):
    result=auth(OpportunityCoordinator(),observed=snapshot(gross))
    assert not result.allowed and result.reason=='portfolio_exposure_unverified'


def test_missing_stale_future_and_failed_venue_are_not_a_flat_account():
    for observed in (None, snapshot({'USDT':0},checked=time.time()-61),snapshot({'USDT':0},checked=time.time()+10),
                     {'status':'error','positions':[]}):
        assert not auth(OpportunityCoordinator(),observed=observed).allowed


def test_fx_requires_observed_exact_pair_not_usd_peg_or_foreign_currency_sum():
    coordinator=OpportunityCoordinator(); config=policy(['upbit','binance'],max_gross_usdt=0,max_gross_krw=0,max_reference_gross=1500000)
    assert not auth(coordinator,venue='upbit',symbol='BTC/KRW',amount=10000,observed=snapshot({'KRW':100000}),config=config).allowed
    assert auth(coordinator,observed=snapshot({'USDT':900}),config=config).reason=='portfolio_fx_unverified'
    stamp=time.time(); fx={'base':'USDT','quote':'KRW','rate':1400,'observed_at':stamp,'source':'upbit:USDT/KRW'}
    # Publish new observed quote without reserving a rejected over-limit proposal.
    result=auth(coordinator,venue='upbit',symbol='ETH/KRW',amount=1000000,observed=snapshot({'KRW':100000},fx=fx),config=config)
    assert not result.allowed and result.reason=='portfolio_reference_cap_exceeded'
    accepted=auth(coordinator,symbol='SOLUSDT',amount=50,observed=snapshot({'USDT':900}),config=config)
    assert accepted.allowed and accepted.portfolio_exposure['reference_gross']==1430000
    assert accepted.portfolio_exposure['fx']['rate']==1400


def test_stock_sell_protection_does_not_require_or_consume_global_cap():
    result=OpportunityCoordinator().authorize(policy=policy(['kis']),asset_class='stock',target='kis',symbol='005930',
        direction='SELL',quantity=1,price=100000,stop_fraction=.02,account_scope='qa:live')
    assert result.allowed and result.portfolio_exposure is None


def test_disabled_and_learning_guards_make_no_private_provider_request():
    owner=SimpleNamespace(binance_client=SimpleNamespace(get_positions_result=Mock(side_effect=AssertionError('private read'))))
    assert collect_exposure(owner,venue='binance',mode='live',policy={'enabled':False}) is None
    assert collect_exposure(owner,venue='binance',mode='learning',policy=policy(['binance'])['portfolio_exposure']) is None
    owner.binance_client.get_positions_result.assert_not_called()


@pytest.mark.parametrize('venue', ['binance','bybit','okx','bitget','kis','kiwoom','mirae','shinhan'])
def test_live_collection_includes_external_holdings_without_ownership_or_leverage_discount(venue):
    row={'symbol':'BTC/USDT:USDT' if venue!='binance' else 'BTCUSDT','size':2,'mark_price':100,
         'linear':True,'contract_size':.01,'leverage':100,'quantity':2,'current_price':100}
    adapter=SimpleNamespace(get_positions_result=Mock(return_value={'status':'success','complete':True,'positions':[row]}))
    owner=SimpleNamespace(binance_client=adapter,adapter=adapter,get_exchange_client=lambda v:adapter)
    result=collect_exposure(owner,venue=venue,mode='live',policy=policy([venue])['portfolio_exposure'])
    assert result['status']=='verified'
    assert sum(result['gross_by_currency'].values())==(2 if venue in ('bybit','okx','bitget') else 200)


def test_inverse_missing_multiplier_and_partial_broker_page_cannot_be_certified():
    with pytest.raises(ValueError): position_gross([{'symbol':'BTC/USDT','size':2,'mark_price':100,'linear':True}],venue='okx')
    adapter=SimpleNamespace(get_positions_result=lambda:{'status':'success','positions':[],'complete':False})
    assert collect_exposure(SimpleNamespace(adapter=adapter),venue='kis',mode='live',policy=policy(['kis'])['portfolio_exposure'])['status']=='unverified'


def test_snapshot_privacy_and_time_order_are_enforced():
    row=snapshot({'USDT':120});row['api_key']='never-export'
    assert 'api_key' not in normalize_exposure_snapshot(row,now=time.time())
    row['started_at']=time.time()+100
    assert normalize_exposure_snapshot(row,now=time.time())['status']=='unverified'


def test_started_venue_publishes_positions_even_without_entry_signal(tmp_path):
    from trading.portfolio_exposure import refresh_exposure
    row=SimpleNamespace(symbol='BTCUSDT',size=1,mark_price=100)
    owner=SimpleNamespace(recorder=SimpleNamespace(db_path=str(tmp_path/'ledger.db')),settings={'account_id':'fixture'},
        binance_client=SimpleNamespace(get_positions_result=Mock(return_value={'status':'success','positions':[row]})))
    refresh_exposure(owner,venue='binance',mode='live',policy=policy(['binance','okx'])['portfolio_exposure'])
    refresh_exposure(owner,venue='binance',mode='live',policy=policy(['binance','okx'])['portfolio_exposure'])
    owner.binance_client.get_positions_result.assert_called_once()
    from trading.opportunity_coordinator import account_scope_for
    result=auth(OpportunityCoordinator(tmp_path/'opportunity_runtime.db'),venue='okx',symbol='ETH/USDT:USDT',
        scope=account_scope_for(owner,'live'),observed=snapshot({'USDT':100}),config=policy(['binance','okx']))
    assert result.allowed


@pytest.mark.parametrize('venue',['upbit','bithumb','coinone'])
def test_spot_external_holdings_are_valued_including_used_not_only_free(venue):
    ticker=Mock(return_value={'timestamp':time.time()*1000,'last':100})
    exchange=SimpleNamespace(fetch_balance=Mock(return_value={'total':{'KRW':5000,'BTC':3}}),
        markets={'BTC/KRW':{}},fetch_ticker=ticker)
    adapter=SimpleNamespace(is_connected=True,api_key='fixture',secret_key='fixture',exchange=exchange)
    exchange.markets['BTC/KRW']={'symbol':'BTC/KRW'}
    result=collect_exposure(SimpleNamespace(get_exchange_client=lambda v:adapter),venue=venue,mode='live',policy=policy([venue])['portfolio_exposure'])
    assert result['status']=='verified' and result['gross_by_currency']['KRW']==300
    ticker.assert_called_once_with('BTC/KRW')


def test_kis_complete_holdings_pages_use_next_cursor_and_do_not_guess_on_loop():
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    adapter=KoreaInvestmentStockAdapter.__new__(KoreaInvestmentStockAdapter)
    adapter.is_connected=True;adapter._account_parts=lambda:('fixture','01')
    adapter._parse_position=lambda raw:{'code':raw['pdno'],'quantity':int(raw['hldg_qty']),'current_price':100}
    pages=[{'rt_cd':'0','output1':[{'pdno':'005930','hldg_qty':'2'}],'_tr_cont':'M','ctx_area_fk100':'F','ctx_area_nk100':'N'},
           {'rt_cd':'0','output1':[{'pdno':'000660','hldg_qty':'3'}],'_tr_cont':'D'}]
    calls=[]
    def read(path,params):calls.append(dict(params));return pages.pop(0)
    adapter._get=read
    result=adapter.get_portfolio_exposure_result()
    assert result['complete'] and len(result['positions'])==2
    assert calls[1]['CTX_AREA_FK100']=='F' and calls[1]['CTX_AREA_NK100']=='N'
    adapter._get=lambda path,params:{'rt_cd':'0','output1':[],'_tr_cont':'M','ctx_area_fk100':'F','ctx_area_nk100':'N'}
    assert adapter.get_portfolio_exposure_result()['complete'] is False


def test_kiwoom_complete_pages_and_proxy_use_the_actual_new_host_method():
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
    adapter=KiwoomStockAdapter.__new__(KiwoomStockAdapter)
    adapter.is_connected=True;adapter.account_no='fixture';adapter.account_password=''
    adapter.kiwoom=SimpleNamespace(tr_remained=True)
    calls=[]
    def read(tr,**kwargs):
        calls.append(kwargs['next']);adapter.kiwoom.tr_remained=len(calls)<2
        return {'multi':[{'quantity':1,'code':str(len(calls))}]}
    adapter._call_block_request=read
    adapter._parse_position_record=lambda raw:{'code':raw['code'],'quantity':1,'current_price':100}
    result=adapter.get_portfolio_exposure_result()
    assert result['complete'] and len(result['positions'])==2 and calls==[0,2]
    proxy=KiwoomProcessProxy.__new__(KiwoomProcessProxy);proxy._call=Mock(return_value=result)
    assert proxy.get_portfolio_exposure_result()==result
    proxy._call.assert_called_once_with('get_portfolio_exposure_result')


def test_submitted_rejection_keeps_gross_until_positions_read_but_preflight_rejection_releases():
    coordinator=OpportunityCoordinator(); before=time.time()
    submitted=auth(coordinator,observed=snapshot({'USDT':800},checked=before),amount=150)
    coordinator.mark_submitting(submitted)
    coordinator.reconcile(submitted,status='rejected',order_id='fixture-receipt')
    assert not auth(coordinator,symbol='ETHUSDT',observed=snapshot({'USDT':800},checked=before),amount=100).allowed
    assert auth(coordinator,symbol='SOLUSDT',observed=snapshot({'USDT':800}),amount=100).allowed
    preflight=auth(coordinator,symbol='ADAUSDT',observed=snapshot({'USDT':0}),amount=100)
    assert preflight.allowed
    coordinator.reconcile(preflight,status='rejected')
    assert not coordinator.snapshot(preflight.opportunity_id,account_scope='qa:live')['reservations']


@pytest.mark.parametrize('payload,expected', [({},None),({'complete':True},True),({'has_more':False},True),
    ({'complete':True,'has_more':True},False),({'complete':False,'has_more':False},False),
    ({'complete':True,'next_cursor':'another-page'},False),({'complete':'true'},None)])
def test_partner_completion_requires_consistent_explicit_evidence(payload,expected):
    from trading.exchanges.position_snapshot import partner_holdings_complete
    assert partner_holdings_complete(payload) is expected
