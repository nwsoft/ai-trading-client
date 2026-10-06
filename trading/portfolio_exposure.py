"""Provider-observed gross exposure. Never net opposite sides or invent FX rates."""
from __future__ import annotations
from collections.abc import Mapping
import math
import time

VENUES = ('binance', 'bybit', 'okx', 'bitget', 'upbit', 'bithumb', 'coinone', 'kiwoom', 'shinhan', 'mirae', 'kis')


def number(value, *, positive=False):
    if value is None or isinstance(value, bool):
        raise ValueError('exposure_number_unverified')
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError('exposure_number_unverified')
    return result


def normalize_exposure_policy(raw):
    from .strategy_scope import canonical_venue
    raw = dict(raw or {})
    venues = raw.get('venues') or []
    if not isinstance(venues, list): venues = []
    venues = list(dict.fromkeys(canonical_venue(str(v)) for v in venues))
    def limit(key):
        try: return min(1e15, number(raw.get(key, 0)))
        except (TypeError, ValueError, OverflowError): return None
    return {'enabled': raw.get('enabled') is True, 'venues': venues,
            'max_gross_by_currency': {'KRW': limit('max_gross_krw'), 'USDT': limit('max_gross_usdt')},
            'max_reference_gross': limit('max_reference_gross'),
            'reference_currency': str(raw.get('reference_currency') or 'KRW').upper(),
            'fx_venue': canonical_venue(str(raw.get('fx_venue') or 'upbit')),
            'max_age_sec': 60}


def normalize_exposure_snapshot(raw, *, now):
    """Persist only the finite evidence contract, never provider payloads/secrets."""
    invalid = {'status':'unverified', 'started_at':now, 'checked_at':now,
               'gross_by_currency':None, 'reason':'exposure_provider_unverified', 'fx':None}
    try:
        if not isinstance(raw, Mapping): return invalid
        started, checked = number(raw.get('started_at'), positive=True), number(raw.get('checked_at'), positive=True)
        if not started <= checked <= now or now-checked > 60: return invalid
        if raw.get('status') != 'verified': return {**invalid, 'started_at':started, 'checked_at':checked}
        gross = raw.get('gross_by_currency')
        if not isinstance(gross, dict) or not gross or any(k not in ('KRW','USDT') for k in gross): return invalid
        clean = {'status':'verified','started_at':started,'checked_at':checked,
                 'gross_by_currency':{k:number(v) for k,v in gross.items()}, 'fx':None}
        fx = raw.get('fx')
        if fx is not None:
            if not isinstance(fx, dict) or fx.get('base') != 'USDT' or fx.get('quote') != 'KRW': return invalid
            stamp = number(fx.get('observed_at'), positive=True)
            if not 0 <= now-stamp <= 60 or fx.get('source') not in {v+':USDT/KRW' for v in ('upbit','bithumb','coinone')}: return invalid
            clean['fx'] = {'base':'USDT','quote':'KRW','rate':number(fx.get('rate'), positive=True),
                           'observed_at':stamp, 'source':fx['source']}
        return clean
    except (TypeError, ValueError, OverflowError): return invalid


def _get(row, key):
    return row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)


def position_gross(rows, *, venue, paper=False):
    """Sum every reported position, including positions the app does not own."""
    if not isinstance(rows, list) or len(rows) > 1024:
        raise ValueError('exposure_positions_unverified')
    quote = 'USDT' if venue in VENUES[:4] else 'KRW'
    gross = 0.0
    for row in rows:
        symbol = _get(row, 'symbol') or _get(row, 'code')
        if not symbol: raise ValueError('exposure_identity_unverified')
        if paper:
            if str(_get(row, 'execution_mode') or '').lower() != 'paper':
                raise ValueError('exposure_mode_unverified')
            qty, price = number(_get(row, 'quantity'), positive=True), number(_get(row, 'entry_price'), positive=True)
            evidence = _get(row, 'entry_evidence') or {}
            contract = (evidence.get('position_sizing') or {}).get('contract_size')
            multiplier = number(contract if venue in ('bybit','okx','bitget') else 1, positive=True)
        elif venue == 'binance':
            if not str(symbol).upper().endswith('USDT'): raise ValueError('exposure_currency_unverified')
            qty, price, multiplier = number(_get(row, 'size'), positive=True), number(_get(row, 'mark_price'), positive=True), 1.0
        elif venue in ('bybit', 'okx', 'bitget'):
            if '/USDT' not in str(symbol).upper() or _get(row, 'linear') is not True:
                raise ValueError('exposure_contract_unverified')
            qty = number(_get(row, 'size'), positive=True)
            price = number(_get(row, 'mark_price'), positive=True)
            multiplier = number(_get(row, 'contract_size'), positive=True)
        else:
            qty, price, multiplier = number(_get(row, 'quantity'), positive=True), number(_get(row, 'current_price'), positive=True), 1.0
        gross += qty * price * multiplier
    return {quote: number(gross)}


def collect_exposure(owner, *, venue, mode, policy):
    """Only an explicitly enabled LIVE guard reads private provider positions."""
    from .strategy_scope import canonical_venue
    venue = canonical_venue(venue)
    config = normalize_exposure_policy(policy)
    mode = str(getattr(mode, 'value', mode)).lower()
    mode = {'live_api':'live','mock':'paper'}.get(mode,mode)
    if not config['enabled'] or mode == 'learning': return None
    started = time.time()
    result = {'status': 'unverified', 'started_at': started, 'checked_at': started,
              'gross_by_currency': None, 'fx': None, 'reason': 'exposure_provider_unverified'}
    try:
        if mode == 'paper':
            if venue == 'binance': store = getattr(owner, 'paper_active_positions', {})
            elif venue in ('upbit','bithumb','coinone','bybit','okx','bitget'):
                store = (getattr(owner, 'paper_positions', {}) or {}).get(venue, {})
            else: store = owner._paper_positions()
            result['gross_by_currency'] = position_gross(list(store.values()), venue=venue, paper=True)
            result['basis'] = 'paper_entry_gross_not_market_value'
            if venue == config['fx_venue'] and config['max_reference_gross']:
                adapter = owner.get_exchange_client(venue)
                ticker = adapter.exchange.fetch_ticker('USDT/KRW')
                stamp = number(ticker.get('timestamp'), positive=True) / 1000
                if not 0 <= time.time()-stamp <= 60: raise ValueError('exposure_fx_stale')
                result['fx'] = {'base':'USDT','quote':'KRW','rate':number(ticker.get('last'), positive=True),
                                'observed_at':stamp,'source':venue + ':USDT/KRW'}
        elif mode == 'live':
            adapter = owner.binance_client if venue == 'binance' else owner.get_exchange_client(venue) if venue in VENUES[1:7] else owner.adapter
            if venue in ('upbit','bithumb','coinone'):
                if not (adapter.is_connected and adapter.api_key and adapter.secret_key): raise ValueError('exposure_provider_unverified')
                raw = adapter.exchange.fetch_balance()
                totals = raw.get('total') if isinstance(raw, dict) else None
                if not isinstance(totals, dict) or not totals: raise ValueError('exposure_holdings_unverified')
                holdings = [(str(k).upper(), number(v)) for k,v in totals.items()]
                holdings = [(k,v) for k,v in holdings if v > 0 and k != 'KRW']
                if len(holdings) > 32: raise ValueError('exposure_valuation_budget')
                gross = 0.0
                budget_started = time.monotonic()
                for asset, qty in holdings:
                    if time.monotonic()-budget_started > 15: raise ValueError('exposure_valuation_budget')
                    pair = asset + '/KRW'
                    market = (adapter.exchange.markets or {}).get(pair)
                    if not market: raise ValueError('exposure_market_unverified')
                    ticker = adapter.exchange.fetch_ticker(pair)
                    stamp = number(ticker.get('timestamp'), positive=True) / 1000
                    if not 0 <= time.time() - stamp <= 300: raise ValueError('exposure_price_stale')
                    gross += qty * number(ticker.get('last'), positive=True)
                result['gross_by_currency'] = {'KRW': number(gross)}
                if venue == config['fx_venue'] and config['max_reference_gross']:
                    ticker = adapter.exchange.fetch_ticker('USDT/KRW')
                    stamp = number(ticker.get('timestamp'), positive=True) / 1000
                    if not 0 <= time.time() - stamp <= 60: raise ValueError('exposure_fx_stale')
                    result['fx'] = {'base':'USDT', 'quote':'KRW', 'rate':number(ticker.get('last'), positive=True),
                                    'observed_at':stamp, 'source':venue + ':USDT/KRW'}
            else:
                getter = getattr(adapter, 'get_portfolio_exposure_result', None)
                snapshot = getter() if callable(getter) else adapter.get_positions_result()
                if not isinstance(snapshot, dict) or snapshot.get('status') != 'success': raise ValueError('exposure_provider_unverified')
                # Do not label a truncated broker first page as the whole account.
                if venue in ('kiwoom','shinhan','mirae','kis') and snapshot.get('complete') is not True:
                    raise ValueError('exposure_positions_incomplete')
                result['gross_by_currency'] = position_gross(snapshot.get('positions'), venue=venue)
            result['basis'] = 'provider_gross_including_external_positions'
        else: raise ValueError('exposure_mode_unverified')
        result.update(status='verified', checked_at=time.time(), reason='exposure_observed')
    except Exception as error:
        code = str(error)
        result.update(status='unverified', checked_at=time.time(), gross_by_currency=None, fx=None,
                      reason=code if code in {'exposure_number_unverified','exposure_provider_unverified',
                          'exposure_positions_unverified','exposure_holdings_unverified','exposure_valuation_budget',
                          'exposure_market_unverified','exposure_price_stale','exposure_fx_stale',
                          'exposure_positions_incomplete','exposure_identity_unverified','exposure_mode_unverified',
                          'exposure_currency_unverified','exposure_contract_unverified'} else 'exposure_provider_unverified')
    return result


def evaluate_exposure(config, snapshots, reservations, *, now, proposed_currency, proposed_gross):
    """Called under the account's atomic order transaction, without provider I/O."""
    evidence = {'status':'blocked', 'reason':'portfolio_exposure_unverified', 'observed_at':now,
                'gross_by_currency':None, 'reference_gross':None, 'reference_currency':config['reference_currency'],
                'missing_venues':[], 'scope':'account_mode_configured_venues'}
    venues = config['venues']
    if (not venues or any(v not in VENUES for v in venues)
        or any(v is None for v in config['max_gross_by_currency'].values())
        or config['max_reference_gross'] is None
        or not any(config['max_gross_by_currency'].values()) and not config['max_reference_gross']):
        evidence['reason'] = 'portfolio_exposure_policy_incomplete'; return evidence
    gross = {'KRW':0.0, 'USDT':0.0}
    try:
        for venue in venues:
            row = snapshots.get(venue) or {}
            if row.get('status') != 'verified' or not 0 <= now - number(row.get('checked_at'), positive=True) <= config['max_age_sec']:
                evidence['missing_venues'].append(venue); continue
            for quote, value in row['gross_by_currency'].items():
                if quote not in gross: raise ValueError('currency')
                gross[quote] += number(value)
        if evidence['missing_venues']: return evidence
        for row in reservations:
            if row.get('target') not in venues or row.get('opens_exposure') is False: continue
            if row.get('status') in {'rejected','cancelled'} and not row.get('exposure_pending'): continue
            if row.get('status') == 'filled' and not row.get('exposure_pending'): continue
            quote = row.get('quote_currency')
            if quote not in gross: raise ValueError('currency')
            gross[quote] += number(row.get('estimated_notional'))
        gross[proposed_currency] += number(proposed_gross, positive=True)
        gross = {k:number(v) for k,v in gross.items()}
        evidence['gross_by_currency'] = gross
        for quote, cap in config['max_gross_by_currency'].items():
            if cap > 0 and gross[quote] > cap:
                evidence['reason'] = 'portfolio_gross_cap_exceeded:' + quote; return evidence
        cap = config['max_reference_gross']
        if cap > 0:
            reference = config['reference_currency']
            if reference not in gross: raise ValueError('reference')
            other = 'USDT' if reference == 'KRW' else 'KRW'
            value = gross[reference]
            if gross[other] > 0:
                if config['fx_venue'] not in venues:
                    evidence['reason'] = 'portfolio_fx_unverified'; return evidence
                fx = (snapshots.get(config['fx_venue']) or {}).get('fx') or {}
                if fx.get('base') != 'USDT' or fx.get('quote') != 'KRW' or not str(fx.get('source') or '').endswith(':USDT/KRW'):
                    evidence['reason'] = 'portfolio_fx_unverified'; return evidence
                if not 0 <= now - number(fx.get('observed_at'), positive=True) <= 60:
                    evidence['reason'] = 'portfolio_fx_stale'; return evidence
                rate = number(fx.get('rate'), positive=True)
                value += gross[other] * rate if reference == 'KRW' else gross[other] / rate
                evidence['fx'] = {k:fx[k] for k in ('base','quote','rate','observed_at','source')}
            evidence['reference_gross'] = number(value)
            if value > cap:
                evidence['reason'] = 'portfolio_reference_cap_exceeded'; return evidence
        evidence.update(status='allowed', reason='portfolio_exposure_within_limits')
    except (TypeError, ValueError, KeyError, OverflowError):
        evidence['reason'] = 'portfolio_exposure_unverified'
    return evidence


def refresh_exposure(owner, *, venue, mode, policy):
    """Publish positions even when that venue has no entry signal; never start it."""
    config = normalize_exposure_policy(policy)
    if not config['enabled']: return
    from .opportunity_coordinator import get_opportunity_coordinator, account_scope_for
    from .strategy_scope import canonical_venue
    venue = canonical_venue(venue)
    if venue not in config['venues']: return
    key = (venue, account_scope_for(owner, mode))
    observed = getattr(owner, '_exposure_refresh_at', None)
    if not isinstance(observed, dict): observed = owner._exposure_refresh_at = {}
    if 0 <= time.time()-observed.get(key,0) < 20: return
    result = collect_exposure(owner, venue=venue, mode=mode, policy=policy)
    if result is None: return
    observed[key] = time.time()
    while len(observed)>33: observed.pop(next(iter(observed)))
    get_opportunity_coordinator(owner).publish_exposure(account_scope=key[1], target=venue, snapshot=result)
