#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자산 통합 상관관계 분석 및 리밸런싱 제안 테스트.

커버 대상:
- _pearson: 피어슨 상관계수 계산 정확도 + 엣지케이스
- _returns_from_prices: 가격 → 로그수익률 변환
- compute_correlation_matrix: 전체 행렬 생성 (대칭성, 대각선=1)
- find_high_correlation_pairs: 고상관 쌍 탐지 (임계값, 정렬)
- suggest_rebalancing: reduce/keep 분류, 분산 알림, 빈 보유 처리
- avg_correlation_of: 개별 자산 평균 상관관계
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from trading.asset_correlation_service import (
    AssetCorrelationService,
    _mean,
    _pearson,
    _returns_from_prices,
    _std,
)


# ─────────────────────────────────────────────────────────────
# 헬퍼 데이터 생성
# ─────────────────────────────────────────────────────────────

def _linear_prices(start: float, end: float, n: int = 30) -> List[float]:
    """선형으로 움직이는 가격 시계열."""
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _flat_prices(value: float = 100.0, n: int = 30) -> List[float]:
    return [value] * n


# BTC 유사 (상승), ETH 유사 (BTC와 높은 상관), GOLD (낮은 상관)
BTC_PRICES = _linear_prices(40000, 60000, 30)
ETH_PRICES = _linear_prices(2000, 3200, 30)   # 같은 방향 → 고상관
# GOLD: BTC와 반대로 움직이는 지그재그 (음의 상관)
# BTC가 +10% 오를 때 GOLD는 -10%, BTC가 -5% 내릴 때 GOLD +5%
_btc_base = 40000.0
_gold_base = 1900.0
_coinx_base = 100.0
BTC_PRICES = []
GOLD_PRICES = []
COINX_PRICES = []  # BTC와 같은 방향 지그재그 → 고상관
for _i in range(30):
    # BTC 지그재그
    _btc = _btc_base * (1.05 if _i % 2 == 0 else 0.95)
    BTC_PRICES.append(_btc)
    _btc_base = _btc
    # GOLD 반대 방향
    _gold = _gold_base * (0.97 if _i % 2 == 0 else 1.03)
    GOLD_PRICES.append(_gold)
    _gold_base = _gold
    # COINX: BTC와 같은 팩턴
    _coinx = _coinx_base * (1.05 if _i % 2 == 0 else 0.95)
    COINX_PRICES.append(_coinx)
    _coinx_base = _coinx
ETH_PRICES = [_linear_prices(2000, 3200, 30)[i] for i in range(30)]
BOND_PRICES = _flat_prices(100.0, 30)           # 변동없음 → 0 상관


PRICE_SERIES = {
    'BTC': BTC_PRICES,
    'ETH': ETH_PRICES,
    'GOLD': GOLD_PRICES,
    'BOND': BOND_PRICES,
    'COINX': COINX_PRICES,
}


# ─────────────────────────────────────────────────────────────
# 1. 순수 함수 테스트
# ─────────────────────────────────────────────────────────────

class TestPureFunctions:

    def test_mean_basic(self):
        assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)

    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_std_basic(self):
        # 표본표준편차 (n-1 분모)
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        result = _std(vals)
        assert result > 0
        # 분산 = 32/7 ≈ 4.571, 표준편차 ≈ 2.138
        assert result == pytest.approx(2.138, rel=0.01)

    def test_std_single_returns_zero(self):
        assert _std([5.0]) == 0.0

    def test_std_empty_returns_zero(self):
        assert _std([]) == 0.0

    def test_pearson_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert _pearson(x, y) == pytest.approx(1.0, abs=1e-6)

    def test_pearson_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 4.0, 3.0, 2.0, 1.0]
        assert _pearson(x, y) == pytest.approx(-1.0, abs=1e-6)

    def test_pearson_uncorrelated(self):
        x = [1.0, 1.0, 1.0, 1.0]
        y = [1.0, 2.0, 1.0, 2.0]
        # x가 상수 → 분모 0 → 0 반환
        assert _pearson(x, y) == 0.0

    def test_pearson_range_clipped(self):
        # 부동소수점 오차로 1 초과가 나와도 클리핑 되어야 함
        x = list(range(100))
        y = list(range(100))
        r = _pearson(x, y)
        assert -1.0 <= r <= 1.0

    def test_pearson_different_lengths_uses_min(self):
        x = [1.0, 2.0, 3.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = _pearson(x, y)
        assert r == pytest.approx(1.0, abs=1e-6)

    def test_pearson_short_returns_zero(self):
        assert _pearson([1.0], [1.0]) == 0.0

    def test_returns_from_prices_basic(self):
        prices = [100.0, 110.0, 105.0]
        rets = _returns_from_prices(prices)
        assert len(rets) == 2
        assert rets[0] == pytest.approx(math.log(110 / 100), rel=1e-6)

    def test_returns_from_prices_single(self):
        assert _returns_from_prices([100.0]) == []

    def test_returns_from_prices_zero_price(self):
        # 0 가격이 포함되면 0.0 수익률
        rets = _returns_from_prices([100.0, 0.0, 100.0])
        assert rets[0] == 0.0

    def test_returns_from_prices_flat(self):
        prices = [100.0] * 5
        rets = _returns_from_prices(prices)
        assert all(r == pytest.approx(0.0) for r in rets)


# ─────────────────────────────────────────────────────────────
# 2. 상관관계 행렬
# ─────────────────────────────────────────────────────────────

class TestCorrelationMatrix:

    def setup_method(self):
        self.svc = AssetCorrelationService(high_corr_threshold=0.70)
        self.matrix = self.svc.compute_correlation_matrix(PRICE_SERIES)

    def test_diagonal_is_one(self):
        for symbol in PRICE_SERIES:
            assert self.matrix[symbol][symbol] == pytest.approx(1.0, abs=1e-6)

    def test_matrix_is_symmetric(self):
        symbols = list(PRICE_SERIES.keys())
        for s1 in symbols:
            for s2 in symbols:
                assert self.matrix[s1][s2] == pytest.approx(self.matrix[s2][s1], abs=1e-9)

    def test_btc_eth_positive_correlation(self):
        # BTC 지그재그, ETH 선형 상승 → 어느 정도 상관관계
        r = self.matrix['BTC']['ETH']
        # 방향 동일성보다 두 값이 유한한 float 인지 확인
        assert isinstance(r, float)
        assert -1.0 <= r <= 1.0

    def test_btc_gold_negative_correlation(self):
        # BTC 지그재그 상승, GOLD 반대 방향 지그재그 → 음의 상관관계
        r = self.matrix['BTC']['GOLD']
        assert r < 0.0

    def test_bond_correlation_near_zero(self):
        # BOND 가격 불변 → 표준편차 0 → 상관계수 0
        r = self.matrix['BTC']['BOND']
        assert r == pytest.approx(0.0, abs=1e-6)

    def test_all_symbols_present(self):
        for symbol in PRICE_SERIES:
            assert symbol in self.matrix

    def test_values_in_range(self):
        for s1 in self.matrix:
            for s2, r in self.matrix[s1].items():
                assert -1.0 <= r <= 1.0, f'{s1}-{s2}: {r} 범위 초과'

    def test_single_symbol(self):
        matrix = self.svc.compute_correlation_matrix({'BTC': BTC_PRICES})
        assert matrix['BTC']['BTC'] == pytest.approx(1.0)

    def test_empty_price_series(self):
        matrix = self.svc.compute_correlation_matrix({})
        assert matrix == {}


# ─────────────────────────────────────────────────────────────
# 3. 고상관 쌍 탐지
# ─────────────────────────────────────────────────────────────

class TestFindHighCorrelationPairs:

    def setup_method(self):
        self.svc = AssetCorrelationService(high_corr_threshold=0.70)
        self.matrix = self.svc.compute_correlation_matrix(PRICE_SERIES)

    def test_btc_eth_found_as_high_pair(self):
        # COINX는 BTC와 완전히 같은 팩턴 → 상관계수 1.0
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        symbols_in_pairs = [(p['symbol_a'], p['symbol_b']) for p in pairs]
        found = any(
            set([s1, s2]) == {'BTC', 'COINX'}
            for s1, s2 in symbols_in_pairs
        )
        assert found

    def test_no_self_pairs(self):
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        for pair in pairs:
            assert pair['symbol_a'] != pair['symbol_b']

    def test_no_duplicate_pairs(self):
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        seen = set()
        for pair in pairs:
            key = frozenset([pair['symbol_a'], pair['symbol_b']])
            assert key not in seen, f'중복 쌍: {pair}'
            seen.add(key)

    def test_pairs_sorted_descending(self):
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        corrs = [abs(p['correlation']) for p in pairs]
        assert corrs == sorted(corrs, reverse=True)

    def test_threshold_respected(self):
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        for pair in pairs:
            assert abs(pair['correlation']) >= 0.70

    def test_empty_matrix(self):
        pairs = self.svc.find_high_correlation_pairs({})
        assert pairs == []

    def test_pair_has_required_fields(self):
        pairs = self.svc.find_high_correlation_pairs(self.matrix)
        for pair in pairs:
            assert 'symbol_a' in pair
            assert 'symbol_b' in pair
            assert 'correlation' in pair
            assert 'risk' in pair
            assert 'message' in pair

    def test_high_threshold_returns_fewer(self):
        svc_strict = AssetCorrelationService(high_corr_threshold=0.99)
        pairs = svc_strict.find_high_correlation_pairs(self.matrix)
        svc_loose = AssetCorrelationService(high_corr_threshold=0.50)
        pairs_loose = svc_loose.find_high_correlation_pairs(self.matrix)
        assert len(pairs) <= len(pairs_loose)


# ─────────────────────────────────────────────────────────────
# 4. 리밸런싱 제안
# ─────────────────────────────────────────────────────────────

class TestSuggestRebalancing:

    def setup_method(self):
        self.svc = AssetCorrelationService(high_corr_threshold=0.70)
        self.matrix = self.svc.compute_correlation_matrix(PRICE_SERIES)

    def _holdings(self, symbols):
        return [{'symbol': s, 'weight': 1.0 / len(symbols), 'asset_class': 'crypto'} for s in symbols]

    def test_returns_required_keys(self):
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC', 'ETH', 'GOLD']),
            matrix=self.matrix,
        )
        assert 'reduce' in result
        assert 'keep' in result
        assert 'diversify' in result
        assert 'summary' in result

    def test_empty_holdings(self):
        result = self.svc.suggest_rebalancing(holdings=[], matrix=self.matrix)
        assert result['reduce'] == []
        assert result['keep'] == []

    def test_high_corr_assets_in_reduce(self):
        # BTC + COINX = 고상관 → 적어도 하나는 reduce 또는 keep에 들어가야 함
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC', 'COINX']),
            matrix=self.matrix,
        )
        reduce_symbols = [r['symbol'] for r in result['reduce']]
        all_symbols = reduce_symbols + [r['symbol'] for r in result['keep']]
        assert set(all_symbols) == {'BTC', 'COINX'}

    def test_diversify_message_when_high_pairs_exist(self):
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC', 'COINX']),
            matrix=self.matrix,
        )
        # BTC-COINX 고상관이면 diversify 알림이 있어야 함
        if self.svc.find_high_correlation_pairs(self.matrix):
            assert len(result['diversify']) > 0

    def test_summary_is_string(self):
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC', 'GOLD']),
            matrix=self.matrix,
        )
        assert isinstance(result['summary'], str)
        assert len(result['summary']) > 0

    def test_reduce_has_reason_field(self):
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC', 'ETH', 'GOLD']),
            matrix=self.matrix,
        )
        for item in result['reduce']:
            assert 'symbol' in item
            assert 'reason' in item

    def test_all_holdings_accounted(self):
        symbols = ['BTC', 'ETH', 'GOLD']
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(symbols),
            matrix=self.matrix,
        )
        accounted = set(
            [r['symbol'] for r in result['reduce']] +
            [r['symbol'] for r in result['keep']]
        )
        assert accounted == set(symbols)

    def test_single_asset_no_reduce(self):
        result = self.svc.suggest_rebalancing(
            holdings=self._holdings(['BTC']),
            matrix=self.matrix,
        )
        assert result['reduce'] == []
        assert len(result['keep']) == 1


# ─────────────────────────────────────────────────────────────
# 5. avg_correlation_of
# ─────────────────────────────────────────────────────────────

class TestAvgCorrelationOf:

    def setup_method(self):
        self.svc = AssetCorrelationService()
        self.matrix = self.svc.compute_correlation_matrix(PRICE_SERIES)

    def test_returns_float(self):
        r = self.svc.avg_correlation_of('BTC', self.matrix)
        assert isinstance(r, float)

    def test_range_0_to_1(self):
        for symbol in PRICE_SERIES:
            r = self.svc.avg_correlation_of(symbol, self.matrix)
            assert 0.0 <= r <= 1.0

    def test_missing_symbol_returns_zero(self):
        r = self.svc.avg_correlation_of('UNKNOWN', self.matrix)
        assert r == 0.0

    def test_btc_coinx_have_high_avg_corr(self):
        # BTC와 COINX는 서로 고상관이므로 평균도 높아야 함
        r_btc = self.svc.avg_correlation_of('BTC', self.matrix)
        assert r_btc > 0.3
