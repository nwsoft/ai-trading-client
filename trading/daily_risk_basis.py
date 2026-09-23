"""Persist an explicitly labelled risk denominator, never infer account daily PnL."""
import hashlib
import math
import sqlite3


def credential_scope(settings, client, venue):
    key = str((settings or {}).get(f'{venue}_api_key') or '')
    if venue == 'binance' and not key:
        key = str(getattr(getattr(client, 'config', None), 'api_key', '') or '')
    return hashlib.sha256(('risk-basis-v1:'+venue+':'+key).encode()).hexdigest() if key else None


def load_or_create(db_path, day, venue, currency, scope, proposed, *, basis='first_verified_observation_adjusted'):
    if not scope or not db_path:
        raise ValueError('일일 위험 기준의 계정 식별자/저장소 확인 필요')
    if not math.isfinite(proposed) or proposed <= 0:
        raise ValueError('유효한 일일 위험 기준 자산 없음')
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_risk_basis (
            day TEXT, venue TEXT, currency TEXT, credential_scope TEXT,
            initial_equity REAL NOT NULL, basis TEXT NOT NULL,
            PRIMARY KEY(day,venue,currency,credential_scope))''')
        conn.execute('''INSERT OR IGNORE INTO daily_risk_basis VALUES (?,?,?,?,?,?)''',
                     (day,venue,currency,scope,proposed,basis))
        value = float(conn.execute('''SELECT initial_equity FROM daily_risk_basis
            WHERE day=? AND venue=? AND currency=? AND credential_scope=?''',
            (day,venue,currency,scope)).fetchone()[0])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('저장된 일일 위험 기준 자산 검증 실패')
    return value
