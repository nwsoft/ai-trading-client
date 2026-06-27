#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
관리자 전용 기능 유틸리티
"""

import os
import sys
from typing import List, Optional


# 관리자/개발자 계정 목록
ADMIN_ACCOUNTS = ['admin', 'developer', 'dev']

# 관리자 전용 기능 목록
ADMIN_FEATURES = {
    'demo_mode': {
        'name': '데모 모드',
        'description': '관리자 전용 고성능 시뮬레이션 모드',
        'accounts': ADMIN_ACCOUNTS
    }
}


def is_admin_account(username: Optional[str] = None) -> bool:
    """
    현재 사용자가 관리자 계정인지 확인
    
    Args:
        username: 확인할 사용자명 (None이면 현재 사용자)
    
    Returns:
        bool: 관리자 계정 여부
    """
    if username is None:
        # 현재 사용자 계정 확인
        try:
            from path_utils import get_current_user_account
            username = get_current_user_account()
        except Exception:
            return False
    
    if not username:
        return False
    
    return username.lower() in ADMIN_ACCOUNTS


def can_access_admin_feature(feature_name: str, username: Optional[str] = None) -> bool:
    """
    특정 관리자 기능에 접근할 수 있는지 확인
    
    Args:
        feature_name: 기능 이름
        username: 확인할 사용자명
    
    Returns:
        bool: 접근 가능 여부
    """
    if not is_admin_account(username):
        return False
    
    if feature_name not in ADMIN_FEATURES:
        return False
    
    feature = ADMIN_FEATURES[feature_name]
    user = username or get_current_user_account()
    
    return user.lower() in feature['accounts']


def get_admin_features_for_user(username: Optional[str] = None) -> List[str]:
    """
    사용자가 접근 가능한 관리자 기능 목록 반환
    
    Args:
        username: 확인할 사용자명
    
    Returns:
        List[str]: 접근 가능한 기능 목록
    """
    if not is_admin_account(username):
        return []
    
    user = username or get_current_user_account()
    accessible_features = []
    
    for feature_name, feature_info in ADMIN_FEATURES.items():
        if user.lower() in feature_info['accounts']:
            accessible_features.append(feature_name)
    
    return accessible_features


def get_current_user_account() -> str:
    """현재 사용자 계정 반환"""
    try:
        from path_utils import get_current_user_account
        account = get_current_user_account()
        if account:
            return account
        
        # 폴백: 토큰 파일에서 계정 정보 확인
        from path_utils import get_token_file_path
        import json
        import os
        
        token_file = get_token_file_path()
        if os.path.exists(token_file):
            with open(token_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
                return token_data.get('id', '')
        
        return ""
    except Exception as e:
        print(f"⚠️ 사용자 계정 확인 실패: {e}")
        return ""


def log_admin_action(action: str, username: Optional[str] = None):
    """
    관리자 액션 로깅
    
    Args:
        action: 수행된 액션
        username: 사용자명
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        user = username or get_current_user_account()
        logger.info(f"🔐 관리자 액션: {user} - {action}")
    except Exception:
        pass


def validate_demo_mode_settings(settings: dict) -> bool:
    """
    데모 모드 설정 유효성 검사
    
    Args:
        settings: 설정 딕셔너리
    
    Returns:
        bool: 유효한 설정인지 여부
    """
    if not settings.get('demo_mode', False):
        return True
    
    # 데모 모드가 활성화된 경우 추가 검증
    if settings.get('paper_trading', False):
        # 데모 모드와 페이퍼 트레이딩은 동시에 활성화할 수 없음
        return False
    
    return True


def get_demo_mode_info() -> dict:
    """
    데모 모드 정보 반환
    
    Returns:
        dict: 데모 모드 관련 정보
    """
    return {
        'name': '데모 모드',
        'description': '관리자 전용 고성능 시뮬레이션 모드',
        'features': [
            '실제 거래소 데이터 사용',
            '가상 잔고로 거래',
            '최적화된 AI 신호',
            '향상된 수익률 시뮬레이션',
            '실시간 거래 로그 출력'
        ],
        'target_accounts': ADMIN_ACCOUNTS,
        'warning': '이 모드는 홍보/데모 목적으로만 사용되어야 합니다.'
    }
