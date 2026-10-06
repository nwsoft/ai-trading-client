from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import math
import time
import pytest
from trading.observed_correlation import daily_returns, aligned_correlation, apply_observed_correlations
from trading.portfolio_orchestrator import PortfolioOrchestrator


def candles(scale=1, *, count=100):
    now=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    rows=[]; price=100*scale
    for i in range(count):
        price*=1+.008*math.sin(i*.73)+.002
        date=(now-timedelta(days=count-i)).strftime('%Y%m%d')
        rows.append({'date':date,'close':price})
    return rows


def test_identical_scaled_prices_match_dates_and_have_measured_positive_correlation():
    a=daily_returns(candles(),now=time.time());b=daily_returns(candles(5),now=time.time())
    result=aligned_correlation(a,b)
    assert result['value']==pytest.approx(1) and result['samples']==99


def test_different_calendar_gaps_do_not_pair_returns_merely_by_array_index():
    left={('20260101','20260102'):.1,('20260102','20260103'):.2}
    right={('20260101','20260103'):.1,('20260103','20260104'):.2}
    result=aligned_correlation(left,right,minimum=2)
    assert result['value'] is None and result['samples']==0


def test_flat_or_insufficient_returns_are_unknown_not_zero_correlation():
    keys=[(str(i),str(i+1)) for i in range(50)]
    assert aligned_correlation(dict.fromkeys(keys,0),dict.fromkeys(keys,.01))['value'] is None
    assert aligned_correlation({keys[0]:.1},{keys[0]:.2})['value'] is None


@pytest.mark.parametrize('change', ['nan','negative','duplicate','reversed','stale'])
def test_invalid_history_is_not_certified(change):
    rows=candles()
    if change=='nan':rows[0]['close']=float('nan')
    if change=='negative':rows[0]['close']=-1
    if change=='duplicate':rows[1]['date']=rows[0]['date']
    if change=='reversed':rows=list(reversed(rows))
    if change=='stale':rows=[{'date':'20200101','close':100}]
    with pytest.raises(ValueError):daily_returns(rows,now=time.time())


def test_incomplete_daily_bar_is_ignored_and_cache_has_bounded_public_requests():
    owner=SimpleNamespace();fetch=Mock(side_effect=lambda symbol,limit:candles(1 if symbol=='A' else 4))
    candidates=[{'symbol':'A','asset_class':'crypto','signal_strength':.8,'volatility':.03},
                {'symbol':'B','asset_class':'crypto','signal_strength':.8,'volatility':.03}]
    policy={'observed_correlation':{'enabled':True}}
    enriched=apply_observed_correlations(owner,venue='okx',candidates=candidates,policy=policy,fetcher=fetch)
    assert all(row['correlation_basis']=='observed_aligned_daily_returns' for row in enriched)
    apply_observed_correlations(owner,venue='okx',candidates=candidates,policy=policy,fetcher=fetch)
    assert fetch.call_count==2
    result=PortfolioOrchestrator().allocate(enriched,1000,policy)
    assert result['allocations']['A']['correlation_pairs'][0]['samples']==99
    rows=candles();today=datetime.now(timezone.utc).strftime('%Y%m%d');rows.append({'date':today,'close':999999999})
    assert len(daily_returns(rows,now=time.time()))==99


def test_missing_peer_is_conservative_and_disabled_feature_makes_no_public_calls():
    candidates=[{'symbol':'A'}, {'symbol':'B'}];fetch=Mock(side_effect=TimeoutError('private error must not export'))
    result=apply_observed_correlations(SimpleNamespace(),venue='upbit',candidates=candidates,
        policy={'observed_correlation':{'enabled':True}},fetcher=fetch)
    assert all(r['avg_correlation']==1 and r['correlation_basis']!='observed_aligned_daily_returns' for r in result)
    fetch.reset_mock()
    assert apply_observed_correlations(SimpleNamespace(),venue='upbit',candidates=candidates,policy={},fetcher=fetch)==candidates
    fetch.assert_not_called()


def test_more_than_thirty_candidates_keeps_unknown_and_bounds_requests():
    fetch=Mock(side_effect=lambda symbol,limit:candles())
    result=apply_observed_correlations(SimpleNamespace(),venue='okx',candidates=[{'symbol':str(i)} for i in range(40)],
        policy={'observed_correlation':{'enabled':True}},fetcher=fetch)
    assert len(result)==40 and fetch.call_count==30
    assert all(r['correlation_basis']!='observed_aligned_daily_returns' for r in result[30:])


def test_uniform_observed_correlation_reduces_total_capital_even_after_score_normalization():
    candidates=[{'symbol':s,'avg_correlation':1,'signal_strength':.8,'volatility':.03,'asset_class':'crypto'} for s in ('A','B')]
    result=PortfolioOrchestrator().allocate(candidates,1000,{'observed_correlation':{'enabled':True},'correlation_penalty':.25})
    assert result['risk_scale']==pytest.approx(.75)
    assert sum(row['capital'] for row in result['allocations'].values())==pytest.approx(375)


def test_large_finite_returns_do_not_overflow_pearson_intermediates():
    left={(str(i),str(i+1)):(i+1)*1e300 for i in range(50)}
    assert aligned_correlation(left,left)['value']==pytest.approx(1)


def test_cross_venue_same_currency_history_is_shared_without_mixing_modes_or_fx():
    from trading.opportunity_coordinator import OpportunityCoordinator
    shared=OpportunityCoordinator()
    a=SimpleNamespace(settings={'account_id':'shared-fixture'},_opportunity_coordinator=shared)
    b=SimpleNamespace(settings={'account_id':'shared-fixture'},_opportunity_coordinator=shared)
    policy={'observed_correlation':{'enabled':True}}
    apply_observed_correlations(a,venue='upbit',mode='paper',candidates=[{'symbol':'BTC/KRW'}],policy=policy,fetcher=lambda s,l:candles())
    result=apply_observed_correlations(b,venue='kis',mode='paper',candidates=[{'symbol':'005930'}],policy=policy,fetcher=lambda s,l:candles(2))
    assert result[0]['correlation_basis']=='observed_aligned_daily_returns'
    assert result[0]['correlation_pairs'][0]['symbol']=='upbit:BTC/KRW'
    assert apply_observed_correlations(b,venue='kis',mode='live',candidates=[{'symbol':'005930'}],policy=policy,fetcher=lambda s,l:candles())[0]['correlation_basis']=='correlation_peer_unavailable'
    assert apply_observed_correlations(b,venue='binance',mode='paper',candidates=[{'symbol':'BTCUSDT'}],policy=policy,fetcher=lambda s,l:candles())[0]['correlation_basis']=='correlation_peer_unavailable'


@pytest.mark.parametrize('venue',['miraeAsset','koreaInvestment'])
def test_actual_stock_controller_aliases_use_the_same_canonical_cache_key(venue):
    result=apply_observed_correlations(SimpleNamespace(),venue=venue,candidates=[{'symbol':'005930'},{'symbol':'000660'}],
        policy={'observed_correlation':{'enabled':True}},fetcher=lambda s,l:candles())
    assert result[0]['correlation_basis']=='observed_aligned_daily_returns'


def test_parallel_venues_keep_separate_scoped_evidence_and_bounded_cache():
    from concurrent.futures import ThreadPoolExecutor
    from trading.opportunity_coordinator import OpportunityCoordinator
    owner=SimpleNamespace(settings={'account_id':'parallel-fixture'},_opportunity_coordinator=OpportunityCoordinator())
    venues=['bybit','okx','bitget','upbit','bithumb','coinone']
    def run(venue):
        return apply_observed_correlations(owner,venue=venue,mode='paper',candidates=[{'symbol':str(i)} for i in range(30)],
            policy={'observed_correlation':{'enabled':True}},fetcher=lambda s,l:candles())
    with ThreadPoolExecutor(6) as pool: results=list(pool.map(run,venues))
    assert len(owner._observed_return_cache)<=120
    assert len(owner._last_correlation_evidence_by_scope)==6
    for venue in venues:assert owner._last_correlation_evidence_by_scope[(venue,'paper')]['source']==venue
    assert all(len(result)==30 for result in results)
