#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""운영 자동화/모니터링 계층."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


class OpsAutomationEngine:
    DEFAULT_POLICY = {
        "enabled": False,
        "max_reject_rate": 0.20,
        "max_avg_slippage_bps": 30.0,
        "min_quality_score": 55.0,
        "auto_rollback": True,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def detect_anomalies(self, execution_metrics: Dict[str, Any], policy: Dict[str, Any] | None = None) -> List[str]:
        effective = dict(self.DEFAULT_POLICY)
        effective.update(policy or {})
        if not bool(effective.get("enabled", False)):
            return []

        reject_rate = self._to_float(execution_metrics.get("reject_rate", 0.0), 0.0)
        avg_slippage = abs(self._to_float(execution_metrics.get("avg_slippage_bps", 0.0), 0.0))
        quality = self._to_float(execution_metrics.get("quality_score", 100.0), 100.0)

        anomalies: List[str] = []
        if reject_rate > self._to_float(effective.get("max_reject_rate", 0.20), 0.20):
            anomalies.append("high_reject_rate")
        if avg_slippage > self._to_float(effective.get("max_avg_slippage_bps", 30.0), 30.0):
            anomalies.append("high_slippage")
        if quality < self._to_float(effective.get("min_quality_score", 55.0), 55.0):
            anomalies.append("low_execution_quality")
        return anomalies

    def build_rollback_action(self, anomalies: List[str], policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective = dict(self.DEFAULT_POLICY)
        effective.update(policy or {})
        should_rollback = bool(anomalies) and bool(effective.get("auto_rollback", True))
        return {
            "should_rollback": should_rollback,
            "reason": ",".join(anomalies) if anomalies else "",
            "action": "rollback_to_last_stable_policy" if should_rollback else "none",
        }

    def build_daily_briefing(self, summary: Dict[str, Any], anomalies: List[str]) -> Dict[str, Any]:
        metrics = summary.get("execution_metrics", {}) if isinstance(summary, dict) else {}
        return {
            "generated_at": datetime.now().isoformat(),
            "orders_executed": int(summary.get("orders_executed", 0) or 0),
            "quality_score": self._to_float(metrics.get("quality_score", 0.0), 0.0),
            "reject_rate": self._to_float(metrics.get("reject_rate", 0.0), 0.0),
            "avg_slippage_bps": self._to_float(metrics.get("avg_slippage_bps", 0.0), 0.0),
            "anomalies": list(anomalies),
            "status": "attention" if anomalies else "stable",
        }
