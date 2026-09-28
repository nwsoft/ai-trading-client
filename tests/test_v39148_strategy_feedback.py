"""Replay assumptions and upload contracts; no live accounts or original customer writes."""
import base64
import math
from copy import deepcopy
from unittest.mock import patch

import pytest

from trading.replay_costs import resolve_replay_costs, replay_cost_components, FIELDS
from trading.custom_strategy_validator import run_historical_replay

@pytest.mark.parametrize('venue,fee',[('binance',.0005),('bybit',.00055),('okx',.0005),('bitget',.0006),('upbit',.0005),('bithumb',.0025),('coinone',.0002)])
def test_venue_reference_is_not_account_verified(venue,fee):
    p=resolve_replay_costs({},venue)
    assert p['rates']['buy_fee_rate']==fee
    assert p['account_verified'] is False
    assert p['status']=='estimated'
    assert p['warnings']
    assert p['round_trip_cost_percent']==pytest.approx((fee*2+.0005)*100)

@pytest.mark.parametrize('broker',['kis','kiwoom','shinhan','mirae','koreainvestment','miraeasset'])
@pytest.mark.parametrize('asset',['stock','etf'])
def test_brokers_and_etf_keep_tax_separate(broker,asset):
    p=resolve_replay_costs({},broker,asset)
    assert p['rates']['spread_rate']==0
    assert p['rates']['sell_tax_rate']==(.002 if asset=='stock' else 0)
    assert p['rates']['buy_fee_rate']==.00015
    assert not p['account_verified']

def test_product_override_precedence_and_settings_preserved():
    settings={'ai_custom_validation_costs':{'fee_rate_per_side':.0011,'venues':{'binance':{'fee_rate_per_side':.0007,'products':{'futures':{'buy_fee_rate':.0002}}}}}}
    before=deepcopy(settings)
    p=resolve_replay_costs(settings,'binance',market_type='futures',overrides={'sell_fee_rate':0})
    assert p['rates']['buy_fee_rate']==.0002
    assert p['rates']['sell_fee_rate']==0
    assert p['field_sources']['sell_fee_rate']=='user_run_override'
    assert resolve_replay_costs(settings,'binance',market_type='spot')['rates']['buy_fee_rate']==.0007
    assert resolve_replay_costs({},'binance',market_type='spot')['rates']['buy_fee_rate']==.001
    assert settings==before

@pytest.mark.parametrize('value',[-.001,float('nan'),float('inf'),True,'oops',.051])
def test_invalid_overrides_never_silently_fallback(value):
    with pytest.raises(ValueError):resolve_replay_costs({},'binance',overrides={'buy_fee_rate':value})

@pytest.mark.parametrize('venue,asset,market',[('unknown','crypto',None),('kis','crypto',None),('upbit','stock',None),('upbit','crypto','futures'),('binance','invalid',None)])
def test_mismatched_cost_contract_rejected(venue,asset,market):
    with pytest.raises(ValueError):resolve_replay_costs({},venue,asset,market)

@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_exit_notional_fee_tax_and_results_match(side):
    p=resolve_replay_costs({},'binance',overrides={'buy_fee_rate':.0003,'sell_fee_rate':.0008,'sell_tax_rate':.002})
    original=deepcopy(p)
    rules={'signal_mode':'independent','entry_signal':side,'executable_entry':{'all':[{'field':'price','operator':'gt','value':0}]},'engine_settings':{'_unit':'percent_points','tp_percent':2,'sl_percent':1}}
    rows=[[1700000000000+i*900000,100,103,97,100,20,1700000000000+(i+1)*900000-1] for i in range(150)]
    result=run_historical_replay(rules,rows,cost_profile=p)
    assert result['trades']
    for t in result['trades']:
        components=replay_cost_components(p,side,t['exit_price']/t['entry_price'])
        assert t['cost_percent']==pytest.approx(sum(components.values())*100)
        assert t['gross_pnl_percent']-t['cost_percent']==pytest.approx(t['net_pnl_percent'])
        assert t['cost_components_percent']['tax']==pytest.approx(components['tax']*100)
    assert result['total_cost_percent']==pytest.approx(sum(t['cost_percent'] for t in result['trades']))
    assert p==original
    assert result['cost_profile']==p

def test_zero_cost_explicit_override():
    assert resolve_replay_costs({},'coinone',overrides=dict.fromkeys(FIELDS,0))['round_trip_cost_percent']==0

def test_real_upload_service_repeat_bundle_and_cleanup(tmp_path):
    from web_platform import application_services as m
    text='15분봉 RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장.'
    payload={'source_kind':'auto','value':'selected-files','files':[{'name':'한글 전략.txt','value':base64.b64encode(text.encode()).decode()}]}
    with patch.object(m,'get_app_data_dir',lambda:str(tmp_path)),patch.object(m,'set_current_user_account',lambda _:None),patch.object(m,'load_settings',lambda **k:{}):
        s=m.ApplicationServices(account='fixture')
        first=s.analyze_strategy_source(**payload)
        second=s.analyze_strategy_source(**payload)
    assert first['rules']['executable_entry']==second['rules']['executable_entry']
    assert first['source_manifest'][0]['included_characters']>0
    assert not list(tmp_path.rglob('*.txt'))

def test_web_preview_uses_same_resolver(monkeypatch):
    from web_platform import application_services as m
    settings={'ai_custom_validation_costs':{'venues':{'okx':{'buy_fee_rate':.0001}}}}
    monkeypatch.setattr(m,'load_settings',lambda **k:settings)
    assert m.ApplicationServices.preview_strategy_replay_costs(None,source='okx')==resolve_replay_costs(settings,'okx')

@pytest.mark.parametrize('override',[{'buy_fee_rate':False},{'buy_fee_rate':float('nan')},{'buy_fee_rate':-.1},{'unknown':0}])
def test_gateway_cost_contract_rejects_invalid_input(override):
    from web_platform.contracts import StrategyHistoricalValidationContract
    with pytest.raises(ValueError):
        StrategyHistoricalValidationContract(scope='binance',strategy_key='k',version_id='v',cost_overrides=override)

def test_crypto_legacy_cost_does_not_override_stock_policy():
    settings={'ai_custom_validation_costs':{'fee_rate_per_side':.001}}
    assert resolve_replay_costs(settings,'kis','stock')['rates']['buy_fee_rate']==.00015
