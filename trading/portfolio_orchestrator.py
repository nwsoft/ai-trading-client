#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""포트폴리오 오케스트레이션 계층.

목표:
- 코인/주식/ETF를 분리 운용하지 않고 포트폴리오 단위로 주문량을 결정
- 리스크 버짓, 상관관계, 동시 손실 한도를 반영해 자본 배분
"""

from __future__ import annotations

from typing import Any, Dict, List


class PortfolioOrchestrator:
    DEFAULT_RISK_BUDGETS = {
        "crypto": 0.40,
        "stock": 0.35,
        "etf": 0.25,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(max(0.0, v) for v in weights.values())
        if total <= 0:
            return {k: 0.0 for k in weights}
        return {k: max(0.0, v) / total for k, v in weights.items()}

    def allocate(self, candidates: List[Dict[str, Any]], total_capital: float, policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective = dict(policy or {})
        budgets = dict(self.DEFAULT_RISK_BUDGETS)
        budgets.update(effective.get("risk_budgets", {}) or {})

        corr_penalty = self._to_float(effective.get("correlation_penalty", 0.35), 0.35)
        max_portfolio_risk = self._to_float(effective.get("max_portfolio_risk", 1.0), 1.0)
        max_symbol_weight = self._to_float(effective.get("max_symbol_weight", 0.25), 0.25)

        raw_weights: Dict[str, float] = {}
        explanations: Dict[str, Dict[str, float]] = {}
        for c in candidates or []:
            symbol = str(c.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            asset_class = str(c.get("asset_class") or "stock").strip().lower()
            vol = max(self._to_float(c.get("volatility", 0.02), 0.02), 1e-6)
            signal = max(0.0, min(1.0, self._to_float(c.get("signal_strength", 0.5), 0.5)))
            corr = max(0.0, min(1.0, self._to_float(c.get("avg_correlation", 0.0), 0.0)))

            budget = self._to_float(budgets.get(asset_class, 0.20), 0.20)
            score = budget * signal / vol
            score *= (1.0 - corr_penalty * corr)

            raw_weights[symbol] = max(0.0, score)
            explanations[symbol] = {
                "budget": budget,
                "signal": signal,
                "volatility": vol,
                "avg_correlation": corr,
            }

        norm = self._normalize_weights(raw_weights)
        clipped = {k: min(v, max_symbol_weight) for k, v in norm.items()}
        norm = self._normalize_weights(clipped)

        portfolio_risk = sum(norm.values())
        risk_scale = min(1.0, max(0.0, max_portfolio_risk / max(portfolio_risk, 1e-6)))

        allocations: Dict[str, Dict[str, float]] = {}
        for symbol, weight in norm.items():
            final_weight = max(0.0, weight * risk_scale)
            allocations[symbol] = {
                "weight": final_weight,
                "capital": max(0.0, total_capital) * final_weight,
                "risk_scale": risk_scale,
                **explanations.get(symbol, {}),
            }

        return {
            "allocations": allocations,
            "portfolio_risk": portfolio_risk,
            "risk_scale": risk_scale,
        }

    def quantity_from_allocation(self, symbol: str, price: float, fallback_qty: float, allocation_result: Dict[str, Any]) -> float:
        safe_price = max(self._to_float(price, 0.0), 0.0)
        if safe_price <= 0:
            return max(0.0, self._to_float(fallback_qty, 0.0))

        alloc = (allocation_result.get("allocations", {}) or {}).get(str(symbol).upper(), {})
        capital = self._to_float(alloc.get("capital", 0.0), 0.0)
        if capital <= 0:
            return max(0.0, self._to_float(fallback_qty, 0.0))

        qty = capital / safe_price
        return max(0.0, min(qty, max(0.0, self._to_float(fallback_qty, fallback_qty))))
