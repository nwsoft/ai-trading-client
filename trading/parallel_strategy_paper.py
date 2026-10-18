"""Order-free forward PAPER validation that can run beside LIVE trading.

This component receives market-analysis snapshots only.  It never owns an
exchange/broker adapter and therefore cannot submit, amend, or cancel a real
order.  Positions are isolated by strategy version, venue, and symbol and are
written to an account-scoped virtual ledger.
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from uuid import uuid4

from path_utils import get_app_data_dir
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.leverage_policy import exchange_leverage_cap
from trading.paper_strategy_ledger import record_paper_strategy_outcome
from trading.position_sizing_policy import calculate_position_sizing, normalize_position_sizing_policy
from trading.trade_candidate import evaluate_trade_candidate


_SPOT_VENUES = {"upbit", "bithumb", "coinone"}
_STOCK_TARGETS = {"kiwoom", "shinhan", "mirae", "miraeasset", "kis", "koreainvestment"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


class ParallelStrategyPaperEngine:
    """Maintain independent per-version virtual positions without order APIs."""

    def __init__(self, *, settings_provider, logger=None):
        self.settings_provider = settings_provider
        self.logger = logger
        self._lock = threading.RLock()
        self._path = Path(get_app_data_dir()) / "parallel_strategy_paper_positions.json"
        self._load_error = ""
        self._positions: Dict[str, Dict[str, Any]] = self._load()
        self._last_error = ""
        self._last_checked_at = None

    def _settings(self) -> Dict[str, Any]:
        try:
            return dict(self.settings_provider() or {})
        except Exception:
            return {}

    def enabled(self) -> bool:
        settings = self._settings()
        policy = dict(settings.get("parallel_strategy_paper_validation") or {})
        # Parallel observation is meaningful only while the primary runtime is
        # LIVE. Global PAPER already has its own order-free execution ledger.
        return not self._load_error and bool(policy.get("enabled", False)) and not bool(settings.get("paper_trading", True))

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or any(not isinstance(v, dict) for v in raw.values()):
                raise ValueError("invalid_snapshot_shape")
            return {str(k):dict(v) for k,v in raw.items()}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._load_error = "parallel_paper_snapshot_invalid"
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(self._positions, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self._path)
        from trading.paper_position_store import fsync_parent
        fsync_parent(self._path)

    @staticmethod
    def _identity(strategy: Mapping[str, Any], target: str, symbol: str) -> str:
        return "|".join((
            str(strategy.get("strategy_key") or ""),
            str(strategy.get("version_id") or ""),
            str(target or "").lower(),
            str(symbol or "").upper(),
        ))

    @staticmethod
    def _quote(target: str, asset_class: str) -> str:
        if str(asset_class).lower() in {"stock", "etf"} or str(target).lower() in _SPOT_VENUES:
            return "KRW"
        return "USDT"

    @staticmethod
    def _asset_class(target: str, asset_class: str) -> str:
        asset = str(asset_class or "crypto").lower()
        if asset in {"stock", "etf"}:
            return asset
        return "crypto_spot" if str(target).lower() in _SPOT_VENUES else "crypto_futures"

    @staticmethod
    def _round_trip_rates(target: str, asset_class: str) -> tuple[float, float, float]:
        venue = str(target or "").lower()
        asset = str(asset_class or "").lower()
        if asset in {"stock", "etf"}:
            # Entry+exit commission/slippage estimates; tax is applied on exit.
            return 0.00030, 0.00040, 0.0018 if asset == "stock" else 0.0
        if venue in _SPOT_VENUES:
            return 0.0010, 0.0006, 0.0
        return 0.0008, 0.0006, 0.0

    def snapshot(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [dict(value) for value in self._positions.values()]

    def _remove_committed(self, identity):
        saved = self._positions.pop(identity)
        try:
            self._save()
        except Exception:
            self._positions[identity] = saved
            raise

    def status(self):
        with self._lock:
            return {"state": "needs_attention" if self._load_error or self._last_error or any(p.get("pending_close") or p.get("watch_error") for p in self._positions.values()) else "watching" if self._positions else "idle",
                    "open_positions": len(self._positions),
                    "pending_closes": sum(bool(p.get("pending_close")) for p in self._positions.values()),
                    "last_checked_at": self._last_checked_at, "reason_code": self._load_error or self._last_error or next((p.get("watch_error") for p in self._positions.values() if p.get("watch_error")), ""),
                    "continues_existing_exits_across_modes": True, "submits_real_orders": False}

    def service_exits(self, quote_provider):
        """Read-only market polling, independent of entry gates and candidate selection."""
        result = {"evaluated": 0, "opened": 0, "closed": 0}
        # Commit frozen exits before any network read. An unavailable quote
        # provider must never delay recovery of an already observed exit.
        with self._lock:
            pending_targets = sorted({(p.get("target"),p.get("symbol"),p.get("asset_class","crypto"))
                                      for p in self._positions.values() if p.get("pending_close")})
        for target, symbol, asset in pending_targets:
            update = self.observe(target=target, symbol=symbol, asset_class=asset,
                primary_execution_mode="exit_only", context={"current_price":0.0},
                strategy_pool=[], market_regime="unknown")
            for key in result: result[key] += update[key]
        with self._lock:
            targets = sorted({(p.get("target"), p.get("symbol"), p.get("asset_class", "crypto"))
                              for p in self._positions.values() if not p.get("pending_close")})
        for target, symbol, asset in targets:
            try:
                price = _float(quote_provider(target, symbol, asset))
            except Exception:
                price = 0.0
            update = self.observe(target=target, symbol=symbol, asset_class=asset,
                primary_execution_mode="exit_only", context={"current_price": price, "_price_only_exit_watch": True},
                strategy_pool=[], market_regime="unknown")
            for key in result: result[key] += update[key]
        return result

    def _close_existing(self, identity, existing, context, price, now):
        # A previous process may have committed before its position snapshot was saved.
        from trading.paper_ledger_index import index_for
        import hashlib
        scope = "binance" if str(existing.get("target")).lower() == "binance" else "unified"
        target, symbol = existing.get("target"), existing.get("symbol")
        event = "paper_outcome_" + hashlib.sha256(
            f"{scope}|{str(target).lower()}|{existing.get('position_id')}".encode()).hexdigest()[:32]
        ledger = self._path.with_name("strategy_paper_outcomes.jsonl")
        try:
            prior = index_for(ledger).event(event)
        except (ValueError, OSError):
            # An unavailable derived index must not prevent freezing an observed exit.
            prior = None
        if prior is not None:
            for key, saved_key in (("position_id", "position_id"), ("strategy_key", "strategy_key"),
                                   ("version_id", "version_id"), ("symbol", "symbol")):
                if str(prior.get(key) or "") != str(existing.get(saved_key) or ""):
                    raise ValueError("parallel_paper_close_identity_conflict")
            if str(prior.get("exchange") or "").lower() != str(target).lower():
                raise ValueError("parallel_paper_close_identity_conflict")
            for key in ("entry_price", "quantity", "contract_size"):
                if prior.get(key) is not None and float(prior[key]) != float(existing.get(key, 1.0 if key == "contract_size" else 0)):
                    raise ValueError("parallel_paper_close_identity_conflict")
            if existing.get("pending_close"):
                for key in ("exit_price", "net_pnl", "fees", "estimated_slippage", "closed_at"):
                    if prior.get(key) != existing["pending_close"].get(key):
                        raise ValueError("parallel_paper_close_identity_conflict")
            self._remove_committed(identity)
            return True
        pending = existing.get("pending_close")
        if not pending:
            if price <= 0:
                self._last_error = "parallel_paper_quote_unavailable"
                existing["watch_error"] = self._last_error
                return False
            existing.pop("watch_error", None)
            side = str(existing.get("side") or "LONG").upper()
            entry = _float(existing.get("entry_price"))
            if entry <= 0: raise ValueError("parallel_paper_entry_price_invalid")
            tp, sl = _float(existing.get("tp_fraction")), _float(existing.get("sl_fraction"))
            signed_return = ((price - entry) / entry) * (1 if side == "LONG" else -1)
            from .numeric_strategy_state import identity as state_identity
            context = {**context, "_numeric_state_identity":state_identity(existing.get("rules") or {}, existing)}
            exit_eval = ({"allowed": False} if context.get("_price_only_exit_watch") else
                DeclarativeStrategyEngine.evaluate_exit(dict(existing.get("rules") or {}), context))
            exit_reason = ("take_profit" if tp > 0 and signed_return >= tp else
                           "stop_loss" if sl > 0 and signed_return <= -sl else
                           "strategy_exit" if exit_eval.get("allowed") and not exit_eval.get("bypassed") else "")
            previous = existing.get("last_observed_at")
            if not previous:
                existing["observation_status"] = "legacy_observation_gap"
            else:
                try:
                    if (now - datetime.fromisoformat(previous)).total_seconds() > 120:
                        existing["observation_status"] = "observation_gap"
                except (TypeError, ValueError): existing["observation_status"] = "observation_gap"
            existing["last_observed_at"] = now.isoformat()
            existing["current_price"] = price
            if not exit_reason:
                self._save()
                return False
            quantity = _float(existing.get("quantity"), 0.0)
            contract = _float(existing.get("contract_size"), 1.0)
            direction = 1.0 if side == "LONG" else -1.0
            gross = (price - entry) * direction * quantity * contract
            fee_rate = _float(existing.get("round_trip_fee_rate"), 0.0)
            slip_rate = _float(existing.get("round_trip_slippage_rate"), 0.0)
            tax_rate = _float(existing.get("exit_tax_rate"), 0.0)
            entry_notional = entry * quantity * contract
            exit_notional = price * quantity * contract
            fees = (entry_notional + exit_notional) * fee_rate / 2.0
            slippage = (entry_notional + exit_notional) * slip_rate / 2.0
            taxes = exit_notional * tax_rate
            net = gross - fees - slippage - taxes
            pending = dict(
                scope="binance" if str(target).lower() == "binance" else "unified",
                strategy_scope=str(existing.get("strategy_scope") or "unified"),
                exchange=target, symbol=symbol,
                strategy_key=str(existing.get("strategy_key") or ""),
                version_id=str(existing.get("version_id") or ""),
                position_id=str(existing.get("position_id") or ""),
                opened_at=existing.get("opened_at"), closed_at=now.isoformat(),
                gross_pnl=gross, net_pnl=net,
                net_pnl_percent=(net / entry_notional * 100.0) if entry_notional else 0.0,
                fees=fees, estimated_slippage=slippage, estimated_taxes=taxes,
                entry_price=entry, exit_price=price, quantity=quantity,
                contract_size=contract,
                side=side, quote_currency=str(existing.get("quote_currency") or ""),
                cost_calculation_status="parallel_paper_recorded_contract",
                calculation_status="valid",
                leverage=existing.get("leverage"),
                entry_reason=str(existing.get("entry_reason") or ""),
                entry_market_regime=str(existing.get("market_regime") or ""),
                entry_regime_scope=str(existing.get("regime_scope") or ""),
                entry_signal_source=str(existing.get("signal_source") or ""),
                sizing_policy_reason=str(
                    dict(existing.get("position_sizing") or {}).get("reason") or ""
                ),
                sizing_target_notional=dict(
                    existing.get("position_sizing") or {}
                ).get("target_notional"),
                sizing_final_notional=dict(
                    existing.get("position_sizing") or {}
                ).get("final_notional"),
                sizing_limiting_reasons=list(dict(
                    existing.get("position_sizing") or {}
                ).get("limiting_reasons") or []),
                exit_reason=exit_reason,
                tp_price=(
                    entry * (1.0 + tp)
                    if side == "LONG" else entry * (1.0 - tp)
                ) if tp > 0 else None,
                sl_price=(
                    entry * (1.0 - sl)
                    if side == "LONG" else entry * (1.0 + sl)
                ) if sl > 0 else None,
                effective_tp_fraction=tp if tp > 0 else None,
                effective_sl_fraction=sl if sl > 0 else None,
                exit_policy_source="custom_strategy_parallel_paper",
                exit_policy_reason="strategy_exit_plan",
            )
            pending.update(fee_rate=fee_rate, slippage_rate=slip_rate, tax_rate=tax_rate)
            pending.update(validation_path="parallel_validation", capital_basis="independent_strategy_virtual_equity",
                           capital_reference=(existing.get("position_sizing") or {}).get("account_equity"),
                           observation_status=existing.get("observation_status", "continuous"),
                           exit_observed_at=now.isoformat(), exit_commit_status="frozen_exit_intent")
            existing["pending_close"] = pending
        # Persist intent before attempting a journal commit. Retries reuse ALL frozen fields.
        self._save()
        record_paper_strategy_outcome(**pending, ledger_file=ledger)
        self._remove_committed(identity)
        return True

    def observe(
        self,
        *,
        target: str,
        symbol: str,
        asset_class: str,
        primary_execution_mode: str,
        context: Mapping[str, Any],
        strategy_pool: Sequence[Mapping[str, Any]],
        market_regime: str,
    ) -> Dict[str, int]:
        """Evaluate and mark independent virtual positions for one market tick."""
        # Parallel validation is deliberately a LIVE companion. LEARNING and
        # global PAPER own separate lifecycles and must not create a second,
        # ambiguous PAPER ledger stream.
        can_open = self.enabled() and str(primary_execution_mode or "").lower() in {"live", "live_api"}
        settings = self._settings()
        maximum = max(
            1,
            min(
                int(dict(settings.get("parallel_strategy_paper_validation") or {}).get(
                    "max_strategies_per_venue", 3
                ) or 3),
                10,
            ),
        )
        position_limit = max(
            1,
            min(
                int(dict(settings.get("parallel_strategy_paper_validation") or {}).get(
                    "max_positions_per_strategy", 1
                ) or 1),
                5,
            ),
        )
        from .strategy_scope import scoped_pool
        strategy_pool = scoped_pool(strategy_pool, asset_class=asset_class, target=target, limit=maximum)
        observing = [
            dict(item) for item in strategy_pool
            if isinstance(item, Mapping)
            and str(item.get("operation_mode") or "").lower() == "paper_validation"
            and item.get("strategy_key") and item.get("version_id")
        ][:maximum] if can_open else []
        price = _float(context.get("current_price", context.get("price", 0.0)), 0.0)

        result = {"evaluated": 0, "opened": 0, "closed": 0}
        now = datetime.now(timezone.utc)
        changed = False
        with self._lock:
            self._last_error = ""
            self._last_checked_at = now.isoformat()
            # Revocation/completion stops new entries, not exits of already open
            # virtual positions. Preserve the entry version's frozen exit rules.
            active_ids = {self._identity(item, target, symbol) for item in observing}
            for identity, position in self._positions.items():
                if (identity not in active_ids
                        and str(position.get("target") or "").lower() == str(target).lower()
                        and str(position.get("symbol") or "").upper() == str(symbol).upper()):
                    observing.append({
                        "strategy_key": position.get("strategy_key"),
                        "version_id": position.get("version_id"),
                        "strategy_scope": position.get("strategy_scope"),
                        "rules": dict(position.get("rules") or {}),
                        "_exit_only": True,
                    })
            from .numeric_strategy_state import NumericStateStore, enrich_states, identity as state_identity
            state_store=NumericStateStore(self._path.with_suffix('.state.sqlite3'))
            context=enrich_states(dict(context),observing,{'venue':target,'symbol':symbol,'mode':'parallel_paper'},state_store)
            for strategy in observing:
                result["evaluated"] += 1
                identity = self._identity(strategy, target, symbol)
                existing = self._positions.get(identity)
                if existing:
                    try:
                        if self._close_existing(identity, existing, context, price, now):
                            result["closed"] += 1
                    except Exception as exc:
                        self._last_error = (str(exc) if isinstance(exc, ValueError) and
                            str(exc).replace("_", "").isalnum() else "parallel_paper_close_storage_unavailable")
                        existing["watch_error"] = self._last_error
                    continue

                if strategy.get("_exit_only") or not can_open or price <= 0 or any(p.get("pending_close") for p in self._positions.values()):
                    continue
                candidate = evaluate_trade_candidate(
                    symbol=symbol, context=context, strategy_pool=[strategy],
                    asset_class=asset_class, target=target, market_regime=market_regime,
                )
                side = str(candidate.final_signal or "HOLD").upper()
                # A pool may intentionally delegate to base NoahAI when this
                # PAPER strategy did not match. Such a fallback is not a
                # validation trade for this strategy and must not be attributed.
                if (not candidate.allowed or side not in {"LONG", "SHORT"}
                    or candidate.strategy_key!=str(strategy.get('strategy_key') or '')
                    or candidate.strategy_version_id!=str(strategy.get('version_id') or '')):
                    continue
                if (str(target).lower() in _SPOT_VENUES or str(asset_class).lower() in {"stock", "etf"}) and side == "SHORT":
                    continue
                open_for_strategy = sum(
                    1 for row in self._positions.values()
                    if str(row.get("strategy_key") or "") == str(strategy.get("strategy_key") or "")
                    and str(row.get("version_id") or "") == str(strategy.get("version_id") or "")
                    and str(row.get("target") or "").lower() == str(target or "").lower()
                )
                if open_for_strategy >= position_limit:
                    continue
                quote = self._quote(target, asset_class)
                normalized = normalize_position_sizing_policy(settings, quote_currency=quote)
                stop = _float(candidate.exit_plan.requested_sl_fraction, 0.0)
                contract_size = max(1e-12, _float(context.get("_contract_size"), 1.0))
                fixed = max(
                    5_000.0 if quote == "KRW" else 5.0,
                    _float(settings.get("min_trade_amount"), 20.0),
                )
                plan = calculate_position_sizing(
                    policy=dict(settings.get("position_sizing_policy") or {}),
                    asset_class=self._asset_class(target, asset_class),
                    quote_currency=quote,
                    account_equity=_float(normalized.get("paper_equity"), 0.0),
                    account_equity_source="parallel_paper_virtual_equity",
                    price=price, stop_fraction=stop,
                    requested_leverage=int(_float(candidate.engine_settings.get("leverage"), 1.0)),
                    leverage_cap=(
                        exchange_leverage_cap(settings, str(target).lower())
                        if self._asset_class(target, asset_class) == "crypto_futures"
                        else 1
                    ),
                    fixed_notional=fixed, risk_multiplier=1.0,
                    contract_size=contract_size,
                )
                if not bool(plan.get("allowed")):
                    continue
                quantity = _float(plan.get("target_quantity"), 0.0)
                if str(asset_class).lower() in {"stock", "etf"}:
                    quantity = float(int(quantity))
                if quantity <= 0:
                    continue
                fee_rate, slip_rate, tax_rate = self._round_trip_rates(target, asset_class)
                self._positions[identity] = {
                    "position_id": f"parallel_paper_{uuid4().hex}",
                    "rules": dict(strategy.get("rules") or {}),
                    "strategy_key": strategy.get("strategy_key"),
                    "version_id": strategy.get("version_id"),
                    "strategy_scope": strategy.get("strategy_scope"),
                    "target": str(target).lower(), "symbol": str(symbol),
                    "asset_class": str(asset_class), "side": side,
                    "entry_price": price, "current_price": price,
                    "quantity": quantity, "contract_size": contract_size,
                    "tp_fraction": _float(candidate.exit_plan.requested_tp_fraction, 0.0),
                    "sl_fraction": stop, "quote_currency": quote,
                    "leverage": int(plan.get("effective_leverage", 1) or 1),
                    "entry_reason": str(candidate.reason or ""),
                    "market_regime": str(candidate.market_regime or ""),
                    "regime_scope": str(candidate.regime_scope or ""),
                    "signal_source": str(candidate.signal_source or ""),
                    "round_trip_fee_rate": fee_rate,
                    "round_trip_slippage_rate": slip_rate,
                    "exit_tax_rate": tax_rate, "opened_at": now.isoformat(),
                    "position_sizing": plan,
                    "last_observed_at": now.isoformat(), "observation_status": "continuous",
                }
                result["opened"] += 1
                changed = True
            if changed:
                self._save()
        return result
