"""Daily returns aligned by both observation dates; missing evidence is not zero."""
from __future__ import annotations
from datetime import datetime, timezone
import math
import time
import threading
from .portfolio_exposure import number

_CACHE_SETUP_LOCK = threading.Lock()


def daily_returns(rows, *, now):
    if not isinstance(rows, list) or len(rows) > 300: raise ValueError('correlation_history_unverified')
    closes = []
    previous = ''
    today = datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%d')
    for row in rows:
        if isinstance(row, dict):
            date = str(row.get('date') or '').replace('-', '')
            price = row.get('close')
            if len(date) != 8 or not date.isdigit(): raise ValueError('correlation_date_unverified')
            datetime.strptime(date, '%Y%m%d')
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            stamp = number(row[0], positive=True)
            if stamp > 1e11: stamp /= 1000
            date = datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y%m%d')
            price = row[4]
        else: raise ValueError('correlation_history_unverified')
        if date <= previous: raise ValueError('correlation_history_order')
        previous = date
        value = number(price, positive=True)
        if date >= today: continue  # Never use the currently forming daily bar.
        closes.append((date, value))
    if not closes or (datetime.fromtimestamp(now, timezone.utc)-datetime.strptime(closes[-1][0], '%Y%m%d').replace(tzinfo=timezone.utc)).days > 7:
        raise ValueError('correlation_history_stale')
    returns = {(left[0],right[0]):right[1]/left[1]-1 for left,right in zip(closes,closes[1:])}
    if any(not math.isfinite(v) for v in returns.values()): raise ValueError('correlation_return_unverified')
    return returns


def aligned_correlation(left, right, *, minimum=40):
    keys = sorted(set(left) & set(right))
    if len(keys) < minimum: return {'value':None, 'samples':len(keys), 'reason':'correlation_sample_insufficient'}
    a,b = [left[k] for k in keys], [right[k] for k in keys]
    if any(not math.isfinite(v) for v in a+b): return {'value':None,'samples':len(keys),'reason':'correlation_return_unverified'}
    scale_a,scale_b = max(abs(v) for v in a),max(abs(v) for v in b)
    if not scale_a or not scale_b: return {'value':None,'samples':len(keys),'reason':'correlation_variance_insufficient'}
    a,b = [v/scale_a for v in a],[v/scale_b for v in b]
    mean_a,mean_b = sum(a)/len(a),sum(b)/len(b)
    va,vb = sum((x-mean_a)**2 for x in a),sum((x-mean_b)**2 for x in b)
    if va <= 1e-20 or vb <= 1e-20: return {'value':None, 'samples':len(keys), 'reason':'correlation_variance_insufficient'}
    value = sum((x-mean_a)*(y-mean_b) for x,y in zip(a,b))/math.sqrt(va*vb)
    return {'value':max(-1.0,min(1.0,value)), 'samples':len(keys), 'reason':'observed_daily_returns',
            'start':keys[0][0], 'end':keys[-1][1]}


def apply_observed_correlations(owner, *, venue, candidates, policy, fetcher, mode="unknown"):
    config = (policy or {}).get('observed_correlation') or {}
    if config.get('enabled') is not True: return candidates
    from .strategy_scope import canonical_venue
    venue = canonical_venue(venue)
    now, started = time.time(), time.monotonic()
    with _CACHE_SETUP_LOCK:
        cache = getattr(owner, '_observed_return_cache', None)
        if not isinstance(cache, dict): cache = owner._observed_return_cache = {}
        lock = getattr(owner, '_correlation_cache_lock', None)
        if lock is None: lock = owner._correlation_cache_lock = threading.RLock()
    histories = {}
    history_times = {}
    problems = {}
    # No more than 30 requests, 10s between calls, 120 completed daily bars.
    # A single provider call is still bounded by that adapter's request timeout.
    for index, candidate in enumerate(candidates[:30]):
        symbol = candidate['symbol']; key = (venue, symbol)
        with lock: cached = cache.get(key)
        if cached and 0 <= now-cached['observed_at'] < 3600:
            histories[symbol] = cached['returns']; history_times[symbol] = cached['observed_at']; continue
        if index >= 30 or time.monotonic()-started > 10:
            problems[symbol] = 'correlation_request_budget'; continue
        try:
            returns = daily_returns(fetcher(symbol, 120), now=now)
            with lock:
                cache[key] = {'returns':returns, 'observed_at':now}
                while len(cache) > 120:
                    cache.pop(next(iter(cache)))
            histories[symbol] = returns
            history_times[symbol] = now
        except Exception:
            problems[symbol] = 'correlation_history_unverified'
    from .opportunity_coordinator import get_opportunity_coordinator, account_scope_for
    quote = 'USDT' if venue in ('binance','bybit','okx','bitget') else 'KRW'
    peers = get_opportunity_coordinator(owner).observed_return_peers(
        account_scope=account_scope_for(owner,mode),venue=venue,quote=quote,histories=histories,
        history_times=history_times,now=now)
    output=[]
    for candidate in candidates:
        symbol = candidate['symbol']; pairs=[]; missing=problems.get(symbol) or ('correlation_request_budget' if symbol not in histories else None)
        targets = [row for row in peers if (row['venue'],row['symbol']) != (venue,symbol)][:30]
        # Missing selected peers are also evidence gaps, not a free diversification benefit.
        known = {(row['venue'],row['symbol']) for row in targets}
        for other in candidates[:30]:
            if other['symbol'] != symbol and (venue,other['symbol']) not in known:
                targets.append({'venue':venue,'symbol':other['symbol'],'returns':{}})
        for other in targets[:30]:
            pair = aligned_correlation(histories.get(symbol, {}), other['returns'])
            pairs.append({'symbol':other['venue'] + ':' + other['symbol'], **pair})
        if not pairs:
            coefficient, basis = 1.0, 'correlation_peer_unavailable'
        elif missing or any(p['value'] is None for p in pairs):
            coefficient, basis = 1.0, missing or 'correlation_pair_unverified'
        else:
            coefficient = sum(max(0.0,p['value']) for p in pairs)/len(pairs)
            basis = 'observed_aligned_daily_returns'
        output.append({**candidate, 'avg_correlation':coefficient, 'correlation_basis':basis,
                       'correlation_pairs':pairs[:30], 'correlation_observed_at':now})
    evidence = {'source':venue, 'observed_at':now,
        'basis':'same_quote_cross_venue_daily_returns', 'candidates':[{k:c[k] for k in ('symbol','avg_correlation','correlation_basis','correlation_pairs')} for c in output[:30]]}
    mode_key = str(getattr(mode, 'value', mode)).lower()
    mode_key = {'mock':'paper','live_api':'live'}.get(mode_key, mode_key)
    with lock:
        scoped = getattr(owner, '_last_correlation_evidence_by_scope', None)
        if not isinstance(scoped, dict): scoped = owner._last_correlation_evidence_by_scope = {}
        scoped[(venue,mode_key)] = evidence
        while len(scoped)>33: scoped.pop(next(iter(scoped)))
        owner._last_correlation_evidence = evidence
    return output
