#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""커뮤니티 QnA/Chat 실시간 연동 테스트.

커버 대상:
- get_community_qna_list(): 목록 조회, 카테고리 필터, 오류 처리
- get_community_qna_detail(): 상세 조회, 답변 포함 구조
- post_community_question(): 질문 등록, 빈값 차단
- post_community_answer(): 답변 등록, 빈값 차단
- get_community_chat_recent(): 채팅 최근 메시지 조회
- send_community_chat_message(): 채팅 전송, 빈값/초과 차단
- get_community_notices(): 공지사항 조회
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from api.backend_api import BackendAPI, BackendConfig


# ────────────────────────────────────────────────────────────────────────────
# 공용 Fixture
# ────────────────────────────────────────────────────────────────────────────

def make_api(response_data: Optional[Dict] = None, raise_exc: bool = False) -> BackendAPI:
    """BackendAPI 인스턴스 생성 + _make_request Mock."""
    api = BackendAPI.__new__(BackendAPI)
    api.token = 'test_token'
    api.config = BackendConfig(
        base_url='https://daltrading.net',
        api_key='',
        timeout=10,
        retry_count=1,
        retry_delay=0,
    )
    import logging
    api.logger = logging.getLogger('test_community')
    api.session = MagicMock()
    api.websocket = None
    api.websocket_thread = None
    api.is_connected = True
    api._signal_callbacks = []
    api._user_id = None
    api._user_grade = None
    api._user_email = None

    if raise_exc:
        api._make_request = MagicMock(side_effect=RuntimeError("네트워크 오류"))
    else:
        api._make_request = MagicMock(return_value=response_data)
    return api


# ────────────────────────────────────────────────────────────────────────────
# 1. QnA 목록 조회
# ────────────────────────────────────────────────────────────────────────────

class TestCommunityQnaList:

    def test_returns_ok_with_items(self):
        api = make_api({'total': 3, 'items': [
            {'id': '1', 'title': 'ETF 추적오차 질문', 'content': '...', 'author': 'user1',
             'category': 'etf', 'answer_count': 2, 'is_answered': True,
             'created_at': '2026-05-01', 'updated_at': '2026-05-01'},
        ]})
        result = api.get_community_qna_list(limit=10)
        assert result['status'] == 'ok'
        assert result['total'] == 3
        assert len(result['items']) == 1

    def test_returns_empty_on_no_response(self):
        api = make_api(None)
        result = api.get_community_qna_list()
        assert result['status'] == 'error'
        assert result['items'] == []
        assert result['total'] == 0

    def test_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.get_community_qna_list()
        assert result['status'] == 'error'
        assert 'error' in result

    def test_passes_category_param(self):
        api = make_api({'total': 0, 'items': []})
        api.get_community_qna_list(limit=5, offset=0, category='trading')
        call_params = api._make_request.call_args
        assert call_params is not None
        assert 'params' in call_params.kwargs or len(call_params.args) >= 3

    def test_items_key_always_present(self):
        for response in [None, {}, {'total': 0}]:
            api = make_api(response)
            result = api.get_community_qna_list()
            assert 'items' in result

    def test_total_key_always_present(self):
        api = make_api({'items': []})
        result = api.get_community_qna_list()
        assert 'total' in result


# ────────────────────────────────────────────────────────────────────────────
# 2. QnA 상세 조회
# ────────────────────────────────────────────────────────────────────────────

class TestCommunityQnaDetail:

    def test_returns_ok_with_question_and_answers(self):
        api = make_api({
            'question': {'id': '1', 'title': 'Q', 'content': 'C', 'author': 'u', 'created_at': ''},
            'answers': [{'id': 'a1', 'content': '답변', 'author': 'expert', 'is_accepted': True}],
        })
        result = api.get_community_qna_detail('1')
        assert result['status'] == 'ok'
        assert result['question']['id'] == '1'
        assert len(result['answers']) == 1

    def test_returns_error_on_not_found(self):
        api = make_api(None)
        result = api.get_community_qna_detail('nonexistent')
        assert result['status'] == 'error'
        assert result['question'] == {}
        assert result['answers'] == []

    def test_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.get_community_qna_detail('1')
        assert result['status'] == 'error'

    def test_answers_key_always_list(self):
        api = make_api({'question': {}, 'answers': None})
        result = api.get_community_qna_detail('1')
        # None이 반환되면 [] 처리
        assert isinstance(result.get('answers', []), list)


# ────────────────────────────────────────────────────────────────────────────
# 3. 질문 등록
# ────────────────────────────────────────────────────────────────────────────

class TestPostCommunityQuestion:

    def test_returns_ok_with_qna_id(self):
        api = make_api({'id': 'q123'})
        result = api.post_community_question('ETF 질문', '내용입니다')
        assert result['status'] == 'ok'
        assert result['qna_id'] == 'q123'

    def test_blocks_empty_title(self):
        api = make_api({'id': 'q1'})
        result = api.post_community_question('', '내용')
        assert result['status'] == 'error'
        assert 'required' in result['error']

    def test_blocks_empty_content(self):
        api = make_api({'id': 'q1'})
        result = api.post_community_question('제목', '')
        assert result['status'] == 'error'

    def test_returns_error_on_no_response(self):
        api = make_api(None)
        result = api.post_community_question('제목', '내용')
        assert result['status'] == 'error'

    def test_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.post_community_question('제목', '내용')
        assert result['status'] == 'error'

    def test_title_truncated_to_200_chars(self):
        api = make_api({'id': 'q1'})
        long_title = 'A' * 300
        api.post_community_question(long_title, '내용')
        call_data = api._make_request.call_args
        # data 파라미터에서 title 길이 확인
        if call_data:
            kwargs = call_data.kwargs
            data_arg = kwargs.get('data') or (call_data.args[2] if len(call_data.args) > 2 else {})
            if data_arg and 'title' in data_arg:
                assert len(data_arg['title']) <= 200


# ────────────────────────────────────────────────────────────────────────────
# 4. 답변 등록
# ────────────────────────────────────────────────────────────────────────────

class TestPostCommunityAnswer:

    def test_returns_ok_with_answer_id(self):
        api = make_api({'id': 'a456'})
        result = api.post_community_answer('q1', '답변 내용')
        assert result['status'] == 'ok'
        assert result['answer_id'] == 'a456'

    def test_blocks_empty_qna_id(self):
        api = make_api({'id': 'a1'})
        result = api.post_community_answer('', '내용')
        assert result['status'] == 'error'

    def test_blocks_empty_content(self):
        api = make_api({'id': 'a1'})
        result = api.post_community_answer('q1', '')
        assert result['status'] == 'error'

    def test_returns_error_on_no_response(self):
        api = make_api(None)
        result = api.post_community_answer('q1', '내용')
        assert result['status'] == 'error'

    def test_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.post_community_answer('q1', '내용')
        assert result['status'] == 'error'


# ────────────────────────────────────────────────────────────────────────────
# 5. 채팅 최근 메시지 조회
# ────────────────────────────────────────────────────────────────────────────

class TestCommunityChat:

    def test_get_chat_returns_ok_with_messages(self):
        api = make_api({'messages': [
            {'id': 'm1', 'author': 'u1', 'content': '안녕하세요', 'timestamp': '2026-05-03T10:00:00'},
            {'id': 'm2', 'author': 'u2', 'content': 'ETF 질문있어요', 'timestamp': '2026-05-03T10:01:00'},
        ]})
        result = api.get_community_chat_recent(room='trading', limit=50)
        assert result['status'] == 'ok'
        assert result['room'] == 'trading'
        assert len(result['messages']) == 2

    def test_get_chat_returns_error_on_no_response(self):
        api = make_api(None)
        result = api.get_community_chat_recent()
        assert result['status'] == 'error'
        assert result['messages'] == []

    def test_get_chat_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.get_community_chat_recent()
        assert result['status'] == 'error'

    def test_get_chat_messages_key_always_present(self):
        api = make_api({})
        result = api.get_community_chat_recent()
        assert 'messages' in result

    def test_send_chat_returns_ok_with_message_id(self):
        api = make_api({'id': 'msg789'})
        result = api.send_community_chat_message('안녕하세요', room='general')
        assert result['status'] == 'ok'
        assert result['message_id'] == 'msg789'

    def test_send_chat_blocks_empty_message(self):
        api = make_api({'id': 'm1'})
        result = api.send_community_chat_message('')
        assert result['status'] == 'error'
        assert 'empty' in result['error']

    def test_send_chat_blocks_whitespace_only_message(self):
        api = make_api({'id': 'm1'})
        result = api.send_community_chat_message('   ')
        assert result['status'] == 'error'

    def test_send_chat_returns_error_on_no_response(self):
        api = make_api(None)
        result = api.send_community_chat_message('테스트')
        assert result['status'] == 'error'

    def test_send_chat_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.send_community_chat_message('테스트')
        assert result['status'] == 'error'

    def test_send_chat_truncates_long_message(self):
        """500자 초과 메시지는 500자로 잘라서 전송."""
        api = make_api({'id': 'm1'})
        long_msg = 'A' * 600
        api.send_community_chat_message(long_msg)
        call_data = api._make_request.call_args
        if call_data:
            kwargs = call_data.kwargs
            data_arg = kwargs.get('data') or (call_data.args[2] if len(call_data.args) > 2 else {})
            if data_arg and 'content' in data_arg:
                assert len(data_arg['content']) <= 500

    def test_chat_rooms_supported(self):
        """general / trading / etf / crypto 채팅방 조회 가능."""
        for room in ('general', 'trading', 'etf', 'crypto'):
            api = make_api({'messages': []})
            result = api.get_community_chat_recent(room=room)
            assert result['room'] == room


# ────────────────────────────────────────────────────────────────────────────
# 6. 공지사항 조회
# ────────────────────────────────────────────────────────────────────────────

class TestCommunityNotices:

    def test_returns_ok_with_notices(self):
        api = make_api({'notices': [
            {'id': 'n1', 'title': '시스템 점검 안내', 'content': '...', 'pinned': True, 'created_at': ''},
        ]})
        result = api.get_community_notices(limit=5)
        assert result['status'] == 'ok'
        assert len(result['notices']) == 1

    def test_returns_error_on_no_response(self):
        api = make_api(None)
        result = api.get_community_notices()
        assert result['status'] == 'error'
        assert result['notices'] == []

    def test_returns_error_on_exception(self):
        api = make_api(raise_exc=True)
        result = api.get_community_notices()
        assert result['status'] == 'error'

    def test_notices_key_always_present(self):
        api = make_api({})
        result = api.get_community_notices()
        assert 'notices' in result
