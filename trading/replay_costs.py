"""Replay assumptions, not account-confirmed fees or LIVE execution policy.

Precedence: reference -> legacy global -> venue -> venue/product -> run override.
Every result embeds the complete profile; existing evidence is never rewritten.
"""
import math
from copy import deepcopy

REFERENCES = {
    'binance': (.0005, 'https://www.binance.com/en/support/faq/detail/360033544231'),
    'okx': (.0005, 'https://www.okx.com/help/how-to-calculate-the-contract-transaction-fee'),
    'bybit': (.00055, 'https://www.bybit.com/en/help-center/article/Trading-Fee-Structure'),
    'bitget': (.0006, 'https://www.bitget.com/support/articles/12560603817155'),
    'upbit': (.0005, 'https://support.upbit.com/hc/ko/articles/36042119755929'),
    'bithumb': (.0025, 'https://feed.bithumb.com/notice/1641427'),
    'coinone': (.0002, 'https://coinone.co.kr/support/fee-guide'),
}
BROKERS={'kis','kiwoom','shinhan','mirae'}
FIELDS=('buy_fee_rate','sell_fee_rate','buy_slippage_rate','sell_slippage_rate','spread_rate','sell_tax_rate')

def resolve_replay_costs(settings, venue, asset_class='crypto', market_type=None, overrides=None):
    if asset_class not in {'crypto','stock','etf'}:raise ValueError('지원하지 않는 비용 자산입니다.')
    venue={'koreainvestment':'kis','miraeasset':'mirae'}.get(str(venue).lower(),str(venue).lower())
    stock=asset_class in {'stock','etf'}
    if venue not in (BROKERS if stock else REFERENCES):raise ValueError('지원하지 않는 비용 기관입니다.')
    product=asset_class if stock else (market_type or ('spot' if venue in {'upbit','bithumb','coinone'} else 'futures'))
    if not stock and product not in {'spot','futures'}:raise ValueError('지원하지 않는 비용 상품입니다.')
    if venue in {'upbit','bithumb','coinone'} and product!='spot':raise ValueError('현물 기관에 선물 비용을 적용할 수 없습니다.')
    warnings=['추정 비용입니다. 계정 등급·할인·주문 역할·거래 시점에 따라 실제 비용이 다릅니다.']
    if stock:
        from .stock_paper_valuation import normalize_stock_paper_cost_policy
        policy=normalize_stock_paper_cost_policy((settings or {}).get('stock_auto_trading',{}))
        rates={'buy_fee_rate':policy['buy_commission_rate'],'sell_fee_rate':policy['sell_commission_rate'],
               'buy_slippage_rate':policy['buy_slippage_rate'],'sell_slippage_rate':policy['sell_slippage_rate'],
               'sell_tax_rate':policy['etf_sell_tax_rate' if product=='etf' else 'stock_sell_tax_rate'],'spread_rate':0.0}
        reference='existing_stock_simulation_policy';basis=policy['cost_source']
        warnings.append('증권사·계좌·시장별 수수료와 세금을 확인하세요. 증권사 확정 요율을 조회한 값이 아닙니다.')
    else:
        fee,reference=REFERENCES[venue]
        if product=='spot' and venue not in {'upbit','bithumb','coinone'}:fee=.001
        rates={'buy_fee_rate':fee,'sell_fee_rate':fee,'buy_slippage_rate':.0002,
               'sell_slippage_rate':.0002,'spread_rate':.0001,'sell_tax_rate':0.0}
        basis='reference_estimate'
        if venue=='coinone':warnings.append('Open API 비이벤트 기준 0.02% 가정입니다. 한시적 0%는 자동 적용하지 않으며 실제 적용률을 입력할 수 있습니다.')
        if venue=='bithumb':warnings.append('쿠폰 미적용 0.25% 보수적 가정입니다. 계정 쿠폰·API 실제 적용률을 확인해 입력하세요.')
    sources={k:basis for k in FIELDS}
    root=dict((settings or {}).get('ai_custom_validation_costs') or {})
    venue_values=dict((root.get('venues') or {}).get(venue) or {})
    product_values=dict((venue_values.get('products') or {}).get(product) or {})
    def apply(values,origin):
        translated={k:values[k] for k in FIELDS if k in values}
        for old,keys,multiplier in [('fee_rate_per_side',('buy_fee_rate','sell_fee_rate'),1),
                                   ('slippage_bps_per_side',('buy_slippage_rate','sell_slippage_rate'),.0001),
                                   ('spread_bps_round_trip',('spread_rate',),.0001)]:
            if old in values:
                if isinstance(values[old],bool):raise ValueError('비용 숫자 형식 오류: '+old)
                try:value=float(values[old])*multiplier
                except (TypeError,ValueError):raise ValueError('비용은 숫자여야 합니다: '+old) from None
                for key in keys:translated.setdefault(key,value)
        for key,raw in translated.items():
            if isinstance(raw,bool):raise ValueError('비용 숫자 형식 오류: '+key)
            try:value=float(raw)
            except (TypeError,ValueError):raise ValueError('비용은 숫자여야 합니다: '+key) from None
            if not math.isfinite(value) or not 0<=value<=.05:raise ValueError('비용은 편도 0~5% 범위여야 합니다: '+key)
            rates[key]=value;sources[key]=origin
    if not stock:apply(root,'legacy_global_setting')
    apply(venue_values,'venue_setting');apply(product_values,'venue_product_setting')
    if overrides is not None:
        if not isinstance(overrides,dict) or set(overrides)-set(FIELDS):raise ValueError('지원하지 않는 비용 항목입니다.')
        apply(overrides,'user_run_override')
    if any(not math.isfinite(v) or not 0<=v<=.05 for v in rates.values()):
        raise ValueError('저장된 비용 가정이 유효하지 않습니다. 기관별 비용 설정을 확인하세요.')
    return {'schema_version':1,'venue':venue,'product':product,'rates':deepcopy(rates),'field_sources':sources,
            'status':'estimated','account_verified':False,'reference_url':reference,'reference_checked_on':'2026-09-27',
            'round_trip_cost_percent':round(sum(rates.values())*100,6),
            'round_trip_fee_percent':round((rates['buy_fee_rate']+rates['sell_fee_rate'])*100,6),
            'warnings':warnings,'funding':'not_modelled','basis':'equal_entry_exit_notional_estimate'}

def replay_cost_components(profile, side, exit_ratio=1.0):
    r=profile['rates'];buy=1.0 if side=='LONG' else exit_ratio;sell=exit_ratio if side=='LONG' else 1.0
    return {'fee':buy*r['buy_fee_rate']+sell*r['sell_fee_rate'],
            'slippage':buy*r['buy_slippage_rate']+sell*r['sell_slippage_rate'],
            'spread':r['spread_rate'],'tax':sell*r['sell_tax_rate']}
