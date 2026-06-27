#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환경 설정에 저장된 Binance API 키를 이용해 최근 거래 내역을 조회하는 테스트 스크립트.
데이터베이스에 기록된 심볼/포지션/선정 코인을 기반으로 필요한 심볼만 순회합니다.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

sys.path.append(str(Path(__file__).resolve().parents[1]))

from api.binance_client import BinanceClient, BinanceConfig
from path_utils import get_config_dir, set_current_user_account, get_db_file_path


def _ensure_default_symbols() -> Set[str]:
    """기본 테스트용 심볼 몇 개를 반환"""
    return {"BTCUSDT", "ETHUSDT", "XRPUSDT", "ADAUSDT"}


def get_recent_symbols_from_db(limit: int = 30) -> Set[str]:
    """trade_log와 selected_coins 테이블에서 최근 심볼을 모아서 반환"""
    symbols: Set[str] = set()
    db_path = Path(get_db_file_path())
    if not db_path.exists():
        return _ensure_default_symbols()

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 최근 거래된 심볼
            cur.execute(
                """
                SELECT symbol FROM trade_log
                WHERE symbol IS NOT NULL AND symbol != ''
                ORDER BY entry_time DESC
                LIMIT ?
                """,
                (limit,),
            )
            symbols.update(row["symbol"].upper() for row in cur.fetchall())

            # 최근 선정된 코인
            cur.execute(
                """
                SELECT symbol FROM selected_coins
                WHERE symbol IS NOT NULL AND symbol != ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            symbols.update(row["symbol"].upper() for row in cur.fetchall())
    except Exception as db_err:
        print(f"[WARN] DB에서 심볼을 가져오는 중 오류: {db_err}")

    if not symbols:
        symbols = _ensure_default_symbols()
    return symbols


def load_settings():
    settings_path = Path(get_config_dir()) / "settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as f:
        return json.load(f), settings_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance 거래 내역 조회 테스트 스크립트")
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="조회 기간(일). 기본 14일",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="심볼별 최대 조회 건수 (최대 1000)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="각 심볼의 원본 응답을 모두 출력",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    set_current_user_account("nwsoft")  # 개발 환경 기본 계정
    settings, settings_path = load_settings()
    api_key = settings.get("binance_api_key", "")
    secret_key = settings.get("binance_secret_key", "")

    if not api_key or not secret_key:
        print(f"[ERROR] Binance API 키가 설정되어 있지 않습니다. 경로: {settings_path}")
        return

    config = BinanceConfig(
        api_key=api_key,
        secret_key=secret_key,
        testnet=settings.get("binance_testnet", False),
        timeout=settings.get("binance_timeout", 30),
        recv_window=settings.get("binance_recv_window", 5000),
    )

    client = BinanceClient(config)
    symbols = sorted(get_recent_symbols_from_db())
    if not symbols:
        print("[WARN] 조회할 심볼이 없어 기본 심볼로 대체합니다.")
        symbols = sorted(_ensure_default_symbols())

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=args.days)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    print(f"[INFO] 조회 기간: {start_time} ~ {end_time} (UTC)")
    print(f"[INFO] 심볼 수: {len(symbols)}, 심볼 목록: {', '.join(symbols)}")

    total_trades = 0
    empty_symbols = []
    for symbol in symbols:
        try:
            trades = client.client.futures_account_trades(
                symbol=symbol,
                startTime=start_ms,
                endTime=end_ms,
                limit=args.limit,
            )
            total_trades += len(trades)
            if trades:
                print(f"[INFO] {symbol} → {len(trades)}건 (sample: {trades[0]})")
                if args.verbose:
                    for trade in trades:
                        print(f"  {trade}")
            else:
                empty_symbols.append(symbol)
                print(f"[INFO] {symbol} → 0건 (주어진 기간 내 체결 없음)")
        except Exception as e:
            print(f"[ERROR] {symbol} 조회 중 오류: {e}")

    if empty_symbols:
        print(f"[INFO] 조회 기간 내 체결 내역이 없던 심볼: {', '.join(empty_symbols)}")
    print(f"[INFO] 총 {total_trades}건의 거래 내역을 조회했습니다. (심볼 수: {len(symbols)})")


if __name__ == "__main__":
    main()
