#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전략 엔진 고도화 계층.

목표:
- 레짐 필터 + 신호 합의 + 과매매 억제 쿨다운을 통해 무의미한 거래를 줄인다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple


class StrategyEngine:
    DEFAULT_POLICY = {
        "enabled": False,
        "allow_regimes": ["trend", "range"],
        # 고변동을 일괄 차단하면 거래 기회가 사라질 수 있다. 기본은
        # 합의 점수와 가드레일로 평가하고, 사용자가 block을 선택할 수 있다.
        "high_vol_action": "evaluate",
        "consensus_threshold": 0.60,
        "cooldown_sec": 60,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def detect_regime(self, analysis_result: Dict[str, Any]) -> str:
        momentum = self._to_float(analysis_result.get("momentum", 0.0), 0.0)
        volatility = abs(momentum)
        if volatility >= 2.0:
            return "high_vol"
        if momentum >= 0.6:
            return "trend"
        if momentum <= -0.6:
            return "trend"
        return "range"

    def consensus_score(self, analysis_result: Dict[str, Any]) -> float:
        score = max(0.0, min(100.0, self._to_float(analysis_result.get("score", 0.0), 0.0))) / 100.0
        momentum = self._to_float(analysis_result.get("momentum", 0.0), 0.0)
        momentum_score = min(1.0, abs(momentum) / 2.5)
        etf_risk = str(analysis_result.get("etf_risk", "ok") or "ok").lower()
        risk_penalty = 0.0 if etf_risk == "ok" else (0.15 if etf_risk == "warn" else 0.35)

        consensus = (score * 0.7) + (momentum_score * 0.3) - risk_penalty
        return max(0.0, min(1.0, consensus))

    def should_trade(
        self,
        *,
        symbol: str,
        analysis_result: Dict[str, Any],
        runtime_state: Dict[str, Any],
        policy: Dict[str, Any] | None = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        effective = dict(self.DEFAULT_POLICY)
        effective.update(policy or {})
        if not bool(effective.get("enabled", False)):
            return True, {"bypassed": True, "reason": "strategy_engine_disabled"}

        regime = self.detect_regime(analysis_result)
        consensus = self.consensus_score(analysis_result)
        allow_regimes = [str(x).strip().lower() for x in (effective.get("allow_regimes") or [])]

        reasons = []
        high_vol_action = str(effective.get("high_vol_action", "evaluate") or "evaluate").lower()
        if regime == "high_vol" and high_vol_action == "block":
            reasons.append("regime_blocked:high_vol")
        elif regime != "high_vol" and allow_regimes and regime not in allow_regimes:
            reasons.append(f"regime_blocked:{regime}")

        threshold = self._to_float(effective.get("consensus_threshold", 0.60), 0.60)
        if consensus < threshold:
            reasons.append(f"consensus_low:{consensus:.2f}<{threshold:.2f}")

        cooldown_sec = max(0, int(effective.get("cooldown_sec", 60) or 60))
        if cooldown_sec > 0:
            key = f"last_trade_at::{str(symbol).upper()}"
            last_trade_at = runtime_state.get(key)
            if isinstance(last_trade_at, datetime):
                elapsed = (datetime.now() - last_trade_at).total_seconds()
                if elapsed < cooldown_sec:
                    reasons.append(f"cooldown:{int(elapsed)}<{cooldown_sec}")

        return len(reasons) == 0, {
            "regime": regime,
            "consensus": round(consensus, 4),
            "reasons": reasons,
        }
