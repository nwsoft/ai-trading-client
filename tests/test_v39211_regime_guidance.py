"""Customer regime question: real help route and actual detector differences.

Synthetic candles/quotes only. No customer files, providers, orders or delivery.
"""
from types import SimpleNamespace
from unittest.mock import Mock
from threading import RLock
import pytest
from config.assistant_support_knowledge import support_topic
from trading.market_selection_runtime import RegimeStabilizer
from trading.stock_analysis_service import StockAnalysisService
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader
from web_platform.application_services import ApplicationServices

QUESTION = '코인과 주식에 시장국면 인식이 좀 다를까요? 주식의 경우 시장국면이 빠르게 바뀌는거 같은데 코인은 보통 일반 국면이더라고요. 국면 확정에 로직적 다른점이 있는지 궁금합니다'
CRYPTO = ['binance', 'okx', 'bybit', 'bitget', 'upbit', 'bithumb', 'coinone']
BROKERS = ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']

@pytest.mark.parametrize('service', ['blockchain','stock','portfolio','ai_analyst','ai_custom','settings','personal_finance'])
@pytest.mark.parametrize('locale', ['ko','en'])
def test_customer_question_gets_code_grounded_local_answer_without_runtime(service, locale, monkeypatch):
    obj = ApplicationServices.__new__(ApplicationServices)
    obj.account = 'synthetic-regime-question'
    obj._audit = Mock()
    obj._assistant_operational_context = Mock(side_effect=AssertionError('generic mechanics must not read private runtime'))
    obj.interactive_ai = SimpleNamespace(ask=Mock(side_effect=AssertionError('no provider')))
    monkeypatch.setattr('web_platform.application_services.load_settings', lambda **kw: {'api_key':'NEVER_ECHO'})
    result = obj.ask_assistant(question=QUESTION, service=service, explanation_level='standard', output_locale=locale)
    assert result['guide_topic'] == 'market_regime_comparison'
    assert result['provider_called'] is False
    assert 'NEVER_ECHO' not in result['answer']
    for evidence in ('300', '600', 'BTC', 'ETH', '005930', '005490'):
        assert evidence in result['answer']
    obj.interactive_ai.ask.assert_not_called()
    obj._assistant_operational_context.assert_not_called()

@pytest.mark.parametrize('question', [
    '코인은 왜 일반 국면인가요?', '주식과 코인 국면 확정 로직 차이',
    '국면 확정에 로직적 다른점이 있나요?', 'How do crypto and stock market regime detection differ?',
])
def test_natural_question_variants(question):
    assert support_topic(question).key == 'market_regime_comparison'

def test_companion_uses_same_guide_without_inventing_live_evidence():
    from web_platform.companion import query
    result = query(QUESTION, {}, {})
    assert result['guide_topic'] == 'market_regime_comparison'
    assert result['evidence']['observed_at'] is None
    assert result['evidence']['freshness'] == 'unknown_time'
    assert result['read_only'] and not result['provider_called'] and not result['orders_submitted']
    assert {a['service'] for a in result['actions']} == {'blockchain','stock'}

def test_specific_no_trade_question_keeps_observed_diagnosis():
    from web_platform.companion import query
    card = {'id':'entry:okx','section':'trading','title':'OKX PAPER','detail':'시세 실패', 'next':'연결 확인'}
    result = query('OKX 일반 국면인데 왜 거래가 없나요?', {'cards':[card]}, {})
    assert result['status'] == 'observed'
    assert '시세 실패' in result['answer']
    assert 'guide_topic' not in result

@pytest.mark.parametrize('endpoint,locale', [('assistant/ask','ko'),('assistant/ask','en'),('companion/query','ko')])
def test_authenticated_gateway_returns_regime_guide_and_preserves_files(endpoint, locale, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.gateway import create_gateway_app
    obj = ApplicationServices.__new__(ApplicationServices)
    obj.account = 'synthetic-regime-gateway'; obj.data_dir = tmp_path
    obj._lock = RLock(); obj._insurance_workspace = None; obj._latest_account_snapshot = None
    obj.runtime_bridge = SimpleNamespace(operation_overview_snapshot=lambda **kw:{})
    obj.runtime_snapshot = lambda:{}; obj._audit = Mock()
    obj.interactive_ai = SimpleNamespace(ask=Mock(side_effect=AssertionError('no provider')))
    monkeypatch.setattr('web_platform.application_services.load_settings', lambda **kw:{})
    sentinel = tmp_path/'original.txt'; sentinel.write_text('synthetic original')
    before = {p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    token = 'synthetic-regime-review-token-long-enough'
    headers = {'Authorization':'Bearer '+token,'X-NoahAI-Intent':'confirmed','X-NoahAI-Locale':locale}
    with TestClient(create_gateway_app(token=token, application_services=obj)) as client:
        response = client.post('/api/v1/'+endpoint, headers=headers, json={'question':QUESTION,'service':'stock'})
    assert response.status_code == 200
    result = response.json()
    assert result['guide_topic'] == 'market_regime_comparison'
    assert result['provider_called'] is False
    assert '600' in result['answer'] and '005930' in result['answer']
    if endpoint.startswith('companion'):
        assert response.headers['cache-control'] == 'no-store'
    assert {p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before

def candles(total_change, volume_spike):
    return [[i, 100, 100, 100, 100*(1+total_change*i/19),
             500 if volume_spike and i == 19 else 100] for i in range(20)]

@pytest.mark.parametrize('venue', CRYPTO)
@pytest.mark.parametrize('change,volume_spike,binance_expected,unified_expected', [
    (0, False, 'normal', 'normal'),
    (.08, False, 'normal', 'normal'),
    (.08, True, 'bull', 'bull'),
    (-.08, True, 'bear', 'bear'),
    (.30, False, 'volatile', 'volatile'),
    # Same 5% whole-series move: Binance's final-five threshold passes;
    # Unified's final-ten 3% threshold fails. 30-minute move stays below 2%.
    (.05, True, 'bull', 'normal'),
])
def test_actual_crypto_detectors_distinguish_volume_and_venue_thresholds(venue, change, volume_spike, binance_expected, unified_expected):
    owner = (Trader if venue == 'binance' else UnifiedTrader).__new__(Trader if venue == 'binance' else UnifiedTrader)
    owner.settings = {}; owner.logger = Mock(); owner.log_event = Mock()
    rows = candles(change, volume_spike)
    if venue == 'binance':
        owner.binance_client = SimpleNamespace(get_klines=lambda *a, **kw: rows)
        actual = owner._analyze_market_regime_binance_fast()
        assert actual == binance_expected
    else:
        owner.exchange_manager = SimpleNamespace(get_klines=lambda *a, **kw: rows)
        actual = owner._compute_current_market_conditions_unified_fast(venue, 'BTC/KRW' if venue in {'upbit','bithumb','coinone'} else 'BTCUSDT')
        assert actual == unified_expected

@pytest.mark.parametrize('broker', BROKERS)
def test_stock_proxy_changes_immediately_after_cache_expires(broker, monkeypatch):
    owner = StockAnalysisService.__new__(StockAnalysisService)
    clock = [1000.0]; change = [1.49]
    owner.adapter = SimpleNamespace(get_realtime_price=lambda symbol: {'change_rate':change[0]})
    owner.broker_name = broker; owner.settings = {'paper_trading':True}
    owner._active_execution_mode = 'paper'; owner._regime_cache = None
    owner._regime_cache_time = 0; owner._REGIME_CACHE_TTL = 300
    owner.log_event = Mock(); owner._emit_analysis_log = Mock(); owner._persist_xai_decision = Mock()
    send = Mock(return_value=True)
    monkeypatch.setattr('trading.stock_analysis_service.pytime.time', lambda:clock[0])
    monkeypatch.setattr('trading.notifications.publish_market_regime_change', send)
    assert owner.get_market_regime() == 'volatile'
    change[0] = 1.51; clock[0] += 299
    assert owner.get_market_regime() == 'volatile'  # existing cache
    values = []
    for pct in (1.51, 1.49, 1.51):
        clock[0] += 301; change[0] = pct
        values.append(owner.get_market_regime())
    assert values == ['bull','volatile','bull']
    assert owner.adapter._regime_data_reason == 'proxy_stock_quotes'
    assert send.call_count == 3

@pytest.mark.parametrize('venue', CRYPTO)
def test_crypto_confirmation_suppresses_alternating_observations(venue):
    state = RegimeStabilizer()
    assert state.observe(venue, 'normal', now=1000) == ('normal',False)
    for i, observed in enumerate(('bull','normal','bull','normal'),1):
        assert state.observe(venue, observed, now=1000+301*i) == ('normal',False)
    assert state.observe(venue,'bull',now=2600) == ('normal',False)
    assert state.observe(venue,'bull',now=2901) == ('bull',True)
