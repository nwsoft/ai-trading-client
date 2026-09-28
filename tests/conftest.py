"""Explicit fixtures only; lifecycle integration tests use real guard transport paths."""
import pytest


@pytest.fixture
def listed_instrument_transport(monkeypatch):
    """For isolated sizing/ledger/order-payload tests predating the listing gate.

    Supplies listing evidence, NOT an allowed=True guard stub. Negative lifecycle,
    expiry, native transport and adapter binding tests do not opt into this fixture.
    """
    from trading import instrument_eligibility as g
    original_id = g.venue_id
    monkeypatch.setattr(g, 'venue_id', lambda v:'kis' if str(v) in {'mock','paper-test'} else original_id(v))
    def fetch(owner, venue):
        if venue in g.STOCKS:
            return [dict(code=s, symbol=s, status='ok', is_etf=s=='069500')
                    for s in ('005930','000660','035420','069500','123456')], 'unit_fixture_current_list'
        rows = []
        for base in ('BTC','ETH','VET','XRP','SOL','INJ'):
            if venue in g.SPOTS:
                rows.append(dict(symbol=base+'/KRW', quote='KRW', spot=True, active=True,
                                 maintenance_status=0,trade_status=1))
            else:
                rows.append(dict(symbol=base+'USDT' if venue=='binance' else base+'/USDT:USDT',
                                 quote='USDT',contract=True,swap=True,active=True,status='TRADING',contract_type='PERPETUAL'))
        return rows, 'unit_fixture_current_list'
    monkeypatch.setattr(g, '_fetch', fetch)
