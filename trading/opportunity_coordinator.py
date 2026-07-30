#!/usr/bin/env python3
"""다중 거래소·증권사의 동일 기회를 연결하고 실행 권한을 조정한다.

동일 BTC 신호를 Bitget과 OKX에서 각각 실행하는 것은 정상적인 병렬 실행이다.
이 모듈은 이를 한 기회로 묶어 관측하되, 같은 거래소/계좌에 같은 주문이
반복 제출되는 경우만 차단한다.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence


PARALLEL = "parallel"
SPLIT = "split"
BEST = "best"
EXECUTION_MODES = {PARALLEL, SPLIT, BEST}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_target(value: Any) -> str:
    return str(value or "").strip().lower()


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OpportunityCoordinator:
    """프로세스 안의 Binance·Unified·증권 실행 경로가 공유하는 조정기."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reservations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._idempotency: Dict[str, float] = {}
        self._results: Dict[str, Dict[str, Dict[str, Any]]] = {}

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
                if now - _float(reservation.get("created_at"), now) > ttl:
                    targets.pop(target, None)
            if not targets:
                self._reservations.pop(opportunity_id, None)

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
        estimated_notional = authorized_quantity * price_value
        estimated_loss = estimated_notional * stop_value
        now = float(signal_time if signal_time is not None else time.time())

        with self._lock:
            ttl = max(
                normalized["duplicate_window_sec"],
                normalized["opportunity_window_sec"] * 2,
            )
            self._cleanup(now, ttl)
            reservations = self._reservations.setdefault(opportunity_id, {})
            aggregate_targets = len(reservations)
            aggregate_notional = sum(
                _float(item.get("estimated_notional"))
                for item in reservations.values()
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
                }
                reservations[current_target] = reservation
                self._idempotency[idempotency_key] = now
                aggregate_targets = len(reservations)
                aggregate_notional = sum(
                    _float(item.get("estimated_notional"))
                    for item in reservations.values()
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
        )

    def release(self, authorization: Mapping[str, Any] | OpportunityAuthorization) -> None:
        values = (
            authorization.to_dict()
            if isinstance(authorization, OpportunityAuthorization)
            else dict(authorization or {})
        )
        opportunity_id = str(values.get("opportunity_id") or "")
        target = _normalize_target(values.get("target"))
        idempotency_key = str(values.get("idempotency_key") or "")
        with self._lock:
            targets = self._reservations.get(opportunity_id, {})
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
        opportunity_id = str(values.get("opportunity_id") or "")
        target = _normalize_target(values.get("target"))
        if not opportunity_id or not target:
            return
        with self._lock:
            self._results.setdefault(opportunity_id, {})[target] = {
                "status": str(status or "unknown"),
                "order_id": str(order_id or ""),
                "detail": str(detail or ""),
                "recorded_at": time.time(),
            }
            reservation = self._reservations.get(opportunity_id, {}).get(target)
            if reservation is not None:
                reservation["status"] = str(status or "unknown")

    def snapshot(self, opportunity_id: str) -> Dict[str, Any]:
        with self._lock:
            reservations = {
                key: dict(value)
                for key, value in self._reservations.get(opportunity_id, {}).items()
            }
            results = {
                key: dict(value)
                for key, value in self._results.get(opportunity_id, {}).items()
            }
        return {
            "opportunity_id": opportunity_id,
            "reservations": reservations,
            "results": results,
        }


_DEFAULT_COORDINATOR = OpportunityCoordinator()


def get_opportunity_coordinator() -> OpportunityCoordinator:
    return _DEFAULT_COORDINATOR


def policy_from_settings(
    settings: Mapping[str, Any] | None,
    *,
    authorized_targets: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    values = dict((settings or {}).get("multi_venue_execution", {}) or {})
    if authorized_targets is not None:
        values["authorized_targets"] = list(authorized_targets)
    return normalize_multi_venue_policy(values)
