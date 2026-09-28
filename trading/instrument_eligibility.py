"""Current instrument eligibility, NOT portfolio valuation or historical evidence.

All entry candidates (including pins) and entry submissions use this contract.
Cache belongs to the adapter/client, never to an account name or a disk backup.
No orders, credentials, ledger writes, or guesses from ticker prices here.
"""
from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy

_INIT_LOCK = threading.Lock()
ALIASES = {'koreainvestment': 'kis', 'miraeasset': 'mirae'}
STOCKS = {'kis', 'mirae', 'kiwoom', 'shinhan'}
SPOTS = {'upbit', 'bithumb', 'coinone'}
FUTURES = {'binance', 'okx', 'bybit', 'bitget'}
CONTRACT = 'noahai.instrument-eligibility.v1'


def venue_id(value):
    value = str(value or '').lower()
    return ALIASES.get(value, value)


def symbol_key(value):
    # Retain settlement currency so inverse/linear instruments cannot collide.
    value = str(value or '').strip().upper()
    if value.startswith('KRW-'):
        value = value[4:] + 'KRW'
    return value.replace('/', '').replace('-', '')


def stock_status(item):
    """Preserve provider restrictions; caution/designation is not delisting."""
    for key in ('trht_yn', 'trading_halt', 'is_suspended', 'is_delisted'):
        if str(item.get(key, '')).lower() in {'y', 'true', '1'}:
            return 'halted'
    return str(item.get('status') or item.get('trading_status') or 'unverified_listing').lower()


def row_state(row, venue):
    if not isinstance(row, dict):
        return 'unknown'
    if row.get('_status_conflict'):
        return 'unknown'
    info = row.get('info') if isinstance(row.get('info'), dict) else {}
    states = {str(value).lower() for value in (row.get('status'), info.get('status'), info.get('state'), info.get('symbolStatus')) if value is not None}
    if states & {'delisted', '상장폐지', 'settled', 'expired', 'closed', 'settling', 'delivering'}:
        return 'delisted'
    if states & {'close_only', 'closeonly', 'reduce_only', 'limit_open'}:
        return 'close_only'
    if states & {'halted', 'suspended', 'suspend', 'inactive', 'break', 'stop', 'stopped', '거래정지', 'prelaunch', 'preopen', 'maintain', 'cancelonly', 'cancel_only', 'offline'}:
        return 'halted'
    if row.get('active') is False:
        return 'halted'
    if venue == 'coinone':
        # Official /public/v2/markets, not CCXT's ticker-derived market list.
        if row.get('maintenance_status') == 1:
            return 'halted'
        trade = row.get('trade_status')
        if row.get('maintenance_status') != 0:
            return 'unknown'
        return {0: 'halted', 1: 'tradable', 2: 'close_only', 3: 'sell_disabled'}.get(trade, 'unknown')
    if venue in STOCKS:
        status = stock_status(row)
        return 'tradable' if status in {'ok', 'normal', 'trading', 'active', '정상'} else ('halted' if status in {'halted', 'suspended', 'delisted', '거래정지', '상장폐지'} else 'unknown')
    if row.get('active') is True or states & {'trading', 'live', 'online'}:
        return 'tradable'
    if venue in {'upbit', 'bithumb'} and row.get('_listed_market') is True:
        return 'tradable'
    return 'unknown'


def _public_json(url):
    import requests
    response = requests.get(url, timeout=(3, 7))
    response.raise_for_status()
    return response.json()


def _fetch(owner, venue):
    if venue in STOCKS:
        rows = []
        for market in ('KOSPI', 'KOSDAQ'):
            result = owner.get_stock_list(market)
            if not isinstance(result, list):
                raise ValueError('invalid_stock_catalogue')
            rows.extend(dict(row, is_etf=False) for row in result)
        etfs = owner.get_etf_list()
        if not isinstance(etfs, list):
            raise ValueError('invalid_etf_catalogue')
        rows.extend(dict(row, is_etf=True) for row in etfs)
        # Partner catalogues may omit trading state. Do not turn absence into
        # OK. Confirm domestic identity/type against the same official master
        # used by KIS, once per refresh; explicit partner restrictions win.
        missing = [row for row in rows if row.get('status') == 'unverified_listing']
        if missing and venue in {'mirae', 'shinhan'}:
            try:
                from trading.exchanges.kis_market_master import market_master
                master = {row['code']: row for market in ('KOSPI', 'KOSDAQ') for row in market_master(market)}
                for row in missing:
                    current = master.get(str(row.get('code') or row.get('symbol')))
                    if current and bool(current.get('is_etf')) == bool(row.get('is_etf')):
                        row.update(status=current['status'], status_source='kis_public_master',
                                   _listing_checked_at=current.get('_listing_checked_at'))
            except Exception:
                pass  # Unknown stays unknown; never overwrite explicit rows.
        return rows, 'broker_current_list'
    if venue == 'coinone':
        data = _public_json('https://api.coinone.co.kr/public/v2/markets/KRW')
        if data.get('result') != 'success' or str(data.get('error_code')) != '0' or not isinstance(data.get('markets'), list):
            raise ValueError('invalid_coinone_catalogue')
        return [dict(row, symbol=f"{row['target_currency']}/{row['quote_currency']}".upper(),
                     spot=True, base=str(row['target_currency']).upper(), quote=str(row['quote_currency']).upper())
                for row in data['markets']], 'coinone_public_markets'
    if venue == 'bithumb':
        # Installed CCXT builds markets from legacy tickers, not listing data.
        data = _public_json('https://api.bithumb.com/v1/market/all')
        if not isinstance(data, list):
            raise ValueError('invalid_bithumb_catalogue')
        rows = []
        for row in data:
            quote, base = str(row['market']).upper().split('-', 1)
            rows.append(dict(row, symbol=f'{base}/{quote}', spot=True, base=base, quote=quote, _listed_market=True))
        return rows, 'bithumb_public_markets'
    if venue == 'binance':
        client = owner if callable(getattr(owner, 'get_exchange_info', None)) else getattr(owner, 'client', None)
        data = client.get_exchange_info()
        return data['symbols'], 'binance_exchange_info'
    exchange = getattr(owner, 'exchange', None)
    if exchange is None:
        raise ValueError('instrument_provider_unavailable')
    markets = exchange.load_markets(reload=True)
    if not isinstance(markets, dict):
        raise ValueError('invalid_market_catalogue')
    rows = []
    for symbol, row in markets.items():
        row = dict(row, symbol=symbol)
        if venue == 'upbit':
            row['_listed_market'] = bool((row.get('info') or {}).get('market'))
        rows.append(row)
    return rows, 'ccxt_reloaded_markets'


def catalogue(owner, venue):
    venue = venue_id(venue)
    if owner is None or not hasattr(owner, '__dict__') or venue not in STOCKS | SPOTS | FUTURES:
        return {'rows': {}, 'reason': 'instrument_provider_unsupported', 'source': 'none', 'checked_at': None}
    with _INIT_LOCK:
        if '_instrument_guard_lock' not in vars(owner):
            owner._instrument_guard_lock = threading.RLock()
            owner._instrument_guard_cache = {}
    with owner._instrument_guard_lock:
        now = time.monotonic()
        # Exchange reconnection must not inherit evidence from the old client.
        identity = id(getattr(owner, 'exchange', None) or getattr(owner, 'client', None))
        cached = owner._instrument_guard_cache.get(venue)
        if cached and cached['expires'] > now and cached['identity'] == identity:
            return cached
        checked_at = time.time()
        try:
            rows, source = _fetch(owner, venue)
            if not rows:
                raise ValueError('empty_instrument_catalogue')
            checked_at = time.time()
            normalized = {}
            for row in rows:
                key = symbol_key(row.get('symbol') or row.get('code'))
                if not key:
                    raise ValueError('missing_instrument_identity')
                # Conflicting duplicate evidence must not overwrite a restriction.
                if key in normalized and row_state(normalized[key], venue) != row_state(row, venue):
                    normalized[key] = dict(row, _status_conflict=True)
                else:
                    normalized[key] = deepcopy(row)
            result = dict(rows=normalized, reason='', source=source, checked_at=checked_at)
            ttl = 300 if venue in STOCKS else 60
            # Do not renew a broker's underlying master-cache evidence for a
            # second full TTL merely by wrapping it in this cache.
            source_times = [float(row['_listing_checked_at']) for row in rows if row.get('_listing_checked_at') is not None]
            if source_times:
                checked_at = min(checked_at, min(source_times))
                ttl -= max(0, time.time() - checked_at)
                if ttl <= 0:
                    raise ValueError('expired_underlying_catalogue')
                # Keep this wrapper strictly inside the source evidence window.
                # A small margin also avoids equality at coarse Windows clocks.
                ttl = max(0.001, ttl - 0.001)
                result['checked_at'] = checked_at
        except Exception as exc:
            result = dict(rows={}, reason='instrument_catalogue_unavailable', source=type(exc).__name__, checked_at=checked_at)
            ttl = 15
        result.update(expires=time.monotonic() + ttl, identity=identity, contract=CONTRACT)
        owner._instrument_guard_cache[venue] = result
        return result


def eligibility(owner, venue, symbol):
    venue = venue_id(venue)
    evidence = catalogue(owner, venue)
    row = evidence['rows'].get(symbol_key(symbol))
    # Futures adapters commonly accept BTCUSDT as shorthand for linear swap.
    if row is None and venue in FUTURES and ':' not in str(symbol):
        row = evidence['rows'].get(symbol_key(symbol) + ':USDT')
    state = row_state(row, venue) if row else 'not_listed'
    if row and venue in SPOTS and (row.get('spot') is False or row.get('contract') is True or str(row.get('quote', '')).upper() != 'KRW'):
        state = 'wrong_product'
    if row and venue in FUTURES:
        contract = str(row.get('contractType') or row.get('contract_type') or '').upper()
        if (venue == 'binance' and contract != 'PERPETUAL') or (venue != 'binance' and not (row.get('swap') or row.get('future') or row.get('contract'))):
            state = 'wrong_product'
        quote = str(row.get('quote') or row.get('quoteAsset') or row.get('quote_asset') or '').upper()
        if quote != 'USDT' or row.get('inverse') is True or str(row.get('settle') or 'USDT').upper() != 'USDT':
            state = 'wrong_product'
    reason = evidence['reason'] or ('' if state == 'tradable' else f'instrument_{state}')
    labels = {'instrument_catalogue_unavailable':'현재 종목 목록 조회 실패',
              'instrument_provider_unsupported':'종목 상태 제공 경로 미지원',
              'instrument_not_listed':'현재 거래 종목 목록에서 확인되지 않음',
              'instrument_halted':'거래 중단 또는 점검 상태',
              'instrument_delisted':'거래지원 종료 또는 만기 상태',
              'instrument_close_only':'신규 진입 불가·청산만 허용',
              'instrument_sell_disabled':'매도 제한 상태·신규 매수 보류',
              'instrument_wrong_product':'현재 기관의 지원 상품·결제통화와 불일치',
              'instrument_unknown':'거래 가능 상태 확인 필요'}
    return dict(allowed=not reason, reason=reason, message=labels.get(reason, '거래 가능'), state=state, venue=venue, symbol=str(symbol), source=evidence['source'], checked_at=evidence['checked_at'], contract=CONTRACT)


def entry_check(owner, venue, symbol):
    result = eligibility(owner, venue, symbol)
    if not result['allowed']:
        # Bounded last diagnostic; never store a growing per-symbol error history.
        emit = True
        if owner is not None and hasattr(owner, '__dict__'):
            owner.last_instrument_rejection = result
            previous = getattr(owner, '_instrument_last_log', (0, ''))
            now = time.monotonic()
            emit = previous[1] != result['reason'] or now - previous[0] >= 60
            if emit:
                owner._instrument_last_log = (now, result['reason'])
        if emit:
            logging.getLogger(__name__).warning('%s %s 신규 진입 제외: %s (%s) · 종목 상태 확인 후 자동 재평가, 반복 시작/기록 초기화 불필요 (ex=%s)', venue, symbol, result['message'], result['reason'], venue)
    return result


def invalidate(owner, venue):
    """Use only on confirmed invalid/inactive instrument rejection, not timeout."""
    lock = getattr(owner, '_instrument_guard_lock', None)
    if lock is not None:
        with lock:
            owner._instrument_guard_cache.pop(venue_id(venue), None)


def instrument_order(venue):
    """Final adapter boundary. Reductions keep their existing ownership guards."""
    import inspect
    from functools import wraps
    venue = venue_id(venue)
    def decorate(fn):
        signature = inspect.signature(fn)
        @wraps(fn)
        def execute(self, *args, **kwargs):
            # Preserve the original disconnected/authentication error. No order
            # can be sent in these paths; do not perform public I/O first.
            if getattr(self, 'is_connected', True) is False:
                return fn(self, *args, **kwargs)
            values = signature.bind(self, *args, **kwargs).arguments
            request = values.get('order_request')
            symbol = getattr(request, 'symbol', None) if request is not None else values.get('symbol')
            side = getattr(request, 'side', None) if request is not None else values.get('side')
            reduction = (venue in SPOTS | STOCKS and str(side).upper() == 'SELL') or values.get('reduce_only') is True or values.get('close_position') is True
            if not reduction:
                result = entry_check(self, venue, symbol)
                if not result['allowed']:
                    return {'status': 'error', 'error': result['reason'], 'reason': result['reason'], 'message': result['message'], 'instrument': result}
            result = fn(self, *args, **kwargs)
            if isinstance(result, dict) and str(result.get('status', '')).lower() in {'error', 'failed', 'rejected'}:
                error = str(result.get('error') or result.get('message') or '').lower()
                if any(text in error for text in ('invalid symbol', 'symbol not found', 'market is closed', 'market is not active', 'symbol is not trading', '상장폐지', '-1121')):
                    invalidate(self, venue)
            return result
        execute.instrument_eligibility_contract = CONTRACT
        return execute
    return decorate
