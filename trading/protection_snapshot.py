"""Read-only protective-order evidence. Query failure is never an empty book."""
import math


def positive(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def assess_protection(orders, *, symbol, position_side, quantity=0, expected_ids=None):
    """Require distinct TP and SL evidence on the closing side of this position."""
    legs = {"tp": [], "sl": []}
    combined_ids = set()
    closing = 'sell' if str(position_side).upper() == 'LONG' else 'buy'
    canonical = lambda s: str(s or '').upper().split(':')[0].replace('/', '').replace('-', '')
    for order in orders:
        info = order.get('info') or {}
        data = {**info, **{k: v for k, v in order.items() if v is not None}}
        subtype = str(data.get('stopOrderType') or data.get('planType') or '').lower()
        close_plan = subtype in ('pos_profit', 'pos_loss', 'profit_plan', 'loss_plan')
        if close_plan and not data.get('side'):
            held = str(data.get('holdSide') or data.get('posSide') or '').lower()
            if held in ('long', 'buy', 'short', 'sell'):
                data['side'] = 'sell' if held in ('long', 'buy') else 'buy'
        if canonical(data.get('symbol') or data.get('instId')) != canonical(symbol):
            continue
        if str(data.get('side') or '').lower() != closing:
            continue
        pos_side = str(data.get('positionSide') or data.get('posSide') or '').upper()
        if pos_side and pos_side not in ('BOTH', 'NET', str(position_side).upper()):
            continue
        status = str(data.get('algoStatus') or data.get('status') or data.get('state') or data.get('planStatus') or '').lower()
        if status not in ('open', 'new', 'pending', 'working', 'live', 'untriggered', 'partially_filled'):
            continue
        close_all = str(data.get('closePosition', '')).lower() == 'true'
        reduce = str(data.get('reduceOnly', '')).lower() == 'true'
        order_type = str(data.get('orderType') or data.get('type') or data.get('ordType') or '').lower()
        # Native closePosition and closing conditional orders qualify; ordinary
        # entry orders with attached TP/SL instructions are not active protection.
        if not (close_all or reduce or close_plan or order_type in ('conditional', 'oco', 'stop_market', 'take_profit_market')):
            continue
        size = positive(data.get('amount') or data.get('origQty') or data.get('sz') or data.get('qty') or data.get('size'))
        if not close_all and positive(quantity) and (size is None or size + 1e-10 < float(quantity)):
            continue
        prices = {
            'tp': next((v for key in ('takeProfitPrice', 'takeProfit', 'tpTriggerPx', 'presetTakeProfitPrice') if (v := positive(data.get(key)))), None),
            'sl': next((v for key in ('stopLossPrice', 'stopLoss', 'slTriggerPx', 'presetStopLossPrice') if (v := positive(data.get(key)))), None),
        }
        trigger = positive(data.get('triggerPrice') or data.get('stopPrice'))
        if trigger:
            if 'take_profit' in order_type or 'takeprofit' in subtype or 'profit' in subtype:
                prices['tp'] = trigger
            elif order_type in ('stop', 'stop_market') or 'stoploss' in subtype or 'loss' in subtype:
                prices['sl'] = trigger
        identity = str(data.get('algoId') or data.get('id') or data.get('orderId') or '')
        if prices['tp'] and prices['sl'] and identity:
            combined_ids.add(identity)
        for leg, price in prices.items():
            expected = (expected_ids or {}).get(leg)
            if price and identity and (not expected or identity == str(expected)):
                if not any(row['id'] == identity for row in legs[leg]):
                    legs[leg].append({'id': identity, 'price': price})
    status = 'verified' if all(len(legs[k]) == 1 for k in legs) else ('missing' if not any(legs.values()) else 'partial_or_ambiguous')
    if status == 'verified' and legs['tp'][0]['id'] == legs['sl'][0]['id'] and legs['tp'][0]['id'] not in combined_ids:
        status = 'partial_or_ambiguous'
    return {'status': status, **legs}


def ccxt_protection_orders(adapter, venue, symbol):
    """Bounded provider-specific reads; errors propagate to the caller."""
    client = adapter.exchange
    normalized = adapter._normalize_symbol(symbol)
    params = ({'trigger': True, 'ordType': 'conditional'}, {'trigger': True, 'ordType': 'oco'}) if venue == 'okx' else (
        ({'trigger': True, 'planType': 'profit_loss'},) if venue == 'bitget' else ({'trigger': True},)
    )
    rows = []
    for query in ({}, *params):
        batch = client.fetch_open_orders(normalized, limit=100, params=query)
        if not isinstance(batch, list) or len(batch) >= 100:
            raise RuntimeError('protection_snapshot_incomplete')
        rows.extend(batch)
    # Bybit full-position stops are also exposed on the position, not only in
    # the order book. Query failure must prevent a duplicate submission.
    if venue == 'bybit':
        for pos in client.fetch_positions([normalized]):
            info = pos.get('info') or {}
            side = str(pos.get('side') or info.get('side') or '').lower()
            if side not in ('long', 'short', 'buy', 'sell'):
                continue
            if not positive(pos.get('contracts')) or not (positive(info.get('takeProfit')) or positive(info.get('stopLoss'))):
                continue
            # Partial stops require order-level quantity evidence. Do not turn
            # a position summary into proof of full-position protection.
            if str(info.get('tpslMode', '')).lower() != 'full':
                continue
            side_name = 'LONG' if side in ('long', 'buy') else 'SHORT'
            if assess_protection(rows, symbol=normalized, position_side=side_name,
                                 quantity=pos['contracts'])['status'] == 'verified':
                continue
            rows.append({'id': 'position:' + str(info.get('positionIdx', side)), 'symbol': pos.get('symbol'),
                         'side': 'sell' if side in ('long', 'buy') else 'buy', 'type': 'conditional',
                         'status': 'open', 'closePosition': True, 'reduceOnly': True,
                         'takeProfit': info.get('takeProfit'), 'stopLoss': info.get('stopLoss')})
    return rows
