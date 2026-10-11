"""Only the public product metadata needed by the USDT futures adapters."""
from decimal import Decimal


def install(exchange, rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty_instrument_catalogue')
    if any(not isinstance(row, dict) or not row.get('symbol') for row in rows):
        raise ValueError('invalid_market_catalogue')
    return exchange.set_markets(rows)


def bitget_usdt_catalogue(exchange):
    """CCXT 4.5 metadata contract, with one public USDT-FUTURES request.

    fetch_default_markets also fetches five unrelated settlement/demo products.
    Keep precision, fees, contract size and status; never guess missing limits.
    """
    fetch = getattr(exchange, 'publicMixGetV2MixMarketContracts', None)
    if not callable(fetch):
        return exchange.load_markets(reload=True)
    response = fetch({'productType': 'USDT-FUTURES'})
    if not isinstance(response, dict) or str(response.get('code')) != '00000' or not isinstance(response.get('data'), list):
        raise ValueError('invalid_bitget_catalogue')
    rows = []
    for raw in response['data']:
        if not isinstance(raw, dict):
            raise ValueError('invalid_bitget_instrument')
        if raw.get('symbolType') != 'perpetual' or raw.get('quoteCoin') != 'USDT' or 'USDT' not in (raw.get('supportMarginCoins') or []):
            continue
        base, quote = raw.get('baseCoin'), raw['quoteCoin']
        if not base or not raw.get('symbol'):
            raise ValueError('invalid_bitget_instrument')
        number = lambda name: exchange.safe_number(raw, name)
        price = (float(Decimal(raw['priceEndStep']) * Decimal(10) ** -int(raw['pricePlace']))
                 if raw.get('priceEndStep') is not None and raw.get('pricePlace') is not None else None)
        rows.append(exchange.safe_market_structure(dict(
            id=raw['symbol'], symbol=f'{base}/{quote}:{quote}', base=base, quote=quote, settle=quote,
            baseId=base, quoteId=quote, settleId=quote, type='swap', spot=False, margin=False,
            swap=True, future=False, option=False, contract=True, linear=True, inverse=False,
            active=raw.get('symbolStatus') == 'normal' if raw.get('symbolStatus') is not None else None,
            marginModes={'cross':True, 'isolated':True}, contractSize=1,
            taker=number('takerFeeRate'), maker=number('makerFeeRate'), expiry=None,
            expiryDatetime=None, strike=None, optionType=None,
            precision={'price':price, 'amount':number('sizeMultiplier')},
            limits={'leverage':{'min':number('minLever'), 'max':number('maxLever')},
                    'amount':{'min':number('minTradeNum'), 'max':number('maxTradeAmount')},
                    'price':{'min':None, 'max':None}, 'cost':{'min':number('minTradeUSDT'), 'max':None}},
            created=exchange.safe_integer(raw,'launchTime'), info=raw)))
    return install(exchange, rows)
