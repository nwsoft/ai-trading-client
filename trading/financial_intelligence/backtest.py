from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from .performance import PortfolioPerformanceEngine


@dataclass
class BacktestResult:
    status: str
    initial_cash: float
    final_equity: float
    total_return: float
    trades: List[Dict[str, Any]]
    equity_curve: List[float]
    metrics: Dict[str, Any]
    assumptions: Dict[str, Any]
    rejected_orders: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BacktestEngine:
    """신호와 체결을 분리한 자산 공통 이벤트 기반 백테스트."""

    def __init__(self):
        self.performance = PortfolioPerformanceEngine()

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def run(
        self,
        bars: Iterable[Mapping[str, Any]],
        signal_fn: Callable[[List[Mapping[str, Any]], int], str | Mapping[str, Any]],
        *,
        initial_cash: float = 10_000.0,
        position_fraction: float = 1.0,
        fee_rate: float = 0.001,
        slippage_bps: float = 5.0,
        spread_bps: float = 2.0,
        funding_rate_per_bar: float = 0.0,
        leverage: float = 1.0,
        maintenance_margin_rate: float = 0.05,
        min_notional: float = 0.0,
        quantity_step: float = 0.0,
        execution_delay_bars: int = 1,
        partial_fill_ratio: float = 1.0,
        fail_indices: Iterable[int] = (),
    ) -> BacktestResult:
        rows = [dict(row) for row in bars]
        if len(rows) < 2:
            return BacktestResult(
                "insufficient_data", initial_cash, initial_cash, 0.0, [], [initial_cash], {},
                {}, [],
            )
        cash = float(initial_cash)
        quantity = 0.0
        entry_price = 0.0
        entry_cost = 0.0
        entry_index = -1
        side = ""
        pending: List[Dict[str, Any]] = []
        trades: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        equity_curve: List[float] = []
        fail_set = {int(value) for value in fail_indices}
        leverage = max(1.0, float(leverage))
        fill_ratio = max(0.0, min(float(partial_fill_ratio), 1.0))
        delay = max(0, int(execution_delay_bars))

        for index, bar in enumerate(rows):
            price = self._number(bar.get("open", bar.get("price", bar.get("close"))))
            close = self._number(bar.get("close", bar.get("price")), price)
            if price <= 0 or close <= 0:
                rejected.append({"index": index, "reason": "invalid_price"})
                equity_curve.append(cash)
                continue

            due = [order for order in pending if order["execute_at"] <= index]
            pending = [order for order in pending if order["execute_at"] > index]
            for order in due:
                if index in fail_set:
                    rejected.append({**order, "index": index, "reason": "simulated_api_failure"})
                    continue
                action = order["action"]
                direction = order["side"]
                adverse = (slippage_bps + spread_bps / 2.0) / 10000.0
                if action == "OPEN":
                    fill_price = price * (1.0 + adverse if direction == "LONG" else 1.0 - adverse)
                else:
                    fill_price = price * (1.0 - adverse if direction == "LONG" else 1.0 + adverse)
                if action == "OPEN" and quantity == 0:
                    cash_budget = cash * max(0.0, min(float(position_fraction), 1.0))
                    # 증거금과 진입 수수료를 합쳐도 가용 현금을 넘지 않게 한다.
                    budget = cash_budget / ((1.0 / leverage) + fee_rate)
                    if budget < min_notional:
                        rejected.append({**order, "index": index, "reason": "below_min_notional"})
                        continue
                    raw_qty = (budget / fill_price) * fill_ratio
                    if quantity_step > 0:
                        raw_qty = int(raw_qty / quantity_step) * quantity_step
                    if raw_qty <= 0:
                        rejected.append({**order, "index": index, "reason": "zero_quantity"})
                        continue
                    entry_cost = raw_qty * fill_price
                    fee = entry_cost * fee_rate
                    margin = entry_cost / leverage
                    if margin + fee > cash:
                        rejected.append({**order, "index": index, "reason": "insufficient_cash"})
                        continue
                    cash -= margin + fee
                    quantity = raw_qty
                    entry_price = fill_price
                    entry_index = index
                    side = direction
                elif action == "CLOSE" and quantity > 0:
                    exit_price = fill_price
                    notional = quantity * exit_price
                    exit_fee = notional * fee_rate
                    margin = entry_cost / leverage
                    gross = (
                        (exit_price - entry_price) * quantity
                        if side == "LONG" else (entry_price - exit_price) * quantity
                    )
                    funding = entry_cost * funding_rate_per_bar * max(0, index - entry_index)
                    cash += margin + gross - exit_fee - funding
                    trades.append(
                        {
                            "entry_index": entry_index,
                            "exit_index": index,
                            "side": side,
                            "entry_price": entry_price,
                            "filled_price": exit_price,
                            "quantity": quantity,
                            "notional": entry_cost,
                            "pnl": gross,
                            "fee": entry_cost * fee_rate + exit_fee + funding,
                            "slippage_bps": slippage_bps + spread_bps / 2.0,
                            "costs_included_in_pnl": True,
                            "hold_bars": index - entry_index,
                        }
                    )
                    quantity = 0.0
                    entry_price = 0.0
                    entry_cost = 0.0
                    entry_index = -1
                    side = ""

            if quantity > 0:
                unrealized = (
                    (close - entry_price) * quantity
                    if side == "LONG" else (entry_price - close) * quantity
                )
                margin = entry_cost / leverage
                if margin + unrealized <= entry_cost * maintenance_margin_rate:
                    pending.append({"action": "CLOSE", "side": side, "execute_at": index, "reason": "liquidation"})
                equity = cash + margin + unrealized
            else:
                equity = cash
            equity_curve.append(equity)

            signal = signal_fn(rows, index)
            if isinstance(signal, Mapping):
                signal_name = str(signal.get("signal") or "HOLD").upper()
            else:
                signal_name = str(signal or "HOLD").upper()
            if quantity == 0 and signal_name in {"LONG", "BUY", "SHORT", "SELL_SHORT"}:
                pending.append(
                    {
                        "action": "OPEN",
                        "side": "SHORT" if signal_name in {"SHORT", "SELL_SHORT"} else "LONG",
                        "signal_index": index,
                        "execute_at": index + delay,
                    }
                )
            elif quantity > 0 and (
                signal_name in {"CLOSE", "EXIT"}
                or (side == "LONG" and signal_name in {"SHORT", "SELL"})
                or (side == "SHORT" and signal_name in {"LONG", "BUY"})
            ):
                pending.append(
                    {
                        "action": "CLOSE",
                        "side": side,
                        "signal_index": index,
                        "execute_at": index + delay,
                    }
                )

        if quantity > 0:
            last = rows[-1]
            last_price = self._number(last.get("close", last.get("price")))
            adverse = (slippage_bps + spread_bps / 2.0) / 10000.0
            exit_price = last_price * (1.0 - adverse if side == "LONG" else 1.0 + adverse)
            gross = (exit_price - entry_price) * quantity if side == "LONG" else (entry_price - exit_price) * quantity
            notional = quantity * exit_price
            exit_fee = notional * fee_rate
            margin = entry_cost / leverage
            cash += margin + gross - exit_fee
            trades.append(
                {
                    "entry_index": entry_index,
                    "exit_index": len(rows) - 1,
                    "side": side,
                    "entry_price": entry_price,
                    "filled_price": exit_price,
                    "quantity": quantity,
                    "notional": entry_cost,
                    "pnl": gross,
                    "fee": entry_cost * fee_rate + exit_fee,
                    "slippage_bps": slippage_bps + spread_bps / 2.0,
                    "costs_included_in_pnl": True,
                    "hold_bars": len(rows) - 1 - entry_index,
                    "forced_final_close": True,
                }
            )
            equity_curve.append(cash)
        metrics = self.performance.trade_metrics(trades)
        assumptions = {
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
            "spread_bps": spread_bps,
            "funding_rate_per_bar": funding_rate_per_bar,
            "leverage": leverage,
            "maintenance_margin_rate": maintenance_margin_rate,
            "min_notional": min_notional,
            "quantity_step": quantity_step,
            "execution_delay_bars": delay,
            "partial_fill_ratio": fill_ratio,
        }
        return BacktestResult(
            "ok",
            initial_cash,
            cash,
            cash / initial_cash - 1.0 if initial_cash else 0.0,
            trades,
            equity_curve,
            metrics,
            assumptions,
            rejected,
        )

    def walk_forward(
        self,
        bars: Iterable[Mapping[str, Any]],
        signal_factory: Callable[[List[Mapping[str, Any]]], Callable[[List[Mapping[str, Any]], int], str]],
        train_size: int,
        test_size: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        rows = [dict(row) for row in bars]
        windows: List[Dict[str, Any]] = []
        start = 0
        while start + train_size + test_size <= len(rows):
            train = rows[start : start + train_size]
            test = rows[start + train_size : start + train_size + test_size]
            result = self.run(test, signal_factory(train), **kwargs)
            windows.append(
                {
                    "train_start": start,
                    "test_start": start + train_size,
                    "test_end": start + train_size + test_size - 1,
                    "total_return": result.total_return,
                    "trades": len(result.trades),
                }
            )
            start += test_size
        return {
            "windows": windows,
            "pass_rate": (
                sum(1 for window in windows if window["total_return"] > 0) / len(windows)
                if windows else 0.0
            ),
            "out_of_sample": True,
        }
