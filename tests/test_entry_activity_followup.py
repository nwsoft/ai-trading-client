"""Cross-venue metadata isolation and session inactivity/worker diagnostics."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import ccxt
import pytest
from trading.entry_diagnostics import decision_code, entry_activity, monitored_cycle, record_entry
from trading.operation_evidence import publish, snapshot, reset
from trading.public_futures_catalogue import bitget_usdt_catalogue
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter


def bitget_raw():
    return dict(symbol='BTCUSDT',baseCoin='BTC',quoteCoin='USDT',supportMarginCoins=['USDT'],
                symbolType='perpetual',symbolStatus='normal',priceEndStep='5',pricePlace='2',
                sizeMultiplier='.001',volumePlace='3',minTradeNum='.001',minTradeUSDT='5',minLever='1',maxLever='125',
                takerFeeRate='.0006',makerFeeRate='.0002',launchTime='1600000000000')


def test_bitget_only_required_public_product_and_precision_matches_installed_sdk():
    raw=bitget_raw()
    baseline=ccxt.bitget()
    baseline.options['fetchMarkets'] = ({'types':['swap']} if hasattr(baseline, 'fetch_default_markets') else ['swap'])
    baseline.publicMixGetV2MixMarketContracts=Mock(side_effect=lambda params:{
        'code':'00000','data':[raw] if params['productType']=='USDT-FUTURES' else []})
    fetch = getattr(baseline, 'fetch_default_markets', baseline.fetch_markets)
    expected=baseline.set_markets(fetch({}))['BTC/USDT:USDT']
    actual=ccxt.bitget({'apiKey':'fixture','secret':'fixture','password':'fixture'})
    actual.fetch_currencies=Mock(side_effect=ccxt.ExchangeNotAvailable('unrelated currencies'))
    actual.publicMixGetV2MixMarketContracts=Mock(side_effect=lambda params:{'code':'00000','data':[raw]}
        if params=={'productType':'USDT-FUTURES'} else (_ for _ in ()).throw(AssertionError('unrelated product')))
    markets=bitget_usdt_catalogue(actual)
    assert markets['BTC/USDT:USDT']==expected
    assert actual.amount_to_precision('BTC/USDT:USDT',.0019)=='0.001'
    assert actual.price_to_precision('BTC/USDT:USDT',12.34)=='12.35'
    actual.fetch_currencies.assert_not_called()
    actual.publicMixGetV2MixMarketContracts.assert_called_once_with({'productType':'USDT-FUTURES'})


@pytest.mark.parametrize('response',[{'code':'00000','data':[]},{'code':'40000','data':[]},
                                    {'code':'00000','data':[{'symbolType':'perpetual','quoteCoin':'USDT','supportMarginCoins':['USDT']}]},None])
def test_bitget_no_stale_or_guessed_fallback(response):
    client=ccxt.bitget();client.publicMixGetV2MixMarketContracts=Mock(return_value=response)
    client.markets={'OLD/USDT:USDT':{'symbol':'OLD/USDT:USDT'}}
    with pytest.raises(ValueError):bitget_usdt_catalogue(client)


def test_bybit_required_linear_catalogue_never_calls_private_currencies_or_options():
    from tests.test_teayu_entry_diagnostics import swap
    client=ccxt.bybit({'apiKey':'fixture','secret':'fixture'})
    client.fetch_future_markets=Mock(return_value=[swap()])
    client.fetch_currencies=Mock(side_effect=AssertionError('private currencies'))
    client.fetch_option_markets=Mock(side_effect=AssertionError('options'))
    owner=BybitFuturesAdapter.__new__(BybitFuturesAdapter);owner.exchange=client
    assert owner.load_instrument_catalogue()['BTC/USDT:USDT']['swap']
    client.fetch_future_markets.assert_called_once_with({'category':'linear'})
    client.fetch_currencies.assert_not_called();client.fetch_option_markets.assert_not_called()


@pytest.mark.parametrize('cls,venue',[(BybitFuturesAdapter,'bybit'),(BitgetFuturesAdapter,'bitget')])
def test_connect_disables_unrelated_dependencies(monkeypatch,cls,venue):
    owner=cls.__new__(cls)
    owner.api_key=owner.secret_key=owner.password='fixture'
    owner.log_event=Mock();owner.load_instrument_catalogue=Mock(return_value={})
    factory=Mock(return_value=SimpleNamespace(load_time_difference=Mock()))
    monkeypatch.setattr(ccxt,venue,factory)
    assert owner.connect()
    cfg=factory.call_args.args[0]
    assert cfg['has']['fetchCurrencies'] is False
    assert cfg['options']['fetchMarkets']['types']==(['linear'] if venue=='bybit' else ['swap'])
    owner.load_instrument_catalogue.assert_called_once()


def test_inactivity_mixed_reasons_heartbeat_recovery_and_pure_snapshot(monkeypatch):
    owner=SimpleNamespace(settings={'paper_trading':True})
    now=[1000.]
    monkeypatch.setattr('trading.operation_evidence.time.time',lambda:now[0])
    @monitored_cycle()
    def cycle(owner,exchange_name):
        record_entry(owner,exchange_name,'hold','',mode='paper')
        record_entry(owner,exchange_name,'skipped','AI 신뢰도 부족',mode='paper')
    for moment in (1000.,1600.,2801.):now[0]=moment;cycle(owner,'okx')
    evidence=snapshot(owner,'okx','paper');before=deepcopy(evidence)
    view=entry_activity(evidence,running=True,now=2802.)
    assert view['status']=='no_recent_entry' and view['no_entry_seconds']==1802
    assert {r['code'] for r in view['recent_reasons']}=={'hold','pre_entry_confidence_low'}
    assert evidence==before
    assert entry_activity(evidence,running=False,now=2802.)['status']=='stopped'
    assert entry_activity(evidence,running=True,now=3802.)['status']=='heartbeat_stale'
    now[0]=2803.;record_entry(owner,'okx','success','',mode='paper')
    recovered=entry_activity(snapshot(owner,'okx','paper'),running=True,now=2804.)
    assert not recovered['attention'] and recovered['recent_reasons']==[]
    assert not snapshot(owner,'okx','live').get('activity')


def test_cycle_reset_discards_late_evidence_and_preserves_original_exception(monkeypatch):
    owner=SimpleNamespace(settings={'paper_trading':True})
    @monitored_cycle('binance')
    def cycle(owner):
        reset(owner,'binance')
        raise RuntimeError('worker failed')
    with pytest.raises(RuntimeError,match='worker failed'):cycle(owner)
    assert not snapshot(owner,'binance','paper').get('activity')
    assert entry_activity({'mode':'learning'},running=True)['status']=='learning'
    assert entry_activity({'mode':'paper'},running=True)['status']=='unobserved'
    assert not entry_activity({'source':'kiwoom','mode':'paper'},running=True)['attention']


def test_short_observation_does_not_claim_long_inactivity_and_reasons_are_bounded(monkeypatch):
    owner=SimpleNamespace(settings={'paper_trading':True})
    monkeypatch.setattr('trading.operation_evidence.time.time',lambda:1000.)
    publish(owner,'upbit','cycle',phase='started')
    publish(owner,'upbit','cycle',phase='returned')
    for _ in range(300):record_entry(owner,'upbit','hold','',mode='paper')
    evidence=snapshot(owner,'upbit','paper')
    assert len(evidence['activity']['recent_reasons'])==128
    assert not entry_activity(evidence,running=True,now=1100.)['attention']


@pytest.mark.parametrize('code',['previous_order_reconciliation_required','available_capital_insufficient',
    'available_capital_reserved_by_other_orders','max_parallel_targets_exceeded','aggregate_loss_cap_exceeded'])
def test_specific_final_reasons_survive_generic_skipped_status_without_raw_errors(code):
    assert decision_code('skipped',f'다중 거래소 기회 정책 차단: {code}:USDT')==code


@pytest.mark.parametrize('base,info,allowed',[('NATGAS',{},False),('XAG',{},False),
    ('UNLISTED_STOCK',{'isRwa':'YES'},False),('BTC',{'isRwa':'NO'},True),('BTC',{},True)])
def test_non_crypto_commodity_and_explicit_rwa_cannot_enter_crypto_candidates(base,info,allowed):
    from trading.market_asset_classifier import is_crypto_derivative_candidate
    assert is_crypto_derivative_candidate(dict(base=base,quote='USDT',active=True,swap=True,info=info)) is allowed


@pytest.mark.parametrize('status,reason,expected',[
    ('strategy_guardrail_blocked','[missing evidence]','strategy_guardrail_blocked'),
    ('profitability_blocked','[sample missing]','profitability_blocked'),
    ('skipped','동적 신뢰도 부족: 0.60 < 0.70','pre_entry_confidence_low'),
    ('skipped','최종 주문 규격 또는 안전 게이트 미통과','order_spec_or_final_safety_blocked'),
    ('skipped','instrument_halted','instrument_halted')])
def test_known_final_status_and_gate_codes_are_not_lost_in_generic_skip(status,reason,expected):
    assert decision_code(status,reason)==expected


def upbit_with_duplicate_ids():
    from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
    owner=UpbitSpotAdapter('','');owner.is_connected=True;owner.log_event=Mock()
    client=ccxt.upbit()
    spot=dict(id='KRW-BTC',symbol='BTC/KRW',type='spot',spot=True,contract=False,
              base='BTC',quote='KRW',active=True,precision={},limits={})
    client.set_markets([spot]);client.markets_by_id['KRW-BTC'].append(dict(spot))
    client.publicGetTicker=Mock(return_value=[dict(market='KRW-BTC',trade_price=100,
        high_price=110,low_price=90,opening_price=95,acc_trade_price_24h=10000,acc_trade_volume_24h=100)])
    owner.exchange=client
    return owner


def test_upbit_duplicate_id_failure_reproduced_and_single_batch_prices_recover():
    owner=upbit_with_duplicate_ids()
    with pytest.raises(ccxt.ArgumentsRequired):owner.exchange.fetch_ticker('BTC/KRW')
    assert owner.get_current_price('KRW-BTC')==100
    assert owner.get_24h_ticker('KRW-BTC')['quoteVolume']==10000
    assert owner.get_24h_tickers(['BTC/KRW'])['BTC/KRW']['last']==100


def test_upbit_recovery_rejects_mismatched_public_quote():
    owner=upbit_with_duplicate_ids()
    owner.exchange.publicGetTicker=Mock(return_value=[dict(market='KRW-ETH',trade_price=999)])
    with pytest.raises(ValueError,match='identity_mismatch'):owner.get_24h_tickers(['BTC/KRW'])
    assert owner.get_current_price('KRW-BTC')==0
