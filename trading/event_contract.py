"""Versioned event metadata. Missing historical evidence stays unknown."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

SESSION_ID = f"{os.getpid()}-{uuid.uuid4().hex}"
MODES = {"learning", "paper", "live"}
CONTRACT_VERSION = 1
MODE_ALIASES = {
    "learning": "learning", "observe": "learning", "analysis": "learning",
    "paper": "paper", "mock": "paper", "simulation": "paper",
    "live": "live", "live_api": "live", "real": "live",
    # Historical Binance values represented a LIVE execution style.
    "optimized": "live", "manual": "live",
}


def venue_key(value):
    value = str(value).strip().lower()
    return {'miraeasset':'mirae','koreainvestment':'kis'}.get(value,value)


def execution_mode_key(value):
    return MODE_ALIASES.get(str(getattr(value, 'value', value) or '').strip().lower(), 'unknown')


def input_issues(kind, data, exchange=None):
    """Validate original evidence BEFORE normalization can hide a conflict.

    Historical metadata is deliberately handled separately. This never grants
    order permission or guesses which of two contradictory facts is correct.
    """
    owners = {venue_key(v) for v in (exchange, data.get('exchange'), data.get('broker'),
              str(kind).split('::', 1)[1] if str(kind).startswith('trade_runtime::') else None)
              if isinstance(v, str) and v.strip() and v != 'unknown'}
    validation = data.get('validation') if isinstance(data.get('validation'), dict) else {}
    raw_modes = [v for v in (data.get('execution_mode'), validation.get('execution_mode')) if v]
    modes = {execution_mode_key(v) for v in raw_modes}
    issues = []
    if len(owners) > 1: issues.append('conflict:exchange')
    if len(modes - {'unknown'}) > 1: issues.append('conflict:execution_mode')
    if 'unknown' in modes: issues.append('invalid:execution_mode')
    return issues


def _instrument_contract(owner, data):
    """Return a common asset envelope without guessing an unknown instrument."""
    try:
        from trading.exchanges.venue_capabilities import venue_capabilities, venue_service
        capabilities = venue_capabilities(owner)
        service = venue_service(owner)
    except Exception:
        capabilities, service = {}, ''
    explicit = str(data.get('instrument_type') or data.get('asset_class') or '').strip().lower()
    if explicit in {'etf', 'stock', 'spot', 'futures', 'derivative'}:
        instrument = explicit
    elif data.get('is_etf') is True:
        instrument = 'etf'
    elif service == 'stock' and data.get('is_etf') is False:
        instrument = 'stock'
    else:
        instrument = str(capabilities.get('market_type') or 'unknown').lower()
    asset_class = 'crypto' if service == 'blockchain' else ('securities' if service == 'stock' else 'unknown')
    return asset_class, instrument


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def metadata(kind: str, data: dict, *, exchange: str | None = None, historical: bool = False,
             created_at: str | None = None) -> dict:
    from config.app_version import RELEASE_VERSION
    kind = str(kind or 'unknown')
    def scalar(value):
        return str(value) if isinstance(value,(str,int,float)) and not isinstance(value,bool) else None
    owners = {venue_key(v) for v in (exchange, data.get("exchange"), data.get("broker"),
              kind.split("::", 1)[1] if kind.startswith("trade_runtime::") else None) if isinstance(v,str) and v.strip()}
    validation = data.get('validation') if isinstance(data.get('validation'),dict) else {}
    modes = {execution_mode_key(value) for value in (data.get('execution_mode'),validation.get('execution_mode')) if value}
    modes.discard('unknown')
    mode = next(iter(modes)) if len(modes)==1 else 'unknown'
    candidate = data.get('trade_candidate') or validation.get('trade_candidate') or {}
    if not isinstance(candidate,dict): candidate = {}
    raw_time = data.get("event_time") or data.get("recorded_at") or created_at
    try:
        instant = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        # SQLite CURRENT_TIMESTAMP is UTC; other naive historical times are not proven.
        if instant.tzinfo is None and raw_time != created_at:
            raise ValueError("unknown timezone")
        instant = instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)
        event_time = instant.isoformat(timespec="microseconds")
    except (TypeError, ValueError):
        event_time = None if historical else datetime.now(timezone.utc).isoformat(timespec="microseconds")
    owner = next(iter(owners)) if len(owners) == 1 else "unknown"
    asset_class, instrument_type = _instrument_contract(owner,data)
    result = data.get('result') if isinstance(data.get('result'),dict) else {}
    reason_code = (data.get("reason_code") or data.get('_learning_decision') or data.get('reason')
                   or validation.get('reason') or validation.get('status'))
    decision_status = data.get('decision_status') or data.get('status') or data.get('action') or data.get('signal')
    return {
        "contract_version": CONTRACT_VERSION,
        "exchange": owner,
        "execution_mode": mode,
        "asset_class": asset_class,
        "instrument_type": instrument_type,
        "event_time": event_time,
        "strategy_version_id": scalar(data.get("strategy_version_id") or data.get("selected_custom_strategy_version_id") or data.get('_selected_custom_strategy_version_id') or candidate.get('strategy_version_id')),
        "strategy_key": scalar(data.get("strategy_key") or data.get("selected_custom_strategy_key") or data.get('_selected_custom_strategy_key') or candidate.get('strategy_key')),
        "reason_code": scalar(reason_code) or "unknown",
        "decision_status": scalar(decision_status) or "unknown",
        "app_version": scalar(data.get("app_version")) or ("unknown" if historical else RELEASE_VERSION),
        "session_id": scalar(data.get("session_id")) or ("unknown" if historical else SESSION_ID),
        "event_kind": scalar(data.get("event_kind")) or ("decision" if kind.startswith("trade_runtime::") else kind),
        "actual_order": int(data["actual_order"]) if isinstance(data.get("actual_order"), (bool,int)) and data['actual_order'] in (0,1) else None,
        "ledger_id": str(data.get('ledger_id') or result.get('ledger_id')) if (data.get('ledger_id') or result.get('ledger_id')) is not None else None,
        "order_id": str(data.get('order_id') or result.get('order_id') or result.get('id')) if (data.get('order_id') or result.get('order_id') or result.get('id')) is not None else None,
    }


def runtime_decision(exchange, symbol, status, reason, execution_mode, **extra):
    data = {'exchange':exchange, 'symbol':symbol, 'status':status, 'reason':reason,
            'execution_mode':execution_mode, 'reason_code':status,
            'recorded_at':datetime.now(timezone.utc).isoformat(), **extra}
    # Keep contradictory original fields intact for the persistence boundary.
    if input_issues('trade_runtime::'+exchange, data, exchange):
        return data
    return {**data, **metadata('trade_runtime::'+exchange,data,exchange=exchange)}


def contract_issues(value: dict) -> list[str]:
    """Return missing/invalid outer-contract fields without blocking execution.

    Adapter implementations and asset-specific evidence may differ, but every
    persisted decision must remain attributable and explainable.  This helper
    is intentionally suitable for onboarding and regression tests; a logging
    defect must never become an implicit order permission.
    """
    required = (
        'contract_version', 'exchange', 'execution_mode', 'asset_class',
        'instrument_type', 'event_time', 'event_kind', 'decision_status',
        'reason_code', 'actual_order',
    )
    issues = [f'missing:{key}' for key in required if key not in value]
    if value.get('execution_mode') not in MODES:
        issues.append('invalid:execution_mode')
    if value.get('asset_class') not in {'crypto', 'securities'}:
        issues.append('invalid:asset_class')
    if value.get('actual_order') not in (None, 0, 1, False, True):
        issues.append('invalid:actual_order')
    if str(value.get('exchange') or '') in {'', 'unknown'}:
        issues.append('unattributed:exchange')
    return issues


def hold_key(symbol: str, kind: str, data: dict, meta: dict) -> str | None:
    """Only byte-equivalent decision evidence may share a one-minute bucket."""
    if str(data.get("status", "")).lower() != "hold" or meta["event_kind"] != "decision":
        return None
    if meta["exchange"] == "unknown" or meta["execution_mode"] == "unknown":
        return None
    if data.get('order_id') is not None or data.get('ledger_id') is not None or data.get('actual_order'):
        return None
    text = canonical_json(data).lower()
    if any(word in text for word in ("blocked", "risk", "pnl_", "차단", "위험", "손실")):
        return None
    evidence = {k: v for k, v in data.items() if k not in {"event_time", "recorded_at", "timestamp"}}
    return hashlib.sha256(canonical_json([symbol, kind, evidence, meta["exchange"], meta["execution_mode"],
        meta["session_id"], str(meta["event_time"])[:16]]).encode()).hexdigest()
