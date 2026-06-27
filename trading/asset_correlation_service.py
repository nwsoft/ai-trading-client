#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자산 통합 상관관계 분석 및 리밸런싱 제안 서비스.

목적:
- 보유 자산(코인/주식/ETF)의 수익률 데이터를 받아 자산 간 상관관계 행렬을 계산한다.
- 고상관 자산 쌍을 탐지해 집중 리스크를 경고한다.
- 상관관계 기반으로 포트폴리오 리밸런싱 방향을 제안한다.

이 모듈은 순수 Python (numpy 없이) 으로 구현되어
외부 패키지 없이 동작한다.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _pearson(x: List[float], y: List[float]) -> float:
    """피어슨 상관계수 계산. 길이가 다르면 최솟값 길이로 자른다."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x = x[:n]
    y = y[:n]
    mx = _mean(x)
    my = _mean(y)
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    denom = math.sqrt(
        sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y)
    )
    if denom == 0.0:
        return 0.0
    return max(-1.0, min(1.0, num / denom))


def _returns_from_prices(prices: List[float]) -> List[float]:
    """가격 리스트로부터 일별 로그 수익률을 계산한다."""
    if len(prices) < 2:
        return []
    result = []
    for i in range(1, len(prices)):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 > 0 and p1 > 0:
            result.append(math.log(p1 / p0))
        else:
            result.append(0.0)
    return result


class AssetCorrelationService:
    """자산 간 상관관계를 계산하고 리밸런싱 방향을 제안한다.

    Parameters
    ----------
    high_corr_threshold:
        이 값 이상이면 "고상관" 경고를 발행한다 (기본 0.70).
    low_corr_threshold:
        이 값 이하이면 "저상관 = 분산 유리" 로 판정한다 (기본 0.30).
    """

    def __init__(
        self,
        high_corr_threshold: float = 0.70,
        low_corr_threshold: float = 0.30,
    ) -> None:
        self.high_corr_threshold = float(high_corr_threshold)
        self.low_corr_threshold = float(low_corr_threshold)

    # ──────────────────────────────────────────────────────────────
    # 공개 메서드
    # ──────────────────────────────────────────────────────────────

    def compute_correlation_matrix(
        self,
        price_series: Dict[str, List[float]],
    ) -> Dict[str, Dict[str, float]]:
        """가격 시계열 딕셔너리로 전체 상관관계 행렬을 반환한다.

        Parameters
        ----------
        price_series:
            { 'BTC': [50000, 51000, ...], 'ETH': [...], ... }

        Returns
        -------
        { 'BTC': { 'BTC': 1.0, 'ETH': 0.83, ... }, ... }
        """
        symbols = list(price_series.keys())
        returns: Dict[str, List[float]] = {
            s: _returns_from_prices(price_series[s]) for s in symbols
        }
        matrix: Dict[str, Dict[str, float]] = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                elif s2 in matrix and s1 in matrix[s2]:
                    matrix[s1][s2] = matrix[s2][s1]
                else:
                    matrix[s1][s2] = _pearson(returns[s1], returns[s2])
        return matrix

    def find_high_correlation_pairs(
        self,
        matrix: Dict[str, Dict[str, float]],
    ) -> List[Dict[str, Any]]:
        """고상관 자산 쌍 목록을 반환한다 (threshold 이상).

        Returns
        -------
        [
          { 'symbol_a': 'BTC', 'symbol_b': 'ETH', 'correlation': 0.85,
            'risk': 'high', 'message': '...' },
          ...
        ]
        """
        pairs = []
        symbols = list(matrix.keys())
        seen: set = set()
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                key = (s1, s2)
                if key in seen:
                    continue
                seen.add(key)
                corr = float(matrix.get(s1, {}).get(s2, 0.0))
                if abs(corr) >= self.high_corr_threshold:
                    pairs.append({
                        'symbol_a': s1,
                        'symbol_b': s2,
                        'correlation': round(corr, 4),
                        'risk': 'high',
                        'message': (
                            f'{s1}과 {s2}의 상관관계({corr:.2f})가 높습니다. '
                            '동시 보유 시 분산 효과가 줄어듭니다.'
                        ),
                    })
        pairs.sort(key=lambda p: abs(p['correlation']), reverse=True)
        return pairs

    def suggest_rebalancing(
        self,
        holdings: List[Dict[str, Any]],
        matrix: Dict[str, Dict[str, float]],
        target_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """상관관계 분석 기반 리밸런싱 방향을 제안한다.

        Parameters
        ----------
        holdings:
            현재 보유 자산 리스트.
            [ { 'symbol': 'BTC', 'weight': 0.40, 'asset_class': 'crypto' }, ... ]
        matrix:
            compute_correlation_matrix() 결과.
        target_count:
            유지할 권장 자산 수. None 이면 현재 수를 기준으로 판단.

        Returns
        -------
        {
          'reduce': [{ 'symbol': ..., 'reason': ... }, ...],   # 비중 축소 권장
          'keep':   [{ 'symbol': ..., 'reason': ... }, ...],   # 유지
          'diversify': [{ 'message': ... }],                   # 분산 필요 알림
          'summary': '...',
        }
        """
        if not holdings:
            return {'reduce': [], 'keep': [], 'diversify': [], 'summary': '보유 자산 없음'}

        symbols = [str(h.get('symbol') or '').strip().upper() for h in holdings]
        symbols = [s for s in symbols if s]

        # 각 자산의 평균 상관관계 계산
        avg_corr: Dict[str, float] = {}
        for s in symbols:
            others = [o for o in symbols if o != s]
            if not others:
                avg_corr[s] = 0.0
                continue
            corrs = [abs(float(matrix.get(s, {}).get(o, 0.0))) for o in others]
            avg_corr[s] = sum(corrs) / len(corrs)

        high_pairs = self.find_high_correlation_pairs(matrix)

        # 고상관 쌍에 포함된 심볼 (비중 축소 후보)
        high_corr_symbols: set = set()
        for pair in high_pairs:
            high_corr_symbols.add(pair['symbol_a'])
            high_corr_symbols.add(pair['symbol_b'])

        reduce_list = []
        keep_list = []
        for s in symbols:
            ac = avg_corr.get(s, 0.0)
            if s in high_corr_symbols and ac >= self.high_corr_threshold:
                reduce_list.append({
                    'symbol': s,
                    'avg_correlation': round(ac, 4),
                    'reason': f'평균 상관관계 {ac:.2f} — 고상관 자산과 중복 보유',
                })
            else:
                keep_list.append({
                    'symbol': s,
                    'avg_correlation': round(ac, 4),
                    'reason': '상관관계 적절',
                })

        diversify = []
        if len(high_pairs) > 0:
            diversify.append({
                'message': (
                    f'고상관 자산 쌍 {len(high_pairs)}개 탐지. '
                    '상관관계가 낮은 자산 추가를 권장합니다.'
                ),
            })

        n_reduce = len(reduce_list)
        n_keep = len(keep_list)
        if n_reduce == 0:
            summary = f'포트폴리오 분산 양호. {n_keep}개 자산 유지 권장.'
        else:
            summary = (
                f'{n_reduce}개 자산 비중 축소 권장 '
                f'(고상관), {n_keep}개 유지.'
            )

        return {
            'reduce': reduce_list,
            'keep': keep_list,
            'diversify': diversify,
            'summary': summary,
        }

    def avg_correlation_of(
        self,
        symbol: str,
        matrix: Dict[str, Dict[str, float]],
    ) -> float:
        """특정 자산의 포트폴리오 내 평균 상관관계를 반환한다."""
        row = matrix.get(symbol, {})
        others = [abs(v) for k, v in row.items() if k != symbol]
        if not others:
            return 0.0
        return sum(others) / len(others)
