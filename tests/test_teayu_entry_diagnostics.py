"""Customer failure regressions: no credentials, account APIs or real orders."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import json

import ccxt
import pytest

from trading import instrument_eligibility as guard
from trading.entry_diagnostics import entry_health, record_entry
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
from trading.operation_evidence import publish, snapshot, reset
from trading.paper_capital import observe_paper_capital
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from web_platform.runtime_bridge import HeadlessRuntimeBridge


def swap():
    return {'symbol':'BTC/USDT:USDT','id':'BTC-USDT-SWAP','base':'BTC','quote':'USDT',
            'settle':'USDT','active':True,'swap':True,'spot':False,'future':False,
            'option':False,'linear':True,'inverse':False,'contract':True,'type':'swap',
            'precision':{},'limits':{},'contractSize':.01}


def test_okx_current_swap_refresh_survives_private_currency_and_option_failure():
    # Exercise the actual installed CCXT load_markets dependency chain.
    raw = ccxt.okx({'apiKey':'fixture','secret':'fixture','password':'fixture'})
    raw.fetch_currencies = Mock(side_effect=ccxt.AuthenticationError('private fixture'))
    raw.fetch_markets_by_type = Mock(side_effect=lambda kind, *a: [swap()] if kind=='swap'
                                     else (_ for _ in ()).throw(ccxt.ExchangeNotAvailable('unrelated option')))
    with pytest.raises(ccxt.AuthenticationError):
        raw.load_markets(reload=True)
    adapter = OkxFuturesAdapter('fixture','fixture','fixture')
    adapter.exchange = raw
    assert guard.eligibility(adapter, 'okx', 'BTCUSDT')['allowed']
    raw.fetch_markets_by_type.assert_called_once_with('swap')
    assert raw.fetch_currencies.call_count == 1  # Old failing path only.


def test_okx_connect_loads_public_swap_metadata_without_funding_api(monkeypatch):
    raw = ccxt.okx()
    raw.fetch_currencies = Mock(side_effect=AssertionError('private API forbidden'))
    raw.fetch_markets_by_type = Mock(side_effect=lambda kind, *a: [swap()] if kind=='swap'
                                     else (_ for _ in ()).throw(AssertionError('unrelated market')))
    raw.fetch_account_configuration = Mock(return_value={})
    def create(config):
        raw.options.update(config['options']); raw.has.update(config['has']); return raw
    monkeypatch.setattr(ccxt, 'okx', create)
    adapter = OkxFuturesAdapter('fixture','fixture','fixture'); adapter.log_event = Mock()
    assert adapter.connect()
    raw.fetch_currencies.assert_not_called()
    raw.fetch_markets_by_type.assert_called_once_with('swap')


def test_transient_refresh_retries_current_data_and_never_reuses_old_markets(monkeypatch):
    raw = SimpleNamespace(markets={'OLD/USDT:USDT':dict(swap(),symbol='OLD/USDT:USDT')})
    raw.load_markets = Mock(side_effect=[ccxt.RequestTimeout('private query'), {swap()['symbol']:swap()}])
    owner = SimpleNamespace(exchange=raw)
    assert guard.eligibility(owner, 'bybit', 'BTCUSDT')['allowed']
    assert raw.load_markets.call_count == 2
    assert not guard.eligibility(owner, 'bybit', 'OLDUSDT')['allowed']
    clock = [100.]
    monkeypatch.setattr(guard.time, 'monotonic', lambda:clock[0])
    owner = SimpleNamespace(exchange=raw)
    raw.load_markets.reset_mock(side_effect=True)
    raw.load_markets.side_effect = ccxt.RequestTimeout('private query')
    assert not guard.eligibility(owner, 'bybit', 'BTCUSDT')['allowed']
    result = guard.catalogue(owner,'bybit')
    assert result['attempts']==2 and result['error_kind']=='network_timeout'
    assert 'private query' not in json.dumps(result)
    assert raw.load_markets.call_count==2
    clock[0] += 16
    raw.load_markets.side_effect = None; raw.load_markets.return_value = {swap()['symbol']:swap()}
    assert guard.eligibility(owner,'bybit','BTCUSDT')['allowed']


def test_authentication_failure_is_not_retried_or_presented_as_timeout():
    raw = SimpleNamespace(load_markets=Mock(side_effect=ccxt.AuthenticationError('secret fixture')))
    result = guard.catalogue(SimpleNamespace(exchange=raw),'bybit')
    assert result['error_kind']=='authentication' and result['attempts']==1
    assert result['rows']=={} and 'secret fixture' not in json.dumps(result)


def pre_entry_owner(cls):
    owner = cls.__new__(cls)
    owner.settings = {'paper_trading':True}; owner.logger = Mock(); owner.log_event = Mock()
    owner._log_trade_event = Mock(); owner._is_verbose_logging = lambda:False
    owner.recorder = SimpleNamespace(count_closed_trades=lambda **kw:500)
    owner.risk_manager = SimpleNamespace(coin_trade_history={})
    owner.binance_client = SimpleNamespace()
    owner._analyze_recent_trading_patterns = lambda *a:dict(recent_trades=30,loss_rate=55.,data_insufficient=False,used_defaults=False)
    owner._analyze_recent_trading_patterns_unified = lambda *a:owner._analyze_recent_trading_patterns()
    owner._evaluate_current_market_conditions = lambda *a:{'volatility_suitable':True}
    owner._evaluate_current_market_conditions_unified = lambda *a:owner._evaluate_current_market_conditions()
    owner._ai_validate_entry_conditions = lambda *a:{'confidence':.65}
    owner._ai_validate_entry_conditions_unified = lambda *a:owner._ai_validate_entry_conditions()
    owner._get_dynamic_entry_thresholds = lambda *a:dict(max_loss_rate=60.,min_trades_history=0,min_ai_confidence=.7)
    owner._get_dynamic_entry_thresholds_unified = lambda *a:owner._get_dynamic_entry_thresholds()
    owner._calculate_dynamic_confidence_threshold = lambda *a:.7
    return owner


@pytest.mark.parametrize('cls,venue',[(Trader,'binance'),(UnifiedTrader,'bybit')])
def test_exact_failed_gate_reported_instead_of_hardcoded_50_percent_loss(cls,venue):
    owner = pre_entry_owner(cls)
    result = (owner._perform_pre_entry_analysis('BTCUSDT',{}) if cls is Trader else
              owner._perform_pre_entry_analysis_unified(venue,'BTCUSDT',{}))
    assert not result['proceed']
    assert result['reason']=='AI 신뢰도 부족 (0.65 < 0.70)'
    row = snapshot(owner,venue,'paper')['pre_entry']
    assert row['required_confidence']==.7 and row['loss_rate']==55.


def test_unified_neutral_missing_history_cannot_become_a_measured_loss_stop():
    owner = pre_entry_owner(UnifiedTrader)
    owner._analyze_recent_trading_patterns_unified = lambda *a:dict(recent_trades=0,loss_rate=50.,used_defaults=True,data_insufficient=True)
    owner._get_dynamic_entry_thresholds_unified = lambda *a:dict(max_loss_rate=50.,min_trades_history=0,min_ai_confidence=.4)
    result = owner._perform_pre_entry_analysis_unified('bybit','BTCUSDT',{})
    assert result['proceed']
    assert snapshot(owner,'bybit','paper')['pre_entry']['loss_rate'] is None
    owner._get_dynamic_entry_thresholds_unified = lambda *a:dict(max_loss_rate=50.,min_trades_history=5,min_ai_confidence=.4)
    assert not owner._perform_pre_entry_analysis_unified('bybit','BTCUSDT',{})['proceed']


def test_unverified_old_losses_do_not_increase_confidence_threshold():
    owner = Trader.__new__(Trader); owner.logger=Mock()
    owner.analyzer=SimpleNamespace(get_user_signal_threshold=lambda:68,
        _analyze_current_market_conditions=lambda:{'level':'NORMAL'})
    owner.risk_manager=SimpleNamespace(coin_trade_history={},coin_consecutive_wins={},coin_consecutive_losses={})
    owner.recorder=SimpleNamespace(get_recent_trades=lambda **kw:[
        dict(exchange='binance',execution_mode='live',pnl_percent=-10,exit_time='old') for _ in range(20)])
    assert owner._calculate_dynamic_confidence_threshold('BTCUSDT',{})==pytest.approx(.68)


def test_measured_partial_history_retains_configured_loss_guard():
    owner=pre_entry_owner(UnifiedTrader)
    owner._analyze_recent_trading_patterns_unified=lambda *a:dict(
        recent_trades=5,loss_rate=80.,used_defaults=False,data_insufficient=True)
    owner._get_dynamic_entry_thresholds_unified=lambda *a:dict(
        max_loss_rate=60.,min_trades_history=0,min_ai_confidence=.4)
    result=owner._perform_pre_entry_analysis_unified('bybit','BTCUSDT',{})
    assert not result['proceed'] and '80.0% >= 60.0%' in result['reason']


def test_funds_diagnosed_before_signals_without_creating_session_or_changing_ledger(tmp_path):
    ledger=tmp_path/'strategy_paper_outcomes.jsonl'
    original=json.dumps(dict(exchange='binance',execution_mode='paper',net_pnl=10))+'\n'
    ledger.write_text(original)
    owner=SimpleNamespace(settings={'paper_trading':True},recorder=SimpleNamespace(db_path=str(tmp_path/'trading.db')))
    observe_paper_capital(owner,venue='binance',positions={})
    funds=owner._last_capital_evidence[('binance','paper')]
    assert funds['reason']=='paper_ledger_currency_unverified'
    assert funds['realized_net_pnl'] is None
    assert ledger.read_text()==original and not (tmp_path/'paper_funds_sessions.json').exists()


def test_final_entry_block_survives_regime_heartbeat_and_cannot_cross_modes_or_reset():
    owner=SimpleNamespace(settings={'paper_trading':True})
    for _ in range(3):record_entry(owner,'okx','skipped','AI 신뢰도 부족 (0.65 < 0.70)',mode='paper')
    publish(owner,'okx','runtime',code='regime_unchanged')
    row=snapshot(owner,'okx','paper')
    assert entry_health(row)['code']=='pre_entry_confidence_low'
    assert row['entry']['consecutive_count']==3
    assert not snapshot(owner,'okx','live').get('entry')
    epoch=0;reset(owner,'okx')
    record_entry(owner,'okx','error','private provider query',mode='paper',expected_generation=epoch)
    assert not snapshot(owner,'okx','paper').get('entry')


def test_read_only_dashboard_prioritizes_wallet_failure_over_candidate_pass():
    owner=SimpleNamespace(settings={'paper_trading':True},_last_capital_evidence={
        ('bybit','paper'):{'capital_basis':'paper_funds_unverified','reason':'paper_ledger_currency_unverified','observed_at':100.}})
    publish(owner,'bybit','candidate',mode='paper',allowed=True,symbol='BTCUSDT')
    bridge=HeadlessRuntimeBridge(account='fixture')
    bridge._app=SimpleNamespace(settings={'paper_trading':True},unified_trader=owner)
    before=deepcopy(vars(owner))
    result=bridge.operation_summary_snapshot(source='bybit')
    assert result['entry_health']['code']=='paper_ledger_currency_unverified'
    assert result['entry_health']['blocked']
    assert vars(owner)==before
    assert bridge.operation_summary_snapshot(source='coinone')['entry_health']['code']=='unavailable'


def test_new_paper_baseline_supersedes_old_funds_rejection_without_claiming_started():
    result=entry_health({'entry':{'code':'paper_funds_unverified','observed_at':100},
        'capital':{'paper_session_id':'fixture','capital_basis':'paper_reconciled_funds','observed_at':101}})
    assert result['code']=='paper_session_ready' and not result['blocked']
    assert result['last_entry_at'] is None
