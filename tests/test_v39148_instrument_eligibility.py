"""Offline lifecycle tests: fresh provider evidence, no keys/accounts/orders."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
import logging
import time

import pytest

from trading import instrument_eligibility as g
from trading.exchanges.venue_capabilities import SUPPORTED_VENUES, venue_capabilities


def row(venue, state='tradable'):
    if venue in g.STOCKS:
        return dict(symbol='005930', code='005930', status='ok' if state == 'tradable' else state)
    if venue in g.SPOTS:
        return dict(symbol='BTC/KRW', quote='KRW', spot=True, active=state == 'tradable', status=state,
                    maintenance_status=0, trade_status=1 if state == 'tradable' else 0)
    return dict(symbol='BTCUSDT' if venue == 'binance' else 'BTC/USDT:USDT', quote='USDT',
                active=state == 'tradable', contract=True, swap=True, status='TRADING' if state == 'tradable' else state,
                contract_type='PERPETUAL', settle='USDT')


@pytest.mark.parametrize('venue', sorted(SUPPORTED_VENUES))
def test_all_venues_refresh_expiry_failure_and_recovery(monkeypatch, venue):
    assert venue_capabilities(venue)['instrument_eligibility_contract'] == g.CONTRACT
    owner = SimpleNamespace()
    item = row(venue)
    rows = [item]
    calls = []
    def fetch(*args):
        calls.append(args)
        if rows is None:
            raise TimeoutError('private details must not be exposed')
        return deepcopy(rows), 'fixture'
    monkeypatch.setattr(g, '_fetch', fetch)
    assert g.eligibility(owner, venue, item['symbol'])['allowed']
    assert g.eligibility(owner, venue, item['symbol'])['allowed']
    assert len(calls) == 1
    rows = [row(venue, 'halted')]
    owner._instrument_guard_cache[venue]['expires'] = 0
    assert not g.eligibility(owner, venue, item['symbol'])['allowed']
    rows = None
    g.invalidate(owner, venue)
    failed = g.eligibility(owner, venue, item['symbol'])
    assert failed['reason'] == 'instrument_catalogue_unavailable'
    assert 'private details' not in str(failed)
    count = len(calls)
    g.eligibility(owner, venue, item['symbol'])
    assert len(calls) == count  # failure backoff
    rows = [item]
    owner._instrument_guard_cache[venue]['expires'] = 0
    assert g.eligibility(owner, venue, item['symbol'])['allowed']


@pytest.mark.parametrize('venue', sorted(SUPPORTED_VENUES))
def test_order_boundary_entry_blocked_exit_preserved(monkeypatch, venue):
    monkeypatch.setattr(g, '_fetch', lambda *a:([row(venue, 'delisted')], 'fixture'))
    class Order:
        calls = 0
        @g.instrument_order(venue)
        def place(self, symbol, side, reduce_only=False):
            self.calls += 1
            return {'status': 'success'}
    obj = Order()
    symbol = row(venue)['symbol']
    assert obj.place(symbol, 'BUY')['status'] == 'error'
    if venue in g.FUTURES:
        assert obj.place(symbol, 'SELL')['status'] == 'error'
        assert obj.place(symbol, 'BUY', reduce_only=True)['status'] == 'success'
    else:
        assert obj.place(symbol, 'SELL')['status'] == 'success'
    assert obj.calls == 1


def test_new_venue_cannot_silently_bypass_contract():
    assert not g.eligibility(SimpleNamespace(), 'new_broker', 'BTCUSDT')['allowed']
    assert SUPPORTED_VENUES == g.STOCKS | g.SPOTS | g.FUTURES


def test_singleflight_and_owner_isolation(monkeypatch):
    calls = []
    def fetch(*args):
        calls.append(1)
        time.sleep(.01)
        return [row('okx')], 'fixture'
    monkeypatch.setattr(g, '_fetch', fetch)
    owner = SimpleNamespace(exchange=object())
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda _:g.eligibility(owner, 'okx', 'BTCUSDT')['allowed'], range(32)))
    assert len(calls) == 1
    owner.exchange = object()
    assert g.eligibility(owner, 'okx', 'BTCUSDT')['allowed']
    assert len(calls) == 2
    assert g.eligibility(SimpleNamespace(), 'okx', 'BTCUSDT')['allowed']
    assert len(calls) == 3


@pytest.mark.parametrize('trade,maintenance,allowed,state', [(1,0,True,'tradable'),(0,0,False,'halted'),(2,0,False,'close_only'),(3,0,False,'sell_disabled'),(1,1,False,'halted'),(None,0,False,'unknown')])
def test_coinone_official_status_not_ticker(monkeypatch, trade, maintenance, allowed, state):
    monkeypatch.setattr(g, '_public_json', lambda url:dict(result='success', error_code='0', markets=[dict(target_currency='btc', quote_currency='krw', trade_status=trade, maintenance_status=maintenance)]))
    actual = g.eligibility(SimpleNamespace(), 'coinone', 'KRW-BTC')
    assert actual['allowed'] is allowed and actual['state'] == state


def test_bithumb_listing_not_legacy_ticker_and_caution_is_not_delisting(monkeypatch):
    monkeypatch.setattr(g, '_public_json', lambda url:[dict(market='KRW-BTC', market_warning='CAUTION')])
    owner = SimpleNamespace(exchange=SimpleNamespace(markets={'OLD/KRW': {'active':True}}))
    assert g.eligibility(owner, 'bithumb', 'BTC/KRW')['allowed']
    assert not g.eligibility(owner, 'bithumb', 'OLD/KRW')['allowed']
    item = next(iter(g.catalogue(owner,'bithumb')['rows'].values()))
    assert item['symbol'] == 'BTC/KRW' and item['base'] == 'BTC'


def test_coinone_provider_case_and_quote_preserve_scoring_identity(monkeypatch):
    monkeypatch.setattr(g,'_public_json',lambda url:{'result':'success','error_code':'0','markets':[
        dict(target_currency='btc',quote_currency='krw',trade_status=1,maintenance_status=0)]})
    item = next(iter(g.catalogue(SimpleNamespace(),'coinone')['rows'].values()))
    assert item['symbol'] == 'BTC/KRW' and item['base'] == 'BTC' and item['quote'] == 'KRW'


@pytest.mark.parametrize('venue', ['upbit','okx','bybit','bitget'])
def test_ccxt_requires_reload_and_never_uses_stale_rows(venue):
    fresh = row(venue)
    old = dict(fresh, symbol='OLD/KRW' if venue == 'upbit' else 'OLD/USDT:USDT')
    class Exchange:
        markets = {old['symbol']: old}
        def load_markets(self, reload=False):
            assert reload is True
            return {fresh['symbol']:fresh}
    owner = SimpleNamespace(exchange=Exchange())
    assert g.eligibility(owner, venue, fresh['symbol'])['allowed']
    assert not g.eligibility(owner, venue, old['symbol'])['allowed']


def test_stock_pins_cannot_reintroduce_halt_or_missing_and_input_preserved():
    from trading.stock_analysis_service import select_stock_universe
    items = [dict(code='005930',status='ok'),dict(code='999999',status='delisted')]
    adapter = SimpleNamespace(exchange_name='kis',get_stock_list=lambda market:items,get_etf_list=lambda:[])
    before = deepcopy(items)
    selected = select_stock_universe(adapter,configured_symbols=['999999','111111','005930'],asset_mode='stock')
    assert selected == ['005930'] and items == before


def test_unknown_conflicting_metadata_wrong_product(monkeypatch):
    for rows, reason in [([dict(row('okx'),active=None,status='')],'instrument_unknown'),
                         ([row('okx'),row('okx','halted')],'instrument_unknown'),
                         ([dict(row('okx'),inverse=True)],'instrument_wrong_product')]:
        monkeypatch.setattr(g, '_fetch', lambda *a:(rows,'fixture'))
        assert g.eligibility(SimpleNamespace(),'okx','BTCUSDT')['reason'] == reason


def test_binance_real_status_contract_filters_backups(monkeypatch):
    owner = SimpleNamespace(get_exchange_info=lambda:{'symbols':[row('binance'),dict(row('binance'),symbol='OLDUSDT',status='BREAK')]})
    assert g.eligibility(owner,'binance','BTCUSDT')['allowed']
    assert not g.eligibility(owner,'binance','OLDUSDT')['allowed']
    assert not g.eligibility(owner,'binance','MISSINGUSDT')['allowed']


def test_stock_provider_restrictions_not_overwritten():
    assert g.stock_status({'status':'halted'}) == 'halted'
    assert g.row_state({'status':'ok','trht_yn':'Y'},'kis') == 'halted'
    assert g.row_state({'status':'ok','market_warning':'CAUTION'},'kis') == 'tradable'
    assert g.row_state({'code':'005930'},'kis') == 'unknown'


@pytest.mark.parametrize('venue',['shinhan','mirae'])
def test_partner_missing_status_requires_official_master(monkeypatch,venue):
    from trading.exchanges import kis_market_master as master
    rows = [dict(code='005930',status=g.stock_status({})),dict(code='999999',status=g.stock_status({})),dict(code='000660',status='halted')]
    owner = SimpleNamespace(get_stock_list=lambda market:rows,get_etf_list=lambda:[])
    monkeypatch.setattr(master,'market_master',lambda market:[dict(code=s,status='ok',is_etf=False,_listing_checked_at=time.time()) for s in ('005930','000660')])
    assert g.eligibility(owner,venue,'005930')['allowed']
    assert not g.eligibility(owner,venue,'999999')['allowed']
    assert not g.eligibility(owner,venue,'000660')['allowed']
    g.invalidate(owner,venue)
    monkeypatch.setattr(master,'market_master',lambda market:(_ for _ in ()).throw(TimeoutError()))
    assert not g.eligibility(owner,venue,'005930')['allowed']


def test_log_rate_bounded(monkeypatch, caplog):
    monkeypatch.setattr(g, '_fetch', lambda *a:([row('okx','halted')],'fixture'))
    owner = SimpleNamespace()
    with caplog.at_level(logging.WARNING):
        for _ in range(100):
            g.entry_check(owner,'okx','BTCUSDT')
    assert len(caplog.records) == 1


@pytest.mark.parametrize('venue,module,cls', [
    ('upbit','upbit_spot_adapter','UpbitSpotAdapter'),('bithumb','bithumb_spot_adapter','BithumbSpotAdapter'),
    ('coinone','coinone_spot_adapter','CoinoneSpotAdapter'),('okx','okx_futures_adapter','OkxFuturesAdapter'),
    ('bybit','bybit_futures_adapter','BybitFuturesAdapter'),('bitget','bitget_futures_adapter','BitgetFuturesAdapter'),
    ('kis','korea_investment_stock_adapter','KoreaInvestmentStockAdapter'),('mirae','mirae_asset_stock_adapter','MiraeAssetStockAdapter'),
    ('shinhan','shinhan_stock_adapter','ShinhanStockAdapter'),('kiwoom','kiwoom_stock_adapter','KiwoomStockAdapter')])
def test_real_adapters_do_not_submit_restricted_entry(monkeypatch,venue,module,cls):
    import importlib
    adapter_class = getattr(importlib.import_module('trading.exchanges.adapters.'+module),cls)
    adapter = adapter_class.__new__(adapter_class)
    adapter.is_connected = True
    monkeypatch.setattr(g,'_fetch',lambda *a:([row(venue,'halted')],'fixture'))
    # Missing all order transport attributes is intentional: reaching an order
    # would fail. The production decorator must reject before any submission.
    assert adapter.place_order.instrument_eligibility_contract == g.CONTRACT
    result = adapter.place_order(row(venue)['symbol'],'BUY',1)
    assert result['status'] == 'error' and result['reason'] == 'instrument_halted'


def test_real_native_binance_entry_and_final_selection_filter(monkeypatch):
    from api.binance_client import BinanceClient, OrderRequest
    from trading.evaluator import Evaluator
    client = BinanceClient.__new__(BinanceClient)
    monkeypatch.setattr(g,'_fetch',lambda *a:([row('binance','halted')],'fixture'))
    assert client.place_order(OrderRequest('BTCUSDT','BUY','MARKET',1))['reason'] == 'instrument_halted'
    assert client.place_futures_order('BTCUSDT','SELL',quantity=1)['reason'] == 'instrument_halted'
    evaluator = Evaluator.__new__(Evaluator)
    evaluator.settings = {}
    evaluator.binance_client = client
    evaluator._selection_singleflight = SimpleNamespace(run=lambda *a,**k:[dict(symbol='BTCUSDT',execution_eligible=True)],invalidate=lambda *a:None)
    assert evaluator.select_trading_coins() == []


def test_provider_metadata_snapshot_does_not_mutate(monkeypatch):
    item = row('okx')
    item['info'] = {'state':'live'}
    monkeypatch.setattr(g,'_fetch',lambda *a:([item],'fixture'))
    owner = SimpleNamespace()
    assert g.eligibility(owner,'okx','BTCUSDT')['allowed']
    item['info']['state'] = 'suspend'
    assert g.eligibility(owner,'okx','BTCUSDT')['allowed']  # immutable until refresh
    g.invalidate(owner,'okx')
    assert not g.eligibility(owner,'okx','BTCUSDT')['allowed']


def test_kis_configured_etfs_must_exist_in_official_master(monkeypatch):
    from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
    from trading.exchanges import kis_market_master as master
    adapter = KoreaInvestmentStockAdapter('','',configured_etf_symbols=['999999','069500'])
    adapter.is_connected = True
    monkeypatch.setattr(master,'market_master',lambda market:[dict(code='069500',is_etf=True,status='ok')])
    assert [r['code'] for r in adapter.get_etf_list()] == ['069500']
    assert adapter._configured_etf_symbols == ['999999','069500']


def test_kiwoom_status_missing_is_unknown_not_delisted():
    from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter
    adapter = KiwoomStockAdapter.__new__(KiwoomStockAdapter)
    adapter.kiwoom = SimpleNamespace(GetMasterStockState=lambda s:'거래정지|증거금100%')
    assert adapter._listing_state('005930') == 'halted'
    adapter.kiwoom = SimpleNamespace(GetMasterStockState=lambda s:'관리종목|증거금100%')
    assert adapter._listing_state('005930') == 'ok'
    adapter.kiwoom = SimpleNamespace()
    assert adapter._listing_state('005930') == 'unknown'


def test_nested_master_cache_cannot_extend_evidence_lifetime(monkeypatch):
    old = dict(row('kis'),_listing_checked_at=time.time()-295)
    monkeypatch.setattr(g,'_fetch',lambda *a:([old],'fixture'))
    owner = SimpleNamespace()
    result = g.catalogue(owner,'kis')
    assert 0 < result['expires'] - time.monotonic() < 5
    g.invalidate(owner,'kis')
    old['_listing_checked_at'] -= 10
    assert not g.eligibility(owner,'kis','005930')['allowed']


@pytest.mark.parametrize('venue',['coinone','bithumb'])
def test_native_catalogue_to_actual_spot_scoring_keeps_ccxt_symbol(monkeypatch,venue):
    from trading.evaluator import Evaluator
    response = {'result':'success','error_code':'0','markets':[
        dict(target_currency='btc',quote_currency='krw',trade_status=1,maintenance_status=0),
        dict(target_currency='old',quote_currency='krw',trade_status=0,maintenance_status=0)]}
    monkeypatch.setattr(g,'_public_json',lambda url:response if venue=='coinone' else [{'market':'KRW-BTC'}])
    evaluator = Evaluator(SimpleNamespace(settings={},binance_client=None),None,settings={})
    evaluator._selection_learning_manager = lambda:SimpleNamespace(should_apply_api_delay=lambda:False,get_max_coins_for_analysis=lambda:10)
    def tickers(adapter,symbols):
        assert symbols == ['BTC/KRW']
        return {'BTC/KRW':dict(last=100,quoteVolume=50000,percentage=1)}
    evaluator._fetch_exchange_tickers = tickers
    selected = evaluator._analyze_candidate_coins_spot(SimpleNamespace(exchange_name=venue))
    assert len(selected)==1 and selected[0]['symbol']=='BTC/KRW' and selected[0]['is_major']


@pytest.mark.parametrize('venue', sorted(g.SPOTS | (g.FUTURES - {'binance'})))
@pytest.mark.parametrize('mode', ['live', 'paper'])
@pytest.mark.parametrize('candidate_state', ['empty', 'rejected', 'unscored'])
def test_existing_positions_checked_before_candidate_only_returns(venue, mode, candidate_state):
    from trading.unified_trader import UnifiedTrader
    from trading.execution_mode import ExecutionMode
    calls = []
    candidates = [] if candidate_state == 'empty' else [{'symbol':'BTCUSDT', 'execution_eligible':False}]
    trader = SimpleNamespace(
        settings={}, logger=logging.getLogger('lifecycle-test'),
        learning_enabled_exchanges={venue},
        selected_coins={venue:candidates},
        _execution_mode=lambda ex:ExecutionMode(mode),
        _monitor_exchange_positions=lambda ex:calls.append(('protect',ex)),
        _auto_adjust_threshold_from_performance=lambda ex:None,
        _apply_connected_strategy_runtime_unified=lambda ex:None,
        _check_and_reselect_coins_unified_optimized=lambda ex:None,
        _prefilter_supported_coins=lambda ex,rows:[] if candidate_state=='rejected' else rows,
        _schedule_unscored_reselection_unified=lambda ex:calls.append(('reselect',ex)),
        log_event=lambda *a,**k:None,
    )
    UnifiedTrader.execute_trading_cycle_unified(trader,venue)
    assert [call for call in calls if call[0]=='protect'] == [('protect',venue)]
    assert calls[0] == ('protect',venue)
    assert (('reselect',venue) in calls) == (candidate_state=='unscored')
