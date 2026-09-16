"""Order-free forward PAPER validation that can run beside LIVE trading.

This component receives market-analysis snapshots only.  It never owns an
exchange/broker adapter and therefore cannot submit, amend, or cancel a real
order.  Positions are isolated by strategy version, venue, and symbol and are
written to an account-scoped virtual ledger.
"""

from __future__ import annotations

import json
import math
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
        self._positions: Dict[str, Dict[str, Any]] = self._load()

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
        return bool(policy.get("enabled", False)) and not bool(settings.get("paper_trading", True))

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {str(k): dict(v) for k, v in dict(raw or {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self._positions, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temp.replace(self._path)

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
        if not self.enabled() or str(primary_execution_mode or "").lower() not in {
            "live", "live_api"
        }:
            return {"evaluated": 0, "opened": 0, "closed": 0}
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
        ][:maximum]
        price = _float(context.get("current_price", context.get("price", 0.0)), 0.0)
        if price <= 0:
            return {"evaluated": len(observing), "opened": 0, "closed": 0}

        result = {"evaluated": 0, "opened": 0, "closed": 0}
        now = datetime.now(timezone.utc)
        changed = False
        with self._lock:
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
            for strategy in observing:
                result["evaluated"] += 1
                identity = self._identity(strategy, target, symbol)
                existing = self._positions.get(identity)
                if existing:
                    side = str(existing.get("side") or "LONG").upper()
                    entry = _float(existing.get("entry_price"), 0.0)
                    tp = _float(existing.get("tp_fraction"), 0.0)
                    sl = _float(existing.get("sl_fraction"), 0.0)
                    signed_return = ((price - entry) / entry) * (1.0 if side == "LONG" else -1.0)
                    exit_eval = DeclarativeStrategyEngine.evaluate_exit(
                        dict(strategy.get("rules") or {}), dict(context)
                    )
                    exit_reason = ""
                    if tp > 0 and signed_return >= tp:
                        exit_reason = "take_profit"
                    elif sl > 0 and signed_return <= -sl:
                        exit_reason = "stop_loss"
                    elif bool(exit_eval.get("allowed")) and not bool(exit_eval.get("bypassed")):
                        exit_reason = "strategy_exit"
                    if exit_reason:
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
                        record_paper_strategy_outcome(
                            scope="binance" if str(target).lower() == "binance" else "unified",
                            strategy_scope=str(strategy.get("strategy_scope") or "unified"),
                            exchange=target, symbol=symbol,
                            strategy_key=str(strategy.get("strategy_key") or ""),
                            version_id=str(strategy.get("version_id") or ""),
                            position_id=str(existing.get("position_id") or ""),
                            opened_at=existing.get("opened_at"), closed_at=now,
                            gross_pnl=gross, net_pnl=net,
                            net_pnl_percent=(net / entry_notional * 100.0) if entry_notional else 0.0,
                            fees=fees, estimated_slippage=slippage, estimated_taxes=taxes,
                            entry_price=entry, exit_price=price, quantity=quantity,
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
                        self._positions.pop(identity, None)
                        result["closed"] += 1
                        changed = True
                    continue

                if strategy.get("_exit_only"):
                    continue
                candidate = evaluate_trade_candidate(
                    symbol=symbol, context=context, strategy_pool=[strategy],
                    asset_class=asset_class, target=target, market_regime=market_regime,
                )
                side = str(candidate.final_signal or "HOLD").upper()
                if not candidate.allowed or side not in {"LONG", "SHORT"}:
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
                }
                result["opened"] += 1
                changed = True
            if changed:
                self._save()
        return result
