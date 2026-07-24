from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional


class PortfolioPerformanceEngine:
    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _max_drawdown(equity: List[float]) -> tuple[float, int]:
        if not equity:
            return 0.0, 0
        peak = equity[0]
        peak_index = 0
        max_dd = 0.0
        recovery = 0
        trough_index = 0
        for index, value in enumerate(equity):
            if value >= peak:
                if trough_index > peak_index and recovery == 0:
                    recovery = index - trough_index
                peak = value
                peak_index = index
                trough_index = index
            elif peak > 0:
                drawdown = (peak - value) / peak
                if drawdown > max_dd:
                    max_dd = drawdown
                    trough_index = index
                    recovery = 0
        return max_dd, recovery

    @staticmethod
    def _downside_deviation(returns: List[float]) -> float:
        downside = [min(value, 0.0) for value in returns]
        if not downside:
            return 0.0
        return math.sqrt(sum(value * value for value in downside) / len(downside))

    def trade_metrics(self, trades: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        rows = list(trades)
        net_results: List[float] = []
        gross_profit = 0.0
        gross_loss = 0.0
        fees = 0.0
        slippage_cost = 0.0
        equity = [100.0]
        for row in rows:
            pnl = self._number(row.get("pnl", row.get("realized_pnl", row.get("profit", 0.0))))
            fee = self._number(row.get("fee", row.get("fees", 0.0)))
            notional = abs(self._number(row.get("notional"), self._number(row.get("price"), 0.0) * self._number(row.get("quantity"), 0.0)))
            # 이벤트 기반 백테스트처럼 체결가 자체에 슬리피지를 반영한 경우에는
            # 성과 집계 단계에서 같은 비용을 다시 차감하지 않는다.
            slippage = (
                0.0
                if bool(row.get("costs_included_in_pnl"))
                else notional * abs(self._number(row.get("slippage_bps"), 0.0)) / 10000.0
            )
            net = pnl - fee - slippage
            net_results.append(net)
            fees += fee
            slippage_cost += slippage
            if net > 0:
                gross_profit += net
            elif net < 0:
                gross_loss += abs(net)
            equity.append(equity[-1] + net)
        wins = [value for value in net_results if value > 0]
        losses = [value for value in net_results if value < 0]
        mdd, recovery = self._max_drawdown(equity)
        mean = statistics.mean(net_results) if net_results else 0.0
        std = statistics.pstdev(net_results) if len(net_results) > 1 else 0.0
        downside = self._downside_deviation(net_results)
        return {
            "trades": len(net_results),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(net_results) if net_results else 0.0,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": sum(net_results),
            "fees": fees,
            "slippage_cost": slippage_cost,
            "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit > 0 else 0.0),
            "expectancy": mean,
            "average_win": statistics.mean(wins) if wins else 0.0,
            "average_loss": statistics.mean(losses) if losses else 0.0,
            "payoff_ratio": (statistics.mean(wins) / abs(statistics.mean(losses))) if wins and losses else 0.0,
            "sharpe": mean / std * math.sqrt(len(net_results)) if std > 1e-12 else 0.0,
            "sortino": mean / downside * math.sqrt(len(net_results)) if downside > 1e-12 else 0.0,
            "max_drawdown": mdd,
            "recovery_periods": recovery,
            "equity_curve": equity,
        }

    def grouped_metrics(self, trades: Iterable[Mapping[str, Any]], group_fields: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        rows = list(trades)
        output: Dict[str, Dict[str, Any]] = {}
        for field in group_fields:
            groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
            for row in rows:
                groups[str(row.get(field) or "unknown")].append(row)
            output[str(field)] = {key: self.trade_metrics(values) for key, values in sorted(groups.items())}
        return output

    def benchmark_compare(
        self,
        portfolio_values: Iterable[float],
        benchmark_values: Iterable[float],
        cash_flows: Optional[Iterable[float]] = None,
    ) -> Dict[str, Any]:
        portfolio = [float(value) for value in portfolio_values]
        benchmark = [float(value) for value in benchmark_values]
        flows = [float(value) for value in (cash_flows or [])]
        if len(portfolio) < 2 or len(benchmark) < 2:
            return {"status": "insufficient_data"}
        adjusted = list(portfolio)
        for index in range(1, min(len(adjusted), len(flows) + 1)):
            adjusted[index] -= flows[index - 1]
        portfolio_return = adjusted[-1] / adjusted[0] - 1.0 if adjusted[0] else 0.0
        benchmark_return = benchmark[-1] / benchmark[0] - 1.0 if benchmark[0] else 0.0
        return {
            "status": "ok",
            "portfolio_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "active_return": portfolio_return - benchmark_return,
            "cash_flow_adjusted": bool(flows),
        }

    def exposure_summary(self, positions: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        dimensions = ("asset_type", "strategy", "broker", "country", "currency", "sector", "management_type")
        totals: Dict[str, Dict[str, float]] = {dimension: defaultdict(float) for dimension in dimensions}
        total_value = 0.0
        for row in positions:
            value = self._number(row.get("market_value"), self._number(row.get("price")) * self._number(row.get("quantity")))
            total_value += value
            for dimension in dimensions:
                totals[dimension][str(row.get(dimension) or "unknown")] += value
        return {
            "total_value": total_value,
            "exposures": {
                dimension: {
                    key: {
                        "value": value,
                        "weight": value / total_value if total_value else 0.0,
                    }
                    for key, value in values.items()
                }
                for dimension, values in totals.items()
            },
        }
