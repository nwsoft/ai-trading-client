"""Explicit new simulated baselines; never rewrite or certify old trade history."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from filelock import FileLock

MAX_PREFIX = 64 * 1024 * 1024


def _store(ledger):
    return Path(ledger).with_name('paper_funds_sessions.json')


def _key(venue, quote):
    from .strategy_scope import canonical_venue
    return f'{canonical_venue(venue)}:{quote.upper()}'


def _load(ledger):
    path = _store(ledger)
    if not path.exists():
        return {'schema_version': 1, 'sessions': {}}
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema_version') != 1 or not isinstance(value.get('sessions'), dict):
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        raise ValueError('paper_session_store_unverified') from exc


def _prefix_digest(ledger, offset):
    if not isinstance(offset, int) or isinstance(offset, bool) or not 0 < offset <= MAX_PREFIX:
        raise ValueError('paper_session_boundary_unverified')
    digest = hashlib.sha256()
    try:
        with Path(ledger).open('rb') as handle:
            remaining = offset
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('paper_session_boundary_unverified')
                digest.update(chunk)
                remaining -= len(chunk)
            if chunk[-1:] != b'\n':
                raise ValueError('paper_session_boundary_unverified')
    except OSError as exc:
        raise ValueError('paper_session_boundary_unverified') from exc
    return digest.hexdigest()


def read_session(ledger, *, venue, quote):
    row = _load(ledger)['sessions'].get(_key(venue, quote))
    if row is None:
        return None
    try:
        if (not isinstance(row, dict) or row['venue_quote'] != _key(venue, quote)
                or not row['session_id'] or not row['started_at']
                or row.get('basis') != 'explicit_new_paper_evaluation'
                or _prefix_digest(ledger, row['ledger_offset']) != row['preserved_sha256']):
            raise ValueError()
        if isinstance(row['initial_capital'], bool):
            raise ValueError()
        capital = float(row['initial_capital'])
        if not math.isfinite(capital) or capital <= 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError('paper_session_boundary_unverified') from exc
    return dict(row)


def start_session(ledger, *, venue, quote, initial_equity, positions, stopped, pending_orders):
    """Caller explicitly requests a *new* evaluation, after stopping and flattening.

    Only a legacy-blocked wallet is eligible. Once created it cannot be reset
    again through this path, even after losses or another unverified record.
    LIVE holdings, order rights, strategies and statistics baselines are untouched.
    """
    from .paper_strategy_ledger import _LOCK
    from .paper_capital import paper_available_funds
    if stopped is not True:
        raise ValueError('paper_session_stop_required')
    if positions:
        raise ValueError('paper_session_flat_required')
    if pending_orders != 0 or isinstance(pending_orders, bool):
        raise ValueError('paper_session_pending_orders')
    try:
        if isinstance(initial_equity, bool):
            raise ValueError()
        capital = float(initial_equity)
        if not math.isfinite(capital) or capital <= 0:
            raise ValueError()
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('initial_equity_unverified') from exc
    ledger = Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(_store(ledger))+'.lock', timeout=2), _LOCK:
        state = _load(ledger)
        existing = read_session(ledger, venue=venue, quote=quote)
        if existing is not None:
            return {**existing, 'created': False}
        funds = paper_available_funds(capital, {}, venue=venue, quote=quote, ledger_file=ledger)
        if funds.get('reason') not in {'paper_ledger_currency_unverified', 'paper_ledger_pnl_unverified'}:
            raise ValueError('paper_session_legacy_block_required')
        offset = ledger.stat().st_size
        row = dict(session_id=f'paper_session_{uuid4().hex}', venue_quote=_key(venue, quote),
                   initial_capital=capital, ledger_offset=offset,
                   preserved_sha256=_prefix_digest(ledger, offset),
                   started_at=datetime.now(timezone.utc).isoformat(),
                   basis='explicit_new_paper_evaluation', previous_reason=funds['reason'])
        state['sessions'][_key(venue, quote)] = row
        temporary = _store(ledger).with_suffix('.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as handle:
                json.dump(state, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, _store(ledger))
        finally:
            temporary.unlink(missing_ok=True)
        return {**row, 'created': True}
