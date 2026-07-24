from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping


class NarrativeEngine:
    """뉴스·가격 반응을 설명 가능한 내러티브 클러스터로 변환한다."""

    def build(
        self,
        news_items: Iterable[Dict[str, Any]],
        price_reactions: Mapping[str, float] | None = None,
        flow_signals: Mapping[str, float] | None = None,
        previous: Iterable[Dict[str, Any]] = (),
    ) -> List[Dict[str, Any]]:
        prices = {str(key).upper(): float(value) for key, value in (price_reactions or {}).items()}
        flows = {str(key).upper(): float(value) for key, value in (flow_signals or {}).items()}
        previous_map = {str(row.get("narrative_id")): row for row in previous}
        clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in news_items:
            entities = item.get("entities") or ["MARKET"]
            topics = item.get("topics") or ["기타"]
            for entity in entities:
                for topic in topics:
                    clusters[f"{str(entity).upper()}|{topic}"].append(dict(item))

        result: List[Dict[str, Any]] = []
        for key, items in clusters.items():
            entity, topic = key.split("|", 1)
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            evidence = sorted(
                items,
                key=lambda row: float(row.get("priority_score", row.get("impact_score", 0.0)) or 0.0),
                reverse=True,
            )[:8]
            news_strength = sum(
                float(row.get("impact_score", 0.0) or 0.0)
                * float(row.get("novelty_score", 0.5) or 0.5)
                * float(row.get("source_score", 0.5) or 0.5)
                for row in evidence
            )
            price = prices.get(entity, 0.0)
            flow = flows.get(entity, 0.0)
            confirmation = self._confirmation(price, flow)
            score = min(100.0, news_strength * 30.0 + min(abs(price), 10.0) * 3.0 + min(abs(flow), 10.0) * 2.0)
            previous_row = previous_map.get(digest)
            previous_score = float((previous_row or {}).get("strength", 0.0) or 0.0)
            change = score - previous_score
            phase = "생성" if not previous_row else "확산" if change > 8 else "약화" if change < -8 else "유지"
            contradiction = news_strength > 0.5 and confirmation == "가격·수급 불일치"
            result.append(
                {
                    "narrative_id": digest,
                    "entity": entity,
                    "topic": topic,
                    "headline": f"{entity} · {topic}",
                    "strength": round(score, 2),
                    "phase": phase,
                    "price_reaction_percent": price,
                    "flow_signal": flow,
                    "confirmation": confirmation,
                    "priced_in_hint": abs(price) >= 3.0 and news_strength < 0.7,
                    "contradiction": contradiction,
                    "evidence_ids": [row.get("news_id") for row in evidence if row.get("news_id")],
                    "counter_evidence": [
                        row.get("news_id")
                        for row in evidence
                        if row.get("fact_claim") != "fact"
                    ],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": "",
                    "model_version": "rule-narrative-1",
                }
            )
        result.sort(key=lambda row: row["strength"], reverse=True)
        return result

    @staticmethod
    def _confirmation(price: float, flow: float) -> str:
        """뉴스의 방향을 추정하지 않고 관측된 가격·수급의 동행 여부만 표시한다."""
        if abs(price) <= 0.2 or abs(flow) <= 0.2:
            return "미확인"
        return "가격·수급 동행" if price * flow > 0 else "가격·수급 불일치"
