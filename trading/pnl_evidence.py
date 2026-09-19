"""Explicit accounting evidence; a fill or an estimated positive PnL is not a verified outcome."""
from __future__ import annotations

import math
from typing import Any, Mapping


def verified_live_samples(rows, venue):
    """For optional performance tuning only, NOT the entry/cold-start guard.

    An incomplete window disables tuning as a whole. Never select only its
    confirmed winners. PAPER and other venues are separate evidence domains.
    """
    selected = [dict(r) for r in rows if isinstance(r, dict)
                and str(r.get('exchange') or venue).lower() == str(venue).lower()
                and str(r.get('execution_mode') or '').lower() not in {'paper','learning','demo','mock'}]
    result = []
    for row in selected:
        if row.get('performance_evidence_ready') is not True:
            return []
        try:
            net = float(row['net_pnl'])
            notional = float(row['entry_price']) * float(row['quantity'])
            if not math.isfinite(net) or not math.isfinite(notional) or notional <= 0:
                return []
        except (KeyError, ValueError, TypeError):
            return []
        result.append({**row, 'pnl':net, 'pnl_percent':net/notional*100})
    return result


def provider_fill_gross_pnl(venue: str, trade: Mapping[str, Any]) -> float | None:
    """Read gross realized PnL, never reinterpret an arbitrary profit/closedPnl.

    CCXT preserves native response fields in info. Bybit closedPnl is a
    different endpoint/basis and deliberately is not treated as fill gross.
    """
    info = trade.get('info') if isinstance(trade.get('info'), dict) else {}
    native_key = {'binance': 'realizedPnl', 'okx': 'fillPnl', 'bitget': 'profit'}.get(venue)
    candidates = [trade.get('realized_pnl'), trade.get('realizedPnl')]
    if native_key:
        candidates.extend((info.get(native_key), trade.get(native_key)))
    for value in candidates:
        if value in (None, ''):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None
    return None


def performance_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    """Metadata for persisted LIVE outcomes consumed by performance policies."""
    status = str(row.get('reconciliation_status') or '')
    mode = str(row.get('execution_mode') or '').lower()
    try:
        net = float(row.get('net_pnl'))
        finite_net = math.isfinite(net)
    except (TypeError, ValueError, OverflowError):
        finite_net = False
    ready = (
        mode in {'live', 'live_api', 'optimized', 'manual'}
        and status in {'exchange_confirmed', 'exchange_confirmed_partial',
                       'broker_order_linked', 'exact_fill_price_no_provider_pnl'}
        and finite_net
    )
    return {
        'execution_mode': mode,
        'reconciliation_status': status,
        'pnl_source': row.get('pnl_source'),
        'net_pnl': row.get('net_pnl'),
        'performance_evidence_ready': ready,
        'pnl_is_net': ready,
    }
