#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거래로그, 분석결과, 최종 손익 등을 SQLite + .log 로 저장
"""

import sqlite3
import json
import hashlib
import logging
import os
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from loguru import logger as _base_logger
from log_system.log_adapter import log_event
import pandas as pd
from trading.pnl_evidence import performance_evidence, provider_fill_gross_pnl


@dataclass
class TradeLog:
    """거래 로그"""
    id: Optional[int]
    symbol: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    leverage: int
    pnl: Optional[float]
    pnl_percent: Optional[float]
    entry_time: datetime
    exit_time: Optional[datetime]
    reason: str
    side: str
    tp_price: Optional[float]
    sl_price: Optional[float]
    fees: float
    slippage: float
    exchange: Optional[str] = None
    order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    model_version: Optional[str] = None
    strategy_variant: Optional[str] = None
    fee_asset: Optional[str] = None
    fee_source: Optional[str] = None
    position_owner: str = "legacy_unknown"
    execution_mode: str = "live"
    spot_baseline_quantity: float = 0.0
    gross_pnl: Optional[float] = None
    net_pnl: Optional[float] = None
    entry_fee: Optional[float] = None
    exit_fee: Optional[float] = None
    entry_fee_asset: Optional[str] = None
    exit_fee_asset: Optional[str] = None
    settlement_currency: Optional[str] = None
    pnl_source: str = "legacy_unverified"
    reconciliation_status: str = "legacy_unverified"
    strategy_key: Optional[str] = None
    strategy_version_id: Optional[str] = None


@dataclass
class AnalysisLog:
    """분석 로그"""
    id: Optional[int]
    symbol: str
    signal: str
    confidence: float
    rsi: float
    macd: float
    sma_20: float
    sma_50: float
    bb_upper: float
    bb_lower: float
    volume_ratio: float
    volatility: float
    trend: str
    reasoning: str
    timestamp: datetime


@dataclass
class OptimizationLog:
    """최적화 로그"""
    id: Optional[int]
    symbol: str
    optimization_type: str
    original_params: Dict
    optimized_params: Dict
    improvement_score: float
    confidence: float
    reasoning: str
    timestamp: datetime


class Recorder:
    def _write_connection(self, *, operation, timeout=5):
        from trading.write_coordination import connection
        background = operation in {'save_ai_decision', 'insert_analysis_log', 'insert_optimization_log',
            'save_ai_trade_analysis', 'save_coin_selection', 'record_coin_change', 'cleanup_old_logs'}
        maintenance = operation in {'link_unresolved_trade_closes_with_executions', 'reconcile_trade_log_with_executions',
                                    'recover_linked_close_time'}
        return connection(self.db_path, operation=operation, priority=20 if maintenance else 10 if background else 0, timeout=timeout)

    def __init__(self, db_path: Optional[str] = None, log_path: Optional[str] = None, binance_client: Optional[Any] = None, exchange: Optional[str] = None, *args, **kwargs):
        # exchange 인자 우선, 없으면 기본값 'binance'
        self.exchange = exchange or getattr(self, 'exchange', None) or 'binance'

        # db_path, log_path 기본값 처리
        if db_path is None or log_path is None:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from path_utils import get_db_file_path, get_log_dir
            if db_path is None:
                # 🔥 사용자 계정별 경로 보장 (v3.8.9.5+)
                db_path = get_db_file_path()
            if log_path is None:
                # 🔥 사용자 계정별 로그 경로 보장 (v3.8.9.5+)
                log_path = get_log_dir()

        self.db_path = db_path
        self.log_path = log_path
        self.binance_client = binance_client

        # 로그 디렉토리 생성
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.log_path, exist_ok=True)

        # 로거 설정
        self._logger = self._get_exchange_logger()
        self.setup_logger()
        logger = self._logger

        # 데이터베이스 초기화
        self.init_database()

        from trading.recorder_write_queue import schedule
        schedule(self)

        logger.info("Recorder 초기화 완료")

    def _get_exchange_logger(self):
        class ExchangeLogger:
            def __init__(self, base_logger, exchange):
                self.base_logger = base_logger
                self.exchange = exchange
            def info(self, msg, *a, **k):
                self.base_logger.info(f"{msg} (ex={self.exchange})", *a, **k)
            def warning(self, msg, *a, **k):
                self.base_logger.warning(f"{msg} (ex={self.exchange})", *a, **k)
            def error(self, msg, *a, **k):
                self.base_logger.error(f"{msg} (ex={self.exchange})", *a, **k)
            def debug(self, msg, *a, **k):
                self.base_logger.debug(f"{msg} (ex={self.exchange})", *a, **k)
        return ExchangeLogger(_base_logger, self.exchange)

    @staticmethod
    def _to_db_datetime(value: Any) -> Any:
        """sqlite 저장 시 datetime 객체를 ISO 문자열로 정규화한다."""
        if isinstance(value, datetime):
            return value.isoformat(sep=' ', timespec='seconds')
        return value

    @staticmethod
    def _get_table_columns(cursor: sqlite3.Cursor, table_name: str) -> List[str]:
        """테이블 컬럼 목록을 소문자 기준으로 반환한다."""
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            return [str(row[1]).lower() for row in (cursor.fetchall() or []) if len(row) > 1]
        except Exception:
            return []

    def _run_exchange_trade_stats_fee_migration(self, conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
        """exchange_trade_stats fee 컬럼 보강 + trade_log 기반 1회 백필 + 검증.

        - 사용자 데이터 경로 DB를 직접 보강
        - 컬럼이 없으면 추가, 있으면 유지
        - 스키마 변경 실패 시 기존 경로로 안전 폴백
        """
        try:
            exchange_cols = set(self._get_table_columns(cursor, 'exchange_trade_stats'))
            if not exchange_cols:
                return

            # 1) 스키마 보강 (optional 접근)
            if 'total_fees' not in exchange_cols:
                cursor.execute("ALTER TABLE exchange_trade_stats ADD COLUMN total_fees REAL DEFAULT 0.0")
            if 'avg_fee' not in exchange_cols:
                cursor.execute("ALTER TABLE exchange_trade_stats ADD COLUMN avg_fee REAL DEFAULT 0.0")
            conn.commit()

            exchange_cols = set(self._get_table_columns(cursor, 'exchange_trade_stats'))
            if 'total_fees' not in exchange_cols or 'avg_fee' not in exchange_cols:
                return

            # 2) trade_log 기반 백필 준비 (legacy exchange NULL -> binance)
            cursor.execute('CREATE TABLE IF NOT EXISTS storage_migrations(name TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0)')
            if cursor.execute("SELECT 1 FROM storage_migrations WHERE name='exchange_stats_fee_v1' AND cursor=1").fetchone():
                return
            trade_cols = set(self._get_table_columns(cursor, 'trade_log'))
            if not trade_cols:
                return

            fee_expr = "COALESCE(fees, 0)" if 'fees' in trade_cols else "0"

            # 기존 max_drawdown 보존
            cursor.execute("SELECT exchange, COALESCE(max_drawdown, 0.0) FROM exchange_trade_stats")
            dd_map = {str(r[0]).lower(): float(r[1] or 0.0) for r in (cursor.fetchall() or []) if r and r[0]}

            cursor.execute(
                f"""
                SELECT
                    LOWER(COALESCE(exchange, 'binance')) as ex,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN COALESCE(pnl, 0) < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(COALESCE(pnl, 0)) as total_pnl,
                    SUM({fee_expr}) as total_fees,
                    AVG({fee_expr}) as avg_fee
                FROM trade_log
                WHERE exit_time IS NOT NULL
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
                GROUP BY LOWER(COALESCE(exchange, 'binance'))
                """
            )
            grouped = cursor.fetchall() or []

            for row in grouped:
                ex = str(row[0] or 'binance').lower()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO exchange_trade_stats (
                        exchange, total_trades, winning_trades, losing_trades,
                        total_pnl, max_drawdown, total_fees, avg_fee, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        ex,
                        int(row[1] or 0),
                        int(row[2] or 0),
                        int(row[3] or 0),
                        float(row[4] or 0.0),
                        float(dd_map.get(ex, 0.0)),
                        float(row[5] or 0.0),
                        float(row[6] or 0.0),
                    ),
                )
            conn.commit()

            # 3) 검증 (요약합 대조)
            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(COALESCE(pnl, 0)), 0.0),
                    COALESCE(SUM({fee_expr}), 0.0)
                FROM trade_log
                WHERE exit_time IS NOT NULL
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
                """
            )
            trade_total_pnl, trade_total_fees = cursor.fetchone() or (0.0, 0.0)

            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(COALESCE(total_pnl, 0)), 0.0),
                    COALESCE(SUM(COALESCE(total_fees, 0)), 0.0)
                FROM exchange_trade_stats
                """
            )
            stats_total_pnl, stats_total_fees = cursor.fetchone() or (0.0, 0.0)

            pnl_gap = abs(float(trade_total_pnl or 0.0) - float(stats_total_pnl or 0.0))
            fee_gap = abs(float(trade_total_fees or 0.0) - float(stats_total_fees or 0.0))

            if pnl_gap > 1e-4 or fee_gap > 1e-4:
                log_event(
                    'trade',
                    f"⚠️ exchange_trade_stats 백필 검증 불일치: pnl_gap={pnl_gap:.6f}, fee_gap={fee_gap:.6f}",
                    exchange=self.exchange,
                    level='WARNING'
                )
            else:
                cursor.execute("INSERT INTO storage_migrations(name,cursor) VALUES('exchange_stats_fee_v1',1) ON CONFLICT(name) DO UPDATE SET cursor=1")
                conn.commit()
                log_event(
                    'trade',
                    "✅ exchange_trade_stats fee 백필/검증 완료",
                    exchange=self.exchange,
                    level='INFO'
                )
        except Exception as e:
            # 마이그레이션 오류가 있어도 기존 경로는 계속 동작하도록 안전 폴백
            log_event('trade', f"⚠️ exchange_trade_stats fee 마이그레이션 스킵: {e}", exchange=self.exchange, level='WARNING')



    def setup_logger(self):
        """로거 설정 - main.py의 포맷 사용"""
        # main.py에서 이미 설정된 loguru 포맷을 사용
        # 별도 포맷 설정 없음
    pass

    def init_database(self):
        """데이터베이스 초기화"""
        try:
            with self._write_connection(operation='init_database') as conn:
                cursor = conn.cursor()

                # 거래 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL,
                        quantity REAL NOT NULL,
                        leverage INTEGER NOT NULL,
                        pnl REAL,
                        pnl_percent REAL,
                        reason TEXT,
                        entry_time DATETIME NOT NULL,
                        exit_time DATETIME,
                        tp_price REAL,
                        sl_price REAL,
                        fees REAL DEFAULT 0,
                        slippage REAL DEFAULT 0,
                        exchange TEXT,
                        order_id TEXT,
                        exit_order_id TEXT,
                        model_version TEXT,
                        strategy_variant TEXT,
                        fee_asset TEXT,
                        fee_source TEXT,
                        position_owner TEXT NOT NULL DEFAULT 'legacy_unknown',
                        execution_mode TEXT NOT NULL DEFAULT 'live',
                        spot_baseline_quantity REAL NOT NULL DEFAULT 0.0,
                        gross_pnl REAL,
                        net_pnl REAL,
                        entry_fee REAL,
                        exit_fee REAL,
                        entry_fee_asset TEXT,
                        exit_fee_asset TEXT,
                        settlement_currency TEXT,
                        pnl_source TEXT NOT NULL DEFAULT 'legacy_unverified',
                        reconciliation_status TEXT NOT NULL DEFAULT 'legacy_unverified',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 분석 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS analysis_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        signal TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        rsi REAL,
                        macd REAL,
                        sma_20 REAL,
                        sma_50 REAL,
                        bb_upper REAL,
                        bb_lower REAL,
                        volume_ratio REAL,
                        volatility REAL,
                        trend TEXT,
                        reasoning TEXT,
                        timestamp DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # AI 최적화 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_optimization (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        optimization_type TEXT NOT NULL,
                        optimization_data TEXT,
                        original_params TEXT,
                        optimized_params TEXT,
                        improvement_score REAL,
                        confidence REAL,
                        reasoning TEXT,
                        timestamp DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # AI 거래 분석 테이블 (익절/손절 분석 결과 저장)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_trade_analysis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_log_id INTEGER,
                        symbol TEXT NOT NULL,
                        analysis_type TEXT NOT NULL, -- PROFIT or LOSS
                        analysis_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(trade_log_id) REFERENCES trade_log(id)
                    )
                """)

                # AI 결정 내역 테이블 (포지션 크기 최적화 결과 저장)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        decision_type TEXT NOT NULL, -- POSITION_SIZE, PATTERN_ANALYSIS, etc.
                        decision_json TEXT NOT NULL,
                        user_feedback TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 코인 평가 테이블
                from trading.decision_storage import ensure_schema
                ensure_schema(conn)

                # 코인 선택 세션 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS coin_selection_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        exchange TEXT NOT NULL DEFAULT 'legacy_unscoped',
                        market_regime TEXT NOT NULL,
                        total_coins INTEGER NOT NULL,
                        major_coins_count INTEGER NOT NULL,
                        alt_coins_count INTEGER NOT NULL,
                        selection_reason TEXT,
                        selection_status TEXT NOT NULL DEFAULT 'scored',
                        adjustment_factor REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 선택된 코인 상세 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS selected_coins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        exchange TEXT NOT NULL DEFAULT 'legacy_unscoped',
                        symbol TEXT NOT NULL,
                        is_major BOOLEAN NOT NULL,
                        selection_status TEXT NOT NULL DEFAULT 'scored',
                        selection_reason TEXT,
                        overall_score REAL,
                        technical_score REAL,
                        volatility_score REAL,
                        volume_score REAL,
                        trend_score REAL,
                        risk_score REAL,
                        volume REAL,
                        price_change_percent REAL,
                        orderbook_depth INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(session_id) REFERENCES coin_selection_sessions(id)
                    )
                """)
                # v3.9.1.12 이하 selected_coins에는 거래소 범위가 없어 Web UI가
                # source-strict 조회를 수행하면 항상 빈 목록이 되었다. 기존 행을
                # 임의로 Binance로 귀속하지 않고 legacy_unscoped로 보존한 뒤,
                # 새 선정부터 거래소와 산출 상태를 명시한다.
                for table_name, columns_to_add in {
                    'coin_selection_sessions': (
                        "exchange TEXT NOT NULL DEFAULT 'legacy_unscoped'",
                        "selection_status TEXT NOT NULL DEFAULT 'scored'",
                    ),
                    'selected_coins': (
                        "exchange TEXT NOT NULL DEFAULT 'legacy_unscoped'",
                        "selection_status TEXT NOT NULL DEFAULT 'scored'",
                        "selection_reason TEXT",
                    ),
                }.items():
                    existing = set(self._get_table_columns(cursor, table_name))
                    for column_sql in columns_to_add:
                        column_name = column_sql.split()[0].lower()
                        if column_name not in existing:
                            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
                            existing.add(column_name)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_selected_coins_exchange_session "
                    "ON selected_coins(exchange, session_id, id)"
                )
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS coin_evaluation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        technical_score REAL,
                        volatility_score REAL,
                        volume_score REAL,
                        trend_score REAL,
                        risk_score REAL,
                        overall_score REAL,
                        rank INTEGER,
                        selection_reason TEXT,
                        risk_level TEXT,
                        timestamp DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 리스크 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS risk_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        risk_type TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        description TEXT,
                        impact_score REAL,
                        timestamp DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 성과 통계 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date DATE NOT NULL,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        losing_trades INTEGER DEFAULT 0,
                        total_pnl REAL DEFAULT 0,
                        win_rate REAL DEFAULT 0,
                        avg_win REAL DEFAULT 0,
                        avg_loss REAL DEFAULT 0,
                        max_drawdown REAL DEFAULT 0,
                        sharpe_ratio REAL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(date)
                    )
                """)

                # 거래소별 거래 통계 테이블 (새로 추가)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exchange_trade_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        exchange TEXT NOT NULL,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        losing_trades INTEGER DEFAULT 0,
                        total_pnl REAL DEFAULT 0.0,
                        max_drawdown REAL DEFAULT 0.0,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(exchange)
                    )
                """)

                # 거래소 원장 기준 실제 체결 내역. trade_log는 NoahAI가 추적한
                # 진입-청산 성과이고, 이 테이블은 수동 주문을 포함한 거래소 체결
                # 원장을 보존한다. 두 의미를 섞어 승률/PnL을 왜곡하지 않는다.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exchange_execution_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        execution_key TEXT NOT NULL UNIQUE,
                        exchange TEXT NOT NULL,
                        trade_id TEXT,
                        order_id TEXT,
                        symbol TEXT NOT NULL,
                        side TEXT,
                        price REAL DEFAULT 0.0,
                        quantity REAL DEFAULT 0.0,
                        cost REAL DEFAULT 0.0,
                        fee REAL DEFAULT 0.0,
                        realized_pnl REAL DEFAULT 0.0,
                        realized_pnl_present INTEGER NOT NULL DEFAULT 0,
                        fee_currency TEXT,
                        executed_at DATETIME,
                        raw_status TEXT,
                        confirmation_status TEXT NOT NULL DEFAULT 'legacy_unverified',
                        source TEXT DEFAULT 'exchange_api',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exchange_order_receipt (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        exchange TEXT NOT NULL,
                        order_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT,
                        requested_quantity REAL DEFAULT 0.0,
                        status TEXT,
                        confirmed INTEGER NOT NULL DEFAULT 0,
                        submitted_at DATETIME,
                        last_checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        source TEXT,
                        raw_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(exchange, order_id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exchange_execution_capability (
                        exchange TEXT PRIMARY KEY,
                        history_available INTEGER NOT NULL DEFAULT 0,
                        history_reason TEXT NOT NULL DEFAULT 'not_checked',
                        historical_trades INTEGER NOT NULL DEFAULT 0,
                        closed_orders_fallback INTEGER NOT NULL DEFAULT 0,
                        history_complete INTEGER NOT NULL DEFAULT 0,
                        coverage_start DATETIME,
                        coverage_end DATETIME,
                        coverage_reason TEXT NOT NULL DEFAULT 'bounded_or_incremental_history',
                        checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                for column_sql in (
                    "history_complete INTEGER NOT NULL DEFAULT 0",
                    "coverage_start DATETIME",
                    "coverage_end DATETIME",
                    "coverage_reason TEXT NOT NULL DEFAULT 'bounded_or_incremental_history'",
                ):
                    try:
                        cursor.execute(
                            f"ALTER TABLE exchange_execution_capability ADD COLUMN {column_sql}"
                        )
                    except sqlite3.OperationalError as exc:
                        if "duplicate column" not in str(exc).lower():
                            raise
                try:
                    cursor.execute(
                        "ALTER TABLE exchange_execution_log ADD COLUMN "
                        "confirmation_status TEXT NOT NULL DEFAULT 'legacy_unverified'"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
                try:
                    cursor.execute(
                        "ALTER TABLE exchange_execution_log ADD COLUMN "
                        "realized_pnl REAL DEFAULT 0.0"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
                try:
                    cursor.execute(
                        "ALTER TABLE exchange_execution_log ADD COLUMN "
                        "realized_pnl_present INTEGER NOT NULL DEFAULT 0"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise

                # 주식/ETF 브로커·자산유형별 거래 통계 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_trade_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        broker TEXT NOT NULL,
                        asset_type TEXT NOT NULL,
                        stat_date DATE NOT NULL,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        losing_trades INTEGER DEFAULT 0,
                        buy_count INTEGER DEFAULT 0,
                        sell_count INTEGER DEFAULT 0,
                        realized_pnl REAL DEFAULT 0.0,
                        win_rate REAL DEFAULT 0.0,
                        avg_pnl REAL DEFAULT 0.0,
                        max_drawdown REAL DEFAULT 0.0,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(broker, asset_type, stat_date)
                    )
                """)

                # 주식 자동매매 실행 품질 메트릭 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_execution_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        broker TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        order_type TEXT,
                        execution_mode TEXT,
                        success INTEGER DEFAULT 0,
                        latency_ms REAL DEFAULT 0.0,
                        slippage_bps REAL DEFAULT 0.0,
                        rejection_reason TEXT,
                        decision_type TEXT DEFAULT 'entry',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 중복 주문 방지(idempotency) 키 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_order_idempotency (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        broker TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        symbol TEXT,
                        side TEXT,
                        order_type TEXT,
                        quantity REAL,
                        price REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(broker, idempotency_key)
                    )
                """)

                # 암호화폐 OMS 명령 원장: 프로세스 재시작 뒤에도 같은 명령을
                # 재제출하지 않고 거래소 결과를 먼저 조회하기 위한 SSOT.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS crypto_order_commands (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        command_id TEXT NOT NULL UNIQUE,
                        exchange TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        intent_type TEXT NOT NULL,
                        quantity REAL DEFAULT 0.0,
                        position_key TEXT,
                        status TEXT NOT NULL DEFAULT 'created',
                        exchange_order_id TEXT,
                        error_class TEXT,
                        error_message TEXT,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.commit()


                # 스키마 보강: ai_optimization에 optimization_data 컬럼이 없으면 추가
                try:
                    cursor.execute("PRAGMA table_info(ai_optimization)")
                    cols = [row[1] for row in cursor.fetchall()]
                    if 'optimization_data' not in cols:
                        cursor.execute("ALTER TABLE ai_optimization ADD COLUMN optimization_data TEXT")
                        conn.commit()
                except Exception:
                    pass
                # 경량 마이그레이션: 실제 체결·모델·수수료 추적 컬럼을 기존 DB에도 추가
                try:
                    cursor.execute("PRAGMA table_info(trade_log)")
                    cols = [row[1] for row in cursor.fetchall()]
                    required_columns = {
                        'strategy_key': 'TEXT',
                        'strategy_version_id': 'TEXT',
                        'exchange': 'TEXT',
                        'order_id': 'TEXT',
                        'exit_order_id': 'TEXT',
                        'model_version': 'TEXT',
                        'strategy_variant': 'TEXT',
                        'fee_asset': 'TEXT',
                        'fee_source': 'TEXT',
                        'position_owner': "TEXT NOT NULL DEFAULT 'legacy_unknown'",
                        'execution_mode': "TEXT NOT NULL DEFAULT 'live'",
                        'spot_baseline_quantity': 'REAL NOT NULL DEFAULT 0.0',
                        'gross_pnl': 'REAL',
                        'net_pnl': 'REAL',
                        'entry_fee': 'REAL',
                        'exit_fee': 'REAL',
                        'entry_fee_asset': 'TEXT',
                        'exit_fee_asset': 'TEXT',
                        'settlement_currency': 'TEXT',
                        'pnl_source': "TEXT NOT NULL DEFAULT 'legacy_unverified'",
                        'reconciliation_status': "TEXT NOT NULL DEFAULT 'legacy_unverified'",
                    }
                    for column, column_type in required_columns.items():
                        if column not in cols:
                            cursor.execute(f"ALTER TABLE trade_log ADD COLUMN {column} {column_type}")
                    conn.commit()
                except Exception:
                    pass

                # 성능 인덱스: 거래소/청산시간 조합 조회 최적화
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_exchange_exit_time ON trade_log(exchange, exit_time)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_exit_time ON trade_log(exit_time DESC)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_exit_order_owner ON trade_log(LOWER(exchange), exit_order_id, UPPER(symbol))")
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_trade_exchange_normalized_exit_time "
                        "ON trade_log(LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')), exit_time DESC)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_exchange_execution_venue_time "
                        "ON exchange_execution_log(exchange, executed_at)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_exchange_execution_confirmed_time "
                        "ON exchange_execution_log(confirmation_status, executed_at DESC)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_exchange_execution_order_id "
                        "ON exchange_execution_log(exchange, order_id)"
                    )
                    conn.commit()
                except Exception:
                    pass

                # 주식 통계 조회 인덱스
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_stats_broker_date ON stock_trade_stats(broker, stat_date)")
                    conn.commit()
                except Exception:
                    pass

                # 실행 품질/중복방지 인덱스
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_exec_metrics_broker_time ON stock_execution_metrics(broker, created_at)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_idempotency_broker_time ON stock_order_idempotency(broker, created_at)")
                    conn.commit()
                except Exception:
                    pass

                # v3.8.9.28+ 사용자 DB 패치: exchange_trade_stats fee 컬럼/백필/검증
                self._run_exchange_trade_stats_fee_migration(conn, cursor)

                log_event('trade', "데이터베이스 초기화 완료", exchange=self.exchange, level='INFO')

        except Exception as e:
            log_event('trade', f"데이터베이스 초기화 오류: {e}", exchange=self.exchange, level='ERROR')

    def log_trade_entry(self, position, trade_params: Dict) -> Optional[int]:
        """거래 진입 로그를 멱등하게 보존한다.

        공통(CCXT) 거래 경로는 실제 체결 원장과 별개로 이 행이 있어야 청산
        시 손익 UPDATE, 거래통계, AI 리포트가 같은 거래를 이어서 볼 수 있다.
        """
        try:
            exchange = str(trade_params.get('exchange') or '').strip().lower() or None
            order_id = str(trade_params.get('order_id') or '').strip() or None
            if exchange and order_id:
                existing = self.execute_query(
                    """
                    SELECT id FROM trade_log
                    WHERE LOWER(COALESCE(exchange, '')) = ? AND order_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (exchange, order_id),
                )
                if existing:
                    return int(existing[0][0])

            trade_log = TradeLog(
                id=None,
                symbol=position.symbol,
                entry_price=position.entry_price,
                exit_price=None,  # 청산 시에만 설정
                quantity=position.quantity,
                leverage=position.leverage,
                pnl=None,  # 청산 시에만 설정
                pnl_percent=None,  # 청산 시에만 설정
                entry_time=position.entry_time,
                exit_time=None,  # 청산 시에만 설정
                reason=trade_params.get('reason', 'AI 신호'),
                side=position.side.value,
                tp_price=position.tp_price,
                sl_price=position.sl_price,
                fees=max(0.0, float(trade_params.get('entry_fee', 0.0) or 0.0)),
                slippage=0.0,
                exchange=exchange,
                order_id=order_id,
                strategy_key=getattr(position, 'custom_strategy_key', None) or trade_params.get('_selected_custom_strategy_key'),
                strategy_version_id=getattr(position, 'custom_strategy_version_id', None) or trade_params.get('_selected_custom_strategy_version_id'),
                fee_asset=str(trade_params.get('entry_fee_asset') or '').strip().upper() or None,
                fee_source=str(trade_params.get('fee_source') or 'exchange_order'),
                position_owner='noahai',
                execution_mode=str(trade_params.get('execution_mode', 'live') or 'live'),
                spot_baseline_quantity=float(
                    trade_params.get(
                        'spot_baseline_quantity',
                        getattr(position, 'spot_baseline_quantity', 0.0),
                    ) or 0.0
                ),
                entry_fee=(max(0.0, float(trade_params['entry_fee'])) if trade_params.get('entry_fee') is not None else None),
                entry_fee_asset=str(trade_params.get('entry_fee_asset') or '').strip().upper() or None,
                settlement_currency=(
                    str(trade_params.get('settlement_currency') or '').strip().upper()
                    or self._settlement_currency(position.symbol, exchange or self.exchange)
                ),
                pnl_source='pending_exchange_close',
                reconciliation_status='open',
            )

            inserted_id = self.insert_trade_log(trade_log)
            if inserted_id is None:
                log_event('trade', f"거래 진입 로그 저장 실패: {position.symbol}", exchange=self.exchange, level='ERROR')
                return None
            log_event('trade', f"거래 진입 로그 기록: {position.symbol}", exchange=self.exchange, level='INFO')
            return inserted_id

        except Exception as e:
            log_event('trade', f"거래 진입 로그 기록 오류: {e}", exchange=self.exchange, level='ERROR')
            return None

    def log_trade_exit(
        self,
        position,
        reason: str,
        exit_price: float,
        actual_trade_info: Optional[Dict[str, Any]] = None,
        *,
        exchange: Optional[str] = None,
        exit_order_id: Optional[str] = None,
    ) -> bool:
        """거래 청산 로그 - 실제 체결 정보(있으면) 기반 정확한 계산
        - actual_trade_info가 제공되면 그 값을 우선 사용
        - 미제공 시 exit_order_id로만 Binance 체결을 조회한다.
        - 주문 ID가 없으면 거래소 확정값을 추측하지 않고 대조 대기로 남긴다.
        """
        try:
            # 1. 실제 거래 정보 준비
            #    - 호출자가 제공한 actual_trade_info 우선
            #    - 없으면 바이낸스 API에서 조회 시도
            if actual_trade_info is None:
                actual_trade_info = self.get_actual_trade_info(
                    position.symbol,
                    position.entry_time,
                    position.side.value,
                    exit_order_id=exit_order_id,
                )

            if actual_trade_info:
                # 실제 거래소 데이터 사용
                actual_exit_price = actual_trade_info.get('exit_price', exit_price)
                actual_fees = actual_trade_info.get('fees', 0.0)
                actual_slippage = actual_trade_info.get('slippage', 0.0)
                actual_quantity = actual_trade_info.get('quantity', position.quantity)
            else:
                # 폴백: 기존 계산 방식 + 수수료/슬리피지 추정
                actual_exit_price = exit_price
                actual_fees = self.estimate_fees(position.quantity, exit_price)
                actual_slippage = self.estimate_slippage(position.symbol)
                actual_quantity = position.quantity

            entry_order_ids = [
                str(value)
                for value in (getattr(position, 'entry_order_ids', []) or [])
                if str(value or '').strip()
            ]
            if len(entry_order_ids) > 1:
                return self._close_managed_entry_group(
                    symbol=position.symbol,
                    exchange=exchange or self.exchange,
                    entry_order_ids=entry_order_ids,
                    exit_price=float(actual_exit_price),
                    reason=reason,
                    fees=float(actual_fees or 0.0),
                    slippage=float(actual_slippage or 0.0),
                    exit_order_id=exit_order_id,
                )

            # 2. 정확한 손익 계산 (단위 일치 + 레버리지 중복 제거)
            # ① 총 손익(화폐단위): 레버리지 곱하지 않음
            side_sign = 1 if position.side.value == "LONG" else -1
            gross_pnl_ccy = (actual_exit_price - position.entry_price) * actual_quantity * side_sign

            # ② 거래금액(엔트리 기준)
            notional = position.entry_price * actual_quantity  # 기준 금액

            # ③ 수수료/슬리피지 '화폐단위'로 정리 후 차감
            #   - 추정만 쓸 때도 화폐단위로 계산(퍼센트 혼합 금지)
            fees_ccy = actual_fees if actual_trade_info else notional * 0.0004   # 왕복 0.04% 가정
            slip_ccy = (
                max(0.0, float(actual_slippage or 0.0))
                if actual_trade_info
                else notional * 0.0002
            )  # 실제값이 없을 때만 0.02% 가정

            net_pnl_ccy = gross_pnl_ccy - fees_ccy - slip_ccy

            # ④ 수익률(%)은 마지막에 환산
            net_pnl_percent = (net_pnl_ccy / notional) * 100

            # ⑤ 최종 PnL (화폐단위)
            net_pnl = net_pnl_ccy

            trade_log = TradeLog(
                id=None,
                symbol=position.symbol,
                entry_price=position.entry_price,
                exit_price=actual_exit_price,
                quantity=actual_quantity,
                leverage=position.leverage,
                pnl=net_pnl,
                pnl_percent=net_pnl_percent,
                entry_time=position.entry_time,
                exit_time=datetime.now(),
                reason=reason,
                side=position.side.value,
                tp_price=position.tp_price,
                sl_price=position.sl_price,
                fees=actual_fees,
                slippage=actual_slippage,
                exchange=self.exchange,
            )

            # 기존 거래 레코드 업데이트 (INSERT 대신 UPDATE).  모든 신규
            # 청산은 gross/net/fee 출처를 같은 계약으로 기록한다.
            success = self.update_trade_log(
                symbol=position.symbol,
                exit_price=actual_exit_price,
                exit_time=datetime.now(),
                pnl_percent=net_pnl_percent,
                pnl_usdt=net_pnl,
                exit_reason=reason,
                position=position,
                additional_fees=actual_fees,
                exchange=exchange,
                entry_order_id=getattr(position, 'entry_order_id', None),
                exit_order_id=exit_order_id,
                fee_asset=(
                    (actual_trade_info or {}).get('fee_asset')
                    or (
                        self._settlement_currency(position.symbol, exchange or self.exchange)
                        if str(exchange or self.exchange or '').strip().lower()
                        in {'upbit', 'bithumb', 'coinone', 'kiwoom', 'shinhan', 'mirae', 'miraeasset', 'koreainvestment', 'kis'}
                        else None
                    )
                ),
                fee_source='exchange_fill' if actual_trade_info else 'estimated',
                gross_pnl=(actual_trade_info or {}).get('gross_pnl', gross_pnl_ccy),
                net_pnl=(actual_trade_info or {}).get('net_pnl'),
                pnl_source=(actual_trade_info or {}).get('pnl_source', 'estimated_close_price'),
                reconciliation_status=(actual_trade_info or {}).get(
                    'reconciliation_status', 'pending_exchange_reconciliation'
                ),
                settlement_currency=self._settlement_currency(position.symbol, exchange or self.exchange),
            )

            if success:
                log_event('trade', f"거래 청산 로그 업데이트 완료: {position.symbol} - 순수익률: {net_pnl_percent:.2f}% (수수료/슬리피지 포함)", exchange=self.exchange, level='INFO')
            else:
                log_event('trade', f"거래 청산 로그 업데이트 실패: {position.symbol}", exchange=self.exchange, level='ERROR')
            return bool(success)

        except Exception as e:
            log_event('trade', f"거래 청산 로그 기록 오류: {e}", exchange=self.exchange, level='ERROR')
            return False

    def _close_managed_entry_group(
        self,
        *,
        symbol: str,
        exchange: str,
        entry_order_ids: List[str],
        exit_price: float,
        reason: str,
        fees: float,
        slippage: float,
        exit_order_id: Optional[str],
        closed_at=None,
        _write_token=None,
    ) -> bool:
        """Close every persisted scale-in row without duplicating aggregate PnL."""
        clean_ids = list(dict.fromkeys(str(value) for value in entry_order_ids if value))
        if not clean_ids:
            return False
        closed_at = closed_at or datetime.now()
        payload=dict(symbol=symbol,exchange=exchange,entry_order_ids=clean_ids,exit_price=exit_price,
            reason=reason,fees=fees,slippage=slippage,exit_order_id=exit_order_id,closed_at=closed_at)
        try:
            placeholders = ",".join("?" for _ in clean_ids)
            with self._write_connection(operation='_close_managed_entry_group') as conn:
                from trading.recorder_write_queue import begin_receipt,finish_receipt
                if begin_receipt(conn,_write_token): return True
                if not _write_token: conn.execute('BEGIN IMMEDIATE')
                rows = conn.execute(
                    f"""
                    SELECT id, entry_price, quantity, UPPER(COALESCE(side, 'LONG'))
                    FROM trade_log
                    WHERE symbol = ?
                      AND LOWER(COALESCE(exchange, '')) = ?
                      AND exit_time IS NULL
                      AND order_id IN ({placeholders})
                    """,
                    (symbol, str(exchange or '').lower(), *clean_ids),
                ).fetchall()
                if len(rows)!=len(clean_ids):
                    return False
                total_notional = sum(
                    max(0.0, float(row[1] or 0.0) * float(row[2] or 0.0))
                    for row in rows
                )
                closed_at = self._to_db_datetime(closed_at)
                for trade_id, entry_price, quantity, side in rows:
                    entry = float(entry_price or 0.0)
                    qty = float(quantity or 0.0)
                    notional = max(0.0, entry * qty)
                    weight = (notional / total_notional) if total_notional > 0 else 0.0
                    row_fees = fees * weight if fees > 0 else notional * 0.0004
                    row_slippage = slippage * weight if slippage > 0 else notional * 0.0002
                    side_sign = 1.0 if str(side).upper() == 'LONG' else -1.0
                    pnl = ((float(exit_price) - entry) * qty * side_sign) - row_fees - row_slippage
                    pnl_percent = (pnl / notional * 100.0) if notional > 0 else 0.0
                    conn.execute(
                        """
                        UPDATE trade_log
                        SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?,
                            reason = ?, fees = ?, slippage = ?, exit_order_id = ?,
                            net_pnl = NULL, pnl_source = 'estimated_close_price',
                            reconciliation_status = 'pending_exchange_reconciliation'
                        WHERE id = ?
                        """,
                        (
                            float(exit_price), closed_at, pnl, pnl_percent, reason,
                            row_fees, row_slippage,
                            str(exit_order_id) if exit_order_id else None,
                            trade_id,
                        ),
                    )
                finish_receipt(conn,_write_token)
                conn.commit()
            log_event(
                'trade',
                f"NoahAI 분할 진입 {len(rows)}건 일괄 청산 원장 반영: {symbol}",
                exchange=exchange,
                level='INFO',
            )
            return bool(rows)
        except Exception as e:
            if _write_token: raise
            from trading.recorder_write_queue import is_busy,enqueue
            if is_busy(e): enqueue(self,'_close_managed_entry_group',payload)
            log_event(
                'trade',
                f"NoahAI 분할 진입 일괄 청산 원장 오류: {e}",
                exchange=exchange,
                level='ERROR',
            )
            return False

    def get_open_managed_trades(self, exchange: str, *, strict: bool = False) -> List[Dict[str, Any]]:
        """Return open positions that a persisted NoahAI entry order owns.

        Account-wide exchange positions and balances are deliberately excluded.
        Legacy rows are accepted only when they have both a NoahAI reason and an
        exchange order id; this provides a safe upgrade path for open positions
        created before ``position_owner`` was introduced.
        """
        venue = str(exchange or "").strip().lower()
        if not venue:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT id, symbol, side, entry_price, quantity, leverage,
                           entry_time, tp_price, sl_price, order_id,
                           COALESCE(position_owner, 'legacy_unknown') AS position_owner,
                           COALESCE(execution_mode, 'live') AS execution_mode,
                           COALESCE(spot_baseline_quantity, 0.0) AS spot_baseline_quantity,
                           reason
                    FROM trade_log
                    WHERE LOWER(COALESCE(exchange, '')) = ?
                      AND exit_time IS NULL
                      AND order_id IS NOT NULL
                      AND TRIM(order_id) <> ''
                      AND (
                            LOWER(COALESCE(position_owner, '')) = 'noahai'
                            OR LOWER(COALESCE(reason, '')) LIKE 'ai %'
                          )
                    ORDER BY entry_time DESC, id DESC
                    """,
                    (venue,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            log_event(
                'trade',
                f"NoahAI 소유 미청산 포지션 조회 오류: {e}",
                exchange=venue,
                level='ERROR',
            )
            if strict:
                raise
            return []

    def get_actual_trade_info(
        self,
        symbol: str,
        entry_time: datetime,
        side: str,
        *,
        exit_order_id: Optional[str] = None,
    ):
        """Return fills for one exact exit order only.

        A same-symbol/time-window scan can absorb a manual trade, a re-entry or
        another partial close.  Older callers without an exit order id now get
        an unresolved result instead of fabricated "actual" execution data.
        """
        try:
            # binance_client가 주입되어 있는지 확인
            if not hasattr(self, 'binance_client') or not self.binance_client:
                return None

            if not exit_order_id:
                return None
            recent_trades = self.binance_client.get_recent_trades(symbol=symbol, limit=200)
            if not recent_trades:
                return None

            exit_trades = []
            total_fees = 0.0
            total_quantity = 0.0
            weighted_exit_price = 0.0
            gross_pnl = 0.0
            fee_assets = set()

            for trade in recent_trades:
                if str(trade.get('order_id') or trade.get('order') or '') == str(exit_order_id):
                    # 청산 거래 (반대 방향)
                    try:
                        t_side = str(trade.get('side', '')).upper()
                        need_side = {'LONG':'SELL','BUY':'SELL','SHORT':'BUY','SELL':'BUY'}.get(side.upper())
                        if not need_side or t_side != need_side:
                            return None
                    except Exception:
                        pass
                    quantity = float(trade['quantity'])
                    price = float(trade['price'])
                    provider_gross = provider_fill_gross_pnl('binance', trade)
                    if provider_gross is None or trade.get('commission') is None:
                        return None
                    commission = float(trade['commission'])
                    if not all(math.isfinite(v) for v in (quantity,price,commission)) or quantity <= 0 or price <= 0:
                        return None
                    if commission != 0 and not (trade.get('commission_asset') or trade.get('commissionAsset')):
                        return None

                    exit_trades.append(trade)
                    total_fees += commission
                    total_quantity += quantity
                    weighted_exit_price += price * quantity
                    gross_pnl += provider_gross
                    if trade.get('commission_asset') or trade.get('commissionAsset'):
                        fee_assets.add(str(trade.get('commission_asset') or trade.get('commissionAsset')).upper())

            if not exit_trades or len(fee_assets) > 1:
                return None

            # 가중 평균 청산가 계산
            avg_exit_price = weighted_exit_price / total_quantity if total_quantity > 0 else 0

            return {
                'exit_price': avg_exit_price,
                'fees': total_fees,
                'slippage': 0.0,  # 바이낸스 API에서 직접 제공하지 않음
                'quantity': total_quantity,
                'gross_pnl': gross_pnl,
                'fee_asset': next(iter(fee_assets)) if len(fee_assets) == 1 else ('MIXED' if fee_assets else None),
                'pnl_source': 'exchange_order_fills',
                'reconciliation_status': 'exchange_confirmed',
            }

        except Exception as e:
            log_event('trade', f"실제 거래 정보 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return None

    def estimate_fees(self, quantity: float, price: float) -> float:
        """수수료 추정"""
        try:
            # 바이낸스 수수료율 (일반적으로 0.04% 왕복)
            fee_rate = 0.0004  # 0.04%
            trade_value = quantity * price
            estimated_fees = trade_value * fee_rate
            return estimated_fees
        except Exception:
            return 0.0

    def estimate_slippage(self, symbol: str) -> float:
        """슬리피지 추정"""
        try:
            # 심볼별 슬리피지 추정 (일반적으로 0.01-0.05%)
            slippage_rate = 0.0002  # 0.02%
            return slippage_rate
        except Exception:
            return 0.0

    def log_analysis_result(self, analysis_result):
        """분석 결과 로그"""
        try:
            analysis_log = AnalysisLog(
                id=None,
                symbol=analysis_result.symbol,
                signal=analysis_result.signal.value,
                confidence=analysis_result.confidence,
                rsi=analysis_result.indicators.rsi,
                macd=analysis_result.indicators.macd,
                sma_20=analysis_result.indicators.sma_20,
                sma_50=analysis_result.indicators.sma_50,
                bb_upper=analysis_result.indicators.bb_upper,
                bb_lower=analysis_result.indicators.bb_lower,
                volume_ratio=analysis_result.indicators.volume_ratio,
                volatility=analysis_result.volatility,
                trend=analysis_result.trend.value,
                reasoning=analysis_result.reasoning,
                timestamp=analysis_result.timestamp
            )

            self.insert_analysis_log(analysis_log)
            log_event('trade', f"분석 결과 로그 기록: {analysis_result.symbol}", exchange=self.exchange, level='DEBUG')

        except Exception as e:
            log_event('trade', f"분석 결과 로그 기록 오류: {e}", exchange=self.exchange, level='ERROR')

    def log_optimization_result(self, optimization_result):
        """최적화 결과 로그"""
        try:
            optimization_log = OptimizationLog(
                id=None,
                symbol=optimization_result.symbol,
                optimization_type=optimization_result.optimization_type.value,
                original_params=optimization_result.original_params,
                optimized_params=optimization_result.optimized_params,
                improvement_score=optimization_result.improvement_score,
                confidence=optimization_result.confidence,
                reasoning=optimization_result.reasoning,
                timestamp=optimization_result.timestamp
            )

            self.insert_optimization_log(optimization_log)
            log_event('trade', f"최적화 결과 로그 기록: {optimization_result.symbol}", exchange=self.exchange, level='INFO')

        except Exception as e:
            log_event('trade', f"최적화 결과 로그 기록 오류: {e}", exchange=self.exchange, level='ERROR')

    def log_risk_event(self, symbol: str, risk_type: str, risk_level: str, description: str, impact_score: float, *, _write_token=None):
        """리스크 이벤트 로그"""
        try:
            with self._write_connection(operation='log_risk_event') as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn,_write_token): return True
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO risk_log (symbol, risk_type, risk_level, description, impact_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    risk_type,
                    risk_level,
                    description,
                    impact_score,
                    self._to_db_datetime(datetime.now())
                ))
                finish_receipt(conn,_write_token)
                conn.commit()

            log_event('trade', f"리스크 이벤트 로그 기록: {symbol} - {risk_type} ({risk_level})", exchange=self.exchange, level='WARNING')

        except Exception as e:
            log_event('trade', f"리스크 이벤트 로그 기록 오류: {e}", exchange=self.exchange, level='ERROR')
            if _write_token: raise
            from trading.recorder_write_queue import enqueue,is_busy
            if is_busy(e): enqueue(self,'log_risk_event',dict(symbol=symbol,risk_type=risk_type,risk_level=risk_level,description=description,impact_score=impact_score))

    def insert_trade_log(self, trade_log: TradeLog, *, _write_token=None) -> Optional[int]:
        """거래 로그 삽입"""
        event_exchange = str(
            getattr(trade_log, 'exchange', None) or self.exchange or ''
        ).strip().lower()
        try:
            logger = self._logger
            with self._write_connection(operation='insert_trade_log') as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn, _write_token):
                    return True
                if _write_token and trade_log.order_id:
                    existing = conn.execute('''SELECT id,quantity,entry_time FROM trade_log
                        WHERE exchange=? AND symbol=? AND order_id=? AND execution_mode=?''',
                        (trade_log.exchange, trade_log.symbol, trade_log.order_id, trade_log.execution_mode)).fetchall()
                    if existing:
                        if len(existing) != 1 or existing[0][1] != trade_log.quantity or existing[0][2] != self._to_db_datetime(trade_log.entry_time):
                            return False
                        finish_receipt(conn, _write_token)
                        return existing[0][0]
                cursor = conn.cursor()

                # 🔥 디버깅: 삽입할 데이터 출력
                log_event('trade', f"[DEBUG] insert_trade_log 호출:", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - symbol: {trade_log.symbol}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - entry_price: {trade_log.entry_price}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - exit_price: {trade_log.exit_price}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - quantity: {trade_log.quantity}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - leverage: {trade_log.leverage}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - side: {trade_log.side}", exchange=event_exchange, level='INFO')
                log_event('trade', f"  - exchange: {getattr(trade_log, 'exchange', None)}", exchange=event_exchange, level='INFO')

                cursor.execute("""
                    INSERT INTO trade_log (
                        symbol, entry_price, exit_price, quantity, leverage,
                        pnl, pnl_percent, entry_time, exit_time, reason,
                        side, tp_price, sl_price, fees, slippage, exchange,
                        order_id, exit_order_id, model_version, strategy_variant,
                        fee_asset, fee_source, position_owner, execution_mode,
                        spot_baseline_quantity, gross_pnl, net_pnl, entry_fee,
                        exit_fee, entry_fee_asset, exit_fee_asset,
                        settlement_currency, pnl_source,
                        reconciliation_status, strategy_key, strategy_version_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_log.symbol, trade_log.entry_price, trade_log.exit_price,
                    trade_log.quantity, trade_log.leverage, trade_log.pnl,
                    trade_log.pnl_percent, self._to_db_datetime(trade_log.entry_time), self._to_db_datetime(trade_log.exit_time),
                    trade_log.reason, trade_log.side, trade_log.tp_price,
                    trade_log.sl_price, trade_log.fees, trade_log.slippage,
                    getattr(trade_log, 'exchange', None),
                    getattr(trade_log, 'order_id', None),
                    getattr(trade_log, 'exit_order_id', None),
                    getattr(trade_log, 'model_version', None),
                    getattr(trade_log, 'strategy_variant', None),
                    getattr(trade_log, 'fee_asset', None),
                    getattr(trade_log, 'fee_source', None),
                    str(getattr(trade_log, 'position_owner', 'legacy_unknown') or 'legacy_unknown'),
                    str(getattr(trade_log, 'execution_mode', 'live') or 'live'),
                    float(getattr(trade_log, 'spot_baseline_quantity', 0.0) or 0.0),
                    getattr(trade_log, 'gross_pnl', None),
                    getattr(trade_log, 'net_pnl', None),
                    getattr(trade_log, 'entry_fee', None),
                    getattr(trade_log, 'exit_fee', None),
                    getattr(trade_log, 'entry_fee_asset', None),
                    getattr(trade_log, 'exit_fee_asset', None),
                    getattr(trade_log, 'settlement_currency', None),
                    str(getattr(trade_log, 'pnl_source', 'legacy_unverified') or 'legacy_unverified'),
                    str(getattr(trade_log, 'reconciliation_status', 'legacy_unverified') or 'legacy_unverified'),
                    getattr(trade_log, 'strategy_key', None),
                    getattr(trade_log, 'strategy_version_id', None),
                ))
                finish_receipt(conn, _write_token)
                conn.commit()

                inserted_id = cursor.lastrowid
                log_event('position', f"✅ 거래 로그 삽입 완료: ID={inserted_id}", exchange=event_exchange, level='INFO',
                          execution_mode=str(getattr(trade_log,'execution_mode','unknown')),
                          details={'symbol':trade_log.symbol, 'ledger_id':inserted_id, 'order_id':trade_log.order_id,
                                   'actual_order': None if trade_log.execution_mode=='live' else False,
                                   'event_kind':'position_recorded'})

                # 🔥 삽입 후 확인
                cursor.execute("SELECT * FROM trade_log WHERE id = ?", (inserted_id,))
                saved_row = cursor.fetchone()
                log_event('trade', f"[DEBUG] 저장된 행: {saved_row}", exchange=event_exchange, level='DEBUG')

                return inserted_id

        except Exception as e:
            # 스키마 불일치의 경우 즉시 보정 후 1회 재시도
            if _write_token:
                raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(e):
                try:
                    enqueue(self, 'insert_trade_log', {'trade_log':asdict(trade_log)})
                except Exception as queue_error:
                    log_event('trade', f'진입 기록 재처리 보존 실패: {type(queue_error).__name__}', exchange=event_exchange, level='ERROR')
            log_event('trade', f"거래 로그 삽입 오류: {e}", exchange=event_exchange, level='ERROR')
            msg = str(e)
            try:
                if 'no column named exchange' in msg or 'has no column named exchange' in msg:
                    with self._write_connection(operation='insert_trade_log') as conn:
                        # 커서 생성 및 사용을 각 try 블록 내에서 안전하게 처리
                        try:
                            c2 = conn.cursor()
                            c2.execute("ALTER TABLE trade_log ADD COLUMN exchange TEXT")
                            conn.commit()
                        except Exception:
                            pass
                        # 재시도
                        try:
                            c2 = conn.cursor()
                            c2.execute("""
                                INSERT INTO trade_log (
                                    symbol, entry_price, exit_price, quantity, leverage,
                                    pnl, pnl_percent, entry_time, exit_time, reason,
                                    side, tp_price, sl_price, fees, slippage, exchange
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                trade_log.symbol, trade_log.entry_price, trade_log.exit_price,
                                trade_log.quantity, trade_log.leverage, trade_log.pnl,
                                trade_log.pnl_percent, self._to_db_datetime(trade_log.entry_time), self._to_db_datetime(trade_log.exit_time),
                                trade_log.reason, trade_log.side, trade_log.tp_price,
                                trade_log.sl_price, trade_log.fees, trade_log.slippage,
                                getattr(trade_log, 'exchange', None)
                            ))
                            conn.commit()
                            return c2.lastrowid
                        except Exception as e2:
                            log_event('trade', f"거래 로그 재삽입 실패(보정 후): {e2}", exchange=event_exchange, level='ERROR')
                            return None
            except Exception:
                pass
            log_event('trade', f"거래 로그 삽입 오류: {e}", exchange=event_exchange, level='ERROR')
            return None

    def save_ai_trade_analysis(self, trade_log_id: Optional[int], symbol: str, analysis: Dict, analysis_type: str):
        """AI 거래 분석 결과 저장 (통합 버전) - ai_trade_analysis 테이블 사용"""
        try:
            with self._write_connection(operation='save_ai_trade_analysis') as conn:
                cursor = conn.cursor()

                # ai_trade_analysis 테이블이 없으면 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_trade_analysis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_log_id INTEGER,
                        symbol TEXT NOT NULL,
                        analysis_type TEXT NOT NULL,
                        analysis_json TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (trade_log_id) REFERENCES trade_log (id)
                    )
                """)

                # trade_log_id가 None이면 최근 trade_log 조회
                if trade_log_id is None:
                    cursor.execute(
                        "SELECT id FROM trade_log WHERE symbol = ? ORDER BY exit_time DESC LIMIT 1",
                        (symbol,)
                    )
                    result = cursor.fetchone()
                    trade_log_id = result[0] if result else None

                if trade_log_id:
                    cursor.execute(
                        """
                        INSERT INTO ai_trade_analysis (trade_log_id, symbol, analysis_type, analysis_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (trade_log_id, symbol, analysis_type, json.dumps(analysis, ensure_ascii=False))
                    )
                    conn.commit()
                    log_event('trade', f"AI 분석 저장 완료: {symbol} - {analysis_type} (trade_log_id: {trade_log_id})", exchange=self.exchange, level='INFO')
                else:
                    log_event('trade', f"trade_log_id를 찾을 수 없어 AI 분석 저장 실패: {symbol}", exchange=self.exchange, level='WARNING')

        except Exception as e:
            log_event('trade', f"AI 분석 저장 오류: {e}", exchange=self.exchange, level='ERROR')

    def get_recent_loss_patterns(self, symbol: str, limit: int = 5) -> List[Dict]:
        """최근 손실 패턴 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 최근 손실 거래 조회
            cursor.execute("""
                SELECT symbol, entry_price, exit_price, pnl, pnl_percent,
                       side, reason, entry_time, exit_time
                FROM trade_log
                WHERE symbol = ? AND pnl < 0
                ORDER BY exit_time DESC
                LIMIT ?
            """, (symbol, limit))

            patterns = []
            for row in cursor.fetchall():
                patterns.append({
                    'symbol': row[0],
                    'entry_price': row[1],
                    'exit_price': row[2],
                    'pnl': row[3],
                    'pnl_percent': row[4],
                    'side': row[5],
                    'reason': row[6],
                    'entry_time': row[7],
                    'exit_time': row[8],
                    'result': 'LOSS'
                })

            conn.close()
            return patterns

        except Exception as e:
            log_event('trade', f"손실 패턴 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return []

    def get_recent_profit_patterns(self, symbol: str, limit: int = 5) -> List[Dict]:
        """최근 수익 패턴 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 최근 수익 거래 조회
            cursor.execute("""
                SELECT symbol, entry_price, exit_price, pnl, pnl_percent,
                       side, reason, entry_time, exit_time
                FROM trade_log
                WHERE symbol = ? AND pnl > 0
                ORDER BY exit_time DESC
                LIMIT ?
            """, (symbol, limit))

            patterns = []
            for row in cursor.fetchall():
                patterns.append({
                    'symbol': row[0],
                    'entry_price': row[1],
                    'exit_price': row[2],
                    'pnl': row[3],
                    'pnl_percent': row[4],
                    'side': row[5],
                    'reason': row[6],
                    'entry_time': row[7],
                    'exit_time': row[8],
                    'result': 'PROFIT'
                })

            conn.close()
            return patterns

        except Exception as e:
            log_event('trade', f"수익 패턴 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return []

    def save_trade_log(self, trade_data: Dict):
        """거래 로그 저장 (데이터베이스 잠금 방지)"""
        max_retries = 3
        retry_delay = 0.1  # 100ms

        for attempt in range(max_retries):
            try:
                with self._write_connection(operation='save_trade_log', timeout=20.0) as conn:
                    # WAL 모드 활성화로 동시 접근 개선
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=10000")
                    conn.execute("PRAGMA temp_store=MEMORY")

                    cursor = conn.cursor()

                    # 거래 로그 테이블이 없으면 생성 (init_database와 동일한 테이블명 사용)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS trade_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT NOT NULL,
                            side TEXT NOT NULL,
                            entry_price REAL NOT NULL,
                            exit_price REAL,
                            quantity REAL NOT NULL,
                            leverage INTEGER NOT NULL,
                            pnl REAL,
                            pnl_percent REAL,
                            reason TEXT,
                            entry_time DATETIME NOT NULL,
                            exit_time DATETIME,
                            tp_price REAL,
                            sl_price REAL,
                            fees REAL DEFAULT 0,
                            slippage REAL DEFAULT 0,
                            exchange TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # 거래 로그 저장 (PNL NULL 방지)
                    pnl = trade_data.get('pnl', 0.0)
                    pnl_percent = trade_data.get('pnl_percent', 0.0)

                    # PNL이 None인 경우 0.0으로 설정
                    if pnl is None:
                        pnl = 0.0
                    if pnl_percent is None:
                        pnl_percent = 0.0

                    cursor.execute("""
                        INSERT INTO trade_log (
                            symbol, side, entry_price, exit_price, quantity, leverage,
                            pnl, pnl_percent, reason, entry_time, exit_time, tp_price, sl_price, exchange
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade_data['symbol'],
                        trade_data['side'],
                        trade_data['entry_price'],
                        trade_data.get('exit_price'),
                        trade_data['quantity'],
                        trade_data['leverage'],
                        pnl,
                        pnl_percent,
                        trade_data.get('reason', ''),
                        trade_data['entry_time'],
                        trade_data.get('exit_time'),
                        trade_data.get('tp_price'),
                        trade_data.get('sl_price'),
                        trade_data.get('exchange')
                    ))

                    conn.commit()
                    log_event('trade', f"거래 로그 저장 완료: {trade_data['symbol']}", exchange=self.exchange, level='INFO')
                    return  # 성공 시 함수 종료

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    log_event('trade', f"데이터베이스 잠금 감지, 재시도 {attempt + 1}/{max_retries}...", exchange=self.exchange, level='WARNING')
                    time.sleep(retry_delay * (2 ** attempt))  # 지수 백오프
                    continue
                else:
                    log_event('trade', f"데이터베이스 잠금 오류 (최대 재시도 초과): {e}", exchange=self.exchange, level='ERROR')
                    break
            except Exception as e:
                log_event('trade', f"거래 로그 저장 오류: {e}", exchange=self.exchange, level='ERROR')
                break
            log_event('trade', f"거래 로그 저장 실패 (최대 재시도 초과): {trade_data['symbol']}", exchange=self.exchange, level='ERROR')



    def insert_analysis_log(self, analysis_log: AnalysisLog):
        """분석 로그 삽입"""
        try:
            with self._write_connection(operation='insert_analysis_log') as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO analysis_log (
                        symbol, signal, confidence, rsi, macd, sma_20, sma_50,
                        bb_upper, bb_lower, volume_ratio, volatility, trend, reasoning, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analysis_log.symbol, analysis_log.signal, analysis_log.confidence,
                    analysis_log.rsi, analysis_log.macd, analysis_log.sma_20, analysis_log.sma_50,
                    analysis_log.bb_upper, analysis_log.bb_lower, analysis_log.volume_ratio,
                    analysis_log.volatility, analysis_log.trend, analysis_log.reasoning,
                    self._to_db_datetime(analysis_log.timestamp)
                ))
                conn.commit()

        except Exception as e:
            log_event('trade', f"분석 로그 삽입 오류: {e}", exchange=self.exchange, level='ERROR')

    def insert_optimization_log(self, optimization_log: OptimizationLog):
        """최적화 로그 삽입"""
        try:
            with self._write_connection(operation='insert_optimization_log') as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ai_optimization (
                        symbol, optimization_type, original_params, optimized_params,
                        improvement_score, confidence, reasoning, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    optimization_log.symbol, optimization_log.optimization_type,
                    json.dumps(optimization_log.original_params),
                    json.dumps(optimization_log.optimized_params),
                    optimization_log.improvement_score, optimization_log.confidence,
                    optimization_log.reasoning, self._to_db_datetime(optimization_log.timestamp)
                ))
                conn.commit()

        except Exception as e:
            log_event('trade', f"최적화 로그 삽입 오류: {e}", exchange=self.exchange, level='ERROR')

    def execute_query(self, query: str, params: tuple = (), *, strict: bool = False) -> List[tuple]:
        """쿼리 실행 (데이터베이스 잠금 방지)"""
        max_retries = 3
        retry_delay = 0.1  # 100ms

        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=20.0) as conn:
                    # WAL 모드 활성화로 동시 접근 개선
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=10000")
                    conn.execute("PRAGMA temp_store=MEMORY")

                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                    conn.commit()
                    return result

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    log_event('trade', f"데이터베이스 잠금 감지, 재시도 {attempt + 1}/{max_retries}...", exchange=self.exchange, level='WARNING')
                    time.sleep(retry_delay * (2 ** attempt))  # 지수 백오프
                    continue
                else:
                    log_event('trade', f"데이터베이스 잠금 오류 (최대 재시도 초과): {e}", exchange=self.exchange, level='ERROR')
                    if strict:
                        raise
                    return []
            except Exception as e:
                log_event('trade', f"쿼리 실행 오류: {e}", exchange=self.exchange, level='ERROR')
                if strict:
                    raise
                return []

        return []

    @staticmethod
    def _execution_number(value: Any) -> float:
        try:
            number = float(value or 0.0)
            return number if math.isfinite(number) else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _execution_time_text(value: Any) -> str:
        if value in (None, ''):
            return ''
        try:
            numeric = float(value)
            if numeric > 1e12:
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            return parsed.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(value)[:32]

    def save_exchange_execution_history(
        self,
        exchange: str,
        trades: List[Dict[str, Any]],
        *,
        source: str = 'exchange_api',
        reconcile: bool = True,
        _write_token: Optional[str] = None,
    ) -> Dict[str, int]:
        """거래소 실제 체결 원장을 중복 없이 저장한다.

        이 데이터는 ``trade_log``의 청산 성과와 별도다. 거래소 API가 PnL을
        제공하지 않는 현물 매수/매도 체결을 임의로 수익/손실로 만들지 않는다.
        """
        venue = str(exchange or '').strip().lower()
        result = {'received': len(trades or []), 'inserted': 0, 'skipped': 0}
        if not venue or not trades:
            return result

        try:
            with self._write_connection(operation='save_exchange_execution_history', timeout=20.0) as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                already_applied = begin_receipt(conn, _write_token)
                cursor = conn.cursor()
                for trade in ([] if already_applied else trades):
                    if not isinstance(trade, dict):
                        result['skipped'] += 1
                        continue
                    symbol = str(trade.get('symbol') or '').strip().upper()
                    side = str(trade.get('side') or '').strip().lower()
                    trade_id = str(trade.get('id') or trade.get('trade_id') or '').strip()
                    order_id = str(trade.get('order') or trade.get('order_id') or '').strip()
                    # create_order 응답은 id가 체결 ID가 아니라 주문 ID다. 두 값이
                    # 같으면 개별 체결 ID로 취급하지 않아 주문별 상세 복구 시 기존
                    # 불완전 행을 갱신할 수 있게 한다.
                    distinct_trade_id = trade_id if trade_id and trade_id != order_id else ''
                    executed_at = self._execution_time_text(
                        trade.get('timestamp')
                        or trade.get('datetime')
                        or trade.get('time')
                        or trade.get('filled_at')
                    )
                    quantity = self._execution_number(
                        trade.get('amount') or trade.get('filled') or trade.get('quantity')
                    )
                    price = self._execution_number(
                        trade.get('average') or trade.get('price') or trade.get('filled_price')
                    )
                    cost = self._execution_number(
                        trade.get('cost') or trade.get('quote_qty') or trade.get('quoteQty')
                    )
                    if cost <= 0 and price > 0 and quantity > 0:
                        cost = price * quantity

                    fee_value = 0.0
                    provider_gross = provider_fill_gross_pnl(venue, trade)
                    realized_present = provider_gross is not None
                    realized_pnl = provider_gross if realized_present else 0.0
                    fee_currency = ''
                    fee_obj = trade.get('fee')
                    fee_present = (
                        fee_obj.get('cost') not in (None, '') if isinstance(fee_obj, dict)
                        else any(trade.get(key) not in (None, '') for key in ('fee_cost', 'feeCost', 'commission', 'fee'))
                    )
                    if isinstance(fee_obj, dict):
                        fee_value = self._execution_number(fee_obj.get('cost'))
                        fee_currency = str(fee_obj.get('currency') or '').strip().upper()
                    else:
                        fee_value = self._execution_number(
                            trade.get('fee_cost') or trade.get('feeCost')
                            or trade.get('commission') or fee_obj
                        )
                        fee_currency = str(
                            trade.get('commission_asset') or trade.get('commissionAsset') or ''
                        ).strip().upper()

                    if not symbol or quantity <= 0 or (not trade_id and not order_id and not executed_at):
                        result['skipped'] += 1
                        continue

                    identity = '|'.join([
                        venue, distinct_trade_id, order_id, symbol, side, executed_at,
                        f'{quantity:.12f}', f'{price:.12f}',
                    ])
                    execution_key = hashlib.sha256(identity.encode('utf-8')).hexdigest()
                    # 주문 접수 응답을 실제 체결로 오인하지 않는다. API 동기화의
                    # 과거 데이터는 filled/closed 계약을 이미 통과하며, 새 주문은
                    # UnifiedTrader가 _execution_confirmed를 명시한다.
                    confirmed_marker = trade.get('_execution_confirmed')
                    status_text = str(trade.get('status') or '').strip().lower()
                    if confirmed_marker is False or status_text in {'new', 'pending', 'open'}:
                        result['skipped'] += 1
                        continue

                    # 같은 주문의 불완전한 접수 기록이 이미 있으면 체결 상세로 보강한다.
                    existing_id = None
                    existing_detail = False
                    if distinct_trade_id:
                        found = cursor.execute(
                            "SELECT id FROM exchange_execution_log WHERE exchange=? "
                            "AND symbol=? AND trade_id=? AND COALESCE(order_id,'')=? ORDER BY id",
                            (venue, symbol, distinct_trade_id, order_id),
                        ).fetchall()
                        if len(found) > 1:
                            # Legacy duplicate repair requires an audited migration.
                            result['skipped'] += 1
                            continue
                        if found:
                            existing_id = int(found[0][0])
                            existing_detail = True
                    if order_id and not distinct_trade_id:
                        cursor.execute(
                            """
                            SELECT id FROM exchange_execution_log
                            WHERE exchange = ? AND order_id = ? AND symbol = ?
                              AND COALESCE(trade_id, '') = ''
                            ORDER BY id DESC LIMIT 1
                            """,
                            (venue, order_id, symbol),
                        )
                        found = cursor.fetchone()
                        existing_id = int(found[0]) if found else None
                        if existing_id is None:
                            detailed = cursor.execute(
                                """
                                SELECT 1 FROM exchange_execution_log
                                WHERE exchange = ? AND order_id = ? AND symbol = ?
                                  AND COALESCE(trade_id, '') <> ''
                                LIMIT 1
                                """,
                                (venue, order_id, symbol),
                            ).fetchone()
                            if detailed:
                                result['skipped'] += 1
                                continue
                    if existing_id is not None:
                        cursor.execute(
                            """
                            UPDATE exchange_execution_log
                            SET side = ?, price = ?, quantity = ?, cost = ?,
                                fee = CASE WHEN ? THEN ? ELSE fee END,
                                realized_pnl = CASE WHEN ? THEN ? ELSE realized_pnl END,
                                realized_pnl_present = MAX(COALESCE(realized_pnl_present,0), ?),
                                fee_currency = COALESCE(NULLIF(?, ''), fee_currency), executed_at = COALESCE(?, executed_at),
                                raw_status = ?, confirmation_status = 'confirmed', source = ?
                            WHERE id = ?
                            """,
                            (
                                side, price, quantity, cost,
                                int(fee_present),
                                fee_value, int(realized_present), realized_pnl,
                                1 if realized_present else 0,
                                fee_currency or None, executed_at or None,
                                str(trade.get('status') or '').strip() or None,
                                str(source or 'exchange_api'), existing_id,
                            ),
                        )
                        result['skipped' if existing_detail else 'inserted'] += 1
                        continue

                    # A previously stored order-level receipt must not remain
                    # beside the newly downloaded per-fill rows. Otherwise one
                    # fill is counted twice and fee/notional totals drift.
                    if order_id and distinct_trade_id:
                        cursor.execute(
                            """
                            DELETE FROM exchange_execution_log
                            WHERE exchange = ? AND order_id = ? AND symbol = ?
                              AND COALESCE(trade_id, '') = ''
                            """,
                            (venue, order_id, symbol),
                        )

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO exchange_execution_log (
                            execution_key, exchange, trade_id, order_id, symbol, side,
                            price, quantity, cost, fee, realized_pnl, realized_pnl_present,
                            fee_currency, executed_at,
                            raw_status, confirmation_status, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            execution_key, venue, distinct_trade_id or None, order_id or None,
                            symbol, side, price, quantity, cost, fee_value, realized_pnl,
                            1 if realized_present else 0,
                            fee_currency or None, executed_at or None,
                            str(trade.get('status') or '').strip() or None,
                            'confirmed',
                            str(source or 'exchange_api'),
                        ),
                    )
                    if cursor.rowcount > 0:
                        result['inserted'] += 1
                    else:
                        result['skipped'] += 1
                if not already_applied:
                    finish_receipt(conn, _write_token)
                conn.commit()
            # TP/SL 보험 주문이나 거래소 화면에서 체결된 청산은 포지션 소멸을
            # 먼저 감지해 trade_log를 닫을 수 있다. 이때 응답 주문 ID가 없더라도
            # 시간·방향·수량 후보는 소유권 증거가 아니므로 미확정으로 남긴다.
            # 실제 주문 ID가 기록된 행만 기존 exact-order 대조를 수행한다.
            if reconcile:
                symbols = sorted({str(t.get('symbol') or '').upper() for t in trades if isinstance(t, dict)} - {''})
                order_ids = sorted({str(t.get('order') or t.get('order_id') or '') for t in trades if isinstance(t, dict)} - {''})
                # Read candidate IDs without holding the process-wide writer.
                # Only affected symbols/orders need reevaluation after a fill.
                with sqlite3.connect(self.db_path, timeout=20.0) as reader:
                    missing_ids, exact_ids = [], []
                    for symbol in symbols:
                        missing_ids.extend(r[0] for r in reader.execute(
                            "SELECT id FROM trade_log WHERE LOWER(exchange)=? AND UPPER(symbol)=? "
                            "AND exit_time IS NOT NULL AND COALESCE(exit_order_id,'')=''", (venue, symbol)))
                    for order_id in order_ids:
                        exact_ids.extend(r[0] for r in reader.execute(
                            "SELECT id FROM trade_log WHERE LOWER(exchange)=? AND exit_order_id=? AND exit_time IS NOT NULL",
                            (venue, order_id)))
                for offset in range(0, len(missing_ids), 25):
                    self.link_unresolved_trade_closes_with_executions(venue, trade_ids=missing_ids[offset:offset+25])
                for offset in range(0, len(exact_ids), 25):
                    self.reconcile_trade_log_with_executions(venue, trade_ids=exact_ids[offset:offset+25])
        except Exception as exc:
            if _write_token:
                raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(exc):
                try:
                    enqueue(self, 'save_exchange_execution_history', dict(exchange=exchange,trades=trades,source=source,reconcile=reconcile))
                except Exception as deferred_error:
                    log_event('trade', f'체결 근거 재처리 보존 실패: {type(deferred_error).__name__}', exchange=venue, level='ERROR')
            log_event(
                'trade',
                f"거래소 체결 원장 저장 오류({venue}): {exc}",
                exchange=venue,
                level='ERROR',
            )
        return result

    @staticmethod
    def _ledger_time_epoch(value: Any) -> Optional[float]:
        """Return a comparable epoch for persisted ledger timestamps."""
        if value in (None, ''):
            return None
        try:
            numeric = float(value)
            if numeric > 1e12:
                numeric /= 1000.0
            return numeric
        except (TypeError, ValueError):
            pass
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    def link_unresolved_trade_closes_with_executions(
        self,
        exchange: str,
        *,
        detection_grace_seconds: float = 120.0,
        trade_ids=None,
    ) -> int:
        """Flag a plausible missing-order candidate, never certify ownership.

        External TP/SL execution can make a position disappear before NoahAI has
        the exchange's final order id.  Symbol-only matching is unsafe, so a
        candidate must also have the expected close side, complete provider PnL,
        matching quantity, and an execution time near the observed close.
        Even a unique candidate may be a manual/other-position fill. Without
        an authoritative order link it must remain unresolved. The historical
        method name/return contract is retained; no order IDs are auto-linked.
        """
        venue = str(exchange or '').strip().lower()
        if not venue:
            return 0
        if trade_ids is None:
            with sqlite3.connect(self.db_path, timeout=20.0) as reader:
                ids = [r[0] for r in reader.execute("SELECT id FROM trade_log WHERE LOWER(exchange)=? AND exit_time IS NOT NULL AND COALESCE(exit_order_id,'')=''", (venue,))]
            return sum(self.link_unresolved_trade_closes_with_executions(venue, detection_grace_seconds=detection_grace_seconds, trade_ids=ids[i:i+25]) for i in range(0, len(ids), 25))
        selected_ids = list(dict.fromkeys(int(i) for i in trade_ids))
        if not selected_ids:
            return 0
        if len(selected_ids) > 100:
            raise ValueError('reconciliation_batch_too_large')
        linked = 0
        try:
            with self._write_connection(operation='link_unresolved_trade_closes_with_executions', timeout=20.0) as conn:
                conn.row_factory = sqlite3.Row
                trades = conn.execute(
                    """
                    SELECT id, symbol, side, quantity, entry_time, exit_time
                    FROM trade_log
                    WHERE LOWER(COALESCE(exchange, '')) = ?
                      AND exit_time IS NOT NULL
                      AND LOWER(COALESCE(execution_mode, '')) IN ('live', 'live_api', 'optimized', 'manual')
                      AND COALESCE(exit_order_id, '') = ''
                      AND LOWER(COALESCE(reconciliation_status, '')) NOT LIKE 'exchange_confirmed%'
                      AND COALESCE(reconciliation_status, '') <> 'broker_order_linked'
                      AND COALESCE(reconciliation_status, '') <> 'exact_fill_price_no_provider_pnl'
                      AND (
                        LOWER(COALESCE(position_owner, '')) = 'noahai'
                        OR LOWER(COALESCE(reason, '')) LIKE 'ai %'
                        OR LOWER(COALESCE(reason, '')) LIKE 'stock_auto_%'
                      )
                    """ + ' AND id IN (' + ','.join('?' for _ in selected_ids) + ') ORDER BY exit_time, id',
                    (venue, *selected_ids),
                ).fetchall()
                used_order_ids = {
                    str(row[0])
                    for row in conn.execute(
                        """
                        SELECT DISTINCT exit_order_id FROM trade_log
                        WHERE LOWER(COALESCE(exchange, '')) = ?
                          AND COALESCE(exit_order_id, '') <> ''
                        """,
                        (venue,),
                    ).fetchall()
                }
                for trade in trades:
                    entry_epoch = self._ledger_time_epoch(trade['entry_time'])
                    exit_epoch = self._ledger_time_epoch(trade['exit_time'])
                    expected_qty = max(0.0, float(trade['quantity'] or 0.0))
                    side = str(trade['side'] or '').strip().upper()
                    expected_close_side = (
                        'sell' if side in {'LONG', 'BUY'}
                        else 'buy' if side in {'SHORT', 'SELL'}
                        else ''
                    )
                    if entry_epoch is None or exit_epoch is None or expected_qty <= 0 or not expected_close_side:
                        continue

                    fills = conn.execute(
                        """
                        SELECT order_id, side, quantity, realized_pnl_present,
                               executed_at
                        FROM exchange_execution_log
                        WHERE exchange = ? AND UPPER(symbol) = UPPER(?)
                          AND COALESCE(order_id, '') <> ''
                          AND confirmation_status = 'confirmed'
                        ORDER BY id
                        """,
                        (venue, str(trade['symbol'])),
                    ).fetchall()
                    by_order: Dict[str, List[sqlite3.Row]] = {}
                    for fill in fills:
                        order_id = str(fill['order_id'] or '')
                        if order_id and order_id not in used_order_ids:
                            by_order.setdefault(order_id, []).append(fill)

                    candidates: List[str] = []
                    tolerance = max(1e-8, expected_qty * 0.001)
                    for order_id, order_fills in by_order.items():
                        if any(str(fill['side'] or '').strip().lower() != expected_close_side for fill in order_fills):
                            continue
                        if any(int(fill['realized_pnl_present'] or 0) != 1 for fill in order_fills):
                            continue
                        fill_epochs = [self._ledger_time_epoch(fill['executed_at']) for fill in order_fills]
                        if any(value is None for value in fill_epochs):
                            continue
                        grace = max(0.0, detection_grace_seconds)
                        earliest_match = max(entry_epoch - 5.0, exit_epoch - grace)
                        if any(
                            value < earliest_match or value > exit_epoch
                            for value in fill_epochs if value is not None
                        ):
                            continue
                        fill_qty = sum(max(0.0, float(fill['quantity'] or 0.0)) for fill in order_fills)
                        if abs(fill_qty - expected_qty) > tolerance:
                            continue
                        candidates.append(order_id)

                    if len(candidates) != 1:
                        continue
                    conn.execute(
                        """
                        UPDATE trade_log
                        SET reconciliation_status = 'candidate_requires_order_evidence'
                        WHERE id = ? AND COALESCE(exit_order_id, '') = ''
                        """,
                        (int(trade['id']),),
                    )
                conn.commit()
        except sqlite3.Error as exc:
            from trading.recorder_write_queue import is_busy
            if is_busy(exc):
                raise
            log_event(
                'trade',
                f"미확정 청산-체결 주문 연결 오류({venue}): {exc}",
                exchange=venue,
                level='ERROR',
            )
        return linked

    @staticmethod
    def _settlement_currency(symbol: str, exchange: str) -> str:
        normalized = str(symbol or '').upper().replace('/', '').replace(':', '').replace('-', '')
        venue = str(exchange or '').lower()
        if venue in {'upbit', 'bithumb', 'coinone', 'kiwoom', 'shinhan', 'mirae', 'miraeasset', 'kis', 'koreainvestment'}:
            return 'KRW'
        for quote in ('USDT', 'USDC', 'USD', 'BTC', 'ETH'):
            if normalized.endswith(quote) or normalized.endswith(f'{quote}SWAP') or normalized.endswith(f'{quote}PERP'):
                return quote
        return ''

    def reconcile_trade_log_with_executions(self, exchange: str, *, trade_ids=None) -> int:
        """Reconcile NoahAI closes only when an exact exit-order match is safe.

        Unknown legacy rows, manual fills, quantity mismatches and mixed fee
        currencies are preserved and labelled; they are never silently rewritten.
        """
        venue = str(exchange or '').strip().lower()
        if not venue:
            return 0
        reconciled = 0
        if trade_ids is None:
            with sqlite3.connect(self.db_path, timeout=20.0) as reader:
                ids = [r[0] for r in reader.execute("SELECT id FROM trade_log WHERE LOWER(exchange)=? AND exit_time IS NOT NULL AND COALESCE(exit_order_id,'')<>''", (venue,))]
            return sum(self.reconcile_trade_log_with_executions(venue, trade_ids=ids[i:i+25]) for i in range(0, len(ids), 25))
        # Maintenance uses small explicit batches, not a full ledger scan per fill.
        selected_ids = None if trade_ids is None else list(dict.fromkeys(int(i) for i in trade_ids))
        if selected_ids == []:
            return 0
        if selected_ids is not None and len(selected_ids) > 100:
            raise ValueError('reconciliation_batch_too_large')
        id_clause = '' if selected_ids is None else ' AND id IN (' + ','.join('?' for _ in selected_ids) + ')'
        try:
            with self._write_connection(operation='reconcile_trade_log_with_executions', timeout=20.0) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT *
                    FROM trade_log
                    WHERE LOWER(COALESCE(exchange, '')) = ?
                      AND exit_time IS NOT NULL
                      AND LOWER(COALESCE(execution_mode, '')) IN ('live', 'live_api', 'optimized', 'manual')
                      AND COALESCE(exit_order_id, '') <> ''
                      AND (
                        LOWER(COALESCE(position_owner, '')) = 'noahai'
                        OR LOWER(COALESCE(reason, '')) LIKE 'ai %'
                        OR LOWER(COALESCE(reason, '')) LIKE 'stock_auto_%'
                      )
                    """ + id_clause,
                    (venue, *(selected_ids or [])),
                ).fetchall()
                for row in rows:
                    # An order cannot certify two independently owned full
                    # closes. Multi-entry allocation needs a separate lot proof.
                    conflict = conn.execute(
                        "SELECT 1 FROM trade_log WHERE id != ? AND LOWER(exchange) = ? "
                        "AND UPPER(symbol) = UPPER(?) AND exit_order_id = ? AND exit_time IS NOT NULL "
                        "AND LOWER(execution_mode) IN ('live','live_api','optimized','manual') LIMIT 1",
                        (int(row['id']), venue, row['symbol'], row['exit_order_id']),
                    ).fetchone()
                    if conflict:
                        conn.execute("UPDATE trade_log SET reconciliation_status='order_attribution_conflict' WHERE id=?", (int(row['id']),))
                        continue
                    existing_status = str(row['reconciliation_status'] or '')
                    final_status = (
                        existing_status.startswith('exchange_confirmed')
                        or existing_status == 'broker_order_linked'
                    )
                    fills = conn.execute(
                        """
                        SELECT side, price, quantity, fee, fee_currency, realized_pnl,
                               COALESCE(realized_pnl_present, 0) AS pnl_present
                        FROM exchange_execution_log
                        WHERE exchange = ? AND order_id = ? AND UPPER(symbol) = UPPER(?)
                          AND confirmation_status = 'confirmed'
                        ORDER BY id
                        """,
                        (venue, str(row['exit_order_id']), str(row['symbol'])),
                    ).fetchall()
                    if not fills:
                        if final_status:
                            continue
                        conn.execute(
                            "UPDATE trade_log SET reconciliation_status = ? WHERE id = ?",
                            ('exchange_fill_not_found', int(row['id'])),
                        )
                        continue
                    expected_side = {'LONG': 'sell', 'BUY': 'sell', 'SHORT': 'buy', 'SELL': 'buy'}.get(str(row['side'] or '').upper())
                    if not expected_side or any(str(fill['side'] or '').lower() != expected_side for fill in fills):
                        if not final_status:
                            conn.execute("UPDATE trade_log SET reconciliation_status = 'close_side_mismatch' WHERE id = ?", (int(row['id']),))
                        continue
                    fill_qty = sum(max(0.0, float(fill['quantity'] or 0.0)) for fill in fills)
                    expected_qty = max(0.0, float(row['quantity'] or 0.0))
                    tolerance = max(1e-8, expected_qty * 0.001)
                    if expected_qty <= 0 or abs(fill_qty - expected_qty) > tolerance:
                        if final_status:
                            continue
                        conn.execute(
                            "UPDATE trade_log SET reconciliation_status = ? WHERE id = ?",
                            ('partial_or_quantity_mismatch', int(row['id'])),
                        )
                        continue
                    quote = sum(float(fill['price'] or 0.0) * float(fill['quantity'] or 0.0) for fill in fills)
                    exit_price = quote / fill_qty if fill_qty > 0 else 0.0
                    pnl_complete = all(int(fill['pnl_present'] or 0) == 1 for fill in fills)
                    gross = sum(float(fill['realized_pnl'] or 0.0) for fill in fills) if pnl_complete else None
                    currencies = {str(fill['fee_currency'] or '').upper() for fill in fills if float(fill['fee'] or 0.0) != 0}
                    exit_fee = sum(float(fill['fee'] or 0.0) for fill in fills)
                    settlement = str(row['settlement_currency'] or '').upper() or self._settlement_currency(row['symbol'], venue)
                    exit_fee_asset = next(iter(currencies)) if len(currencies) == 1 else (
                        'MIXED' if currencies else str(row['exit_fee_asset'] or row['fee_asset'] or '').upper()
                    )
                    # Legacy `fees` may already be entry+exit total, or an
                    # estimate. Reusing it as entry fee double charges costs;
                    # treating NULL as zero silently invents a net result.
                    if row['entry_fee'] is None:
                        conn.execute("""UPDATE trade_log SET gross_pnl=?,net_pnl=NULL,
                            exit_price=?,exit_fee=?,pnl_source=?,
                            reconciliation_status='entry_fee_evidence_missing' WHERE id=?""",
                            (gross,exit_price,exit_fee,'exchange_realized_pnl' if gross is not None else 'exact_fill_price_no_provider_pnl',int(row['id'])))
                        continue
                    entry_fee = float(row['entry_fee'])
                    entry_fee_asset = str(row['entry_fee_asset'] or row['fee_asset'] or '').upper()
                    entry_fee_convertible = entry_fee == 0 or (
                        bool(settlement) and bool(entry_fee_asset) and entry_fee_asset == settlement
                    )
                    exit_fee_convertible = not currencies or currencies == {settlement}
                    fee_convertible = entry_fee_convertible and exit_fee_convertible
                    if gross is None:
                        if final_status:
                            continue
                        conn.execute(
                            """
                            UPDATE trade_log SET exit_price = ?, exit_fee = ?, fees = ?,
                                fee_asset = COALESCE(NULLIF(?, ''), fee_asset),
                                entry_fee_asset = COALESCE(NULLIF(?, ''), entry_fee_asset),
                                exit_fee_asset = COALESCE(NULLIF(?, ''), exit_fee_asset),
                                settlement_currency = COALESCE(NULLIF(?, ''), settlement_currency),
                                pnl_source = 'exact_fill_price_no_provider_pnl',
                                reconciliation_status = 'provider_realized_pnl_unavailable'
                            WHERE id = ?
                            """,
                            (exit_price, exit_fee, entry_fee + exit_fee, exit_fee_asset,
                             entry_fee_asset, exit_fee_asset, settlement, int(row['id'])),
                        )
                        continue
                    net = gross - entry_fee - exit_fee if fee_convertible else None
                    display_pnl = gross if net is None else net
                    notional = max(0.0, float(row['entry_price'] or 0.0) * expected_qty)
                    pnl_percent = display_pnl / notional * 100.0 if notional > 0 else 0.0
                    status = 'exchange_confirmed' if fee_convertible else 'exchange_confirmed_fee_conversion_required'
                    final_values = (exit_price, display_pnl, pnl_percent, gross, net, entry_fee, exit_fee,
                                    entry_fee + exit_fee, exit_fee_asset or None, entry_fee_asset or None,
                                    exit_fee_asset or None, settlement or None, 'exchange_realized_pnl', status)
                    final_fields = ('exit_price','pnl','pnl_percent','gross_pnl','net_pnl','entry_fee','exit_fee',
                                    'fees','fee_asset','entry_fee_asset','exit_fee_asset','settlement_currency','pnl_source','reconciliation_status')
                    if tuple(row[name] for name in final_fields) == final_values:
                        reconciled += 1
                        continue
                    conn.execute(
                        """
                        UPDATE trade_log
                        SET exit_price = ?, pnl = ?, pnl_percent = ?, gross_pnl = ?, net_pnl = ?,
                            entry_fee = ?, exit_fee = ?, fees = ?, fee_asset = ?,
                            entry_fee_asset = ?, exit_fee_asset = ?,
                            settlement_currency = ?, pnl_source = 'exchange_realized_pnl',
                            reconciliation_status = ?
                        WHERE id = ?
                        """,
                        (exit_price, display_pnl, pnl_percent, gross, net, entry_fee, exit_fee,
                         entry_fee + exit_fee, exit_fee_asset or None,
                         entry_fee_asset or None, exit_fee_asset or None,
                         settlement or None, status, int(row['id'])),
                    )
                    reconciled += 1
                conn.commit()
        except sqlite3.Error as exc:
            from trading.recorder_write_queue import is_busy
            if is_busy(exc):
                raise
            log_event('trade', f"체결-청산 원장 대조 오류({venue}): {exc}", exchange=venue, level='ERROR')
        return reconciled

    def get_recent_exchange_executions(
        self,
        exchange: str,
        *,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """거래소 API를 호출하지 않고 로컬 확정 체결 원장을 반환한다."""
        venue = str(exchange or '').strip().lower()
        if not venue:
            return []
        try:
            with sqlite3.connect(self.db_path, timeout=20.0) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT trade_id, order_id, symbol, side, price, quantity, cost,
                           fee, realized_pnl, fee_currency, executed_at, raw_status,
                           confirmation_status, source
                    FROM exchange_execution_log
                    WHERE exchange = ? AND confirmation_status = 'confirmed'
                    ORDER BY COALESCE(executed_at, created_at) DESC, id DESC
                    LIMIT ?
                    """,
                    (venue, max(1, int(limit))),
                ).fetchall()
            return [
                {
                    'id': row['trade_id'],
                    'trade_id': row['trade_id'],
                    'order': row['order_id'],
                    'order_id': row['order_id'],
                    'symbol': row['symbol'],
                    'side': row['side'],
                    'price': float(row['price'] or 0.0),
                    'amount': float(row['quantity'] or 0.0),
                    'quantity': float(row['quantity'] or 0.0),
                    'cost': float(row['cost'] or 0.0),
                    'fee': {
                        'cost': float(row['fee'] or 0.0),
                        'currency': row['fee_currency'] or '',
                    },
                    'realized_pnl': float(row['realized_pnl'] or 0.0),
                    'timestamp': row['executed_at'],
                    'executed_at': row['executed_at'],
                    'status': row['raw_status'],
                    'confirmation_status': row['confirmation_status'],
                    'source': row['source'],
                }
                for row in rows
            ]
        except Exception as exc:
            log_event(
                'trade',
                f"로컬 체결 원장 조회 오류({venue}): {exc}",
                exchange=venue,
                level='ERROR',
            )
            return []

    def get_exchange_execution_cursor(self, exchange: str) -> Dict[str, Any]:
        """증분 거래소 조회에 사용할 마지막 체결 시각·ID를 반환한다."""
        venue = str(exchange or '').strip().lower()
        if not venue:
            return {}
        try:
            with sqlite3.connect(self.db_path, timeout=20.0) as conn:
                row = conn.execute(
                    """
                    SELECT trade_id, executed_at
                    FROM exchange_execution_log
                    WHERE exchange = ? AND confirmation_status = 'confirmed'
                    ORDER BY COALESCE(executed_at, created_at) DESC, id DESC
                    LIMIT 1
                    """,
                    (venue,),
                ).fetchone()
            if not row:
                return {}
            trade_id = str(row[0] or '').strip()
            executed_at = str(row[1] or '').strip()
            since_ms = None
            if executed_at:
                try:
                    parsed = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
                    since_ms = int(parsed.timestamp() * 1000)
                except Exception:
                    since_ms = None
            return {
                'trade_id': trade_id or None,
                'since_ms': since_ms,
                'executed_at': executed_at or None,
            }
        except Exception as exc:
            log_event(
                'trade',
                f"체결 증분 커서 조회 오류({venue}): {exc}",
                exchange=venue,
                level='ERROR',
            )
            return {}

    def save_exchange_execution_capability(self, exchange: str, capability: Dict[str, Any]) -> bool:
        """Persist an explicit supported/unsupported verdict; empty is not zero."""
        venue = str(exchange or '').strip().lower()
        if not venue or not isinstance(capability, dict):
            return False
        try:
            with self._write_connection(operation='save_exchange_execution_capability', timeout=20.0) as conn:
                conn.execute(
                    """
                    INSERT INTO exchange_execution_capability (
                        exchange, history_available, history_reason,
                        historical_trades, closed_orders_fallback, history_complete,
                        coverage_start, coverage_end, coverage_reason, checked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(exchange) DO UPDATE SET
                        history_available = excluded.history_available,
                        history_reason = excluded.history_reason,
                        historical_trades = excluded.historical_trades,
                        closed_orders_fallback = excluded.closed_orders_fallback,
                        history_complete = excluded.history_complete,
                        coverage_start = COALESCE(excluded.coverage_start, coverage_start),
                        coverage_end = COALESCE(excluded.coverage_end, coverage_end),
                        coverage_reason = excluded.coverage_reason,
                        checked_at = CURRENT_TIMESTAMP
                    """,
                    (
                        venue,
                        1 if bool(capability.get('history_available')) else 0,
                        str(capability.get('history_reason') or 'not_checked'),
                        1 if bool(capability.get('historical_trades')) else 0,
                        1 if bool(capability.get('closed_orders_fallback')) else 0,
                        1 if bool(capability.get('history_complete')) else 0,
                        capability.get('coverage_start'),
                        capability.get('coverage_end'),
                        str(capability.get('coverage_reason') or 'bounded_or_incremental_history'),
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            log_event('trade', f"체결 API 기능 상태 저장 오류({venue}): {exc}", exchange=venue, level='WARNING')
            return False

    def save_exchange_order_receipt(
        self,
        exchange: str,
        order: Dict[str, Any],
        *,
        source: str,
        _write_token: Optional[str] = None,
    ) -> bool:
        """주문 접수와 확정 체결을 분리해 주문 ID별 복구 기준을 보존한다."""
        venue = str(exchange or '').strip().lower()
        order_id = str(
            order.get('order') or order.get('order_id') or order.get('orderId')
            or order.get('id') or ''
        ).strip()
        symbol = str(order.get('symbol') or '').strip().upper()
        if not venue or not order_id or not symbol:
            return False
        try:
            raw_json = json.dumps(order, ensure_ascii=False, default=str)
            with self._write_connection(operation='save_exchange_order_receipt', timeout=20.0) as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn, _write_token):
                    return True
                conn.execute(
                    """
                    INSERT INTO exchange_order_receipt (
                        exchange, order_id, symbol, side, requested_quantity,
                        status, confirmed, submitted_at, last_checked_at, source, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                    ON CONFLICT(exchange, order_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        side = COALESCE(excluded.side, exchange_order_receipt.side),
                        requested_quantity = CASE
                            WHEN excluded.requested_quantity > 0 THEN excluded.requested_quantity
                            ELSE exchange_order_receipt.requested_quantity END,
                        status = CASE
                            WHEN lower(exchange_order_receipt.status) IN ('filled','closed') THEN exchange_order_receipt.status
                            WHEN lower(excluded.status) IN ('filled','closed') THEN excluded.status
                            WHEN lower(exchange_order_receipt.status) IN ('canceled','cancelled','rejected','expired') THEN exchange_order_receipt.status
                            WHEN lower(exchange_order_receipt.status) IN ('partially_filled','partiallyfilled')
                                 AND lower(COALESCE(excluded.status,'')) IN ('new','open','pending','') THEN exchange_order_receipt.status
                            ELSE COALESCE(excluded.status, exchange_order_receipt.status) END,
                        confirmed = MAX(exchange_order_receipt.confirmed, excluded.confirmed),
                        submitted_at = COALESCE(exchange_order_receipt.submitted_at, excluded.submitted_at),
                        last_checked_at = CURRENT_TIMESTAMP,
                        source = excluded.source,
                        raw_json = CASE
                            WHEN lower(exchange_order_receipt.status) IN ('filled','closed') AND lower(COALESCE(excluded.status,'')) NOT IN ('filled','closed') THEN exchange_order_receipt.raw_json
                            WHEN lower(exchange_order_receipt.status) IN ('canceled','cancelled','rejected','expired') AND lower(COALESCE(excluded.status,'')) NOT IN ('filled','closed') THEN exchange_order_receipt.raw_json
                            WHEN lower(exchange_order_receipt.status) IN ('partially_filled','partiallyfilled') AND lower(COALESCE(excluded.status,'')) IN ('new','open','pending','') THEN exchange_order_receipt.raw_json
                            ELSE excluded.raw_json END
                    """,
                    (
                        venue, order_id, symbol,
                        str(order.get('side') or '').strip().lower() or None,
                        self._execution_number(
                            order.get('amount') or order.get('filled') or order.get('quantity')
                        ),
                        str(order.get('status') or '').strip() or None,
                        1 if bool(order.get('_execution_confirmed')) else 0,
                        self._execution_time_text(
                            order.get('timestamp') or order.get('datetime') or order.get('time')
                        ) or None,
                        str(source or 'order_receipt'), raw_json,
                    ),
                )
                finish_receipt(conn, _write_token)
                conn.commit()
            return True
        except Exception as exc:
            if _write_token:
                raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(exc):
                try:
                    enqueue(self, 'save_exchange_order_receipt', dict(exchange=exchange,order=order,source=source))
                except Exception as deferred_error:
                    log_event('trade', f'주문 접수 재처리 보존 실패: {type(deferred_error).__name__}', exchange=venue, level='ERROR')
            log_event('trade', f"주문 접수 원장 저장 오류({venue}): {exc}", exchange=venue, level='ERROR')
            return False

    def get_exchange_order_references(self, exchange: str, limit: int = 500) -> List[Dict[str, Any]]:
        """미확정 접수와 상세가 빈 레거시 원장의 주문 ID를 복구 대상으로 반환한다."""
        venue = str(exchange or '').strip().lower()
        if not venue:
            return []
        try:
            with sqlite3.connect(self.db_path, timeout=20.0) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT order_id, symbol, side, status, confirmed
                    FROM exchange_order_receipt
                    WHERE exchange = ? AND confirmed = 0
                      AND LOWER(COALESCE(status, '')) NOT IN (
                          'canceled', 'cancelled', 'rejected', 'expired',
                          'failed', 'error'
                      )
                    UNION
                    SELECT order_id, symbol, side, raw_status, 0
                    FROM exchange_execution_log
                    WHERE exchange = ? AND order_id IS NOT NULL
                      AND (confirmation_status != 'confirmed' OR executed_at IS NULL)
                      AND LOWER(COALESCE(raw_status, '')) NOT IN (
                          'canceled', 'cancelled', 'rejected', 'expired',
                          'failed', 'error'
                      )
                    LIMIT ?
                    """,
                    (venue, venue, max(1, int(limit))),
                )
                return [
                    {
                        'order_id': row[0], 'symbol': row[1], 'side': row[2],
                        'status': row[3], 'confirmed': bool(row[4]),
                    }
                    for row in cur.fetchall()
                    if row and row[0]
                ]
        except Exception as exc:
            log_event('trade', f"주문 복구 대상 조회 오류({venue}): {exc}", exchange=venue, level='ERROR')
            return []

    def get_trade_history(self, symbol: Optional[str] = None, days: int = 30, since_ts: Optional[float] = None, *, strict: bool = False) -> List[Dict]:
        """거래 히스토리 조회"""
        try:
            if since_ts:
                # 특정 시간 이후의 거래 조회
                since_datetime = datetime.fromtimestamp(since_ts).strftime('%Y-%m-%d %H:%M:%S')
                if symbol:
                    query = """
                        SELECT * FROM trade_log
                        WHERE symbol = ? AND exit_time > ?
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        ORDER BY exit_time DESC
                    """
                    params = (symbol, since_datetime)
                else:
                    query = """
                        SELECT * FROM trade_log
                        WHERE exit_time > ?
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        ORDER BY exit_time DESC
                    """
                    params = (since_datetime,)
            else:
                # 기존 days 기반 조회
                if symbol:
                    query = """
                        SELECT * FROM trade_log
                        WHERE symbol = ? AND exit_time > datetime('now', '-{} days')
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        ORDER BY exit_time DESC
                    """.format(days)
                    params = (symbol,)
                else:
                    query = """
                        SELECT * FROM trade_log
                        WHERE exit_time > datetime('now', '-{} days')
                          AND LOWER(COALESCE(reason, '')) != 'binance_import'
                        ORDER BY exit_time DESC
                    """.format(days)
                    params = ()

            results = self.execute_query(query, params, strict=strict)

            trade_history = []
            column_names = [item[1] for item in self.execute_query('PRAGMA table_info(trade_log)', strict=strict)]
            for row in results:
                # DB 실제 컬럼 순서: id, symbol, side, entry_price, exit_price,
                #   quantity, leverage, pnl, pnl_percent, reason, entry_time, exit_time,
                #   tp_price, sl_price, fees, slippage, exchange, created_at
                trade_history.append({
                    'id': row[0],
                    'symbol': row[1],
                    'side': row[2],
                    'entry_price': row[3],
                    'exit_price': row[4],
                    'quantity': row[5],
                    'leverage': row[6],
                    'pnl': row[7],
                    'pnl_percent': row[8],
                    'reason': row[9],
                    'entry_time': row[10],
                    'exit_time': row[11],
                    'tp_price': row[12],
                    'sl_price': row[13],
                    'fees': row[14],
                    'slippage': row[15],
                    'exchange': row[16] if len(row) > 16 else None,
                    **performance_evidence(dict(zip(column_names, row))),
                })

            return trade_history

        except Exception as e:
            log_event('trade', f"거래 히스토리 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            if strict:
                raise
            return []

    def count_closed_trades(
        self,
        *,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> int:
        """재시작 이후에도 유지되는 실제 종료 거래 수를 반환한다.

        과거 스키마에서 exchange가 비어 있던 행은 기존 Binance 거래로 본다.
        진입만 기록되고 종료되지 않은 행은 학습 단계 계산에서 제외한다.
        """
        clauses = [
            "exit_time IS NOT NULL",
            "exit_price IS NOT NULL",
            "LOWER(COALESCE(reason, '')) != 'binance_import'",
        ]
        params: List[Any] = []
        if exchange:
            clauses.append("COALESCE(NULLIF(LOWER(exchange), ''), 'binance') = ?")
            params.append(str(exchange).strip().lower())
        if symbol:
            clauses.append("UPPER(symbol) = ?")
            params.append(str(symbol).strip().upper())
        rows = self.execute_query(
            f"SELECT COUNT(*) FROM trade_log WHERE {' AND '.join(clauses)}",
            tuple(params),
        )
        try:
            return max(0, int(rows[0][0] or 0)) if rows else 0
        except Exception:
            return 0

    def get_performance_stats(self, days: int = 30) -> Dict:
        """성과 통계 조회"""
        try:
            query = """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(pnl) as total_pnl,
                    AVG(CASE WHEN pnl > 0 THEN pnl_percent ELSE NULL END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN pnl_percent ELSE NULL END) as avg_loss,
                    MIN(pnl) as max_drawdown
                FROM trade_log
                WHERE exit_time > datetime('now', '-{} days')
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """.format(days)

            results = self.execute_query(query)

            if results and results[0]:
                row = results[0]
                total_trades = row[0] or 0
                winning_trades = row[1] or 0
                losing_trades = row[2] or 0
                total_pnl = row[3] or 0.0
                avg_win = row[4] or 0.0
                avg_loss = row[5] or 0.0
                max_drawdown = row[6] or 0.0

                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

                return {
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'total_pnl': total_pnl,
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'max_drawdown': max_drawdown
                }

            return {}

        except Exception as e:
            log_event('trade', f"성과 통계 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return {}

    def get_daily_actual_trades(
        self,
        date: datetime,
        *,
        exchange: Optional[str] = None,
        execution_mode: str = 'live',
        strict: bool = False,
    ) -> List[Dict]:
        """특정 날짜의 청산 거래를 거래소·실행모드별로 조회한다.

        일일 LIVE 손실 가드레일이 다른 거래소나 PAPER 행을 합산하지 않도록
        날짜 문자열의 공백/T/UTC offset 차이를 epoch로 정규화한다.
        미대조 행도 반환하되 확정 손익으로 승격하지 않는다.
        """
        try:
            start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)

            query = """
                SELECT id, symbol, side, entry_price, exit_price, quantity,
                       leverage, pnl, pnl_percent, reason, entry_time, exit_time,
                       tp_price, sl_price, fees, slippage,
                       COALESCE(exchange, 'binance') AS exchange,
                       execution_mode, reconciliation_status, net_pnl, pnl_source
                FROM trade_log
                WHERE exit_time >= ? AND exit_time < ?
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """
            # Broad indexed date window, then exact local/aware time comparison.
            # UTC offsets and legacy space-separated timestamps must not drop a close.
            params: List[Any] = [(start_date - timedelta(days=2)).date().isoformat(),
                                 (end_date + timedelta(days=2)).date().isoformat()]
            if exchange:
                query += " AND LOWER(COALESCE(NULLIF(exchange, ''), 'binance')) = LOWER(?)"
                params.append(str(exchange).strip().lower())
            normalized_mode = str(execution_mode or '').strip().lower()
            if normalized_mode == 'live':
                # Unknown legacy mode is retained as UNVERIFIED, not silently lost.
                query += " AND LOWER(COALESCE(execution_mode, '')) IN ('live','live_api','optimized','manual','')"
            elif normalized_mode:
                query += " AND LOWER(COALESCE(NULLIF(execution_mode, ''), 'live')) = LOWER(?)"
                params.append(normalized_mode)
            query += " ORDER BY exit_time DESC"

            results = self.execute_query(query, tuple(params), strict=strict)

            daily_trades = []
            for row in results:
                closed_at = self._ledger_time_epoch(row[11])
                if closed_at is None:
                    raise ValueError('invalid close timestamp in daily ledger')
                if not start_date.timestamp() <= closed_at < end_date.timestamp():
                    continue
                daily_trades.append({
                    'id': row[0],
                    'symbol': row[1],
                    'side': row[2],
                    'entry_price': row[3],
                    'exit_price': row[4],
                    'quantity': row[5],
                    'leverage': row[6],
                    'pnl': row[7],
                    'realized_pnl': row[7],
                    'pnl_percent': row[8],
                    'reason': row[9],
                    'entry_time': row[10],
                    'exit_time': row[11],
                    'tp_price': row[12],
                    'sl_price': row[13],
                    'fees': row[14],
                    'slippage': row[15],
                    'exchange': row[16],
                    'execution_mode': row[17],
                    **performance_evidence({'execution_mode': row[17],
                                           'reconciliation_status': row[18],
                                           'net_pnl': row[19], 'pnl_source': row[20]}),
                })

            return daily_trades

        except Exception as e:
            log_event('trade', f"일일 거래 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            if strict:
                raise
            return []

    def get_symbol_performance(self, symbol: str, days: int = 30) -> Dict:
        """심볼별 성과 조회"""
        try:
            query = """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(pnl) as total_pnl,
                    AVG(pnl_percent) as avg_pnl_percent,
                    MAX(pnl_percent) as best_trade,
                    MIN(pnl_percent) as worst_trade
                FROM trade_log
                WHERE symbol = ? AND exit_time > datetime('now', '-{} days')
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """.format(days)

            results = self.execute_query(query, (symbol,))

            if results and results[0]:
                row = results[0]
                total_trades = row[0] or 0
                winning_trades = row[1] or 0
                total_pnl = row[2] or 0.0
                avg_pnl_percent = row[3] or 0.0
                best_trade = row[4] or 0.0
                worst_trade = row[5] or 0.0

                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

                return {
                    'symbol': symbol,
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl_percent': avg_pnl_percent,
                    'best_trade': best_trade,
                    'worst_trade': worst_trade
                }

            return {}

        except Exception as e:
            log_event('trade', f"심볼별 성과 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return {}

    def get_recent_loss_patterns_summary(self, symbol: str, hours: int = 24) -> Dict:
        """최근 손실 패턴 요약 (간단 버전)"""
        try:
            query = f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl_percent < 0 THEN 1 ELSE 0 END) as loss_trades,
                    SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) as profit_trades,
                    AVG(CASE WHEN pnl_percent < 0 THEN ABS(pnl_percent) END) as avg_loss_rate,
                    AVG(CASE WHEN pnl_percent > 0 THEN pnl_percent END) as avg_profit_rate
                FROM trade_log
                WHERE symbol = ? AND exit_time > datetime('now', ?)
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
            """
            params = (symbol, f'-{hours} hours')
            results = self.execute_query(query, params)
            summary = {
                'total_trades': 0,
                'loss_trades': 0,
                'profit_trades': 0,
                'avg_loss_rate': 0.0,
                'avg_profit_rate': 0.0,
                'loss_reasons': []
            }
            if results and results[0]:
                row = results[0]
                summary.update({
                    'total_trades': row[0] or 0,
                    'loss_trades': row[1] or 0,
                    'profit_trades': row[2] or 0,
                    'avg_loss_rate': row[3] or 0.0,
                    'avg_profit_rate': row[4] or 0.0,
                })
            # 손실 사유 수집
            reasons = self.execute_query(
                f"""
                SELECT reason FROM trade_log
                WHERE symbol = ? AND pnl_percent < 0 AND exit_time > datetime('now', ?)
                  AND LOWER(COALESCE(reason, '')) != 'binance_import'
                """,
                (symbol, f'-{hours} hours')
            )
            summary['loss_reasons'] = [r[0] for r in reasons if r and r[0]]
            return summary
        except Exception as e:
            log_event('trade', f"최근 손실 패턴 요약 오류: {e}", exchange=self.exchange, level='ERROR')
            return {}

    def update_daily_stats(self):
        """일일 통계 업데이트"""
        try:
            today = datetime.now().date()
            stats = self.get_performance_stats(1)

            with self._write_connection(operation='update_daily_stats') as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO performance_stats (
                        date, total_trades, winning_trades, losing_trades,
                        total_pnl, win_rate, avg_win, avg_loss, max_drawdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    today, stats.get('total_trades', 0), stats.get('winning_trades', 0),
                    stats.get('losing_trades', 0), stats.get('total_pnl', 0),
                    stats.get('win_rate', 0), stats.get('avg_win', 0),
                    stats.get('avg_loss', 0), stats.get('max_drawdown', 0)
                ))
                conn.commit()

            log_event('trade', "일일 통계 업데이트 완료", exchange=self.exchange, level='INFO')

        except Exception as e:
            log_event('trade', f"일일 통계 업데이트 오류: {e}", exchange=self.exchange, level='ERROR')

    def save_exchange_trade_stats(self, exchange: str, stats: Dict[str, Any]):
        """거래소별 거래 통계 저장"""
        try:
            with self._write_connection(operation='save_exchange_trade_stats') as conn:
                cursor = conn.cursor()

                table_cols = set(self._get_table_columns(cursor, 'exchange_trade_stats'))
                has_fee_cols = 'total_fees' in table_cols and 'avg_fee' in table_cols

                # 디버깅: 저장할 통계 데이터 확인
                log_event('trade', f"[DEBUG] save_exchange_trade_stats 호출:", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - exchange: {exchange}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - stats: {stats}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - total_trades: {stats.get('total_trades', 0)}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - winning_trades: {stats.get('winning_trades', 0) or stats.get('profitable_trades', 0)}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - losing_trades: {stats.get('losing_trades', 0)}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - total_pnl: {stats.get('total_pnl', 0.0)}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - max_drawdown: {stats.get('max_drawdown', 0.0)}", exchange=self.exchange, level='INFO')

                total_fees = float(stats.get('total_fees', stats.get('fees_total', 0.0)) or 0.0)
                total_trades = int(stats.get('total_trades', 0) or 0)
                avg_fee = float(stats.get('avg_fee', (total_fees / total_trades if total_trades > 0 else 0.0)) or 0.0)
                log_event('trade', f"  - total_fees: {total_fees}", exchange=self.exchange, level='INFO')
                log_event('trade', f"  - avg_fee: {avg_fee}", exchange=self.exchange, level='INFO')

                # 거래소별 통계 업데이트 또는 삽입
                if has_fee_cols:
                    cursor.execute("""
                        INSERT OR REPLACE INTO exchange_trade_stats (
                            exchange, total_trades, winning_trades, losing_trades,
                            total_pnl, max_drawdown, total_fees, avg_fee, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        exchange,
                        total_trades,
                        stats.get('winning_trades', 0) or stats.get('profitable_trades', 0),
                        stats.get('losing_trades', 0),
                        stats.get('total_pnl', 0.0),
                        stats.get('max_drawdown', 0.0),
                        total_fees,
                        avg_fee,
                    ))
                else:
                    cursor.execute("""
                        INSERT OR REPLACE INTO exchange_trade_stats (
                            exchange, total_trades, winning_trades, losing_trades,
                            total_pnl, max_drawdown, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        exchange,
                        total_trades,
                        stats.get('winning_trades', 0) or stats.get('profitable_trades', 0),
                        stats.get('losing_trades', 0),
                        stats.get('total_pnl', 0.0),
                        stats.get('max_drawdown', 0.0)
                    ))
                # Capture the INSERT result before the verification SELECT.
                # Returning an undefined variable after commit reported a
                # successful write as a failure (observed in customer logs).
                inserted_id = cursor.lastrowid
                conn.commit()

                # 저장 후 확인
                cursor.execute("SELECT * FROM exchange_trade_stats WHERE exchange = ?", (exchange,))
                saved_data = cursor.fetchone()
                log_event('trade', f"🔍 [DEBUG] 저장된 데이터: {saved_data}", exchange=self.exchange, level='INFO')

                log_event('trade', f"✅ {exchange} 거래 통계 저장 완료", exchange=self.exchange, level='INFO')
                return inserted_id

        except Exception as e:
            log_event('trade', f"❌ {exchange} 거래 통계 저장 실패: {e}", exchange=self.exchange, level='ERROR')
            return False

    def update_trade_log(
        self,
        symbol: str,
        exit_price: float,
        exit_time,
        pnl_percent: float,
        pnl_usdt: float,
        exit_reason: str,
        position: Optional[Any] = None,
        additional_fees: float = 0.0,
        exit_order_id: Optional[str] = None,
        fee_asset: Optional[str] = None,
        fee_source: Optional[str] = None,
        exchange: Optional[str] = None,
        entry_order_id: Optional[str] = None,
        gross_pnl: Optional[float] = None,
        net_pnl: Optional[float] = None,
        pnl_source: str = 'estimated_close_price',
        reconciliation_status: str = 'pending_exchange_reconciliation',
        settlement_currency: Optional[str] = None,
        _write_token: Optional[str] = None,
    ):
        """개별 거래 로그 업데이트 (종료 정보)"""
        retry_payload = dict(locals())
        retry_payload.pop('self')
        try:
            logger = self._logger
            log_event('trade', f"[DEBUG] update_trade_log 호출: symbol={symbol}, exit_price={exit_price}, exit_time={exit_time}, pnl_percent={pnl_percent}, pnl_usdt={pnl_usdt}, exit_reason={exit_reason}", exchange=self.exchange, level='INFO')

            with self._write_connection(operation='update_trade_log') as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn, _write_token):
                    return True
                cursor = conn.cursor()

                # Symbol-only matching can close another venue's row or a
                # same-symbol re-entry.  Prefer the exact entry order id and
                # always apply the venue boundary when the caller has it.
                lookup_order_id = str(
                    entry_order_id
                    or getattr(position, 'entry_order_id', '')
                    or ''
                ).strip()
                where = ["symbol = ?", "exit_time IS NULL"]
                params: List[Any] = [symbol]
                if exchange:
                    where.append("LOWER(COALESCE(exchange, '')) = ?")
                    params.append(str(exchange).strip().lower())
                if lookup_order_id:
                    where.append("order_id = ?")
                    params.append(lookup_order_id)
                cursor.execute(f"""
                    SELECT id, entry_price, quantity, side, tp_price, sl_price,
                           fees, entry_fee, fee_asset, entry_fee_asset
                    FROM trade_log
                    WHERE {' AND '.join(where)}
                    ORDER BY entry_time DESC LIMIT 1
                """, tuple(params))

                trade_data = cursor.fetchone()
                if trade_data:
                    (
                        trade_id, entry_price, quantity, side, stored_tp_price,
                        stored_sl_price, stored_fees, stored_entry_fee,
                        stored_fee_asset, stored_entry_fee_asset,
                    ) = trade_data
                    log_event('trade', f"[DEBUG] 찾은 거래: id={trade_id}, entry_price={entry_price}, quantity={quantity}, side={side}, tp_price={stored_tp_price}, sl_price={stored_sl_price}", exchange=self.exchange, level='INFO')

                    # 🔥 TP/SL 판단 로직 (문제 1 해결)
                    final_tp_price = stored_tp_price
                    final_sl_price = stored_sl_price
                    
                    # position 객체가 있으면 우선 사용, 없으면 DB 값 사용
                    if position and hasattr(position, 'tp_price') and hasattr(position, 'sl_price'):
                        if position.tp_price is not None:
                            final_tp_price = float(position.tp_price)
                        if position.sl_price is not None:
                            final_sl_price = float(position.sl_price)
                    
                    # TP/SL 판단: exit_price와 비교하여 어떤 것으로 청산되었는지 판단
                    if final_tp_price and final_sl_price and entry_price > 0:
                        side_upper = str(side).upper()
                        is_long = side_upper in ('BUY', 'LONG')
                        
                        # 가격 비교 시 허용 오차 (0.01% 또는 tickSize 고려)
                        tolerance = max(entry_price * 0.0001, 0.0001)  # 0.01% 또는 최소 0.0001
                        
                        if is_long:
                            # LONG 포지션: TP는 exit_price >= tp_price, SL은 exit_price <= sl_price
                            if exit_price >= (final_tp_price - tolerance):
                                # TP로 청산
                                final_tp_price = final_tp_price
                                final_sl_price = None  # SL 값 제거
                                log_event('trade', f"[DEBUG] {symbol} TP로 청산 판단: exit_price={exit_price}, tp_price={final_tp_price}", exchange=self.exchange, level='INFO')
                            elif exit_price <= (final_sl_price + tolerance):
                                # SL로 청산
                                final_tp_price = None  # TP 값 제거
                                final_sl_price = final_sl_price
                                log_event('trade', f"[DEBUG] {symbol} SL로 청산 판단: exit_price={exit_price}, sl_price={final_sl_price}", exchange=self.exchange, level='INFO')
                            else:
                                # 기타 청산 (수동 등) - 둘 다 유지
                                log_event('trade', f"[DEBUG] {symbol} 기타 청산: exit_price={exit_price}, tp_price={final_tp_price}, sl_price={final_sl_price}", exchange=self.exchange, level='INFO')
                        else:
                            # SHORT 포지션: TP는 exit_price <= tp_price, SL은 exit_price >= sl_price
                            if exit_price <= (final_tp_price + tolerance):
                                # TP로 청산
                                final_tp_price = final_tp_price
                                final_sl_price = None  # SL 값 제거
                                log_event('trade', f"[DEBUG] {symbol} TP로 청산 판단: exit_price={exit_price}, tp_price={final_tp_price}", exchange=self.exchange, level='INFO')
                            elif exit_price >= (final_sl_price - tolerance):
                                # SL로 청산
                                final_tp_price = None  # TP 값 제거
                                final_sl_price = final_sl_price
                                log_event('trade', f"[DEBUG] {symbol} SL로 청산 판단: exit_price={exit_price}, sl_price={final_sl_price}", exchange=self.exchange, level='INFO')
                            else:
                                # 기타 청산 (수동 등) - 둘 다 유지
                                log_event('trade', f"[DEBUG] {symbol} 기타 청산: exit_price={exit_price}, tp_price={final_tp_price}, sl_price={final_sl_price}", exchange=self.exchange, level='INFO')

                    entry_fee_value = float(
                        stored_entry_fee if stored_entry_fee is not None else stored_fees or 0.0
                    )
                    exit_fee_value = float(additional_fees or 0.0)
                    total_fees = entry_fee_value + exit_fee_value
                    gross_value = float(gross_pnl if gross_pnl is not None else pnl_usdt)
                    resolved_net = net_pnl
                    settlement = str(settlement_currency or '').strip().upper() or None
                    entry_fee_ccy = str(
                        stored_entry_fee_asset or stored_fee_asset or ''
                    ).strip().upper() or None
                    exit_fee_ccy = str(fee_asset or '').strip().upper() or None
                    entry_fee_convertible = entry_fee_value == 0 or (
                        bool(settlement) and bool(entry_fee_ccy) and entry_fee_ccy == settlement
                    )
                    exit_fee_convertible = exit_fee_value == 0 or (
                        bool(settlement) and bool(exit_fee_ccy) and exit_fee_ccy == settlement
                    )
                    fee_convertible = entry_fee_convertible and exit_fee_convertible
                    if resolved_net is None and fee_convertible:
                        resolved_net = gross_value - total_fees
                    display_pnl = float(resolved_net) if resolved_net is not None else gross_value
                    notional = max(0.0, float(entry_price or 0.0) * float(quantity or 0.0))
                    resolved_percent = (display_pnl / notional * 100.0) if notional > 0 else float(pnl_percent or 0.0)
                    resolved_status = str(reconciliation_status or 'pending_exchange_reconciliation')
                    if not fee_convertible and resolved_status == 'exchange_confirmed':
                        resolved_status = 'exchange_confirmed_fee_conversion_required'

                    cursor.execute("""
                        UPDATE trade_log
                        SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?, reason = ?,
                            tp_price = ?, sl_price = ?, fees = ?, exit_order_id = ?,
                            fee_asset = COALESCE(?, fee_asset), fee_source = COALESCE(?, fee_source),
                            gross_pnl = ?, net_pnl = ?, entry_fee = ?, exit_fee = ?,
                            entry_fee_asset = COALESCE(?, entry_fee_asset),
                            exit_fee_asset = COALESCE(?, exit_fee_asset),
                            settlement_currency = COALESCE(?, settlement_currency),
                            pnl_source = ?, reconciliation_status = ?
                        WHERE id = ?
                    """, (
                        exit_price,
                        self._to_db_datetime(exit_time),
                        display_pnl,
                        resolved_percent,
                        exit_reason,
                        final_tp_price,
                        final_sl_price,
                        total_fees,
                        str(exit_order_id) if exit_order_id is not None else None,
                        fee_asset,
                        fee_source,
                        gross_value,
                        resolved_net,
                        entry_fee_value,
                        exit_fee_value,
                        entry_fee_ccy,
                        exit_fee_ccy,
                        settlement,
                        str(pnl_source or 'estimated_close_price'),
                        resolved_status,
                        trade_id,
                    ))

                    finish_receipt(conn, _write_token)
                    conn.commit()

                    # 업데이트 후 확인
                    cursor.execute("SELECT exit_price, exit_time, pnl, pnl_percent, reason, tp_price, sl_price FROM trade_log WHERE id = ?", (trade_id,))
                    updated_data = cursor.fetchone()
                    log_event('trade', f"[DEBUG] 업데이트 후 데이터: {updated_data}", exchange=self.exchange, level='INFO')

                    log_event('trade', f"✅ {symbol} 거래 로그 업데이트 완료: 종료가 {exit_price}, PnL {pnl_percent:.2f}%, TP={final_tp_price}, SL={final_sl_price}", exchange=self.exchange, level='INFO')
                    return True
                else:
                    log_event('trade', f"⚠️ {symbol} 미종료 거래를 찾을 수 없음", exchange=self.exchange, level='WARNING')

                    # 디버깅: 해당 심볼의 모든 거래 확인
                    cursor.execute("SELECT id, symbol, entry_time, exit_time FROM trade_log WHERE symbol = ? ORDER BY entry_time DESC LIMIT 3", (symbol,))
                    all_trades = cursor.fetchall()
                    log_event('trade', f"[DEBUG] {symbol} 최근 거래들: {all_trades}", exchange=self.exchange, level='INFO')

                    return False

        except Exception as e:
            if _write_token:
                raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(e):
                try:
                    enqueue(self, 'update_trade_log', retry_payload)
                    log_event('trade', f'{symbol} 청산 기록 저장 대기 · 원본 보존 후 자동 재처리. 저장 완료 전 손익 대조 필요', exchange=exchange or self.exchange, level='ERROR')
                except Exception as queue_error:
                    log_event('trade', f'{symbol} 청산 재처리 근거 저장 실패: {type(queue_error).__name__}. 거래 기록 대조 필요', exchange=exchange or self.exchange, level='ERROR')
            log_event('trade', f"❌ {symbol} 거래 로그 업데이트 실패: {e}", exchange=self.exchange, level='ERROR')
            import traceback
            log_event('trade', f"❌ 상세 오류: {traceback.format_exc()}", exchange=self.exchange, level='ERROR')
            return False

    def record_partial_trade_close(
        self,
        *,
        symbol: str,
        exchange: str,
        entry_order_id: Optional[str],
        exit_order_id: Optional[str],
        closed_quantity: float,
        exit_price: float,
        gross_pnl: float,
        exit_fee: float,
        fee_asset: Optional[str],
        reason: str,
        pnl_source: str,
        reconciliation_status: str,
        closed_at=None,
        _write_token=None,
    ) -> bool:
        """Split one verified partial close from its still-open entry lot."""
        import math
        try:
            amounts=[float(v) for v in (closed_quantity,exit_price,gross_pnl,exit_fee)]
        except (ValueError,TypeError):
            return False
        if not all(math.isfinite(v) for v in amounts) or amounts[0]<=0 or amounts[1]<=0 or amounts[3]<0:
            return False
        venue = str(exchange or '').strip().lower()
        qty = max(0.0, float(closed_quantity or 0.0))
        if not venue or qty <= 0 or not entry_order_id:
            return False
        closed_at = closed_at or datetime.now()
        payload = {k:v for k,v in locals().copy().items() if k in (
            'symbol','exchange','entry_order_id','exit_order_id','closed_quantity','exit_price','gross_pnl',
            'exit_fee','fee_asset','reason','pnl_source','reconciliation_status','closed_at')}
        try:
            with self._write_connection(operation='record_partial_trade_close', timeout=20.0) as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn, _write_token): return True
                if not _write_token: conn.execute('BEGIN IMMEDIATE')
                if exit_order_id:
                    previous = conn.execute('''SELECT quantity,exit_price,gross_pnl,exit_fee FROM trade_log
                        WHERE lower(exchange)=? AND symbol=? AND order_id=? AND exit_order_id=? AND exit_time IS NOT NULL''',
                        (venue,symbol,str(entry_order_id),str(exit_order_id))).fetchall()
                    if previous:
                        if len(previous)!=1 or tuple(previous[0]) != (qty,float(exit_price),float(gross_pnl),float(exit_fee)):
                            return False
                        finish_receipt(conn,_write_token)
                        return True
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT * FROM trade_log
                    WHERE symbol = ? AND LOWER(COALESCE(exchange, '')) = ?
                      AND order_id = ? AND exit_time IS NULL
                    ORDER BY entry_time DESC, id DESC LIMIT 1
                    """,
                    (symbol, venue, str(entry_order_id)),
                ).fetchone()
                if row is None:
                    return False
                open_qty = max(0.0, float(row['quantity'] or 0.0))
                if qty >= open_qty - max(1e-8, open_qty * 0.001):
                    return False
                ratio = qty / open_qty
                # Legacy aggregate fees do not prove an entry commission.
                entry_fee_total = float(row['entry_fee']) if row['entry_fee'] is not None else None
                allocated_entry_fee = entry_fee_total * ratio if entry_fee_total is not None else None
                remaining_entry_fee = entry_fee_total - allocated_entry_fee if entry_fee_total is not None else None
                settlement = str(row['settlement_currency'] or '').upper() or self._settlement_currency(symbol, venue)
                entry_fee_ccy = str(row['entry_fee_asset'] or row['fee_asset'] or '').upper()
                exit_fee_ccy = str(fee_asset or '').upper()
                fee_convertible = (
                    allocated_entry_fee is not None and allocated_entry_fee >= 0
                    and (allocated_entry_fee == 0 or (settlement and entry_fee_ccy == settlement))
                    and (float(exit_fee or 0.0) <= 0 or (settlement and exit_fee_ccy == settlement))
                )
                net_pnl = (
                    float(gross_pnl) - allocated_entry_fee - max(0.0, float(exit_fee or 0.0))
                    if fee_convertible else None
                )
                display_pnl = float(gross_pnl) if net_pnl is None else net_pnl
                notional = max(0.0, float(row['entry_price'] or 0.0) * qty)
                pnl_percent = display_pnl / notional * 100.0 if notional else 0.0
                conn.execute(
                    "UPDATE trade_log SET quantity = ?, fees = ?, entry_fee = ? WHERE id = ?",
                    (open_qty - qty, remaining_entry_fee, remaining_entry_fee, int(row['id'])),
                )
                columns = [
                    'symbol','entry_price','exit_price','quantity','leverage','pnl','pnl_percent',
                    'entry_time','exit_time','reason','side','tp_price','sl_price','fees','slippage',
                    'exchange','order_id','exit_order_id','model_version','strategy_variant','fee_asset',
                    'fee_source','position_owner','execution_mode','spot_baseline_quantity','gross_pnl',
                    'net_pnl','entry_fee','exit_fee','entry_fee_asset','exit_fee_asset',
                    'settlement_currency','pnl_source','reconciliation_status','strategy_key','strategy_version_id',
                ]
                values = [
                    row['symbol'], row['entry_price'], float(exit_price), qty, row['leverage'], display_pnl,
                    pnl_percent, row['entry_time'], self._to_db_datetime(closed_at), reason, row['side'],
                    row['tp_price'], row['sl_price'], allocated_entry_fee + float(exit_fee) if allocated_entry_fee is not None else None,
                    row['slippage'], row['exchange'], row['order_id'], str(exit_order_id or '') or None,
                    row['model_version'], row['strategy_variant'], fee_asset or row['fee_asset'],
                    'exchange_fill', row['position_owner'], row['execution_mode'], row['spot_baseline_quantity'],
                    float(gross_pnl), net_pnl, allocated_entry_fee, float(exit_fee or 0.0),
                    entry_fee_ccy or None, exit_fee_ccy or None, settlement or None,
                    pnl_source, reconciliation_status if net_pnl is not None else 'entry_fee_evidence_missing',row['strategy_key'],row['strategy_version_id'],
                ]
                conn.execute(
                    f"INSERT INTO trade_log ({', '.join(columns)}) VALUES ({', '.join('?' for _ in values)})",
                    tuple(values),
                )
                finish_receipt(conn,_write_token)
                conn.commit()
            return True
        except sqlite3.Error as exc:
            if _write_token: raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(exc) and exit_order_id:
                enqueue(self,'record_partial_trade_close',payload)
            log_event('trade', f"부분청산 원장 기록 오류({venue}/{symbol}): {exc}", exchange=venue, level='ERROR')
            return False

    def load_exchange_trade_stats(self, exchange: Optional[str] = None) -> Dict[str, Any]:
        """거래소별 거래 통계 로드"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                table_cols = set(self._get_table_columns(cursor, 'exchange_trade_stats'))
                has_fee_cols = 'total_fees' in table_cols and 'avg_fee' in table_cols
                fee_select = ", COALESCE(total_fees, 0), COALESCE(avg_fee, 0)" if has_fee_cols else ""

                if exchange:
                    # 특정 거래소 통계
                    cursor.execute(f"""
                        SELECT total_trades, winning_trades, losing_trades,
                               total_pnl, max_drawdown, last_updated{fee_select}
                        FROM exchange_trade_stats
                        WHERE exchange = ?
                    """, (exchange,))
                    result = cursor.fetchone()

                    if result:
                        payload = {
                            'total_trades': result[0],
                            'winning_trades': result[1],
                            'losing_trades': result[2],
                            'total_pnl': result[3],
                            'max_drawdown': result[4],
                            'last_updated': result[5]
                        }
                        if has_fee_cols:
                            payload['total_fees'] = float(result[6] or 0.0)
                            payload['avg_fee'] = float(result[7] or 0.0)
                        else:
                            payload['total_fees'] = 0.0
                            payload['avg_fee'] = 0.0
                        return payload
                    return {}
                else:
                    # 모든 거래소 통계
                    cursor.execute(f"""
                        SELECT exchange, total_trades, winning_trades, losing_trades,
                               total_pnl, max_drawdown, last_updated{fee_select}
                        FROM exchange_trade_stats
                    """)
                    results = cursor.fetchall()

                    stats = {}
                    for row in results:
                        item = {
                            'total_trades': row[1],
                            'winning_trades': row[2],
                            'losing_trades': row[3],
                            'total_pnl': row[4],
                            'max_drawdown': row[5],
                            'last_updated': row[6]
                        }
                        if has_fee_cols:
                            item['total_fees'] = float(row[7] or 0.0)
                            item['avg_fee'] = float(row[8] or 0.0)
                        else:
                            item['total_fees'] = 0.0
                            item['avg_fee'] = 0.0
                        stats[row[0]] = item
                    return stats

        except Exception as e:
            log_event('trade', f"❌ 거래 통계 로드 실패: {e}", exchange=self.exchange, level='ERROR')
            return {}

    def save_stock_trade_stats(self, broker: str, asset_type: str, stats: Dict[str, Any], stat_date: Optional[str] = None) -> bool:
        """주식/ETF 브로커·자산유형 통계 저장"""
        try:
            target_date = stat_date or datetime.now().strftime('%Y-%m-%d')
            with self._write_connection(operation='save_stock_trade_stats') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO stock_trade_stats (
                        broker, asset_type, stat_date,
                        total_trades, winning_trades, losing_trades,
                        buy_count, sell_count,
                        realized_pnl, win_rate, avg_pnl, max_drawdown,
                        last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        str(broker),
                        str(asset_type),
                        target_date,
                        int(stats.get('total_trades', 0) or 0),
                        int(stats.get('winning_trades', 0) or 0),
                        int(stats.get('losing_trades', 0) or 0),
                        int(stats.get('buy_count', 0) or 0),
                        int(stats.get('sell_count', 0) or 0),
                        float(stats.get('realized_pnl', 0.0) or 0.0),
                        float(stats.get('win_rate', 0.0) or 0.0),
                        float(stats.get('avg_pnl', 0.0) or 0.0),
                        float(stats.get('max_drawdown', 0.0) or 0.0),
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            log_event('trade', f"주식 통계 저장 실패({broker}/{asset_type}): {e}", exchange=self.exchange, level='ERROR')
            return False

    def load_stock_trade_stats(self, broker: Optional[str] = None, asset_type: Optional[str] = None, days: int = 30) -> List[Dict[str, Any]]:
        """주식/ETF 브로커·자산유형 통계 조회"""
        try:
            where_clauses = ["stat_date >= date('now', ?)"]
            params: List[Any] = [f'-{max(1, int(days))} days']

            if broker:
                where_clauses.append("broker = ?")
                params.append(broker)
            if asset_type:
                where_clauses.append("asset_type = ?")
                params.append(asset_type)

            query = f"""
                SELECT broker, asset_type, stat_date,
                       total_trades, winning_trades, losing_trades,
                       buy_count, sell_count,
                       realized_pnl, win_rate, avg_pnl, max_drawdown,
                       last_updated
                FROM stock_trade_stats
                WHERE {' AND '.join(where_clauses)}
                ORDER BY stat_date DESC, broker ASC, asset_type ASC
            """

            rows = self.execute_query(query, tuple(params))
            result: List[Dict[str, Any]] = []
            for row in rows:
                result.append({
                    'broker': row[0],
                    'asset_type': row[1],
                    'stat_date': row[2],
                    'total_trades': row[3],
                    'winning_trades': row[4],
                    'losing_trades': row[5],
                    'buy_count': row[6],
                    'sell_count': row[7],
                    'realized_pnl': row[8],
                    'win_rate': row[9],
                    'avg_pnl': row[10],
                    'max_drawdown': row[11],
                    'last_updated': row[12],
                })
            return result
        except Exception as e:
            log_event('trade', f"주식 통계 조회 실패: {e}", exchange=self.exchange, level='ERROR')
            return []

    def save_stock_execution_metric(self, metric: Dict[str, Any], *, _write_token=None) -> bool:
        """주식 자동매매 주문 실행 품질 메트릭 저장."""
        try:
            with self._write_connection(operation='save_stock_execution_metric') as conn:
                from trading.recorder_write_queue import begin_receipt,finish_receipt
                if begin_receipt(conn,_write_token):return True
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO stock_execution_metrics (
                        broker, symbol, side, order_type, execution_mode,
                        success, latency_ms, slippage_bps, rejection_reason, decision_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(metric.get('broker') or ''),
                        str(metric.get('symbol') or ''),
                        str(metric.get('side') or ''),
                        str(metric.get('order_type') or ''),
                        str(metric.get('execution_mode') or ''),
                        int(bool(metric.get('success', False))),
                        float(metric.get('latency_ms', 0.0) or 0.0),
                        float(metric.get('slippage_bps', 0.0) or 0.0),
                        str(metric.get('rejection_reason') or ''),
                        str(metric.get('decision_type') or 'entry'),
                    ),
                )
                finish_receipt(conn,_write_token)
                conn.commit()
            return True
        except Exception as e:
            log_event('trade', f"실행 메트릭 저장 실패: {e}", exchange=self.exchange, level='ERROR')
            if _write_token:raise
            from trading.recorder_write_queue import enqueue,is_busy
            if is_busy(e):enqueue(self,'save_stock_execution_metric',{'metric':metric})
            return False

    def load_stock_execution_metrics(self, broker: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """주식 자동매매 실행 메트릭 조회."""
        try:
            clauses = ["created_at >= datetime('now', ?)"]
            params: List[Any] = [f'-{max(1, int(days))} days']
            if broker:
                clauses.append("broker = ?")
                params.append(str(broker))

            query = f"""
                SELECT broker, symbol, side, order_type, execution_mode,
                       success, latency_ms, slippage_bps, rejection_reason,
                       decision_type, created_at
                FROM stock_execution_metrics
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
            """
            rows = self.execute_query(query, tuple(params))
            result: List[Dict[str, Any]] = []
            for row in rows:
                result.append({
                    'broker': row[0],
                    'symbol': row[1],
                    'side': row[2],
                    'order_type': row[3],
                    'execution_mode': row[4],
                    'success': bool(row[5]),
                    'latency_ms': row[6],
                    'slippage_bps': row[7],
                    'rejection_reason': row[8],
                    'decision_type': row[9],
                    'created_at': row[10],
                })
            return result
        except Exception as e:
            log_event('trade', f"실행 메트릭 조회 실패: {e}", exchange=self.exchange, level='ERROR')
            return []

    def is_duplicate_stock_order_key(self, broker: str, idempotency_key: str, within_seconds: int = 120) -> bool:
        """최근 동일 idempotency 키 주문 존재 여부 확인."""
        try:
            rows = self.execute_query(
                """
                SELECT id
                FROM stock_order_idempotency
                WHERE broker = ?
                  AND idempotency_key = ?
                  AND created_at >= datetime('now', ?)
                LIMIT 1
                """,
                (str(broker), str(idempotency_key), f'-{max(1, int(within_seconds))} seconds'),
            )
            return bool(rows)
        except Exception:
            return False

    def save_stock_order_idempotency(
        self,
        *,
        broker: str,
        idempotency_key: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
    ) -> bool:
        """중복 주문 방지 키 저장."""
        try:
            with self._write_connection(operation='save_stock_order_idempotency') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stock_order_idempotency (
                        broker, idempotency_key, symbol, side, order_type, quantity, price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(broker),
                        str(idempotency_key),
                        str(symbol),
                        str(side),
                        str(order_type),
                        float(quantity or 0.0),
                        (None if price is None else float(price)),
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            log_event('trade', f"idempotency 저장 실패: {e}", exchange=self.exchange, level='ERROR')
            return False

    def claim_crypto_order_command(
        self, *, command_id: str, exchange: str, symbol: str, side: str,
        intent_type: str, quantity: float, position_key: str = "",
    ) -> Dict[str, Any]:
        """명령을 원자적으로 선점한다. 기존 명령이면 재제출 권한을 주지 않는다."""
        try:
            with self._write_connection(operation='claim_crypto_order_command', timeout=20.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO crypto_order_commands (
                        command_id, exchange, symbol, side, intent_type, quantity,
                        position_key, status, attempts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'created', 0)
                    """,
                    (str(command_id), str(exchange), str(symbol), str(side),
                     str(intent_type), float(quantity or 0.0), str(position_key or "")),
                )
                claimed = cursor.rowcount == 1
                cursor.execute(
                    """SELECT status, exchange_order_id, error_class, attempts
                       FROM crypto_order_commands WHERE command_id = ?""",
                    (str(command_id),),
                )
                row = cursor.fetchone() or ("unknown", None, None, 0)
                conn.commit()
            return {
                "claimed": claimed,
                "status": str(row[0] or "unknown"),
                "exchange_order_id": str(row[1] or ""),
                "error_class": str(row[2] or ""),
                "attempts": int(row[3] or 0),
            }
        except Exception as exc:
            log_event('trade', f"암호화폐 주문 명령 선점 실패: {exc}", exchange=self.exchange, level='ERROR')
            return {"claimed": False, "status": "ledger_error", "error": str(exc)}

    def update_crypto_order_command(
        self, command_id: str, *, status: str, exchange_order_id: str = "",
        error_class: str = "", error_message: str = "", increment_attempt: bool = False, _write_token=None,
    ) -> bool:
        payload = dict(command_id=command_id,status=status,exchange_order_id=exchange_order_id,
                       error_class=error_class,error_message=error_message,increment_attempt=increment_attempt)
        try:
            with self._write_connection(operation='update_crypto_order_command', timeout=20.0) as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn,_write_token): return True
                if not _write_token: conn.execute('BEGIN IMMEDIATE')
                previous=conn.execute('SELECT status,exchange_order_id FROM crypto_order_commands WHERE command_id=?',(str(command_id),)).fetchone()
                if previous is None: return False
                if previous[1] and exchange_order_id and str(previous[1])!=str(exchange_order_id): return False
                # Late retry of an earlier uncertain status must not erase an
                # acknowledged order or permit a second submission.
                if previous[0] in {'confirmed','filled','submitted','accepted'} and status in {'pending','submitting','ambiguous','failed','rejected','unknown'}:
                    finish_receipt(conn,_write_token)
                    return True
                conn.execute(
                    """
                    UPDATE crypto_order_commands
                    SET status = ?, exchange_order_id = COALESCE(NULLIF(?, ''), exchange_order_id),
                        error_class = ?, error_message = ?,
                        attempts = attempts + ?, updated_at = CURRENT_TIMESTAMP
                    WHERE command_id = ?
                    """,
                    (str(status), str(exchange_order_id or ""), str(error_class or ""),
                     str(error_message or "")[:1000], 1 if increment_attempt else 0,
                     str(command_id)),
                )
                finish_receipt(conn,_write_token)
                conn.commit()
            return True
        except Exception as exc:
            if _write_token: raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(exc): enqueue(self,'update_crypto_order_command',payload)
            log_event('trade', f"암호화폐 주문 명령 갱신 실패: {exc}", exchange=self.exchange, level='ERROR')
            return False

    def cleanup_old_logs(self, days: int = 90):
        """Prune diagnostic logs only; financial and risk evidence is retained."""
        try:
            cutoff_date = self._to_db_datetime(datetime.now() - timedelta(days=days))

            with self._write_connection(operation='cleanup_old_logs') as conn:
                cursor = conn.cursor()

                # 오래된 분석 로그 삭제
                cursor.execute("DELETE FROM analysis_log WHERE timestamp < ?", (cutoff_date,))

                # 오래된 최적화 로그 삭제
                cursor.execute("DELETE FROM ai_optimization WHERE timestamp < ?", (cutoff_date,))

                conn.commit()

            log_event('trade', f"{days}일 이전 로그 정리 완료", exchange=self.exchange, level='INFO')

        except Exception as e:
            log_event('trade', f"로그 정리 오류: {e}", exchange=self.exchange, level='ERROR')

    def export_data(self, export_path: str, data_type: str = "all"):
        """데이터 내보내기"""
        try:
            if data_type == "trades" or data_type == "all":
                trades_df = pd.read_sql_query("SELECT * FROM trade_log", sqlite3.connect(self.db_path))
                trades_df.to_csv(f"{export_path}/trades.csv", index=False)

            if data_type == "analysis" or data_type == "all":
                analysis_df = pd.read_sql_query("SELECT * FROM analysis_log", sqlite3.connect(self.db_path))
                analysis_df.to_csv(f"{export_path}/analysis.csv", index=False)

            if data_type == "optimization" or data_type == "all":
                optimization_df = pd.read_sql_query("SELECT * FROM ai_optimization", sqlite3.connect(self.db_path))
                optimization_df.to_csv(f"{export_path}/optimization.csv", index=False)

            log_event('trade', f"데이터 내보내기 완료: {export_path}", exchange=self.exchange, level='INFO')

        except Exception as e:
            log_event('trade', f"데이터 내보내기 오류: {e}", exchange=self.exchange, level='ERROR')

    def get_database_info(self) -> Dict:
        """데이터베이스 정보 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 테이블별 레코드 수 조회
                tables = ['trade_log', 'analysis_log', 'ai_optimization', 'coin_evaluation', 'risk_log', 'performance_stats']
                table_counts = {}

                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    table_counts[table] = count

                # 데이터베이스 크기 조회
                cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                db_size = cursor.fetchone()[0]

                return {
                    'database_path': self.db_path,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'table_counts': table_counts,
                    'last_updated': datetime.now()
                }

        except Exception as e:
            log_event('trade', f"데이터베이스 정보 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return {}

    def save_ai_decision(
        self, symbol: str, decision_type: str, decision_data: dict,
        user_feedback: Optional[str] = None, *, exchange: Optional[str] = None,
        _write_token: Optional[str] = None,
    ):
        """AI 결정 내역을 데이터베이스에 저장"""
        try:
            with self._write_connection(operation='save_ai_decision') as conn:
                from trading.recorder_write_queue import begin_receipt, finish_receipt
                if begin_receipt(conn, _write_token):
                    return True
                cursor = conn.cursor()
                from trading.decision_storage import save
                event_meta = save(conn, symbol, decision_type, decision_data, user_feedback, exchange)
                finish_receipt(conn, _write_token)
                conn.commit()

                if event_meta.get('storage_status') == 'quarantined':
                    log_event('system', 'AI 판단 기록의 기관·모드 근거 충돌: 원본 별도 보존, 학습 제외. 설정 → 업데이트 → 유지관리 · 저장소에서 확인하세요.',
                              exchange=exchange, level='WARNING')
                    return event_meta

                event_exchange = str(
                    exchange or decision_data.get('exchange') or self.exchange or ''
                ).strip().lower()
                log_event(
                    'trade', f"[{symbol}] AI 결정 내역 저장 완료: {decision_type}",
                    exchange=event_exchange, level='DEBUG',
                )

        except Exception as e:
            if _write_token:
                raise
            from trading.recorder_write_queue import is_busy, enqueue
            if is_busy(e):
                try:
                    enqueue(self, 'save_ai_decision', dict(symbol=symbol, decision_type=decision_type,
                        decision_data=decision_data, user_feedback=user_feedback, exchange=exchange))
                except Exception as queue_error:
                    log_event('trade', f'AI 판단 재처리 근거 저장 실패: {type(queue_error).__name__}', exchange=exchange or self.exchange, level='ERROR')
            event_exchange = str(exchange or self.exchange or '').strip().lower()
            log_event('trade', f"AI 결정 내역 저장 오류: {e}", exchange=event_exchange, level='ERROR')
        finally:
            if not _write_token:
                from trading.recorder_write_queue import schedule
                schedule(self)

    def get_ai_decisions(self, symbol: Optional[str] = None, limit: int = 50,
                         *, exchange: Optional[str] = None, execution_mode: Optional[str] = None) -> List[dict]:
        """AI 결정 내역 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                conditions, params = [], []
                for key, value in (('symbol',symbol),('exchange',exchange),('execution_mode',execution_mode)):
                    if value:
                        conditions.append(f'{key}=?'); params.append(value)
                where = ' WHERE '+' AND '.join(conditions) if conditions else ''
                ordering = 'event_time' if exchange else 'created_at'
                cursor.execute(f"""SELECT id,symbol,decision_type,decision_json,user_feedback,created_at,
                    exchange,execution_mode,event_time,strategy_version_id,reason_code,repeat_count,last_event_time,
                    contract_version,asset_class,instrument_type,decision_status,actual_order,order_id,ledger_id,event_kind
                    FROM ai_decisions {where} ORDER BY {ordering} DESC,id DESC LIMIT ?""", [*params,max(1,min(int(limit),1000))])

                results = []
                for row in cursor.fetchall():
                    try:
                        decision_data = json.loads(row[3]) if row[3] else {}
                        parse_status = 'ok'
                    except (ValueError,TypeError):
                        decision_data = {}; parse_status = 'invalid_original_retained'
                    results.append({
                        'id': row[0],
                        'symbol': row[1],
                        'decision_type': row[2],
                        'decision_data': decision_data,
                        'user_feedback': row[4],
                        'created_at': row[5],
                        'exchange': row[6], 'execution_mode': row[7], 'event_time': row[8],
                        'strategy_version_id': row[9], 'reason_code': row[10],
                        'repeat_count': row[11], 'last_event_time': row[12],
                        'contract_version': row[13], 'asset_class': row[14],
                        'instrument_type': row[15], 'decision_status': row[16],
                        'actual_order': None if row[17] is None else bool(row[17]),
                        'order_id': row[18], 'ledger_id': row[19], 'event_kind': row[20],
                        'parse_status': parse_status,
                    })

                return results

        except Exception as e:
            log_event('trade', f"AI 결정 내역 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return []

    def record_coin_change(self, old_coins: List[str], new_coins: List[str], reason: str = 'dynamic_replacement'):
        """코인 교체 기록 저장"""
        try:
            with self._write_connection(operation='record_coin_change') as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS coin_change_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        old_coins TEXT,
                        new_coins TEXT,
                        change_reason TEXT
                    )
                ''')
                cursor.execute('''
                    INSERT INTO coin_change_log (old_coins, new_coins, change_reason)
                    VALUES (?, ?, ?)
                ''', (','.join(old_coins or []), ','.join(new_coins or []), reason))
                conn.commit()
        except Exception as e:
            log_event('trade', f"코인 교체 기록 저장 오류: {e}", exchange=self.exchange, level='ERROR')

    def save_coin_selection(
        self,
        selected_coins: List[Dict],
        num_alt: int,
        num_major: int,
        market_regime: str,
        selection_reason: str = "initial_selection",
        adjustment_factor: float = 1.0,
        *,
        exchange: Optional[str] = None,
        selection_status: str = "scored",
    ) -> int:
        """🔥 코인 선택 데이터를 데이터베이스에 저장"""
        try:
            exchange_key = str(exchange or self.exchange or 'binance').strip().lower()
            status_key = str(selection_status or 'scored').strip().lower()
            with self._write_connection(operation='save_coin_selection') as conn:
                cursor = conn.cursor()

                # 1. 코인 선택 세션 정보 저장
                cursor.execute("""
                    INSERT INTO coin_selection_sessions
                    (timestamp, exchange, market_regime, total_coins, major_coins_count, alt_coins_count,
                    selection_reason, selection_status, adjustment_factor)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self._to_db_datetime(datetime.now()),
                    exchange_key,
                    market_regime,
                    len(selected_coins),
                    num_major,
                    num_alt,
                    selection_reason,
                    status_key,
                    adjustment_factor
                ))

                session_id = int(cursor.lastrowid or -1)

                # 2. 각 선택된 코인의 상세 정보 저장
                for coin in selected_coins:
                    cursor.execute("""
                        INSERT INTO selected_coins
                        (session_id, exchange, symbol, is_major, selection_status, selection_reason,
                        overall_score, technical_score,
                        volatility_score, volume_score, trend_score, risk_score,
                        volume, price_change_percent, orderbook_depth)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        session_id,
                        exchange_key,
                        coin.get('symbol', ''),
                        coin.get('is_major', False),
                        str(coin.get('selection_status') or status_key),
                        str(coin.get('selection_reason') or selection_reason),
                        coin.get('overall_score'),
                        coin.get('technical_score'),
                        coin.get('volatility_score'),
                        coin.get('volume_score'),
                        coin.get('trend_score'),
                        coin.get('risk_score'),
                        coin.get('volume', 0.0),
                        coin.get('priceChangePercent', 0.0),
                        coin.get('orderbook_depth', 0)
                    ))

                conn.commit()
                log_event('trade', f"✅ 코인 선택 데이터 저장 완료: 세션 ID {session_id}, 코인 {len(selected_coins)}개", exchange=exchange_key, level='INFO')
                return session_id

        except Exception as e:
            exchange_key = str(exchange or self.exchange or 'binance').strip().lower()
            log_event('trade', f"❌ 코인 선택 데이터 저장 오류: {e}", exchange=exchange_key, level='ERROR')
            import traceback
            log_event('trade', traceback.format_exc(), exchange=exchange_key, level='ERROR')
            return -1

    def migrate_database_schema(self):
        """기존 거래를 보존하면서 ``trade_log`` 스키마를 증분 보강한다.

        이 메서드는 앱 시작 때마다 호출된다. 따라서 테이블을 삭제·재생성하거나
        청산된 행만 복원하면 미청산 거래와 거래소/주문 식별자가 유실된다.
        필요한 컬럼과 인덱스만 멱등적으로 추가하고, 행 수가 바뀌지 않았는지
        검증한다.
        """
        try:
            with self._write_connection(operation='migrate_database_schema') as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_log'")
                if not cursor.fetchone():
                    log_event('trade', "trade_log 테이블이 없습니다. 새로 생성합니다.", exchange=self.exchange, level='INFO')
                    self.init_database()
                    return

                cursor.execute("SELECT COUNT(*) FROM trade_log")
                rows_before = int((cursor.fetchone() or [0])[0] or 0)

                required_columns = {
                    'exchange': 'TEXT',
                    'order_id': 'TEXT',
                    'exit_order_id': 'TEXT',
                    'model_version': 'TEXT',
                    'strategy_variant': 'TEXT',
                    'fee_asset': 'TEXT',
                    'fee_source': 'TEXT',
                    'position_owner': "TEXT NOT NULL DEFAULT 'legacy_unknown'",
                    'execution_mode': "TEXT NOT NULL DEFAULT 'live'",
                    'spot_baseline_quantity': 'REAL NOT NULL DEFAULT 0.0',
                    'gross_pnl': 'REAL',
                    'net_pnl': 'REAL',
                    'entry_fee': 'REAL',
                    'exit_fee': 'REAL',
                    'entry_fee_asset': 'TEXT',
                    'exit_fee_asset': 'TEXT',
                    'settlement_currency': 'TEXT',
                    'pnl_source': "TEXT NOT NULL DEFAULT 'legacy_unverified'",
                    'reconciliation_status': "TEXT NOT NULL DEFAULT 'legacy_unverified'",
                }
                existing_columns = set(self._get_table_columns(cursor, 'trade_log'))
                added_columns = []
                for column, column_type in required_columns.items():
                    if column not in existing_columns:
                        cursor.execute(
                            f"ALTER TABLE trade_log ADD COLUMN {column} {column_type}"
                        )
                        added_columns.append(column)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_symbol_entry
                    ON trade_log(symbol, entry_time)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_exchange_exit_time
                    ON trade_log(exchange, exit_time)
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_exit_time ON trade_log(exit_time DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_exit_order_owner ON trade_log(LOWER(exchange), exit_order_id, UPPER(symbol))")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trade_exchange_normalized_exit_time "
                    "ON trade_log(LOWER(REPLACE(REPLACE(REPLACE(COALESCE(exchange, ''), '_', ''), '-', ''), ' ', '')), exit_time DESC)"
                )

                # exchange_trade_stats fee 컬럼/백필/검증
                self._run_exchange_trade_stats_fee_migration(conn, cursor)

                conn.commit()
                cursor.execute("SELECT COUNT(*) FROM trade_log")
                rows_after = int((cursor.fetchone() or [0])[0] or 0)
                final_columns = set(self._get_table_columns(cursor, 'trade_log'))
                missing_columns = sorted(set(required_columns) - final_columns)
                if rows_after != rows_before:
                    raise RuntimeError(
                        f"trade_log 행 수 변경 감지: before={rows_before}, after={rows_after}"
                    )
                if missing_columns:
                    raise RuntimeError(
                        f"trade_log 필수 컬럼 보강 실패: {', '.join(missing_columns)}"
                    )
                log_event(
                    'trade',
                    "✅ 데이터베이스 증분 마이그레이션 완료 "
                    f"(rows={rows_after}, added={added_columns or ['none']})",
                    exchange=self.exchange,
                    level='INFO',
                )

        except Exception as e:
            log_event('trade', f"데이터베이스 스키마 마이그레이션 오류: {e}", exchange=self.exchange, level='ERROR')
            raise

    def update_trade_on_exit(self, symbol: str, entry_time: datetime, *,
                           exit_price: float, pnl: float, pnl_percent: float,
                           fees: float, slippage: float, reason: str,
                           side: Optional[str] = None,
                           exchange: Optional[str] = None,
                           entry_order_id: Optional[str] = None,
                           exit_order_id: Optional[str] = None):
        try:
            log_event('trade', f"🔍 [DEBUG] update_trade_log 호출: symbol={symbol}, exit_price={exit_price}, entry_time={entry_time}, pnl_percent={pnl_percent}, pnl={pnl}, reason={reason}", exchange=self.exchange, level='INFO')

            with self._write_connection(operation='update_trade_on_exit') as conn:
                cursor = conn.cursor()

                # 거래소·주문 ID·방향까지 사용해 동일 심볼의 다른 거래소/재진입을
                # 잘못 청산하지 않는다. 패치 전 레거시 행은 주문 ID가 없을 수 있어
                # 동일 거래소+심볼+방향으로 한 번만 폴백한다.
                params: List[Any] = [symbol]
                where = ["symbol = ?", "exit_time IS NULL"]
                if exchange:
                    where.append("LOWER(COALESCE(exchange, '')) = ?")
                    params.append(str(exchange).lower())
                if side:
                    where.append("UPPER(COALESCE(side, '')) = ?")
                    params.append(str(side).upper())
                if entry_order_id:
                    where.append("order_id = ?")
                    params.append(str(entry_order_id))
                cursor.execute(
                    f"""
                    SELECT id, entry_price, quantity, side FROM trade_log
                    WHERE {' AND '.join(where)}
                    ORDER BY entry_time DESC LIMIT 1
                    """,
                    tuple(params),
                )

                trade_data = cursor.fetchone()
                if trade_data is None and entry_order_id:
                    fallback_params: List[Any] = [symbol]
                    fallback_where = ["symbol = ?", "exit_time IS NULL"]
                    if exchange:
                        fallback_where.append("LOWER(COALESCE(exchange, '')) = ?")
                        fallback_params.append(str(exchange).lower())
                    if side:
                        fallback_where.append("UPPER(COALESCE(side, '')) = ?")
                        fallback_params.append(str(side).upper())
                    cursor.execute(
                        f"""
                        SELECT id, entry_price, quantity, side FROM trade_log
                        WHERE {' AND '.join(fallback_where)}
                        ORDER BY entry_time DESC LIMIT 1
                        """,
                        tuple(fallback_params),
                    )
                    trade_data = cursor.fetchone()
                if trade_data:
                    trade_id, entry_price, quantity, side = trade_data
                    log_event('trade', f"🔍 [DEBUG] 찾은 거래: id={trade_id}, entry_price={entry_price}, quantity={quantity}, side={side}", exchange=self.exchange, level='INFO')

                    # 종료 정보 업데이트
                    cursor.execute("""
                        UPDATE trade_log
                        SET exit_price = ?, exit_time = ?, pnl = ?, pnl_percent = ?, reason = ?,
                            fees = ?, slippage = ?, exit_order_id = ?
                        WHERE id = ?
                    """, (
                        exit_price, self._to_db_datetime(datetime.now()), pnl, pnl_percent, reason,
                        fees, slippage, str(exit_order_id) if exit_order_id else None,
                        trade_id,
                    ))

                    conn.commit()

                    # 업데이트 후 확인
                    cursor.execute("SELECT exit_price, exit_time, pnl, pnl_percent, reason FROM trade_log WHERE id = ?", (trade_id,))
                    updated_data = cursor.fetchone()
                    log_event('trade', f"🔍 [DEBUG] 업데이트 후 데이터: {updated_data}", exchange=self.exchange, level='INFO')

                    log_event('trade', f"✅ {symbol} 거래 로그 업데이트 완료: 종료가 {exit_price}, PnL {pnl_percent:.2f}%", exchange=self.exchange, level='INFO')
                    return True
                else:
                    log_event('trade', f"⚠️ {symbol} 미종료 거래를 찾을 수 없음", exchange=self.exchange, level='WARNING')

                    # 디버깅: 해당 심볼의 모든 거래 확인
                    cursor.execute("SELECT id, symbol, entry_time, exit_time FROM trade_log WHERE symbol = ? ORDER BY entry_time DESC LIMIT 3", (symbol,))
                    all_trades = cursor.fetchall()
                    log_event('trade', f"🔍 [DEBUG] {symbol} 최근 거래들: {all_trades}", exchange=self.exchange, level='INFO')

                    return False
        except Exception as e:
            import traceback
            log_event('trade', f"❌ {symbol} 거래 로그 업데이트 실패: {e}", exchange=self.exchange, level='ERROR')
            log_event('trade', f"❌ 상세 오류: {traceback.format_exc()}", exchange=self.exchange, level='ERROR')
            # 폴백 시도
            try:
                with self._write_connection(operation='update_trade_on_exit') as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE trade_log
                        SET exit_price=?, exit_time=?, pnl=?, pnl_percent=?, fees=?, slippage=?, reason=?
                        WHERE id=?
                        """,
                        (
                            exit_price,
                            self._to_db_datetime(datetime.now()),
                            pnl,
                            pnl_percent,
                            fees,
                            slippage,
                            reason,
                            trade_id,
                        )
                    )
                    if cursor.rowcount > 0:
                        conn.commit()
                        log_event('trade', f"✅ 폴백 업데이트 성공: {symbol} (id={trade_id}) - PnL: {pnl:.2f}", exchange=self.exchange, level='INFO')
                        return True
                    # 추가 디버깅: 최근 3개 트레이스 출력
                    try:
                        cursor.execute(
                            "SELECT id, symbol, side, entry_time, exit_time FROM trade_log WHERE symbol = ? ORDER BY entry_time DESC LIMIT 3",
                            (symbol,)
                        )
                        recent = cursor.fetchall()
                        log_event('trade', f"🔍 [DEBUG] 최근 거래(상위 3): {recent}", exchange=self.exchange, level='INFO')
                    except Exception:
                        pass
            except Exception as fe:
                log_event('trade', f"폴백 업데이트 시도 실패: {fe}", exchange=self.exchange, level='ERROR')
            return False

        try:
            conn.commit()
            log_event('trade', f"✅ 거래 청산 업데이트 완료: {symbol} - PnL: {pnl:.2f}", exchange=self.exchange, level='INFO')
            return True
        except Exception as e:
            log_event('trade', f"거래 청산 업데이트 오류: {e}", exchange=self.exchange, level='ERROR')
            return False

    def get_recent_trades(
        self,
        coin: str = "",
        exchange: Optional[str] = None,
        days: int = 30,
        *,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """최근 청산 거래를 조회한다.

        ``symbol``이 전달되면 ``H/KRW``·``AVAX/USDT:USDT`` 같은 거래소 원본
        심볼을 정확히 조회한다. ``coin``은 기존 USDT 호출과의 호환용이며,
        둘 다 비어 있으면 해당 거래소의 모든 결제통화 거래를 반환한다.
        """
        try:
            try:
                safe_days = max(1, min(int(days), 3650))
            except (TypeError, ValueError):
                safe_days = 30

            query = (
                "SELECT symbol, COALESCE(exchange, ''), entry_price, exit_price, quantity, leverage, "
                "pnl, pnl_percent, entry_time, exit_time, COALESCE(reason, ''), "
                "COALESCE(fees, 0), COALESCE(slippage, 0), "
                "execution_mode, reconciliation_status, pnl_source, net_pnl "
                "FROM trade_log "
                f"WHERE exit_time > datetime('now', '-{safe_days} days') "
                "AND LOWER(COALESCE(reason, '')) != 'binance_import' "
                "AND LOWER(COALESCE(execution_mode, '')) IN ('live','live_api','optimized','manual') "
            )
            params: List[Any] = []
            normalized_symbol = str(symbol or "").strip()
            normalized_coin = str(coin or "").strip()
            if normalized_symbol:
                query += "AND UPPER(symbol) = UPPER(?) "
                params.append(normalized_symbol)
            elif normalized_coin:
                query += "AND UPPER(symbol) LIKE UPPER(?) "
                params.append(f"{normalized_coin}%USDT%")
            if exchange:
                query += "AND LOWER(COALESCE(exchange, '')) = LOWER(?) "
                params.append(exchange)
            # Consumers consistently use ``rows[-N:]`` as the newest window.
            query += "ORDER BY exit_time ASC"

            rows = self.execute_query(query, tuple(params))
            results: List[Dict[str, Any]] = []
            for r in rows:
                results.append({
                    'symbol': r[0],
                    'exchange': r[1] or None,
                    'entry_price': r[2],
                    'exit_price': r[3],
                    'quantity': r[4],
                    'leverage': r[5],
                    'pnl': r[6],
                    'pnl_percent': r[7],
                    'entry_time': r[8],
                    'exit_time': r[9],
                    'reason': r[10],
                    'fees': r[11],
                    'slippage': r[12],
                    **performance_evidence(dict(zip(
                        ('execution_mode', 'reconciliation_status', 'pnl_source', 'net_pnl'), r[13:17]
                    ))),
                })
            # Historical repair writes exchange UTC timestamps while legacy
            # rows may contain local/offset timestamps. Lexical SQL order is
            # not chronological and must not select the wrong newest sample.
            results.sort(key=lambda row: self._ledger_time_epoch(row['exit_time']) or 0)
            return results
        except Exception as e:
            log_event('trade', f"최근 거래 이력 조회 오류: {e}", exchange=self.exchange, level='ERROR')
            return []

    def flush_to_db(self, timeout: int = 10) -> bool:
        """DB flush 강제 보장 (타임아웃 처리)"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 현재 대기 중인 모든 트랜잭션 커밋
                with sqlite3.connect(self.db_path, timeout=20.0) as conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=FULL")  # 강제 동기화
                    conn.commit()
                return True
            except Exception as e:
                time.sleep(0.5)

        raise TimeoutError(f"DB flush timeout after {timeout} seconds")
