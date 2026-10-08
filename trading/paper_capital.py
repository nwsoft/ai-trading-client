"""Available simulated funds, separate from LIVE balances and unrealized gains."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


def _number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError('unverified_number')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('unverified_number')
    return result


def paper_available_funds(initial_equity, positions, *, venue: str, quote: str,
                          ledger_file: Path) -> dict:
    """Reconcile the complete bounded close ledger and current open margin.

    No current-price profit is spendable. A malformed/truncated/legacy ledger
    blocks new simulated entries instead of restoring the original bankroll.
    Reservation concurrency remains the OpportunityCoordinator's authority.
    """
    from .strategy_scope import canonical_venue
    from .paper_strategy_ledger import normalize_paper_outcome_costs, paper_outcome_calculation_status
    result = {'available_capital': 0.0, 'capital_basis': 'paper_funds_unverified',
              'quote_currency': quote, 'initial_capital': None,
              'realized_net_pnl': None, 'open_margin': None}
    try:
        initial = _number(initial_equity)
        if initial <= 0:
            raise ValueError('initial_equity_unverified')
        from .paper_funds_session import read_session
        session = read_session(ledger_file, venue=venue, quote=quote)
        offset = 0
        if session is not None:
            initial, offset = float(session['initial_capital']), session['ledger_offset']
            result.update(paper_session_id=session['session_id'], paper_session_started_at=session['started_at'],
                          paper_session_basis=session['basis'], historical_pnl_restored=False)
        realized, margin = 0.0, 0.0
        seen = {}
        if ledger_file.exists():
            if ledger_file.stat().st_size - offset > 64 * 1024 * 1024:
                raise ValueError('paper_ledger_reconciliation_budget')
            with ledger_file.open('rb') as handle:
                handle.seek(offset)
                for index, line in enumerate(handle):
                    if index >= 100_000:
                        raise ValueError('paper_ledger_reconciliation_budget')
                    if not line.strip():
                        continue
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError('paper_ledger_invalid')
                    if canonical_venue(str(raw.get('exchange') or '')) != canonical_venue(venue):
                        continue
                    if raw.get('execution_mode') != 'paper':
                        continue
                    # Order-free strategy observation has its own positions;
                    # its closes cannot fund the execution PAPER wallet.
                    if raw.get('cost_calculation_status') == 'parallel_paper_recorded_contract':
                        continue
                    row = normalize_paper_outcome_costs(raw)
                    if str(row.get('quote_currency') or '').upper() != quote:
                        raise ValueError('paper_ledger_currency_unverified')
                    identity = str(row.get('event_id') or '')
                    if not identity or paper_outcome_calculation_status(row) != 'valid':
                        raise ValueError('paper_ledger_pnl_unverified')
                    if identity in seen:
                        if seen[identity] != _number(row.get('net_pnl')):
                            raise ValueError('paper_ledger_event_conflict')
                        continue
                    seen[identity] = _number(row.get('net_pnl'))
                    realized += seen[identity]
        for position in list((positions or {}).values()):
            get = position.get if isinstance(position, Mapping) else lambda k, d=None: getattr(position, k, d)
            if str(get('execution_mode') or '').lower() != 'paper':
                raise ValueError('paper_position_mode_unverified')
            qty, price = _number(get('quantity')), _number(get('entry_price'))
            if qty <= 0 or price <= 0:
                raise ValueError('paper_position_notional_unverified')
            spot = quote == 'KRW' or canonical_venue(venue) in {'kis', 'kiwoom', 'mirae', 'shinhan'}
            leverage = 1.0 if spot else _number(get('leverage', 1))
            sizing = (get('entry_evidence', {}) or {}).get('position_sizing') or {}
            if canonical_venue(venue) in {'okx', 'bybit', 'bitget'} and 'contract_size' not in sizing:
                raise ValueError('paper_position_margin_unverified')
            contract = _number(sizing.get('contract_size', 1))
            if leverage < 1 or contract <= 0:
                raise ValueError('paper_position_margin_unverified')
            # Same conservative cost cushion as the atomic pending reservation.
            margin += qty * price * contract / leverage * 1.02
        available = max(0.0, initial + realized - margin)
        if not all(math.isfinite(v) for v in (realized, margin, available)):
            raise ValueError('paper_funds_nonfinite')
        result.update(available_capital=available, capital_basis='paper_reconciled_funds',
                      initial_capital=initial, realized_net_pnl=realized, open_margin=margin)
    except (ValueError, TypeError, OSError, AttributeError, OverflowError) as error:
        # Reasons are finite local codes; private ledger text never reaches UI.
        allowed = {'initial_equity_unverified', 'paper_ledger_reconciliation_budget',
                   'paper_ledger_invalid', 'paper_ledger_currency_unverified',
                   'paper_ledger_pnl_unverified', 'paper_position_mode_unverified',
                   'paper_ledger_event_conflict',
                   'paper_position_notional_unverified', 'paper_position_margin_unverified',
                   'paper_funds_nonfinite'}
        allowed.update({'paper_session_store_unverified', 'paper_session_boundary_unverified'})
        result['reason'] = str(error) if str(error) in allowed else 'paper_funds_reconciliation_required'
    return result


def paper_funds_for(owner, initial_equity, positions, *, venue, quote):
    recovery = getattr(owner, '_paper_recovery_error', '')
    if isinstance(recovery, str) and recovery:
        return {'available_capital': 0.0, 'capital_basis': 'paper_funds_unverified',
                'quote_currency': quote, 'reason': recovery}
    from .paper_strategy_ledger import ledger_path
    path = getattr(getattr(owner, 'recorder', None), 'db_path', None)
    if isinstance(path, (str, Path)) and str(path):
        ledger = Path(path).resolve().parent / 'strategy_paper_outcomes.jsonl'
    else:
        from path_utils import get_current_user_account
        captured = str(getattr(owner, '_opportunity_account', '') or '')
        if captured and captured != str(get_current_user_account() or ''):
            return {'available_capital': 0.0, 'capital_basis': 'paper_funds_unverified',
                    'quote_currency': quote, 'reason': 'paper_account_scope_changed'}
        ledger = ledger_path()
    return paper_available_funds(initial_equity, positions, venue=venue,
                                 quote=quote, ledger_file=ledger)


def remember_capital(owner, *, venue, mode, funds):
    """Bounded owner-scoped evidence; summary reads do not query accounts."""
    import time
    from .strategy_scope import canonical_venue
    state = getattr(owner, '_last_capital_evidence', None)
    if not isinstance(state, dict):
        state = owner._last_capital_evidence = {}
    key = (canonical_venue(venue), str(getattr(mode, 'value', mode)).lower())
    state[key] = {field: funds.get(field) for field in ('available_capital', 'capital_basis',
        'quote_currency', 'initial_capital', 'realized_net_pnl', 'open_margin', 'reason',
        'paper_session_id', 'paper_session_started_at', 'paper_session_basis', 'historical_pnl_restored')}
    state[key]['observed_at'] = time.time()
    while len(state) > 33:
        state.pop(next(iter(state)))
