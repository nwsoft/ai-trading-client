#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sizing outcomes CSV 요약 유틸리티
 - 입력: analytics/sizing_outcomes.csv
 - 출력: 전체/거래소별 요약 통계(dict) 또는 콘솔 출력
"""

from __future__ import annotations
import csv
import os
from statistics import mean, median
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple


def _safe_float(v) -> float:
    try:
        if isinstance(v, str) and v.endswith('%'):
            v = v[:-1]
        return float(v)
    except Exception:
        return 0.0


def summarize_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """CSV 행 리스트로부터 요약 통계를 계산"""
    if not rows:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_pnl': 0.0,
            'median_pnl': 0.0,
            'avg_size': 0.0,
        }

    pnls = [_safe_float(r.get('pnl_percent')) for r in rows]
    wins = [p for p in pnls if p > 0]
    sizes = [_safe_float(r.get('position_size')) for r in rows]

    total = len(rows)
    win_rate = (len(wins) / total) * 100 if total else 0.0
    avg_pnl = mean(pnls) if pnls else 0.0
    med_pnl = median(pnls) if pnls else 0.0
    avg_size = mean(sizes) if sizes else 0.0

    return {
        'total_trades': total,
        'win_rate': round(win_rate, 2),
        'avg_pnl': round(avg_pnl, 6),
        'median_pnl': round(med_pnl, 6),
        'avg_size': round(avg_size, 8),
    }


def summarize_csv(csv_path: str, limit: int | None = None, days: int | None = None) -> Dict[str, Any]:
    """CSV 파일의 전체/거래소별 요약 생성"""
    if not os.path.exists(csv_path):
        return {'error': f'file not found: {csv_path}'}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 기간 필터(최근 N일)
    if isinstance(days, int) and days > 0:
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            filtered = []
            for r in rows:
                ts = r.get('timestamp')
                if not ts:
                    continue
                dt = None
                try:
                    # Python 3.11+: fromisoformat supports 'Z'? If not, replace
                    if ts.endswith('Z'):
                        ts = ts.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    try:
                        # Fallback: naive parse
                        dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
                    except Exception:
                        dt = None
                if dt and dt >= since:
                    filtered.append(r)
            rows = filtered
        except Exception:
            # 기간 필터 실패 시 원본 사용
            pass
    # 최근 N건만 요약(옵션)
    if isinstance(limit, int) and limit > 0:
        rows = rows[-limit:]

    summary = summarize_rows(rows)

    # 거래소별 요약
    by_exchange: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        ex = r.get('exchange') or 'unknown'
        by_exchange.setdefault(ex, []).append(r)

    exchange_summary = {ex: summarize_rows(rlist) for ex, rlist in by_exchange.items()}

    return {
        'overall': summary,
        'by_exchange': exchange_summary,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Summarize sizing_outcomes.csv')
    parser.add_argument('--path', default=None, help='CSV 파일 경로 (기본: Documents/NoahAI/analytics/sizing_outcomes.csv)')
    parser.add_argument('--limit', type=int, default=None, help='최근 N건만 요약 (옵션)')
    parser.add_argument('--days', type=int, default=None, help='최근 N일 데이터만 요약 (옵션)')
    args = parser.parse_args()

    if args.path:
        csv_path = args.path
    else:
        # 기본 경로 추정
        try:
            from noahai_client.path_utils import get_app_data_dir
            csv_path = os.path.join(get_app_data_dir(), 'analytics', 'sizing_outcomes.csv')
        except Exception:
            csv_path = os.path.join(os.path.expanduser('~'), 'Documents', 'NoahAI', 'analytics', 'sizing_outcomes.csv')

    result = summarize_csv(csv_path, limit=args.limit, days=args.days)
    if 'error' in result:
        print(result['error'])
        return 1

    print('=== Sizing Outcomes Summary ===')
    overall = result['overall']
    print(f"Total: {overall['total_trades']} | WinRate: {overall['win_rate']}% | AvgPnL: {overall['avg_pnl']}% | MedianPnL: {overall['median_pnl']}% | AvgSize: {overall['avg_size']}")
    print('\n--- By Exchange ---')
    for ex, s in result['by_exchange'].items():
        print(f"{ex}: Total={s['total_trades']} WinRate={s['win_rate']}% AvgPnL={s['avg_pnl']}% MedianPnL={s['median_pnl']}% AvgSize={s['avg_size']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
