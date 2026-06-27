#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래 로그를 연합학습용 RL 전이 데이터로 변환한다."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass
class RLTransition:
    """강화학습 전이(표준 구조)"""

    transition_id: str
    symbol: str
    action: int
    reward: float
    done: bool
    state: List[float]
    next_state: List[float]
    timestamp: str
    exchange: str


@dataclass
class AnonymizedRLTransition:
    """개인 식별정보를 제거한 전이 데이터"""

    transition_id: str
    user_hash: str
    symbol_bucket: str
    action: int
    reward: float
    done: bool
    state: List[float]
    next_state: List[float]
    timestamp_date: str
    exchange: str


class RLDataAdapter:
    """trade_log 기반 RL 전이 데이터 생성기"""

    def __init__(self, db_path: str, user_scope: str = "default") -> None:
        self.db_path = db_path
        self.user_scope = user_scope

    def fetch_trade_rows(self, limit: int = 1000) -> List[Dict[str, Any]]:
        if not os.path.exists(self.db_path):
            return []

        query = """
            SELECT
                id,
                symbol,
                side,
                entry_price,
                exit_price,
                quantity,
                leverage,
                pnl,
                pnl_percent,
                entry_time,
                exit_time,
                exchange
            FROM trade_log
            ORDER BY id ASC
            LIMIT ?
        """

        rows: List[Dict[str, Any]] = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(query, (int(limit),)):
                rows.append(dict(row))
        return rows

    def build_transitions(self, rows: Sequence[Dict[str, Any]]) -> List[RLTransition]:
        if not rows:
            return []

        transitions: List[RLTransition] = []
        for idx, row in enumerate(rows):
            next_row = rows[idx + 1] if idx + 1 < len(rows) else row
            done = idx + 1 >= len(rows)
            transition = RLTransition(
                transition_id=f"t_{row.get('id', idx)}",
                symbol=str(row.get("symbol") or "UNKNOWN"),
                action=self._map_action(row.get("side")),
                reward=self._compute_reward(row),
                done=done,
                state=self._to_state_vector(row),
                next_state=self._to_state_vector(next_row),
                timestamp=self._to_iso8601(row.get("exit_time") or row.get("entry_time")),
                exchange=str(row.get("exchange") or "unknown"),
            )
            transitions.append(transition)
        return transitions

    def anonymize(
        self,
        transitions: Iterable[RLTransition],
        salt: str,
    ) -> List[AnonymizedRLTransition]:
        anonymized: List[AnonymizedRLTransition] = []
        user_hash = self._hash_text(f"{self.user_scope}:{salt}")
        for t in transitions:
            anonymized.append(
                AnonymizedRLTransition(
                    transition_id=t.transition_id,
                    user_hash=user_hash,
                    symbol_bucket=self._symbol_bucket(t.symbol),
                    action=t.action,
                    reward=t.reward,
                    done=t.done,
                    state=t.state,
                    next_state=t.next_state,
                    timestamp_date=t.timestamp[:10],
                    exchange=t.exchange,
                )
            )
        return anonymized

    def to_json_records(self, transitions: Iterable[AnonymizedRLTransition]) -> List[Dict[str, Any]]:
        return [asdict(t) for t in transitions]

    def to_jsonl(self, transitions: Iterable[AnonymizedRLTransition]) -> str:
        return "\n".join(json.dumps(asdict(t), ensure_ascii=False) for t in transitions)

    def _to_state_vector(self, row: Dict[str, Any]) -> List[float]:
        entry = float(row.get("entry_price") or 0.0)
        exit_price = float(row.get("exit_price") or entry)
        qty = float(row.get("quantity") or 0.0)
        leverage = float(row.get("leverage") or 1.0)
        pnl_percent = float(row.get("pnl_percent") or 0.0)
        hold_minutes = self._calc_hold_minutes(row.get("entry_time"), row.get("exit_time"))
        price_change = ((exit_price - entry) / entry) if entry > 0 else 0.0

        return [
            round(price_change, 8),
            round(qty, 8),
            round(leverage, 8),
            round(pnl_percent, 8),
            round(hold_minutes, 4),
        ]

    def _compute_reward(self, row: Dict[str, Any]) -> float:
        pnl_percent = row.get("pnl_percent")
        if pnl_percent is not None:
            return float(pnl_percent)

        pnl = float(row.get("pnl") or 0.0)
        qty = float(row.get("quantity") or 0.0)
        entry = float(row.get("entry_price") or 0.0)
        notion = qty * entry
        if notion <= 0:
            return 0.0
        return pnl / notion

    @staticmethod
    def _map_action(side: Any) -> int:
        side_text = str(side or "").strip().lower()
        if side_text in {"buy", "long"}:
            return 1
        if side_text in {"sell", "short"}:
            return 2
        return 0

    @staticmethod
    def _symbol_bucket(symbol: str) -> str:
        sym = str(symbol or "").upper()
        if sym.startswith("BTC"):
            return "BTC"
        if sym.startswith("ETH"):
            return "ETH"
        return "ALT"

    @staticmethod
    def _to_iso8601(value: Any) -> str:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, str) and value.strip():
            return value.strip().replace(" ", "T")
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _calc_hold_minutes(entry_time: Any, exit_time: Any) -> float:
        try:
            if not entry_time or not exit_time:
                return 0.0
            e = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            x = datetime.fromisoformat(str(exit_time).replace("Z", "+00:00"))
            return max(0.0, (x - e).total_seconds() / 60.0)
        except Exception:
            return 0.0
