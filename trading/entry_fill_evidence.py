"""Read provider-reported entry fills; requested size/market price are not fills."""
import math


def owned_entry_fill(receipt):
    if not isinstance(receipt, dict): return None
    raw = receipt.get('order') if isinstance(receipt.get('order'), dict) else receipt
    order_id = raw.get('orderId') or raw.get('id') or receipt.get('order_id')
    quantity = raw.get('executedQty', receipt.get('executed_qty'))
    price = raw.get('avgPrice', receipt.get('avg_price'))
    try:
        q, p = float(quantity), float(price)
        if not order_id or not all(math.isfinite(v) and v > 0 for v in (q,p)):
            return None
    except (TypeError, ValueError): return None
    return {'order_id': str(order_id), 'quantity': q, 'price': p,
            'complete': str(raw.get('status') or receipt.get('status') or '').upper() == 'FILLED',
            'terminal': str(raw.get('status') or receipt.get('status') or '').upper() in {'FILLED', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'EXPIRED_IN_MATCH'}}


def reconcile_owned_pending_entries(owner):
    """At most three read-only lookups per 30s; absence never proves rejection."""
    import time
    from .opportunity_coordinator import get_opportunity_coordinator, account_scope_for, finish_submission
    now = time.monotonic()
    if now - getattr(owner, '_pending_entry_lookup_at', -31.) < 30.:
        return
    owner._pending_entry_lookup_at = now
    coordinator = get_opportunity_coordinator(owner)
    for row in coordinator.pending_submissions(account_scope=account_scope_for(owner,'live'),target='binance'):
        symbol = row.get('symbol')
        if not symbol:
            continue
        try:
            lookup = {'orderId':row['order_id']} if row.get('order_id') else {'origClientOrderId':row['client_order_id']}
            receipt = owner.binance_client.client.futures_get_order(symbol=symbol,**lookup)
            if not isinstance(receipt,dict) or receipt.get('symbol') != symbol:
                continue
            if not ((row.get('order_id') and str(receipt.get('orderId')) == str(row['order_id']))
                    or receipt.get('clientOrderId') == row['client_order_id']):
                continue
            status = str(receipt.get('status') or '').upper()
            terminal = status in {'CANCELED','CANCELLED','REJECTED','EXPIRED','EXPIRED_IN_MATCH'} or (status=='FILLED' and owned_entry_fill(receipt) is not None)
            finish_submission(owner,row,{'order':receipt,'status':status},confirmed=terminal)
        except Exception:
            # Lookup errors/not-found retain the reservation. No retry order,
            # balance adoption, key mutation or automatic LIVE resume.
            continue
