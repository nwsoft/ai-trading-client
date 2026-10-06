"""Strict CCXT futures snapshot: failure is never a confirmed flat account."""
import math
import time


def validate_quantities(rows, keys):
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('position_row_invalid')
        raw = next((row[k] for k in keys if row.get(k) not in (None, '')), None)
        quantity = float(str(raw).replace(',', ''))
        if not math.isfinite(quantity) or quantity < 0 or not quantity.is_integer():
            raise ValueError('position_quantity_invalid')


def ccxt_snapshot(adapter):
    if not adapter.is_connected or not adapter.exchange:
        return {'status':'unavailable', 'positions':None, 'reason':'not_connected'}
    try:
        raw = adapter.exchange.fetch_positions()
        if not isinstance(raw, list):
            raise ValueError('positions_not_list')
        positions = []
        for row in raw:
            if not isinstance(row, dict) or row.get('contracts') is None:
                raise ValueError('position_quantity_missing')
            quantity = float(row['contracts'])
            if not math.isfinite(quantity) or quantity < 0:
                raise ValueError('position_quantity_invalid')
            if quantity == 0:
                continue
            side = str(row.get('side') or '').upper()
            symbol = str(row.get('symbol') or '')
            pnl = float(row['unrealizedPnl'])
            if not symbol or side not in ('LONG','SHORT') or not math.isfinite(pnl):
                raise ValueError('position_evidence_invalid')
            market = (getattr(adapter.exchange, 'markets', None) or {}).get(symbol) or {}
            positions.append({'symbol':symbol, 'side':side, 'size':quantity,
                              'contract_size':row.get('contractSize', market.get('contractSize')),
                              'linear':market.get('linear'),
                              'quantity_unit':'contracts', 'unrealized_pnl':pnl,
                              'entry_price':row.get('entryPrice'), 'mark_price':row.get('markPrice'),
                              'leverage':row.get('leverage'), 'liquidation_price':row.get('liquidationPrice')})
        return {'status':'success', 'positions':positions, 'checked_at':time.time()}
    except Exception as exc:
        return {'status':'error', 'positions':None, 'reason':type(exc).__name__}


def partner_holdings_complete(data):
    """A declared next page or contradictory flags defeat completion claims."""
    if not isinstance(data, dict): return None
    if any(data.get(k) not in (None, '') for k in ('next_cursor','nextToken','ctx_area_nk100')):
        return False
    if data.get('has_more') is True or data.get('complete') is False:
        return False
    if data.get('complete') is True or data.get('has_more') is False:
        return True
    return None


def stock_snapshot(adapter):
    try:
        positions = adapter.get_positions(strict=True)
        if not isinstance(positions, list):
            raise ValueError('positions_not_list')
        for row in positions:
            if not isinstance(row, dict) or not (row.get('code') or row.get('symbol')):
                raise ValueError('position_identity_missing')
            quantity = float(row['quantity'])
            if not math.isfinite(quantity) or quantity <= 0:
                raise ValueError('position_quantity_invalid')
        return {'status':'success','positions':positions,'checked_at':time.time(),
                'complete':getattr(adapter, '_last_positions_complete', None)}
    except Exception as exc:
        return {'status':'error','positions':None,'reason':type(exc).__name__}
