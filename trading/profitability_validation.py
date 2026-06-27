#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수익성 검증 계층.

목표:
- 전략의 "작동"이 아니라 "수익성"을 수치 KPI로 판정
- 백테스트/워크포워드/거래비용/슬리피지 반영 결과를 단일 리포트로 제공
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ProfitabilityReport:
    total_trades: int
    gross_pnl: float
    net_pnl: float
    win_rate: float
    sharpe: float
    mdd: float
    expectancy: float
    walkforward_pass_rate: float
    enabled: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "gross_pnl": round(self.gross_pnl, 4),
            "net_pnl": round(self.net_pnl, 4),
            "win_rate": round(self.win_rate, 4),
            "sharpe": round(self.sharpe, 4),
            "mdd": round(self.mdd, 4),
            "expectancy": round(self.expectancy, 4),
            "walkforward_pass_rate": round(self.walkforward_pass_rate, 4),
            "enabled": self.enabled,
            "reasons": list(self.reasons),
        }


class ProfitabilityValidator:
    """자동매매 ON/OFF를 수익성 KPI로 판정한다."""

    DEFAULT_POLICY: Dict[str, Any] = {
        # enabled=True: 거래 데이터가 쌓인 뒤 KPI가 크게 흔들릴 때만 차단
        # 거래 데이터가 min_trades 미만이면 bypassed=True로 통과(초기 학습 기간 보호)
        "enabled": True,
        "min_trades": 10,
        "min_win_rate": 0.42,
        "min_sharpe": 0.20,
        "max_mdd": 0.30,
        "min_expectancy": 0.0,
        "walkforward_splits": 4,
        "min_walkforward_pass_rate": 0.40,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _extract_trade_return(self, trade: Dict[str, Any]) -> float:
        pnl = self._to_float(trade.get("pnl", trade.get("realized_pnl", trade.get("profit", 0.0))), 0.0)
        fee = self._to_float(trade.get("fee", trade.get("fees", 0.0)), 0.0)
        slippage_bps = self._to_float(trade.get("slippage_bps", 0.0), 0.0)
        qty = max(self._to_float(trade.get("quantity", trade.get("filled_quantity", 1.0)), 1.0), 1e-8)
        price = max(self._to_float(trade.get("filled_price", trade.get("price", 1.0)), 1.0), 1e-8)

        notional = qty * price
        slippage_cost = notional * (abs(slippage_bps) / 10000.0)
        net = pnl - fee - slippage_cost
        return net

    @staticmethod
    def _max_drawdown_from_equity(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            peak = max(peak, v)
            if peak <= 0:
                continue
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _safe_sharpe(returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_r = statistics.mean(returns)
        std_r = statistics.pstdev(returns)
        if std_r <= 1e-12:
            return 0.0
        return mean_r / std_r * math.sqrt(len(returns))

    def _walkforward_pass_rate(self, returns: List[float], splits: int) -> float:
        if not returns:
            return 0.0
        safe_splits = max(1, int(splits or 1))
        chunk = max(1, len(returns) // safe_splits)
        passed = 0
        windows = 0
        for i in range(0, len(returns), chunk):
            window = returns[i:i + chunk]
            if not window:
                continue
            windows += 1
            if statistics.mean(window) > 0:
                passed += 1
        if windows == 0:
            return 0.0
        return passed / windows

    def evaluate_strategy(self, recent_trades: List[Dict[str, Any]], policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective = dict(self.DEFAULT_POLICY)
        effective.update(policy or {})

        if not bool(effective.get("enabled", False)):
            return {
                "enabled": True,
                "bypassed": True,
                "reason": "profitability_validation_disabled",
            }

        returns = [self._extract_trade_return(t or {}) for t in (recent_trades or [])]
        total_trades = len(returns)
        gross_pnl = sum(self._to_float((t or {}).get("pnl", (t or {}).get("realized_pnl", (t or {}).get("profit", 0.0))), 0.0) for t in (recent_trades or []))
        net_pnl = sum(returns)

        wins = sum(1 for r in returns if r > 0)
        win_rate = (wins / total_trades) if total_trades > 0 else 0.0
        expectancy = statistics.mean(returns) if returns else 0.0

        equity = [100.0]
        running = 100.0
        for r in returns:
            running += r
            equity.append(running)

        sharpe = self._safe_sharpe(returns)
        mdd = self._max_drawdown_from_equity(equity)
        walkforward = self._walkforward_pass_rate(returns, int(effective.get("walkforward_splits", 4) or 4))

        reasons: List[str] = []
        if total_trades < int(effective.get("min_trades", 20) or 20):
            # 거래 데이터가 min_trades 미만이면 초기 학습 기간으로 간주 → bypass(차단 없음)
            return {
                "enabled": True,
                "bypassed": True,
                "reason": "insufficient_trades",
                "total_trades": total_trades,
            }
        if win_rate < self._to_float(effective.get("min_win_rate", 0.48), 0.48):
            reasons.append("win_rate_below_threshold")
        if sharpe < self._to_float(effective.get("min_sharpe", 0.60), 0.60):
            reasons.append("sharpe_below_threshold")
        if mdd > self._to_float(effective.get("max_mdd", 0.25), 0.25):
            reasons.append("mdd_above_threshold")
        if expectancy < self._to_float(effective.get("min_expectancy", 0.0), 0.0):
            reasons.append("expectancy_below_threshold")
        if walkforward < self._to_float(effective.get("min_walkforward_pass_rate", 0.50), 0.50):
            reasons.append("walkforward_below_threshold")

        report = ProfitabilityReport(
            total_trades=total_trades,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            win_rate=win_rate,
            sharpe=sharpe,
            mdd=mdd,
            expectancy=expectancy,
            walkforward_pass_rate=walkforward,
            enabled=(len(reasons) == 0),
            reasons=reasons,
        )
        return report.to_dict()
