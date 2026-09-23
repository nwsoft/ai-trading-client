"""Same-venue spot valuation with explicit missing-market versus failed-read states.

No orders, balance changes, guessed prices, or delisting claims. A missing market
is evidence only about this venue's current catalogue, not an asset's value.
"""
import math
import threading
import time


class SpotValuation:
    def __init__(self):
        self._lock = threading.Lock()
        self._catalogues = {}

    def values(self, venue, exchange, assets, quote='KRW'):
        if not assets:
            return {}
        # Bound metadata requests, including failures. Never fall back to stale
        # metadata after a failed refresh or reuse another account's client.
        with self._lock:
            now = time.monotonic()
            cached = self._catalogues.get(venue)
            if cached and cached[0] is exchange and now < cached[1]:
                markets, failure = cached[2:]
            else:
                try:
                    markets = exchange.load_markets(reload=True)
                    if not isinstance(markets, dict) or not markets:
                        raise ValueError('empty_market_catalogue')
                    if any(not isinstance(m, dict) or not m.get('base') or
                           not m.get('quote') or not m.get('symbol') for m in markets.values()):
                        raise ValueError('invalid_market_catalogue')
                    markets = {s: dict(m) for s, m in markets.items()}
                    failure = ''
                except Exception as exc:
                    markets, failure = {}, type(exc).__name__
                self._catalogues[venue] = (exchange, now + (15 if failure else 300), markets, failure)
        if failure:
            return {a: {'status': 'market_query_failed', 'price': None} for a in assets}

        prices = {}
        def price(symbol):
            if symbol not in prices:
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    if ticker.get('timestamp') is not None:
                        timestamp = float(ticker['timestamp']) / 1000
                        if not math.isfinite(timestamp) or time.time() - timestamp > 300 or timestamp > time.time() + 30:
                            raise ValueError('stale_or_invalid_ticker')
                    number = float(ticker['last'])
                    prices[symbol] = number if math.isfinite(number) and number > 0 else None
                except Exception:
                    prices[symbol] = None
            return prices[symbol]

        def usable(m):
            # Coinone's installed CCXT adapter explicitly returns active=None.
            # This is a valuation route, not permission to place a trade: a
            # listed market + valid current ticker can price an asset without
            # claiming that missing active metadata means trading is enabled.
            return m.get('spot') is not False and m.get('contract') is not True and m.get('active') is not False

        results = {}
        for asset in assets:
            listed = [m for m in markets.values() if m['base'] == asset or m['quote'] == asset]
            if not listed:
                results[asset] = {'status': 'no_supported_market', 'price': None}
                continue
            routes = []
            for m in listed:
                if not usable(m) or m['base'] != asset:
                    continue
                if m['quote'] == quote:
                    routes.insert(0, [m['symbol']])
                else:
                    # An asset may trade in BTC/USDT rather than KRW. Both legs
                    # must be live same-venue markets; never borrow foreign prices.
                    for bridge in markets.values():
                        if usable(bridge) and bridge['base'] == m['quote'] and bridge['quote'] == quote:
                            routes.append([m['symbol'], bridge['symbol']])
            result = {'status': 'valuation_route_unavailable', 'price': None}
            for route in routes:
                values = [price(s) for s in route]
                if any(v is None for v in values):
                    result = {'status': 'price_query_failed', 'price': None}
                    continue
                value = math.prod(values)
                if math.isfinite(value) and value > 0:
                    result = {'status': 'priced', 'price': value, 'route': route}
                    break
            results[asset] = result
        return results
