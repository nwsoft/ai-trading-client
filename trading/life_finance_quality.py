#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생활금융 품질/전환 지표 계층 (6번 착수).

목표:
- 추천 정확도, 상담/추천 전환율, 유지율 지표를 표준 포맷으로 집계
"""

from __future__ import annotations

from typing import Any, Dict, List


class LifeFinanceQualityTracker:
    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def build_quality_report(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(events or [])
        if total == 0:
            return {
                "total_events": 0,
                "recommendation_accuracy": 0.0,
                "conversion_rate": 0.0,
                "retention_rate": 0.0,
                "status": "insufficient_data",
            }

        recommendation_total = 0
        recommendation_correct = 0
        상담_노출 = 0
        상담_전환 = 0
        sessions = set()
        return_sessions = set()

        for e in events or []:
            et = str(e.get("event_type") or "").strip().lower()
            meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
            sid = str(e.get("session_id") or "").strip()
            if sid:
                sessions.add(sid)
                if bool(meta.get("is_returning", False)):
                    return_sessions.add(sid)

            if et in {"recommendation_shown", "recommendation_feedback"}:
                recommendation_total += 1
                if bool(meta.get("is_correct", False)):
                    recommendation_correct += 1

            if et in {"assistant_response", "recommendation_shown"}:
                상담_노출 += 1
            if et in {"goal_created", "product_applied", "budget_saved"}:
                상담_전환 += 1

        recommendation_accuracy = (recommendation_correct / recommendation_total) if recommendation_total > 0 else 0.0
        conversion_rate = (상담_전환 / 상담_노출) if 상담_노출 > 0 else 0.0
        retention_rate = (len(return_sessions) / len(sessions)) if sessions else 0.0

        return {
            "total_events": total,
            "recommendation_accuracy": round(recommendation_accuracy, 4),
            "conversion_rate": round(conversion_rate, 4),
            "retention_rate": round(retention_rate, 4),
            "status": "ok",
        }
