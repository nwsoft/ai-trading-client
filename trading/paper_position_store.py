"""Crash-safe persistence for simulated open positions.

Closed PAPER outcomes are an append-only ledger, but an open simulated
position also has to survive an application/update restart.  This module keeps
that transient state separate from LIVE positions and never calls an exchange.
"""

from __future__ import annotations

import json
import os
import threading
import math
from filelock import FileLock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


_LOCKS: Dict[str, threading.RLock] = {}
_PROCESS_LOCKS: Dict[str, FileLock] = {}


def position_lock(path: Path):
    key = str(path.resolve())
    if key not in _PROCESS_LOCKS:
        _PROCESS_LOCKS[key] = FileLock(key + ".lock", timeout=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    return _PROCESS_LOCKS[key]


def _lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.RLock()
    return _LOCKS[key]


def position_store_path(settings: Dict[str, Any] | None, engine: str) -> Path:
    settings = settings if isinstance(settings, dict) else {}
    explicit = settings.get(f"paper_position_store_path_{engine}")
    if explicit:
        return Path(str(explicit)).expanduser()
    from path_utils import get_app_data_dir
    return Path(get_app_data_dir()) / f"paper_open_positions_{engine}.json"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    enum_value = getattr(value, "value", None)
    return _json_safe(enum_value if enum_value is not None else str(value))


def serialize_position(position: Any) -> Dict[str, Any]:
    fields = (
        "symbol", "side", "entry_price", "current_price", "quantity", "leverage",
        "unrealized_pnl", "unrealized_pnl_percent", "entry_time", "tp_price", "sl_price",
        "position_id", "entry_order_id", "entry_order_ids", "entry_time_source",
        "execution_mode", "position_owner", "custom_strategy_id", "custom_strategy_name",
        "custom_strategy_rules", "custom_strategy_key", "custom_strategy_version_id",
        "custom_strategy_scope", "exit_policy", "entry_evidence", "custom_order_plan_state",
        "spot_baseline_quantity",
        "pnl_calculation_status",
    )
    return {name: _json_safe(getattr(position, name, None)) for name in fields}


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deserialize_position(row: Dict[str, Any], position_cls: Any, side_cls: Any) -> Any:
    if str(row.get("execution_mode") or "").lower() != "paper":
        raise ValueError("non_paper_position_rejected")
    symbol = str(row.get("symbol") or "").strip()
    entry_price = float(row.get("entry_price") or 0.0)
    quantity = float(row.get("quantity") or 0.0)
    if (not symbol or any(isinstance(row.get(k), bool) for k in ("entry_price", "quantity"))
            or not all(math.isfinite(n) and n > 0 for n in (entry_price, quantity))):
        raise ValueError("invalid_paper_position_identity")
    side = side_cls(str(getattr(row.get("side"), "value", row.get("side")) or "").upper())
    return position_cls(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        current_price=float(row.get("current_price") or entry_price),
        quantity=quantity,
        leverage=max(1, int(row.get("leverage") or 1)),
        unrealized_pnl=float(row.get("unrealized_pnl") or 0.0),
        unrealized_pnl_percent=float(row.get("unrealized_pnl_percent") or 0.0),
        entry_time=_parse_datetime(row.get("entry_time")),
        tp_price=None if row.get("tp_price") is None else float(row.get("tp_price")),
        sl_price=None if row.get("sl_price") is None else float(row.get("sl_price")),
        position_id=str(row.get("position_id") or "") or None,
        entry_order_id=str(row.get("entry_order_id") or "") or None,
        entry_order_ids=[str(item) for item in list(row.get("entry_order_ids") or []) if item],
        entry_time_source=str(row.get("entry_time_source") or "execution"),
        execution_mode="paper",
        position_owner=str(row.get("position_owner") or "legacy_unknown"),
        custom_strategy_id=str(row.get("custom_strategy_id") or "") or None,
        custom_strategy_name=str(row.get("custom_strategy_name") or "") or None,
        custom_strategy_rules=dict(row.get("custom_strategy_rules") or {}),
        custom_strategy_key=str(row.get("custom_strategy_key") or "") or None,
        custom_strategy_version_id=str(row.get("custom_strategy_version_id") or "") or None,
        custom_strategy_scope=str(row.get("custom_strategy_scope") or "") or None,
        exit_policy=dict(row.get("exit_policy") or {}),
        entry_evidence=dict(row.get("entry_evidence") or {}),
        custom_order_plan_state=dict(row.get("custom_order_plan_state") or {}),
        spot_baseline_quantity=float(row.get("spot_baseline_quantity") or 0.0),
        pnl_calculation_status=str(row.get('pnl_calculation_status') or ''),
    )


def save_positions(path: Path, stores: Dict[str, Dict[str, Any]], *, ledger_file: Path | None = None) -> None:
    payload = {
        "schema_version": 1,
        "execution_mode": "paper",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "venues": {
            str(venue).lower(): {
                str(symbol): serialize_position(position)
                for symbol, position in dict(positions or {}).items()
            }
            for venue, positions in dict(stores or {}).items()
        },
    }
    if ledger_file is not None:
        payload['close_ledger_checkpoint'] = ledger_checkpoint(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with _lock(path), position_lock(path):
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(path)
        fsync_parent(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def load_positions(path: Path, position_cls: Any, side_cls: Any, *, ledger_file: Path | None = None) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("paper_position_store_budget")
    with _lock(path), position_lock(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
    if ledger_file is not None and payload.get('close_ledger_checkpoint') is not None:
        validate_ledger_checkpoint(ledger_file, payload['close_ledger_checkpoint'])
    if int(payload.get("schema_version") or 0) != 1 or payload.get("execution_mode") != "paper":
        raise ValueError("unsupported_paper_position_store")
    restored: Dict[str, Dict[str, Any]] = {}
    for venue, positions in dict(payload.get("venues") or {}).items():
        venue_positions: Dict[str, Any] = {}
        for symbol, row in dict(positions or {}).items():
            try:
                position = deserialize_position(dict(row or {}), position_cls, side_cls)
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("paper_position_store_invalid") from exc
            venue_positions[str(symbol)] = position
        restored[str(venue).lower()] = venue_positions
    return restored


def close_state(position: Any) -> dict:
    """Only identity/units/confirmed state; prices observed later are not proof."""
    row = serialize_position(position)
    return {
        'position_id': row['position_id'], 'symbol': row['symbol'], 'side': row['side'],
        'entry_time': row['entry_time'], 'entry_price': row['entry_price'],
        'quantity': row['quantity'],
        'contract_size': (row.get('entry_evidence') or {}).get('position_sizing', {}).get('contract_size'),
        'completed': sorted((row.get('custom_order_plan_state') or {}).get('completed_partial_indices', [])),
    }


def recovery_digest(value: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def close_recovery_evidence(position: Any, *, quantity: float, plan: dict) -> dict:
    import math
    before = close_state(position)
    if not before['position_id'] or not math.isfinite(quantity) or not 0 < quantity <= before['quantity']:
        raise ValueError('paper_close_recovery_identity_unverified')
    after = {**before, 'quantity': max(0., before['quantity'] - quantity),
             'completed': sorted(plan.get('completed_partial_indices', []))}
    value = {'schema_version': 1, 'before': before, 'after': after, 'after_plan': plan}
    return {**value, 'sha256': recovery_digest(value)}


def reconcile_close_events(stores: dict, ledger_file: Path, *, execution_scope: str = 'unified') -> bool:
    """Replay durable closes once; missing legacy proof blocks instead of guessing."""
    import math
    from filelock import FileLock
    from trading.paper_strategy_ledger import read_close_ledger, close_outcome_digest, paper_outcome_calculation_status
    if execution_scope not in {'unified', 'binance'}:
        raise ValueError('paper_close_recovery_scope_invalid')
    if not ledger_file.exists():
        if any((p.entry_evidence or {}).get('paper_close_events') for ps in stores.values() for p in ps.values()):
            raise ValueError('paper_close_recovery_ledger_changed')
        return False
    with FileLock(str(ledger_file) + '.lock', timeout=10):
        rows = read_close_ledger(ledger_file)
    known = {str(row.get('event_id') or '') for row in rows}
    if any(not set((p.entry_evidence or {}).get('paper_close_events', [])).issubset(known) for ps in stores.values() for p in ps.values()):
        raise ValueError('paper_close_recovery_ledger_changed')
    changed = False
    for row in rows:
        if str(row.get('scope') or '').lower() != execution_scope:
            continue
        venue, symbol = str(row.get('exchange') or '').lower(), str(row.get('symbol') or '')
        position = (stores.get(venue) or {}).get(symbol)
        evidence = row.get('close_recovery')
        if not evidence:
            if position is None or not position.position_id:
                continue
            identity = str(row.get('position_id') or '')
            parent = str(position.position_id)
            if identity == parent:
                raise ValueError('paper_close_recovery_evidence_missing')
            if identity.startswith(parent + ':partial:'):
                try:
                    index = int(identity[len(parent + ':partial:'):])
                except ValueError as exc:
                    raise ValueError('paper_close_recovery_evidence_missing') from exc
                if index not in (position.custom_order_plan_state or {}).get('completed_partial_indices', []):
                    raise ValueError('paper_close_recovery_evidence_missing')
            continue
        if not isinstance(evidence, dict):
            raise ValueError('paper_close_recovery_evidence_invalid')
        content = {k: v for k, v in evidence.items() if k != 'sha256'}
        if (content.get('schema_version') != 1 or recovery_digest(content) != evidence.get('sha256')
            or content.get('outcome_sha256') != close_outcome_digest(row)
            or paper_outcome_calculation_status(row) != 'valid'):
            raise ValueError('paper_close_recovery_evidence_invalid')
        before, after = content['before'], content['after']
        identity = str(before.get('position_id') or '')
        # Bind the recovery state to the actual ledger slice and execution venue.
        same = all(before.get(k) == after.get(k) for k in ('position_id','symbol','side','entry_time','entry_price','contract_size'))
        unit_matches = before['contract_size'] == row.get('contract_size') or (
            venue in {'upbit', 'bithumb', 'coinone', 'binance'}
            and before['contract_size'] is None and row.get('contract_size') == 1.0
        )  # Intrinsic base-asset quantity contract; never infer foreign futures.
        valid_numbers = all(not isinstance(v,bool) and math.isfinite(float(v)) for v in (before['quantity'], after['quantity'], row['quantity']))
        if (not identity or not same or not valid_numbers or before['symbol'] != symbol
            or not 0 <= after['quantity'] < before['quantity']
            or abs(before['quantity'] - after['quantity'] - row['quantity']) > max(1e-9, before['quantity']*1e-10)
            or before['entry_price'] != row['entry_price'] or before['side'] != row['side']
            or not unit_matches
            or str(row.get('position_id') or '') not in {identity, identity+':partial:'+str(index_from_plan(content))}):
            raise ValueError('paper_close_recovery_evidence_invalid')
        import hashlib
        event_identity = '|'.join((execution_scope, venue, str(row['position_id'])))
        expected_event = 'paper_outcome_' + hashlib.sha256(event_identity.encode()).hexdigest()[:32]
        is_full = str(row['position_id']) == identity
        if (row.get('event_id') != expected_event
            or sorted(content['after_plan'].get('completed_partial_indices', [])) != after['completed']
            or not set(before['completed']).issubset(after['completed'])
            or (is_full and (after['quantity'] != 0 or after['completed'] != before['completed']))
            or (not is_full and index_from_plan(content) is None)):
            raise ValueError('paper_close_recovery_evidence_invalid')
        if position is None or str(position.position_id or '') != identity:
            continue  # already fully closed, or a different later position
        state = close_state(position)
        applied = list((position.entry_evidence or {}).get('paper_close_events', []))
        event = str(row.get('event_id') or '')
        if not event:
            raise ValueError('paper_close_recovery_evidence_invalid')
        if event in applied:
            # A later close may have reduced quantity further, but cannot increase it.
            if state['quantity'] > after['quantity'] or not set(after['completed']).issubset(state['completed']):
                raise ValueError('paper_close_recovery_snapshot_conflict')
            continue
        if state not in (before, after):
            raise ValueError('paper_close_recovery_snapshot_conflict')
        if after['quantity'] == 0:
            stores[venue].pop(symbol)
        else:
            position.quantity = after['quantity']
            position.custom_order_plan_state = dict(content['after_plan'])
            position.entry_evidence = {**(position.entry_evidence or {}), 'paper_close_events': applied + [event]}
        changed = True
    return changed


def index_from_plan(content: dict):
    new_indices = set(content['after']['completed']) - set(content['before']['completed'])
    return next(iter(new_indices)) if len(new_indices) == 1 else None


def fsync_parent(path: Path):
    # Windows file fsync/atomic replace is exercised in installation acceptance;
    # directory fsync is available on POSIX, not emulated on Windows.
    if os.name == 'posix':
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def ledger_checkpoint(path: Path) -> dict:
    import hashlib
    from filelock import FileLock
    with FileLock(str(path) + '.lock', timeout=10):
        if path.exists() and path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('paper_close_recovery_budget')
        data = path.read_bytes() if path.exists() else b''
    return {'schema_version': 1, 'offset': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def validate_ledger_checkpoint(path: Path, checkpoint: dict):
    import hashlib
    from filelock import FileLock
    if (not isinstance(checkpoint, dict) or checkpoint.get('schema_version') != 1
        or type(checkpoint.get('offset')) is not int or not 0 <= checkpoint['offset'] <= 64*1024*1024):
        raise ValueError('paper_close_recovery_checkpoint_invalid')
    with FileLock(str(path) + '.lock', timeout=10):
        if (not path.exists() and checkpoint['offset']) or (path.exists() and path.stat().st_size < checkpoint['offset']):
            raise ValueError('paper_close_recovery_ledger_changed')
        data = b''
        if path.exists():
            with path.open('rb') as handle:
                data = handle.read(checkpoint['offset'])
    if hashlib.sha256(data).hexdigest() != checkpoint.get('sha256'):
        raise ValueError('paper_close_recovery_ledger_changed')
