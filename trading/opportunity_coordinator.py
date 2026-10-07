#!/usr/bin/env python3
"""다중 거래소·증권사의 동일 기회를 연결하고 실행 권한을 조정한다.

동일 BTC 신호를 Bitget과 OKX에서 각각 실행하는 것은 정상적인 병렬 실행이다.
이 모듈은 이를 한 기회로 묶어 관측하되, 같은 거래소/계좌에 같은 주문이
반복 제출되는 경우만 차단한다.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
import json
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence


PARALLEL = "parallel"
SPLIT = "split"
BEST = "best"
EXECUTION_MODES = {PARALLEL, SPLIT, BEST}


def capture_account_scope(owner: Any) -> None:
    """Capture ownership at construction; later global login changes are ignored."""
    from path_utils import get_current_user_account
    owner._opportunity_account = str(get_current_user_account() or '')


def account_scope_for(owner: Any, mode: Any) -> str:
    app = getattr(owner, 'main_app', None)
    settings = getattr(owner, 'settings', None) or getattr(owner, '_paper_settings', None) or {}
    account = (getattr(app, 'account', None) or settings.get('account_id')
               or settings.get('user_id') or getattr(owner, '_opportunity_account', None)
               or 'isolated-owner:' + str(id(app or owner)))
    normalized_mode = str(getattr(mode, 'value', mode) or 'unknown').lower()
    normalized_mode = {'mock': 'paper', 'live_api': 'live'}.get(normalized_mode, normalized_mode)
    # Only a pseudonymous ownership token reaches runtime telemetry.
    return hashlib.sha256(str(account).encode()).hexdigest()[:24] + ':' + normalized_mode


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _normalize_target(value: Any) -> str:
    from .strategy_scope import canonical_venue
    return canonical_venue(str(value or '').strip().lower())


def _normalize_direction(value: Any) -> str:
    normalized = str(value or "HOLD").strip().upper()
    if normalized == "BUY":
        return "LONG"
    if normalized == "SELL":
        return "SHORT"
    return normalized


def _base_symbol(symbol: Any, asset_class: str) -> str:
    raw = str(symbol or "").strip().upper()
    if str(asset_class or "").lower() == "stock":
        return raw
    if "-" in raw and raw.startswith(("KRW-", "USDT-", "USD-")):
        return raw.split("-", 1)[1]
    if "/" in raw:
        return raw.split("/", 1)[0]
    for quote in ("USDT", "USDC", "BUSD", "KRW", "USD"):
        if raw.endswith(quote) and len(raw) > len(quote):
            return raw[: -len(quote)]
    return raw


def _quote_currency(symbol: Any, target: str, asset_class: str) -> str:
    if str(asset_class or "").lower() == "stock":
        return "KRW"
    raw = str(symbol or "").strip().upper()
    if raw.startswith("KRW-") or raw.endswith("/KRW") or raw.endswith("KRW"):
        return "KRW"
    return "USDT"


def normalize_multi_venue_policy(values: Mapping[str, Any] | None) -> Dict[str, Any]:
    raw = dict(values or {})
    aliases = {
        "each": PARALLEL,
        "parallel_independent": PARALLEL,
        "selected_each": PARALLEL,
        "risk_split": SPLIT,
        "split_global_risk": SPLIT,
        "best_only": BEST,
        "best_execution_only": BEST,
    }
    mode = aliases.get(str(raw.get("mode") or PARALLEL).strip().lower())
    if mode is None:
        mode = str(raw.get("mode") or PARALLEL).strip().lower()
    if mode not in EXECUTION_MODES:
        mode = PARALLEL
    targets = raw.get("authorized_targets", raw.get("_authorized_targets", []))
    if isinstance(targets, str):
        targets = targets.replace(";", ",").split(",")
    authorized_targets = list(
        dict.fromkeys(
            _normalize_target(value)
            for value in (targets or [])
            if _normalize_target(value)
        )
    )
    costs = {
        _normalize_target(key): max(0.0, _float(value, 0.0))
        for key, value in dict(raw.get("target_cost_bps", {}) or {}).items()
        if _normalize_target(key)
    }
    max_loss = {
        str(key or "").strip().upper(): max(0.0, _float(value, 0.0))
        for key, value in dict(raw.get("max_loss_by_currency", {}) or {}).items()
        if str(key or "").strip()
    }
    return {
        "enabled": bool(raw.get("enabled", True)),
        "mode": mode,
        "authorized_targets": authorized_targets,
        "opportunity_window_sec": max(
            5, min(3600, int(_float(raw.get("opportunity_window_sec"), 60)))
        ),
        "duplicate_window_sec": max(
            5, min(3600, int(_float(raw.get("duplicate_window_sec"), 120)))
        ),
        "max_parallel_targets": max(
            0, min(20, int(_float(raw.get("max_parallel_targets"), 0)))
        ),
        "best_target": _normalize_target(raw.get("best_target")),
        "target_cost_bps": costs,
        "max_loss_by_currency": max_loss,
        "portfolio_exposure": dict(raw.get("portfolio_exposure", {}) or {}),
    }


@dataclass(frozen=True)
class OpportunityAuthorization:
    allowed: bool
    reason: str
    opportunity_id: str
    idempotency_key: str
    execution_mode: str
    target: str
    base_symbol: str
    direction: str
    quantity_factor: float
    requested_quantity: float
    authorized_quantity: float
    quote_currency: str
    estimated_notional: float
    estimated_loss: float
    aggregate_targets: int
    aggregate_notional: float
    aggregate_estimated_loss: float
    account_scope: str = 'default'
    reserved_capital: float = 0.0
    portfolio_exposure: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OpportunityCoordinator:
    """프로세스 안의 Binance·Unified·증권 실행 경로가 공유하는 조정기."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._reservations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._idempotency: Dict[str, float] = {}
        self._results: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._state_loaded = storage_path is None
        self._exposure_snapshots = {}
        self._exposure_evidence = {}
        self._observed_market_returns = {}

    @contextmanager
    def _transaction(self):
        with self._lock:
            if self.storage_path is None:
                yield
                return
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.storage_path, timeout=2)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS opportunity_runtime (id INTEGER PRIMARY KEY, state TEXT NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT state FROM opportunity_runtime WHERE id=1').fetchone()
                if row:
                    state = json.loads(row[0])
                    self._reservations = state['reservations']
                    self._idempotency = state['idempotency']
                    self._results = state['results']
                    self._exposure_snapshots = state.get('exposure_snapshots', {})
                    self._exposure_evidence = state.get('exposure_evidence', {})
                self._state_loaded = True
                yield
                state = json.dumps({'reservations': self._reservations, 'idempotency': self._idempotency,
                                    'results': self._results, 'exposure_snapshots': self._exposure_snapshots,
                                    'exposure_evidence': self._exposure_evidence}, allow_nan=False)
                db.execute('INSERT OR REPLACE INTO opportunity_runtime VALUES (1, ?)', (state,))

    @staticmethod
    def opportunity_id(
        *,
        asset_class: str,
        symbol: str,
        direction: str,
        strategy_version: str = "",
        signal_time: float | None = None,
        window_sec: int = 60,
    ) -> str:
        now = float(signal_time if signal_time is not None else time.time())
        bucket = int(now // max(1, int(window_sec)))
        identity = "|".join(
            (
                str(asset_class or "").strip().lower(),
                _base_symbol(symbol, asset_class),
                _normalize_direction(direction),
                str(strategy_version or "noah_base").strip(),
                str(bucket),
            )
        )
        return "opp-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _best_target(policy: Mapping[str, Any], targets: Sequence[str]) -> str:
        preferred = _normalize_target(policy.get("best_target"))
        if preferred and preferred in targets:
            return preferred
        costs = dict(policy.get("target_cost_bps", {}) or {})
        if costs:
            return min(
                targets,
                key=lambda target: (
                    _float(costs.get(target), float("inf")),
                    targets.index(target),
                ),
            )
        return targets[0] if targets else ""

    def _cleanup(self, now: float, ttl: int) -> None:
        for key, created_at in list(self._idempotency.items()):
            if now - created_at > ttl:
                self._idempotency.pop(key, None)
        for opportunity_id, targets in list(self._reservations.items()):
            for target, reservation in list(targets.items()):
                if (not (reservation.get('exposure_pending') and reservation.get('status') in {'filled','cancelled','rejected'})
                    and reservation.get('status') not in {'submitting', 'unknown', 'pending'}
                    and now - _float(reservation.get("created_at"), now) > ttl):
                    targets.pop(target, None)
            if not targets:
                self._reservations.pop(opportunity_id, None)
        # Completed diagnostic history is bounded independently of reservations.
        while len(self._results) > 256:
            self._results.pop(next(iter(self._results)))

    @staticmethod
    def _scope_key(opportunity_id: str, account_scope: str) -> str:
        return hashlib.sha256(str(account_scope or 'default').encode()).hexdigest()[:24] + ':' + opportunity_id

    def authorize(
        self,
        *,
        policy: Mapping[str, Any] | None,
        asset_class: str,
        target: str,
        symbol: str,
        direction: str,
        quantity: float,
        price: float,
        stop_fraction: float,
        strategy_version: str = "",
        account_scope: str = "default",
        signal_time: float | None = None,
        reserve: bool = True,
        capital_guard_enabled: bool = False,
        available_capital: float | None = None,
        capital_basis: str = "",
        leverage: float = 1.0,
        contract_size: float = 1.0,
        exposure_snapshot: Mapping[str, Any] | None = None,
    ) -> OpportunityAuthorization:
        normalized = normalize_multi_venue_policy(policy)
        current_target = _normalize_target(target)
        targets = list(normalized["authorized_targets"])
        if not targets:
            targets = [current_target]
        quantity_value = max(0.0, _float(quantity))
        price_value = max(0.0, _float(price))
        stop_value = max(0.0, abs(_float(stop_fraction)))
        direction_value = _normalize_direction(direction)
        base = _base_symbol(symbol, asset_class)
        quote = _quote_currency(symbol, current_target, asset_class)
        opportunity_id = self.opportunity_id(
            asset_class=asset_class,
            symbol=symbol,
            direction=direction_value,
            strategy_version=strategy_version,
            signal_time=signal_time,
            window_sec=normalized["opportunity_window_sec"],
        )
        idempotency_identity = "|".join(
            (
                opportunity_id,
                current_target,
                str(account_scope or "default"),
            )
        )
        idempotency_key = "order-" + hashlib.sha256(
            idempotency_identity.encode("utf-8")
        ).hexdigest()[:24]

        reason = "authorized_parallel"
        allowed = True
        if not bool(normalized["enabled"]):
            reason = "multi_venue_policy_bypassed"
            mode = PARALLEL
        elif current_target not in targets:
            allowed = False
            reason = "target_not_authorized"

        mode = normalized["mode"] if bool(normalized["enabled"]) else PARALLEL
        factor = 1.0
        if mode == SPLIT:
            factor = 1.0 / max(1, len(targets))
            reason = "authorized_risk_split"
        elif mode == BEST:
            best_target = self._best_target(normalized, targets)
            if current_target != best_target:
                allowed = False
                reason = f"best_target_selected:{best_target}"
            else:
                reason = "authorized_best_target"

        authorized_quantity = quantity_value * factor if allowed else 0.0
        estimated_notional = authorized_quantity * price_value * max(0.0, _float(contract_size))
        estimated_loss = estimated_notional * stop_value
        required_capital = estimated_notional / max(1.0, _float(leverage, 1.0)) * 1.02
        now = float(signal_time if signal_time is not None else time.time())
        exposure_evidence = None

        with self._transaction():
            ttl = max(
                normalized["duplicate_window_sec"],
                normalized["opportunity_window_sec"] * 2,
            )
            self._cleanup(now, ttl)
            scope_key = self._scope_key(opportunity_id, account_scope)
            reservations = self._reservations.setdefault(scope_key, {})
            aggregate_targets = len(reservations)
            aggregate_notional = sum(
                _float(item.get("estimated_notional"))
                for item in reservations.values()
                if str(item.get('quote_currency') or '').upper() == quote
            )
            aggregate_loss = sum(
                _float(item.get("estimated_loss"))
                for item in reservations.values()
                if str(item.get("quote_currency") or "").upper() == quote
            )

            if allowed and reserve and idempotency_key in self._idempotency:
                allowed = False
                reason = "duplicate_order_same_target_account_signal"
                authorized_quantity = 0.0
                estimated_notional = 0.0
                estimated_loss = 0.0

            # Uncertain orders survive signal buckets and restart. A new
            # strategy/version must not create another entry while one receipt
            # for this wallet/instrument is still unresolved.
            account_prefix = self._scope_key('', account_scope)
            if allowed and reserve and any(
                key.startswith(account_prefix) and any(
                    item.get('target') == current_target and item.get('base_symbol') == base
                    and item.get('status') in {'submitting', 'unknown', 'pending'}
                    for item in values.values())
                for key, values in self._reservations.items()
            ):
                allowed, reason = False, 'previous_order_reconciliation_required'
                authorized_quantity = estimated_notional = estimated_loss = 0.0

            if allowed and reserve and len(self._reservations) >= 1024 and not reservations:
                allowed, reason = False, 'reservation_capacity_reconciliation_required'
                authorized_quantity = estimated_notional = estimated_loss = 0.0

            if allowed and capital_guard_enabled:
                free = _float(available_capital, -1.0)
                reserved_capital = sum(
                    _float(item.get('reserved_capital'))
                    for key, rows in self._reservations.items() if key.startswith(account_prefix)
                    for item in rows.values()
                    if item.get('target') == current_target and item.get('quote_currency') == quote
                    and item.get('status') in {'reserved', 'submitting', 'pending', 'unknown'}
                )
                if capital_basis == 'paper_funds_unverified':
                    allowed, reason = False, 'paper_funds_reconciliation_required'
                elif capital_basis == 'available_balance_unverified' or free < 0 or price_value <= 0 or required_capital <= 0:
                    allowed, reason = False, 'available_capital_or_notional_unverified'
                elif required_capital > free:
                    allowed, reason = False, 'available_capital_insufficient'
                elif reserved_capital + required_capital > free:
                    allowed, reason = False, 'available_capital_reserved_by_other_orders'
                if not allowed:
                    authorized_quantity = estimated_notional = estimated_loss = 0.0

            # Gross risk is account-wide; collection is done before this lock.
            # Confirmed fills/cancels remain counted until a later full snapshot.
            from .portfolio_exposure import normalize_exposure_policy, normalize_exposure_snapshot, evaluate_exposure
            global_config = normalize_exposure_policy(normalized.get('portfolio_exposure'))
            if reserve and global_config['enabled'] and (asset_class != 'stock' or direction_value != 'SHORT'):
                exposure_key = self._scope_key('', account_scope)
                snapshots = self._exposure_snapshots.setdefault(exposure_key, {})
                if isinstance(exposure_snapshot, Mapping):
                    row = normalize_exposure_snapshot(exposure_snapshot, now=time.time())
                    # An older concurrent query must never replace newer evidence.
                    if _float(row.get('checked_at')) >= _float((snapshots.get(current_target) or {}).get('checked_at')):
                        snapshots[current_target] = row
                for key, rows in list(self._reservations.items()):
                    if not key.startswith(account_prefix): continue
                    for target_name, item in list(rows.items()):
                        observed = snapshots.get(target_name) or {}
                        if (item.get('exposure_pending') and item.get('status') in {'filled', 'cancelled', 'rejected'}
                            and observed.get('status') == 'verified'
                            and _float(observed.get('started_at')) > _float(item.get('terminal_at'), float('inf'))):
                            item['exposure_pending'] = False
                            if item.get('status') in {'cancelled', 'rejected'}:
                                rows.pop(target_name, None)
                pending_gross = [item for key, rows in self._reservations.items() if key.startswith(account_prefix)
                                 for item in rows.values()]
                exposure_evidence = evaluate_exposure(global_config, snapshots, pending_gross, now=time.time(),
                    proposed_currency=quote, proposed_gross=quantity_value * factor * price_value * max(0.0, _float(contract_size)))
                if current_target not in global_config['venues']:
                    exposure_evidence.update(status='blocked', reason='portfolio_current_venue_not_covered')
                self._exposure_evidence[exposure_key] = exposure_evidence
                while len(self._exposure_snapshots) > 128:
                    old = next(iter(self._exposure_snapshots))
                    self._exposure_snapshots.pop(old, None); self._exposure_evidence.pop(old, None)
                if allowed and exposure_evidence['status'] != 'allowed':
                    allowed, reason = False, exposure_evidence['reason']
                    authorized_quantity = estimated_notional = estimated_loss = 0.0

            max_targets = int(normalized["max_parallel_targets"] or 0)
            if (
                allowed
                and max_targets > 0
                and current_target not in reservations
                and len(reservations) >= max_targets
            ):
                allowed = False
                reason = "max_parallel_targets_exceeded"
                authorized_quantity = 0.0
                estimated_notional = 0.0
                estimated_loss = 0.0

            loss_cap = _float(
                normalized["max_loss_by_currency"].get(quote),
                0.0,
            )
            if allowed and loss_cap > 0 and aggregate_loss + estimated_loss > loss_cap:
                allowed = False
                reason = f"aggregate_loss_cap_exceeded:{quote}"
                authorized_quantity = 0.0
                estimated_notional = 0.0
                estimated_loss = 0.0

            if allowed and reserve:
                reservation = {
                    "created_at": now,
                    "idempotency_key": idempotency_key,
                    "target": current_target,
                    "quote_currency": quote,
                    "estimated_notional": estimated_notional,
                    "estimated_loss": estimated_loss,
                    "status": "reserved",
                    "base_symbol": base,
                    "symbol": str(symbol).upper(),
                    "reserved_capital": required_capital if capital_guard_enabled else 0.0,
                    "exposure_pending": bool(exposure_evidence and exposure_evidence["status"] == "allowed"),
                    "opens_exposure": asset_class != "stock" or direction_value != "SHORT",
                }
                reservations[current_target] = reservation
                self._idempotency[idempotency_key] = now
                aggregate_targets = len(reservations)
                aggregate_notional = sum(
                    _float(item.get("estimated_notional"))
                    for item in reservations.values()
                    if str(item.get('quote_currency') or '').upper() == quote
                )
                aggregate_loss = sum(
                    _float(item.get("estimated_loss"))
                    for item in reservations.values()
                    if str(item.get("quote_currency") or "").upper() == quote
                )

        return OpportunityAuthorization(
            allowed=allowed,
            reason=reason,
            opportunity_id=opportunity_id,
            idempotency_key=idempotency_key,
            execution_mode=mode,
            target=current_target,
            base_symbol=base,
            direction=direction_value,
            quantity_factor=factor if allowed else 0.0,
            requested_quantity=quantity_value,
            authorized_quantity=authorized_quantity,
            quote_currency=quote,
            estimated_notional=estimated_notional,
            estimated_loss=estimated_loss,
            aggregate_targets=aggregate_targets,
            aggregate_notional=aggregate_notional,
            aggregate_estimated_loss=aggregate_loss,
            account_scope=account_scope,
            reserved_capital=required_capital if allowed and capital_guard_enabled else 0.0,
            portfolio_exposure=exposure_evidence,
        )

    def release(self, authorization: Mapping[str, Any] | OpportunityAuthorization) -> None:
        values = (
            authorization.to_dict()
            if isinstance(authorization, OpportunityAuthorization)
            else dict(authorization or {})
        )
        opportunity_id = self._scope_key(str(values.get("opportunity_id") or ""), str(values.get('account_scope') or 'default'))
        target = _normalize_target(values.get("target"))
        idempotency_key = str(values.get("idempotency_key") or "")
        with self._transaction():
            targets = self._reservations.get(opportunity_id, {})
            reservation = targets.get(target)
            if reservation and (reservation.get('status') in {'submitting', 'unknown', 'pending'}
                                or reservation.get('exposure_pending') and reservation.get('status') in {'filled', 'cancelled', 'rejected'}):
                return
            targets.pop(target, None)
            if not targets:
                self._reservations.pop(opportunity_id, None)
            if idempotency_key:
                self._idempotency.pop(idempotency_key, None)

    def record_result(
        self,
        authorization: Mapping[str, Any] | OpportunityAuthorization,
        *,
        status: str,
        order_id: str = "",
        detail: str = "",
    ) -> None:
        values = (
            authorization.to_dict()
            if isinstance(authorization, OpportunityAuthorization)
            else dict(authorization or {})
        )
        opportunity_id = self._scope_key(str(values.get("opportunity_id") or ""), str(values.get('account_scope') or 'default'))
        target = _normalize_target(values.get("target"))
        if not opportunity_id or not target:
            return
        with self._transaction():
            reservation = self._reservations.get(opportunity_id, {}).get(target)
            previous = str((reservation or {}).get('status') or '')
            if previous == 'filled' and status in {'submitted', 'pending', 'failed'}:
                status = 'filled'
            elif status == 'submitted':
                status = 'pending'
            elif previous in {'submitting', 'pending', 'unknown'} and status == 'failed':
                status = 'unknown'
            self._results.setdefault(opportunity_id, {})[target] = {
                "status": str(status or "unknown"),
                "order_id": str(order_id or (self._results.get(opportunity_id, {}).get(target) or {}).get("order_id") or ""),
                "detail": str(detail or "")[:300],
                "recorded_at": time.time(),
            }
            reservation = self._reservations.get(opportunity_id, {}).get(target)
            if reservation is not None:
                reservation["status"] = str(status or "unknown")
                if status in {"filled", "cancelled", "rejected"}:
                    reservation["terminal_at"] = time.time()
                if status == "rejected" and previous == "reserved":
                    reservation["exposure_pending"] = False

    def mark_submitting(self, authorization) -> None:
        self.record_result(authorization, status='submitting')

    @staticmethod
    def client_order_id(authorization) -> str:
        values = authorization.to_dict() if isinstance(authorization, OpportunityAuthorization) else dict(authorization or {})
        identity = str(values.get('account_scope') or '') + ':' + str(values.get('idempotency_key') or '')
        return 'na26' + hashlib.sha256(identity.encode()).hexdigest()[:28]

    def pending_submissions(self, *, account_scope: str, target: str, limit=3, offset=0):
        with self._transaction():
            prefix = self._scope_key('', account_scope)
            pending = []
            for key, rows in self._reservations.items():
                item = rows.get(target)
                if not key.startswith(prefix) or not item or item.get('status') not in {'submitting','pending','unknown'}:
                    continue
                authorization = {**item, 'opportunity_id':key.split(':',1)[1], 'account_scope':account_scope}
                pending.append({**authorization, 'order_id':(self._results.get(key,{}).get(target) or {}).get('order_id',''),
                                'client_order_id':self.client_order_id(authorization)})
            if not pending:
                return []
            start = max(0, int(offset)) % len(pending)
            return (pending[start:] + pending[:start])[:max(0,min(3,int(limit)))]

    def reconcile(self, authorization, *, status: str, order_id: str = '') -> None:
        """Only callers with provider-confirmed evidence may use terminal states."""
        if status not in {'filled', 'rejected', 'cancelled'}:
            raise ValueError('confirmed_terminal_state_required')
        self.record_result(authorization, status=status, order_id=order_id)
        if status in {'rejected', 'cancelled'}:
            self.release(authorization)

    def reconcile_order_id(self, *, account_scope: str, target: str, order_id: str, status: str) -> None:
        if not order_id or status not in {'filled', 'rejected', 'cancelled'}:
            return
        with self._transaction():
            prefix = self._scope_key('', account_scope)
            for key, results in self._results.items():
                if not key.startswith(prefix) or (results.get(target) or {}).get('order_id') != order_id:
                    continue
                results[target]['status'] = status
                reservation = self._reservations.get(key, {}).get(target)
                if reservation:
                    reservation['status'] = status
                    reservation['terminal_at'] = time.time()
                    if status in {'rejected', 'cancelled'} and not reservation.get('exposure_pending'):
                        self._reservations[key].pop(target, None)
                        self._idempotency.pop(reservation.get('idempotency_key'), None)

    def observed_return_peers(self, *, account_scope, venue, quote, histories, history_times, now):
        """Account/mode-scoped bounded public history; no UI/provider/disk I/O."""
        with self._lock:
            scope = self._observed_market_returns.setdefault(account_scope, {})
            for symbol, returns in histories.items():
                scope[(venue,symbol)] = {'venue':venue, 'symbol':symbol, 'quote':quote,
                                        'returns':returns, 'observed_at':history_times[symbol]}
            for key,row in list(scope.items()):
                if not 0 <= now-row['observed_at'] < 3600: scope.pop(key,None)
            while len(scope)>330: scope.pop(next(iter(scope)))
            while len(self._observed_market_returns)>32:
                self._observed_market_returns.pop(next(iter(self._observed_market_returns)))
            return [row for row in scope.values() if row['quote']==quote]

    def publish_exposure(self, *, account_scope, target, snapshot):
        from .portfolio_exposure import normalize_exposure_snapshot
        clean = normalize_exposure_snapshot(snapshot, now=time.time())
        key = self._scope_key('', account_scope)
        with self._transaction():
            snapshots = self._exposure_snapshots.setdefault(key, {})
            if _float(clean.get('checked_at')) >= _float((snapshots.get(target) or {}).get('checked_at')):
                snapshots[target] = clean
            while len(self._exposure_snapshots) > 128:
                old = next(iter(self._exposure_snapshots))
                self._exposure_snapshots.pop(old, None); self._exposure_evidence.pop(old, None)

    def runtime_snapshot(self, *, account_scope: str, target: str) -> Dict[str, Any]:
        # Presentation never performs disk/provider I/O. Other processes are
        # synchronized at the next transaction, not by a UI polling timer.
        with self._lock:
            if not self._state_loaded:
                return {'status': 'not_observed', 'pending_orders': None, 'requires_reconciliation': False}
            prefix = self._scope_key('', account_scope)
            items = [dict(row) for key, rows in self._reservations.items() if key.startswith(prefix)
                     for row in rows.values() if row.get('target') == target]
            unresolved = [r for r in items if r.get('status') in {'submitting', 'pending', 'unknown'}]
            return {'pending_orders': len(unresolved), 'reserved_orders': sum(r.get('status') == 'reserved' for r in items),
                    'oldest_pending_at': min((r['created_at'] for r in unresolved), default=None),
                    'requires_reconciliation': bool(unresolved), 'restart_persistent': self.storage_path is not None,
                    'scope': 'account_mode_venue', 'available_funds_certified': False,
                    'portfolio_exposure': self._exposure_evidence.get(prefix)}

    def snapshot(self, opportunity_id: str, *, account_scope: str = 'default') -> Dict[str, Any]:
        scoped_id = self._scope_key(opportunity_id, account_scope)
        with self._transaction():
            reservations = {
                key: dict(value)
                for key, value in self._reservations.get(scoped_id, {}).items()
            }
            results = {
                key: dict(value)
                for key, value in self._results.get(scoped_id, {}).items()
            }
        return {
            "opportunity_id": opportunity_id,
            "reservations": reservations,
            "results": results,
        }


_DEFAULT_COORDINATOR = OpportunityCoordinator()
_COORDINATORS: Dict[str, OpportunityCoordinator] = {}
_COORDINATORS_LOCK = threading.RLock()


def get_opportunity_coordinator(owner=None) -> OpportunityCoordinator:
    cached = getattr(owner, '_opportunity_coordinator', None)
    if isinstance(cached, OpportunityCoordinator):
        return cached
    path = getattr(getattr(owner, 'recorder', None), 'db_path', None)
    if not isinstance(path, (str, Path)) or not str(path):
        return _DEFAULT_COORDINATOR
    storage_path = str(Path(path).resolve().parent / 'opportunity_runtime.db')
    with _COORDINATORS_LOCK:
        if storage_path not in _COORDINATORS:
            _COORDINATORS[storage_path] = OpportunityCoordinator(storage_path)
        coordinator = _COORDINATORS[storage_path]
        if owner is not None:
            owner._opportunity_coordinator = coordinator
        return coordinator


def finish_submission(owner, authorization, receipt, *, success=False, confirmed=False) -> None:
    if not authorization:
        return
    from .execution_optimizer import ExecutionOptimizer
    row = receipt if isinstance(receipt, dict) else {}
    state = ExecutionOptimizer._submission_state(success, row)
    raw = (row.get('raw_result') if isinstance(row.get('raw_result'), dict)
           else row.get('order') if isinstance(row.get('order'), dict) else row)
    provider_status = str(raw.get('status') or row.get('status') or '').upper()
    terminal_filled = provider_status in {'FILLED', 'CLOSED'}
    status = 'filled' if confirmed and terminal_filled else 'pending' if state == 'accepted' else 'rejected' if state == 'rejected' else 'unknown'
    order_id = str(raw.get('orderId') or raw.get('id') or row.get('order_id') or row.get('orderId') or row.get('id') or row.get('order_no') or '')
    if confirmed and order_id and provider_status in {'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'EXPIRED_IN_MATCH'}:
        status = 'rejected' if provider_status == 'REJECTED' else 'cancelled'
    coordinator = get_opportunity_coordinator(owner)
    if status in {'filled', 'rejected', 'cancelled'}:
        coordinator.reconcile(authorization, status=status, order_id=order_id)
    else:
        coordinator.record_result(authorization, status=status, order_id=order_id)


def policy_from_settings(
    settings: Mapping[str, Any] | None,
    *,
    authorized_targets: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    values = dict((settings or {}).get("multi_venue_execution", {}) or {})
    if authorized_targets is not None:
        values["authorized_targets"] = list(authorized_targets)
    return normalize_multi_venue_policy(values)
