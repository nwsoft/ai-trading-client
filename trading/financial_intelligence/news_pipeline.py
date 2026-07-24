from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

from .models import NewsItem, parse_datetime


class NewsPipeline:
    TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]{2,}")
    CLAIM_TERMS = {"발표", "공시", "확정", "보고", "according", "reported", "announced"}
    SPECULATIVE_TERMS = {"전망", "추정", "가능성", "could", "may", "rumor", "예상"}

    def __init__(
        self,
        entity_aliases: Optional[Mapping[str, Iterable[str]]] = None,
        source_scores: Optional[Mapping[str, float]] = None,
    ):
        defaults = {
            "BTC": ["bitcoin", "비트코인", "btc"],
            "ETH": ["ethereum", "이더리움", "eth"],
            "005930": ["삼성전자", "samsung electronics"],
            "AAPL": ["apple", "애플", "aapl"],
        }
        self.entity_aliases = {
            str(entity).upper(): {str(alias).lower() for alias in aliases}
            for entity, aliases in (entity_aliases or defaults).items()
        }
        self.source_scores = {str(key).lower(): float(value) for key, value in (source_scores or {}).items()}

    @classmethod
    def _tokens(cls, text: str) -> List[str]:
        return [token.lower() for token in cls.TOKEN_RE.findall(str(text or ""))]

    @classmethod
    def _canonical_text(cls, text: str) -> str:
        return " ".join(cls._tokens(text))

    def normalize(self, raw: Dict[str, Any], default_source: str = "unknown") -> NewsItem:
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or raw.get("description") or "").strip()
        source = str(raw.get("source") or default_source).strip()
        url = str(raw.get("url") or raw.get("link") or "").strip()
        published = parse_datetime(raw.get("published_at") or raw.get("published") or datetime.now(timezone.utc)).isoformat()
        digest = hashlib.sha256(f"{url}|{title}|{published[:10]}".encode("utf-8")).hexdigest()[:24]
        content = f"{title} {summary}".lower()
        entities = sorted(
            entity
            for entity, aliases in self.entity_aliases.items()
            if any(alias in content for alias in aliases)
        )
        claim_type = "fact"
        if any(term in content for term in self.SPECULATIVE_TERMS):
            claim_type = "estimate"
        elif not any(term in content for term in self.CLAIM_TERMS):
            claim_type = "unknown"
        topics = self._topic_tags(content)
        source_score = self.source_scores.get(source.lower(), float(raw.get("source_score", 0.5) or 0.5))
        impact = min(1.0, 0.15 * len(entities) + 0.12 * len(topics) + (0.25 if claim_type == "fact" else 0.05))
        flags: List[str] = []
        if not url:
            flags.append("missing_source_url")
        if claim_type != "fact":
            flags.append("unverified_or_speculative")
        return NewsItem(
            news_id=str(raw.get("news_id") or digest),
            title=title,
            published_at=published,
            source=source,
            url=url,
            summary=summary,
            entities=entities,
            topics=topics,
            source_score=max(0.0, min(source_score, 1.0)),
            impact_score=impact,
            fact_claim=claim_type,
            quality_flags=flags,
        )

    @staticmethod
    def _topic_tags(content: str) -> List[str]:
        mapping = {
            "실적": ["earnings", "실적", "revenue", "매출"],
            "통화정책": ["fomc", "금리", "rate decision", "central bank"],
            "규제": ["regulation", "규제", "sec", "금융위"],
            "상장": ["listing", "상장", "delisting", "상폐"],
            "기술": ["ai", "반도체", "technology", "blockchain"],
            "수급": ["fund flow", "외국인", "기관", "etf flow"],
        }
        return [topic for topic, terms in mapping.items() if any(term in content for term in terms)]

    def deduplicate(self, items: Iterable[NewsItem | Dict[str, Any]], threshold: float = 0.82) -> List[NewsItem]:
        normalized = [item if isinstance(item, NewsItem) else self.normalize(item) for item in items]
        unique: List[NewsItem] = []
        for item in sorted(normalized, key=lambda row: row.published_at):
            canonical = self._canonical_text(item.title)
            duplicate_index = None
            for index, existing in enumerate(unique):
                ratio = SequenceMatcher(None, canonical, self._canonical_text(existing.title)).ratio()
                same_url = bool(item.url and existing.url and item.url == existing.url)
                if same_url or ratio >= threshold:
                    duplicate_index = index
                    break
            if duplicate_index is None:
                unique.append(item)
            else:
                existing = unique[duplicate_index]
                if (item.source_score, len(item.summary)) > (existing.source_score, len(existing.summary)):
                    item.quality_flags.append("deduplicated_representative")
                    unique[duplicate_index] = item
                else:
                    existing.quality_flags.append("duplicate_reports_collapsed")
        return unique

    def score_novelty(self, items: Iterable[NewsItem]) -> List[NewsItem]:
        previous_tokens: List[set[str]] = []
        output: List[NewsItem] = []
        for item in sorted(items, key=lambda row: row.published_at):
            tokens = set(self._tokens(f"{item.title} {item.summary}"))
            max_overlap = 0.0
            for past in previous_tokens[-50:]:
                union = tokens | past
                overlap = len(tokens & past) / len(union) if union else 0.0
                max_overlap = max(max_overlap, overlap)
            item.novelty_score = max(0.0, min(1.0, 1.0 - max_overlap))
            previous_tokens.append(tokens)
            output.append(item)
        return output

    def prioritize(
        self,
        items: Iterable[NewsItem],
        held_symbols: Iterable[str] = (),
    ) -> List[Dict[str, Any]]:
        held = {str(symbol).upper() for symbol in held_symbols}
        result: List[Dict[str, Any]] = []
        for item in items:
            held_match = bool(held.intersection(item.entities))
            priority = (
                item.impact_score * 0.35
                + item.novelty_score * 0.25
                + item.source_score * 0.25
                + (0.15 if held_match else 0.0)
            )
            payload = item.to_dict()
            payload["held_match"] = held_match
            payload["priority_score"] = round(priority, 4)
            result.append(payload)
        result.sort(key=lambda row: (row["priority_score"], row["published_at"]), reverse=True)
        return result

    def fetch_rss(self, url: str, source: str = "rss", timeout: float = 8.0) -> Dict[str, Any]:
        try:
            response = requests.get(url, timeout=max(1.0, float(timeout)), headers={"User-Agent": "NoahAI/1.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            rows: List[NewsItem] = []
            for item in root.findall(".//item"):
                rows.append(
                    self.normalize(
                        {
                            "title": item.findtext("title") or "",
                            "summary": item.findtext("description") or "",
                            "url": item.findtext("link") or "",
                            "published_at": item.findtext("pubDate") or datetime.now(timezone.utc).isoformat(),
                        },
                        source,
                    )
                )
            return {"status": "ok", "items": [item.to_dict() for item in rows]}
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}:{exc}", "items": []}
