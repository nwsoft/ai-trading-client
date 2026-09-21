"""Preserve rejected evidence outside normal learning/decision queries."""
import hashlib
from trading.event_contract import canonical_json


def preserve(conn, kind, data, issues, *, exchange=None, symbol=None):
    conn.execute('''CREATE TABLE IF NOT EXISTS contract_rejections(
        fingerprint TEXT PRIMARY KEY, kind TEXT, exchange TEXT, symbol TEXT,
        original_json TEXT NOT NULL, issues TEXT NOT NULL,
        occurrences INTEGER NOT NULL DEFAULT 1,
        first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    body = canonical_json(data)
    encoded = canonical_json(issues)
    fingerprint = hashlib.sha256(canonical_json([kind, exchange, symbol, body, issues]).encode()).hexdigest()
    conn.execute('''INSERT INTO contract_rejections(fingerprint,kind,exchange,symbol,original_json,issues)
        VALUES(?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET
        occurrences=occurrences+1,last_seen=CURRENT_TIMESTAMP''',
        (fingerprint, kind, exchange, symbol, body, encoded))


def count(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contract_rejections'").fetchone()
    return conn.execute('SELECT COALESCE(SUM(occurrences),0) FROM contract_rejections').fetchone()[0] if exists else 0
