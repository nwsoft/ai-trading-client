#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전략 엔진 고도화 계층.

목표:
- 레짐 필터 + 신호 합의 + 과매매 억제 쿨다운을 통해 무의미한 거래를 줄인다.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
        "regime_hysteresis_confirmations": 2,
        "regime_data_max_age_sec": 300,
    }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def detect_regime_details(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        momentum = self._to_float(analysis_result.get("momentum", 0.0), 0.0)
        volatility = abs(momentum)
        if volatility >= 2.0:
            regime = "high_vol"
            confidence = min(1.0, 0.80 + ((volatility - 2.0) / 5.0))
        elif volatility >= 0.6:
            regime = "trend"
            confidence = min(0.95, 0.60 + ((volatility - 0.6) / 3.5))
        else:
            regime = "range"
            confidence = max(0.55, 0.90 - ((volatility / 0.6) * 0.35))

        raw_timestamp = (
            analysis_result.get("observed_at")
            or analysis_result.get("as_of")
            or analysis_result.get("timestamp")
        )
        observed_at = datetime.now(timezone.utc)
        source_timestamp_present = raw_timestamp is not None
        if isinstance(raw_timestamp, datetime):
            observed_at = raw_timestamp
        elif raw_timestamp:
            try:
                observed_at = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            except Exception:
                source_timestamp_present = False
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        else:
            observed_at = observed_at.astimezone(timezone.utc)
        age_sec = max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds())
        return {
            "regime": regime,
            "confidence": round(confidence, 4),
            "observed_at": observed_at.isoformat(),
            "data_age_sec": round(age_sec, 3),
            "source_timestamp_present": source_timestamp_present,
            "evidence": {
                "momentum": round(momentum, 6),
                "absolute_momentum": round(volatility, 6),
            },
        }

    def detect_regime(self, analysis_result: Dict[str, Any]) -> str:
        return str(self.detect_regime_details(analysis_result)["regime"])

    @staticmethod
    def _stabilize_regime(
        *,
        symbol: str,
        candidate: str,
        confidence: float,
        runtime_state: Dict[str, Any],
        confirmations_required: int,
    ) -> Dict[str, Any]:
        """국면 왕복 전환을 줄인다. 고변동 진입과 최초 판정은 즉시 반영한다."""
        key = f"regime_state::{str(symbol).upper()}"
        previous = runtime_state.get(key)
        if not isinstance(previous, dict) or not previous.get("regime"):
            state = {
                "regime": candidate,
                "candidate": candidate,
                "candidate_count": confirmations_required,
                "changed_at": datetime.now(timezone.utc).isoformat(),
            }
            runtime_state[key] = state
            return {
                "regime": candidate,
                "candidate_regime": candidate,
                "transition_pending": False,
                "confirmation_count": confirmations_required,
            }

        current = str(previous.get("regime") or candidate)
        if candidate == current:
            previous.update({"candidate": candidate, "candidate_count": confirmations_required})
            runtime_state[key] = previous
            return {
                "regime": current,
                "candidate_regime": candidate,
                "transition_pending": False,
                "confirmation_count": confirmations_required,
            }

        pending_count = (
            int(previous.get("candidate_count", 0) or 0) + 1
            if str(previous.get("candidate") or "") == candidate
            else 1
        )
        immediate_high_vol = candidate == "high_vol" and confidence >= 0.80
        if immediate_high_vol or pending_count >= confirmations_required:
            previous.update({
                "regime": candidate,
                "candidate": candidate,
                "candidate_count": confirmations_required,
                "changed_at": datetime.now(timezone.utc).isoformat(),
            })
            transition_pending = False
            effective = candidate
        else:
            previous.update({"candidate": candidate, "candidate_count": pending_count})
            transition_pending = True
            effective = current
        runtime_state[key] = previous
        return {
            "regime": effective,
            "candidate_regime": candidate,
            "transition_pending": transition_pending,
            "confirmation_count": pending_count,
        }

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

        regime_details = self.detect_regime_details(analysis_result)
        confirmations_required = max(
            1, int(effective.get("regime_hysteresis_confirmations", 2) or 2)
        )
        stabilized = self._stabilize_regime(
            symbol=symbol,
            candidate=str(regime_details["regime"]),
            confidence=float(regime_details["confidence"]),
            runtime_state=runtime_state,
            confirmations_required=confirmations_required,
        )
        regime = str(stabilized["regime"])
        consensus = self.consensus_score(analysis_result)
        allow_regimes = [str(x).strip().lower() for x in (effective.get("allow_regimes") or [])]

        reasons = []
        max_age_sec = max(0, int(effective.get("regime_data_max_age_sec", 300) or 300))
        if (
            max_age_sec > 0
            and regime_details.get("source_timestamp_present")
            and float(regime_details.get("data_age_sec", 0.0) or 0.0) > max_age_sec
        ):
            reasons.append(
                f"regime_data_stale:{int(regime_details['data_age_sec'])}>{max_age_sec}"
            )
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
                now = datetime.now(last_trade_at.tzinfo) if last_trade_at.tzinfo else datetime.now()
                elapsed = (now - last_trade_at).total_seconds()
                if elapsed < cooldown_sec:
                    reasons.append(f"cooldown:{int(elapsed)}<{cooldown_sec}")

        return len(reasons) == 0, {
            "regime": regime,
            "candidate_regime": stabilized["candidate_regime"],
            "regime_confidence": regime_details["confidence"],
            "regime_observed_at": regime_details["observed_at"],
            "regime_data_age_sec": regime_details["data_age_sec"],
            "regime_transition_pending": stabilized["transition_pending"],
            "regime_confirmation_count": stabilized["confirmation_count"],
            "regime_confirmations_required": confirmations_required,
            "regime_evidence": regime_details["evidence"],
            "consensus": round(consensus, 4),
            "reasons": reasons,
        }
