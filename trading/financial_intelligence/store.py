from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import utc_now_iso


class FinancialIntelligenceStore:
    """금융 인텔리전스 입력·결과·기능 상태를 재현 가능하게 저장한다."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
            return self._connection

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fi_records (
                    record_type TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (record_type, record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_fi_records_type_asof
                    ON fi_records(record_type, as_of DESC);

                CREATE TABLE IF NOT EXISTS fi_feature_status (
                    feature_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fi_analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    analysis_type TEXT NOT NULL,
                    input_snapshot_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    calculation_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def upsert_records(self, record_type: str, records: Iterable[Dict[str, Any]]) -> int:
        with self._lock:
            conn = self._connect()
            count = 0
            for record in records:
                record_id = str(
                    record.get("record_id")
                    or record.get("event_id")
                    or record.get("news_id")
                    or record.get("symbol")
                    or ""
                )
                if not record_id:
                    continue
                provenance = record.get("provenance") or {}
                conn.execute(
                    """
                    INSERT INTO fi_records(record_type, record_id, as_of, source, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_type, record_id) DO UPDATE SET
                        as_of=excluded.as_of,
                        source=excluded.source,
                        payload_json=excluded.payload_json,
                        created_at=excluded.created_at
                    """,
                    (
                        record_type,
                        record_id,
                        str(record.get("as_of") or record.get("timestamp") or record.get("published_at") or provenance.get("as_of") or utc_now_iso()),
                        str(record.get("source") or provenance.get("source") or "unknown"),
                        self._json(record),
                        utc_now_iso(),
                    ),
                )
                count += 1
            conn.commit()
            return count

    def list_records(self, record_type: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT payload_json FROM fi_records WHERE record_type=? ORDER BY as_of DESC LIMIT ?",
                (record_type, max(1, int(limit))),
            ).fetchall()
            return [json.loads(row["payload_json"]) for row in rows]

    def set_feature_status(self, feature_id: str, status: str, evidence: str = "") -> None:
        allowed = {"current", "partial", "planned", "blocked"}
        normalized = status if status in allowed else "planned"
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO fi_feature_status(feature_id, status, evidence, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(feature_id) DO UPDATE SET
                    status=excluded.status, evidence=excluded.evidence, updated_at=excluded.updated_at
                """,
                (feature_id, normalized, evidence, utc_now_iso()),
            )
            conn.commit()

    def feature_statuses(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT feature_id, status, evidence, updated_at FROM fi_feature_status ORDER BY feature_id"
            ).fetchall()
            return {row["feature_id"]: dict(row) for row in rows}

    def save_analysis(
        self,
        run_id: str,
        analysis_type: str,
        inputs: Dict[str, Any],
        result: Dict[str, Any],
        calculation_version: str = "fi-1",
    ) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                INSERT OR REPLACE INTO fi_analysis_runs(
                    run_id, analysis_type, input_snapshot_json, result_json,
                    calculation_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    analysis_type,
                    self._json(inputs),
                    self._json(result),
                    calculation_version,
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
