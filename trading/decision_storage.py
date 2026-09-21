"""Additive decision schema and bounded, resumable historical attribution."""
from __future__ import annotations

import json
from trading.event_contract import metadata, hold_key, canonical_json, input_issues

COLUMNS = {
    "contract_version": "INTEGER", "exchange": "TEXT", "execution_mode": "TEXT", "asset_class": "TEXT", "instrument_type": "TEXT", "event_time": "TEXT",
    "strategy_version_id": "TEXT", "reason_code": "TEXT", "strategy_key": "TEXT",
    "app_version": "TEXT", "session_id": "TEXT", "event_kind": "TEXT", "decision_status": "TEXT",
    "actual_order": "INTEGER", "ledger_id": "TEXT", "order_id": "TEXT",
    "repeat_count": "INTEGER NOT NULL DEFAULT 1", "last_event_time": "TEXT", "aggregate_key": "TEXT",
}


def ensure_schema(conn):
    # Concurrent exchange workers can initialize Recorder on the same old DB.
    # Acquire the writer lock before inspecting/adding columns.
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')
    existing = {r[1] for r in conn.execute("PRAGMA table_info(ai_decisions)")}
    for name, sql_type in COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE ai_decisions ADD COLUMN {name} {sql_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_venue_mode_time ON ai_decisions(exchange, execution_mode, event_time DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_venue_time ON ai_decisions(exchange, event_time DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_strategy_time ON ai_decisions(strategy_version_id, event_time DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_type_venue_id ON ai_decisions(decision_type,exchange,id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_asset_venue_time ON ai_decisions(asset_class,exchange,event_time DESC,id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created ON ai_decisions(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_symbol_created ON ai_decisions(symbol,created_at DESC)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_aggregate ON ai_decisions(aggregate_key) WHERE aggregate_key IS NOT NULL")
    conn.execute("CREATE TABLE IF NOT EXISTS storage_migrations(name TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0)")


def save(conn, symbol, kind, data, feedback=None, exchange=None):
    meta = metadata(kind, data, exchange=exchange)
    issues = input_issues(kind, data, exchange)
    if str(kind).startswith(('trade_runtime::', 'stock_auto_trade', 'stock_auto_exit')):
        if meta['exchange'] == 'unknown': issues.append('missing:exchange')
        if meta['execution_mode'] == 'unknown': issues.append('missing:execution_mode')
    if issues:
        from trading.contract_rejections import preserve
        preserve(conn, kind, {'decision': data, 'user_feedback': feedback}, issues, exchange=exchange, symbol=symbol)
        return {**meta, 'storage_status': 'quarantined', 'contract_issues': issues}
    key = hold_key(symbol, kind, data, meta) if feedback is None else None
    names = list(meta)
    sql = f"""INSERT INTO ai_decisions(symbol,decision_type,decision_json,user_feedback,{','.join(names)},last_event_time,aggregate_key)
        VALUES ({','.join('?' for _ in range(len(names)+6))})
        ON CONFLICT(aggregate_key) WHERE aggregate_key IS NOT NULL DO UPDATE SET
        repeat_count=repeat_count+1,last_event_time=excluded.last_event_time"""
    conn.execute(sql, [symbol, kind, canonical_json(data), feedback, *meta.values(), meta['event_time'], key])
    return meta


def backfill_batch(conn, limit=1000):
    # Serialize read-cursor/write-cursor across processes, not just UI jobs.
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')
    row = conn.execute("SELECT cursor FROM storage_migrations WHERE name='decision_metadata_v1'").fetchone()
    cursor = int(row[0]) if row else 0
    rows = conn.execute("SELECT id,decision_type,decision_json,created_at FROM ai_decisions WHERE id>? ORDER BY id LIMIT ?", (cursor, limit)).fetchall()
    for ident, kind, raw, created in rows:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict): data = {}
        except (ValueError, TypeError):
            data = {}
        meta = metadata(kind, data, historical=True, created_at=created)
        conn.execute(f"UPDATE ai_decisions SET {','.join(name+'=?' for name in meta)},last_event_time=? WHERE id=? AND exchange IS NULL",
                     [*meta.values(), meta['event_time'], ident])
    if rows:
        conn.execute("INSERT INTO storage_migrations(name,cursor) VALUES('decision_metadata_v1',?) ON CONFLICT(name) DO UPDATE SET cursor=MAX(cursor,excluded.cursor)", (rows[-1][0],))
    return len(rows)
