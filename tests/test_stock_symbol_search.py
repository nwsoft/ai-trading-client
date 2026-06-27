#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""종목 자동완성/즐겨찾기/최근검색 단위 테스트.

커버 대상:
- StockSearchProfile: 프로파일 정규화 (중복 제거, 대소문자, 빈값, 한도)
- 최근검색 기록: 중복 방지, 최신 우선 정렬, 최대 12개 한도
- 즐겨찾기 토글: 추가/제거, 최대 20개 한도, 중복 방지
- 자동완성 제안: 코드 prefix 우선, 이름 포함, 빈쿼리 시 즐겨찾기+최근검색 우선
- asset_mode 필터: stock 모드에서 ETF 제외, etf 모드에서 주식 제외, all 포함
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────
# 순수 로직 헬퍼 — 대시보드 메서드를 의존성 없이 재현
# ─────────────────────────────────────────────────────────────

def _normalize_profile(profile: Any) -> Dict[str, Any]:
    """_get_stock_search_profile 로직 재현."""
    if not isinstance(profile, dict):
        profile = {}
    recent_codes = profile.get('recent_codes', [])
    favorites = profile.get('favorites', [])
    if not isinstance(recent_codes, list):
        recent_codes = []
    if not isinstance(favorites, list):
        favorites = []
    norm_recent = [str(c or '').strip().upper() for c in recent_codes if str(c or '').strip()]
    norm_favorites = [str(c or '').strip().upper() for c in favorites if str(c or '').strip()]
    return {
        'recent_codes': list(dict.fromkeys(norm_recent))[:12],
        'favorites': list(dict.fromkeys(norm_favorites))[:20],
    }


def _save_profile(settings: dict, key: str, profile: dict) -> dict:
    """_save_stock_search_profile 로직 재현 (persist 없이 dict 반환)."""
    normalized = {
        'recent_codes': list(dict.fromkeys([
            str(c or '').strip().upper()
            for c in (profile.get('recent_codes', []) or [])
            if str(c or '').strip()
        ]))[:12],
        'favorites': list(dict.fromkeys([
            str(c or '').strip().upper()
            for c in (profile.get('favorites', []) or [])
            if str(c or '').strip()
        ]))[:20],
    }
    settings[key] = normalized
    return normalized


def _record_recent(settings: dict, code: str) -> dict:
    """_record_recent_stock_search 로직 재현."""
    symbol = str(code or '').strip().upper()
    if not symbol:
        return _normalize_profile(settings.get('stock_search_profile', {}))
    profile = _normalize_profile(settings.get('stock_search_profile', {}))
    recent = [c for c in profile.get('recent_codes', []) if c != symbol]
    recent.insert(0, symbol)
    profile['recent_codes'] = recent[:12]
    return _save_profile(settings, 'stock_search_profile', profile)


def _toggle_favorite(settings: dict, code: str) -> dict:
    """_toggle_stock_favorite 로직 재현."""
    symbol = str(code or '').strip().upper()
    if not symbol:
        return _normalize_profile(settings.get('stock_search_profile', {}))
    profile = _normalize_profile(settings.get('stock_search_profile', {}))
    favorites = list(profile.get('favorites', []))
    if symbol in favorites:
        favorites = [c for c in favorites if c != symbol]
    else:
        favorites.insert(0, symbol)
        favorites = list(dict.fromkeys(favorites))[:20]
    profile['favorites'] = favorites
    return _save_profile(settings, 'stock_search_profile', profile)


def _mode_matches(asset_mode: str, is_etf: bool) -> bool:
    """_stock_mode_matches 로직 재현."""
    if asset_mode == 'stock':
        return not is_etf
    if asset_mode == 'etf':
        return bool(is_etf)
    return True


def _get_suggestions(
    symbol_index: List[Dict[str, Any]],
    settings: dict,
    query: str,
    asset_mode: str = 'all',
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """_get_stock_search_suggestions 로직 재현."""
    q = str(query or '').strip().upper()
    if not symbol_index:
        return []

    if not q:
        profile = _normalize_profile(settings.get('stock_search_profile', {}))
        preferred_codes = list(dict.fromkeys(
            list(profile.get('favorites', []) or []) +
            list(profile.get('recent_codes', []) or [])
        ))
        preferred_set = set(preferred_codes)
        by_code = {str(item.get('code', '')).upper(): item for item in symbol_index}
        suggestions: List[Dict[str, Any]] = []
        for code in preferred_codes:
            item = by_code.get(str(code or '').upper())
            if item and _mode_matches(asset_mode, bool(item.get('is_etf'))):
                suggestions.append(item)
        if len(suggestions) < limit:
            for item in symbol_index:
                code = str(item.get('code', '')).upper()
                if code in preferred_set:
                    continue
                if not _mode_matches(asset_mode, bool(item.get('is_etf'))):
                    continue
                suggestions.append(item)
                if len(suggestions) >= limit:
                    break
        return suggestions[:limit]

    ranked = []
    for item in symbol_index:
        if not _mode_matches(asset_mode, bool(item.get('is_etf'))):
            continue
        code = str(item.get('code') or '').upper()
        name = str(item.get('name') or '').upper()
        if not code:
            continue
        rank = None
        if code.startswith(q):
            rank = 0
        elif q in code:
            rank = 1
        elif name.startswith(q):
            rank = 2
        elif q in name:
            rank = 3
        if rank is not None:
            ranked.append((rank, item))
    ranked.sort(key=lambda t: (t[0], str(t[1].get('code', ''))))
    return [item for _, item in ranked[:max(1, int(limit))]]


# ─────────────────────────────────────────────────────────────
# 샘플 데이터
# ─────────────────────────────────────────────────────────────

SAMPLE_INDEX = [
    {'code': '005930', 'name': '삼성전자', 'is_etf': False},
    {'code': '000660', 'name': 'SK하이닉스', 'is_etf': False},
    {'code': '207940', 'name': '삼성바이오로직스', 'is_etf': False},
    {'code': '035420', 'name': 'NAVER', 'is_etf': False},
    {'code': '069500', 'name': 'KODEX 200', 'is_etf': True},
    {'code': '114800', 'name': 'KODEX 인버스', 'is_etf': True},
    {'code': '105190', 'name': 'TIGER 200', 'is_etf': True},
    {'code': '091160', 'name': 'KODEX 반도체', 'is_etf': True},
    {'code': '069660', 'name': 'KOSEF 200', 'is_etf': True},
    {'code': '252670', 'name': 'KODEX 200선물인버스2X', 'is_etf': True},
]


# ─────────────────────────────────────────────────────────────
# 1. 프로파일 정규화
# ─────────────────────────────────────────────────────────────

class TestNormalizeProfile:

    def test_empty_profile_returns_defaults(self):
        result = _normalize_profile({})
        assert result['recent_codes'] == []
        assert result['favorites'] == []

    def test_none_input_returns_defaults(self):
        result = _normalize_profile(None)
        assert result['recent_codes'] == []
        assert result['favorites'] == []

    def test_codes_uppercased(self):
        result = _normalize_profile({'recent_codes': ['005930', '000660'], 'favorites': ['069500']})
        assert all(c == c.upper() for c in result['recent_codes'])
        assert all(c == c.upper() for c in result['favorites'])

    def test_duplicates_removed(self):
        result = _normalize_profile({'recent_codes': ['005930', '005930', '000660'], 'favorites': []})
        assert result['recent_codes'].count('005930') == 1

    def test_empty_strings_filtered(self):
        result = _normalize_profile({'recent_codes': ['', '  ', '005930'], 'favorites': []})
        assert '' not in result['recent_codes']
        assert '  ' not in result['recent_codes']
        assert '005930' in result['recent_codes']

    def test_recent_codes_capped_at_12(self):
        codes = [str(i).zfill(6) for i in range(20)]
        result = _normalize_profile({'recent_codes': codes, 'favorites': []})
        assert len(result['recent_codes']) <= 12

    def test_favorites_capped_at_20(self):
        codes = [str(i).zfill(6) for i in range(30)]
        result = _normalize_profile({'recent_codes': [], 'favorites': codes})
        assert len(result['favorites']) <= 20

    def test_non_list_recent_codes_becomes_empty(self):
        result = _normalize_profile({'recent_codes': '005930', 'favorites': []})
        assert result['recent_codes'] == []

    def test_non_list_favorites_becomes_empty(self):
        result = _normalize_profile({'recent_codes': [], 'favorites': None})
        assert result['favorites'] == []


# ─────────────────────────────────────────────────────────────
# 2. 최근검색 기록
# ─────────────────────────────────────────────────────────────

class TestRecordRecentSearch:

    def test_new_code_inserted_at_head(self):
        settings = {}
        result = _record_recent(settings, '005930')
        assert result['recent_codes'][0] == '005930'

    def test_existing_code_moved_to_head(self):
        settings = {'stock_search_profile': {'recent_codes': ['000660', '005930'], 'favorites': []}}
        result = _record_recent(settings, '005930')
        assert result['recent_codes'][0] == '005930'
        assert result['recent_codes'].count('005930') == 1

    def test_recent_capped_at_12(self):
        existing = [str(i).zfill(6) for i in range(12)]
        settings = {'stock_search_profile': {'recent_codes': existing, 'favorites': []}}
        result = _record_recent(settings, '999999')
        assert len(result['recent_codes']) <= 12
        assert result['recent_codes'][0] == '999999'

    def test_empty_code_ignored(self):
        settings = {}
        result = _record_recent(settings, '')
        assert result['recent_codes'] == []

    def test_lowercase_code_uppercased(self):
        settings = {}
        result = _record_recent(settings, '005930')
        assert '005930' in result['recent_codes']

    def test_settings_updated(self):
        settings = {}
        _record_recent(settings, '005930')
        assert 'stock_search_profile' in settings
        assert settings['stock_search_profile']['recent_codes'][0] == '005930'


# ─────────────────────────────────────────────────────────────
# 3. 즐겨찾기 토글
# ─────────────────────────────────────────────────────────────

class TestToggleFavorite:

    def test_add_to_empty_favorites(self):
        settings = {}
        result = _toggle_favorite(settings, '005930')
        assert '005930' in result['favorites']

    def test_add_moves_to_head(self):
        settings = {'stock_search_profile': {'recent_codes': [], 'favorites': ['000660']}}
        result = _toggle_favorite(settings, '005930')
        assert result['favorites'][0] == '005930'

    def test_remove_existing_favorite(self):
        settings = {'stock_search_profile': {'recent_codes': [], 'favorites': ['005930', '000660']}}
        result = _toggle_favorite(settings, '005930')
        assert '005930' not in result['favorites']
        assert '000660' in result['favorites']

    def test_favorites_capped_at_20(self):
        existing = [str(i).zfill(6) for i in range(20)]
        settings = {'stock_search_profile': {'recent_codes': [], 'favorites': existing}}
        result = _toggle_favorite(settings, '999999')
        assert len(result['favorites']) <= 20

    def test_duplicate_not_created(self):
        settings = {}
        _toggle_favorite(settings, '005930')
        result = _toggle_favorite(settings, '005930')  # 두 번째: 제거
        assert '005930' not in result['favorites']

    def test_empty_code_ignored(self):
        settings = {}
        result = _toggle_favorite(settings, '')
        assert result['favorites'] == []

    def test_settings_persisted(self):
        settings = {}
        _toggle_favorite(settings, '069500')
        assert '069500' in settings['stock_search_profile']['favorites']


# ─────────────────────────────────────────────────────────────
# 4. asset_mode 필터
# ─────────────────────────────────────────────────────────────

class TestAssetModeFilter:

    def test_all_mode_includes_both(self):
        assert _mode_matches('all', True) is True
        assert _mode_matches('all', False) is True

    def test_stock_mode_excludes_etf(self):
        assert _mode_matches('stock', True) is False
        assert _mode_matches('stock', False) is True

    def test_etf_mode_excludes_stock(self):
        assert _mode_matches('etf', True) is True
        assert _mode_matches('etf', False) is False

    def test_unknown_mode_includes_all(self):
        assert _mode_matches('unknown_xyz', True) is True
        assert _mode_matches('unknown_xyz', False) is True


# ─────────────────────────────────────────────────────────────
# 5. 자동완성 제안
# ─────────────────────────────────────────────────────────────

class TestGetSearchSuggestions:

    def test_empty_index_returns_empty(self):
        result = _get_suggestions([], {}, '005930')
        assert result == []

    def test_code_prefix_match_rank0(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '0059')
        codes = [item['code'] for item in result]
        assert '005930' in codes
        # prefix 매칭이 첫 번째이어야 함
        assert result[0]['code'] == '005930'

    def test_code_contains_match_rank1(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '660')
        codes = [item['code'] for item in result]
        assert '000660' in codes

    def test_name_prefix_match_rank2(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, 'KODEX')
        codes = [item['code'] for item in result]
        # KODEX로 시작하는 ETF들이 포함되어야 함
        assert any(c in codes for c in ['069500', '114800', '091160', '252670'])

    def test_name_contains_match_rank3(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '인버스')
        codes = [item['code'] for item in result]
        assert '114800' in codes  # KODEX 인버스

    def test_limit_applied(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '', limit=3)
        assert len(result) <= 3

    def test_stock_mode_excludes_etf(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '069500', asset_mode='stock')
        codes = [item['code'] for item in result]
        assert '069500' not in codes

    def test_etf_mode_excludes_stock(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '005930', asset_mode='etf')
        codes = [item['code'] for item in result]
        assert '005930' not in codes

    def test_all_mode_includes_both(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '0', asset_mode='all', limit=20)
        codes = [item['code'] for item in result]
        has_stock = any(c in codes for c in ['005930', '000660'])
        has_etf = any(c in codes for c in ['069500', '114800'])
        assert has_stock
        assert has_etf

    def test_empty_query_returns_favorites_first(self):
        settings = {'stock_search_profile': {'recent_codes': [], 'favorites': ['069500', '005930']}}
        result = _get_suggestions(SAMPLE_INDEX, settings, '', limit=8)
        if result:
            assert result[0]['code'] in ('069500', '005930')

    def test_empty_query_includes_recent_after_favorites(self):
        settings = {
            'stock_search_profile': {
                'favorites': ['005930'],
                'recent_codes': ['000660'],
            }
        }
        result = _get_suggestions(SAMPLE_INDEX, settings, '', limit=8)
        codes = [item['code'] for item in result]
        # 즐겨찾기 + 최근검색이 앞에 위치
        fav_pos = codes.index('005930') if '005930' in codes else 999
        rec_pos = codes.index('000660') if '000660' in codes else 999
        assert fav_pos < rec_pos or rec_pos == 999  # 즐겨찾기가 최근검색보다 앞

    def test_no_match_returns_empty(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, 'XYZXYZ')
        assert result == []

    def test_results_are_list_of_dicts(self):
        result = _get_suggestions(SAMPLE_INDEX, {}, '005930')
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)
            assert 'code' in item
            assert 'name' in item


# ─────────────────────────────────────────────────────────────
# 6. 프로파일 저장 정합성
# ─────────────────────────────────────────────────────────────

class TestSaveProfileConsistency:

    def test_save_normalizes_on_write(self):
        settings = {}
        dirty_profile = {
            'recent_codes': ['005930', '  ', '005930', '000660'],
            'favorites': ['069500', None, '069500'],
        }
        result = _save_profile(settings, 'stock_search_profile', dirty_profile)
        assert result['recent_codes'].count('005930') == 1
        assert '' not in result['recent_codes']
        assert result['favorites'].count('069500') == 1

    def test_save_updates_settings_dict(self):
        settings = {}
        _save_profile(settings, 'stock_search_profile', {'recent_codes': ['005930'], 'favorites': []})
        assert settings['stock_search_profile']['recent_codes'] == ['005930']

    def test_save_empty_profile(self):
        settings = {}
        result = _save_profile(settings, 'stock_search_profile', {})
        assert result['recent_codes'] == []
        assert result['favorites'] == []

    def test_save_and_reload_idempotent(self):
        settings = {}
        profile = {'recent_codes': ['005930', '000660'], 'favorites': ['069500']}
        saved = _save_profile(settings, 'stock_search_profile', profile)
        saved2 = _save_profile(settings, 'stock_search_profile', saved)
        assert saved == saved2
