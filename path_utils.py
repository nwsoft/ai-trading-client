#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
경로 처리 유틸리티 - PyInstaller 배포 환경 대응
"""

import os
import sys
import json
from pathlib import Path

# 전역 변수로 현재 사용자 계정 저장
_current_user_account = None

def set_current_user_account(account_name: str):
    """현재 사용자 계정 설정"""
    global _current_user_account
    _current_user_account = account_name

def get_current_user_account() -> str:
    """현재 사용자 계정 반환"""
    global _current_user_account
    return _current_user_account or ""

def get_app_base_dir():
    """애플리케이션 기본 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 배포 환경 - 내부 경로 사용
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            # PyInstaller 내부 경로 (빌드 시 포함된 파일들)
            return meipass
        # 일반 실행 파일
        return os.path.dirname(sys.executable)
    else:
        # 개발 환경
        return os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir():
    """사용자 데이터 디렉토리 반환 (로그, 설정 파일 등)"""
    if getattr(sys, 'frozen', False):
        # 배포 환경 - 사용자 Documents 폴더 사용 (동적 스캔)
        base_dir = find_noahai_dir()
        
        # 사용자 계정이 설정되어 있으면 하위 폴더 사용
        if _current_user_account:
            account_dir = os.path.join(base_dir, _current_user_account)
            os.makedirs(account_dir, exist_ok=True)
            return account_dir
        
        # 사용자 계정이 없으면 기본 경로 사용 (로그인 전 - 최소한의 파일만)
        os.makedirs(base_dir, exist_ok=True)
        return base_dir
    else:
        # 개발 환경 - 프로젝트 내 data 폴더 사용
        base_dir = os.path.join(get_app_base_dir(), 'data')
        
        # 사용자 계정이 설정되어 있으면 하위 폴더 사용
        if _current_user_account:
            account_dir = os.path.join(base_dir, _current_user_account)
            os.makedirs(account_dir, exist_ok=True)
            return account_dir
        
        # 사용자 계정이 없으면 기본 경로 사용 (로그인 전 - 최소한의 파일만)
        os.makedirs(base_dir, exist_ok=True)
        return base_dir

def get_log_dir():
    """로그 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        # 배포 환경 - 사용자 데이터 디렉토리 (계정별 폴더 사용)
        log_dir = os.path.join(get_app_data_dir(), 'logs')
    else:
        # 개발 환경 - 프로젝트 내 data 폴더 (계정별 폴더 사용)
        base_dir = os.path.join(get_app_base_dir(), 'data')
        # 사용자 계정이 설정되어 있으면 하위 폴더 사용
        if _current_user_account:
            log_dir = os.path.join(base_dir, _current_user_account, 'logs')
        else:
            log_dir = os.path.join(base_dir, 'logs')
    
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_log_file_path():
    """메인 로그 파일 경로 반환"""
    return os.path.join(get_log_dir(), 'trading.log')

def get_exchange_log_file_path(exchange_name: str) -> str:
    """거래소별 로그 파일 경로 반환"""
    return os.path.join(get_log_dir(), f'trading_{exchange_name}.log')

def get_config_dir():
    """설정 파일 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        # 배포 환경 - 사용자 데이터 디렉토리 (계정별 폴더 사용)
        config_dir = os.path.join(get_app_data_dir(), 'config')
    else:
        # 개발 환경 - data 폴더 내 사용자별 config 폴더 사용
        if _current_user_account:
            # 사용자 계정이 있으면 data/사용자ID/config 사용
            data_dir = os.path.join(get_app_base_dir(), 'data', _current_user_account)
            config_dir = os.path.join(data_dir, 'config')
        else:
            # 사용자 계정이 없으면 data 폴더 직접 사용 (로그인 전)
            # config 폴더를 만들지 않고 data 폴더에 직접 저장
            data_dir = os.path.join(get_app_base_dir(), 'data')
            config_dir = data_dir
    
    # 로그인 전에는 폴더를 생성하지 않음 (theme_config.json만 필요)
    if _current_user_account or getattr(sys, 'frozen', False):
        os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_db_dir():
    """데이터베이스 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        # 배포 환경 - 사용자 데이터 디렉토리 (계정별 폴더 사용)
        db_dir = get_app_data_dir()
    else:
        # 개발 환경 - 프로젝트 내 data 폴더 (계정별 폴더 사용)
        base_dir = os.path.join(get_app_base_dir(), 'data')
        
        # 사용자 계정이 설정되어 있으면 하위 폴더 사용
        if _current_user_account:
            db_dir = os.path.join(base_dir, _current_user_account)
        else:
            db_dir = base_dir
    
    os.makedirs(db_dir, exist_ok=True)
    return db_dir

def get_db_file_path():
    """데이터베이스 파일 경로 반환"""
    return os.path.join(get_db_dir(), 'trading.db')

def get_ai_learning_data_path():
    """AI 학습 데이터 파일 경로 반환"""
    if getattr(sys, 'frozen', False):
        # 배포 환경 - 사용자 데이터 디렉토리 사용
        return os.path.join(get_db_dir(), 'ai_learning_data.json')
    else:
        # 개발 환경 - 프로젝트 내 data 폴더 사용 (계정별 폴더 사용)
        base_dir = os.path.join(get_app_base_dir(), 'data')
        
        # 사용자 계정이 설정되어 있으면 하위 폴더 사용
        if _current_user_account:
            data_dir = os.path.join(base_dir, _current_user_account)
        else:
            data_dir = base_dir
        
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'ai_learning_data.json')


def get_theme_config_path():
    """테마 설정 파일 경로 반환"""
    if _current_user_account:
        # 사용자 계정이 있으면 사용자별 폴더 사용 (일관성 있게 get_config_dir 사용)
        config_dir = get_config_dir()
        return os.path.join(config_dir, 'theme_config.json')
    else:
        # 로그인 전에는 임시 경로 사용 (공통 폴더 생성 방지)
        if getattr(sys, 'frozen', False):
            # 배포 환경 - 사용자 Documents 폴더 직접 사용 (동적 스캔)
            base_dir = find_noahai_dir()
            os.makedirs(base_dir, exist_ok=True)
            return os.path.join(base_dir, 'theme_config.json')
        else:
            # 개발 환경 - 프로젝트 data 폴더 직접 사용
            base_dir = os.path.join(get_app_base_dir(), 'data')
            os.makedirs(base_dir, exist_ok=True)
            return os.path.join(base_dir, 'theme_config.json')

def get_token_file_path():
    """토큰 파일 경로 반환"""
    return os.path.join(get_app_data_dir(), 'token.json')

def get_credentials_file_path():
    """자격 증명 파일 경로 반환"""
    return os.path.join(get_app_data_dir(), 'credentials.json')

def get_reports_dir():
    """AI 리포트 디렉토리 반환"""
    reports_dir = os.path.join(get_app_data_dir(), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir

def get_assets_dir():
    """에셋 디렉토리 반환"""
    assets_dir = os.path.join(get_app_data_dir(), 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    return assets_dir

def get_chart_analyzer_assets_dir():
    """차트 분석기 에셋 디렉토리 반환"""
    chart_dir = os.path.join(get_assets_dir(), 'chart_analyzer')
    os.makedirs(chart_dir, exist_ok=True)
    return chart_dir

def get_cache_dir():
    """캐시 디렉토리 반환"""
    cache_dir = os.path.join(get_app_data_dir(), 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def get_chart_uploads_cache_dir():
    """차트 업로드 캐시 디렉토리 반환"""
    upload_dir = os.path.join(get_cache_dir(), 'chart_uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

def get_exchange_overrides_path():
    """거래소 오버라이드 파일 경로 반환"""
    return os.path.join(get_app_data_dir(), 'exchange_overrides.json')

def get_exchange_ai_learning_data_path(exchange_name: str):
    """거래소별 AI 학습 데이터 파일 경로 반환"""
    return os.path.join(get_app_data_dir(), f'ai_learning_data_{exchange_name}.json')

def is_frozen():
    """PyInstaller 배포 환경인지 확인"""
    return getattr(sys, 'frozen', False)

def find_noahai_dir():
    """NoahAI 디렉토리 찾기 (동적 스캔)"""
    base_docs_dir = os.path.join(os.path.expanduser('~'), 'Documents')
    canonical_dir = os.path.join(base_docs_dir, 'NoahAI')

    # v3.9.0.x와 v3.9.1.x의 정본 경로를 항상 먼저 사용한다. 백업/복사
    # 폴더(NoahAI_old 등)가 함께 있을 때 os.listdir 순서로 잘못 선택하지 않는다.
    if os.path.isdir(canonical_dir):
        return canonical_dir

    # 과거에 이름이 달라진 NoahAI 폴더만 있는 경우에는 결정적인 순서로 승계한다.
    if not os.path.isdir(base_docs_dir):
        return canonical_dir
    for item in sorted(os.listdir(base_docs_dir)):
        if item.startswith('NoahAI'):
            item_path = os.path.join(base_docs_dir, item)
            if os.path.isdir(item_path):
                return item_path

    # NoahAI 폴더가 없으면 기본 폴더 반환
    return canonical_dir

def find_available_account_dir():
    """사용 가능한 계정 디렉토리 찾기 (순차 번호 방식)"""
    base_dir = find_noahai_dir()
    
    # 기본 폴더가 사용 가능한지 확인
    if not os.path.exists(base_dir):
        return base_dir
    
    # 순차적으로 번호를 붙여서 사용 가능한 폴더 찾기
    counter = 2
    while True:
        test_dir = f"{base_dir}{counter}"
        if not os.path.exists(test_dir):
            return test_dir
        counter += 1

def get_account_info_from_token():
    """토큰 파일에서 계정 정보 읽기 (강화된 버전)"""
    try:
        # 개발환경에서는 프로젝트 data 폴더와 사용자별 폴더 모두 확인
        if not getattr(sys, 'frozen', False):
            # 개발 환경 - 기본 경로와 사용자별 폴더 모두 확인
            base_data_dir = os.path.join(get_app_base_dir(), 'data')
            possible_paths = [
                os.path.join(base_data_dir, 'token.json'),  # 기본 경로
            ]
            
            # 사용자별 폴더 확인
            if os.path.exists(base_data_dir):
                for item in os.listdir(base_data_dir):
                    item_path = os.path.join(base_data_dir, item)
                    if os.path.isdir(item_path):
                        token_path = os.path.join(item_path, 'token.json')
                        if os.path.exists(token_path):
                            possible_paths.append(token_path)
            
            # 디버그 출력 (환경변수 NOAHAI_DEBUG_PATHS=1 일 때만)
            if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                print(f"개발환경 토큰 파일 검색: {len(possible_paths)}개 경로 확인")
                for path in possible_paths:
                    print(f"   - {path}")
            
            for token_path in possible_paths:
                if os.path.exists(token_path):
                    with open(token_path, 'r', encoding='utf-8') as f:
                        token_data = json.load(f)
                        if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                            print(f"토큰 파일 읽기 성공: {token_path}")
                        
                        # user_info 객체에서 id 가져오기
                        if 'user_info' in token_data and 'id' in token_data['user_info']:
                            user_id = token_data['user_info']['id']
                            if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                                print(f"[OK] user_info.id에서 사용자 ID 발견: {user_id}")
                            return user_id, token_path
                        
                        # 직접 user_id나 username 확인
                        user_id = token_data.get('user_id', token_data.get('username', ''))
                        if user_id:
                            if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                                print(f"[OK] 직접 키에서 사용자 ID 발견: {user_id}")
                            return user_id, token_path
                        
                        if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                            print(f"[WARNING] 토큰 파일에 사용자 ID 없음: {token_path}")
            return None, None
        
        # 배포 환경에서는 사용자 Documents 폴더 확인 (동적 스캔)
        base_docs_dir = os.path.join(os.path.expanduser('~'), 'Documents')
        possible_paths = []
        
        # NoahAI 폴더들 스캔
        for item in os.listdir(base_docs_dir):
            if item.startswith('NoahAI'):
                item_path = os.path.join(base_docs_dir, item)
                if os.path.isdir(item_path):
                    # NoahAI 폴더 내의 사용자별 폴더들 스캔
                    for user_folder in os.listdir(item_path):
                        user_folder_path = os.path.join(item_path, user_folder)
                        if os.path.isdir(user_folder_path):
                            token_path = os.path.join(user_folder_path, 'token.json')
                            if os.path.exists(token_path):
                                possible_paths.append(token_path)
        
        # 기본 NoahAI 폴더도 확인
        base_noahai_path = os.path.join(base_docs_dir, 'NoahAI', 'token.json')
        if os.path.exists(base_noahai_path):
            possible_paths.append(base_noahai_path)
        
        if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
            print(f"[DEBUG] 배포환경 토큰 파일 검색: {len(possible_paths)}개 경로 확인")
            for path in possible_paths:
                print(f"   - {path}")
        
        for token_path in possible_paths:
            if os.path.exists(token_path):
                with open(token_path, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                    if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                        print(f"[OK] 토큰 파일 읽기 성공: {token_path}")
                    
                    # user_info 객체에서 id 가져오기
                    if 'user_info' in token_data and 'id' in token_data['user_info']:
                        user_id = token_data['user_info']['id']
                        if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                            try:
                                import sys as _sys
                                print(f"[OK] user_info.id에서 사용자 ID 발견: {user_id}", file=_sys.stderr)
                            except Exception:
                                pass
                        return user_id, token_path
                    
                    # 직접 user_id나 username 확인
                    user_id = token_data.get('user_id', token_data.get('username', ''))
                    if user_id:
                        if os.getenv('NOAHAI_DEBUG_PATHS') == '1':
                            try:
                                import sys as _sys
                                print(f"[OK] 직접 키에서 사용자 ID 발견: {user_id}", file=_sys.stderr)
                            except Exception:
                                pass
                        return user_id, token_path
                    
                    # 디버깅 로그 추가 필요
                    try:
                        import sys as _sys
                        print(f"[WARNING] 토큰 파일에 사용자 ID 없음: {token_path}", file=_sys.stderr)
                    except Exception:
                        pass
        
        # 디버깅 로그 추가 필요
        try:
            import sys as _sys
            print("[ERROR] 사용 가능한 토큰 파일을 찾지 못함", file=_sys.stderr)
        except Exception:
            pass
        return None, None
        
    except Exception as e:
        # 디버깅 로그 추가 필요
        try:
            import sys as _sys, traceback
            print(f"[ERROR] 토큰 파일 읽기 오류: {e}", file=_sys.stderr)
            print(traceback.format_exc(), file=_sys.stderr)
        except Exception:
            pass
        return None, None

def update_settings_with_template():
    """기존 설정 파일을 템플릿과 병합하여 누락된 항목 추가"""
    try:
        import json
        
        # 현재 설정 파일 경로
        current_settings_path = os.path.join(get_config_dir(), 'settings.json')
        template_settings_path = os.path.join(get_config_dir(), 'settings_template.json')
        
        # 현재 설정 파일이 없으면 업데이트 불필요
        if not os.path.exists(current_settings_path):
            print("[WARNING] 현재 설정 파일이 없어 업데이트 불필요")
            return False
        
        # 템플릿 파일이 없으면 업데이트 불가
        if not os.path.exists(template_settings_path):
            print("[WARNING] 템플릿 파일이 없어 업데이트 불가")
            return False
        
        from config.settings import read_settings_json_file

        # 현재 설정과 템플릿을 Windows locale과 무관하게 로드
        current_settings, _ = read_settings_json_file(current_settings_path)
        template_settings, _ = read_settings_json_file(template_settings_path)
        
        # 누락된 항목만 최신 설정 정본 위에 경로 단위로 추가한다. 이
        # 호환 함수가 오래된 전체 settings snapshot을 다시 쓰지 못하게 한다.
        changes = {}
        
        # signal_thresholds 섹션 추가
        if 'signal_thresholds' not in current_settings:
            changes['signal_thresholds'] = template_settings.get('signal_thresholds', {})
            print("[OK] signal_thresholds 섹션 추가됨")
        
        # analyzer_settings 섹션 추가
        if 'analyzer_settings' not in current_settings:
            changes['analyzer_settings'] = template_settings.get('analyzer_settings', {})
            print("[OK] analyzer_settings 섹션 추가됨")
        
        # 기존 섹션 내 누락된 항목들 추가
        for section in ['signal_thresholds', 'analyzer_settings']:
            if section in current_settings and section in template_settings:
                for key, value in template_settings[section].items():
                    if key not in current_settings[section]:
                        changes[f'{section}.{key}'] = value
                        print(f"[OK] {section}.{key} 추가됨")
        
        # 업데이트된 설정 저장
        if changes:
            from config.settings import patch_settings_paths
            if not patch_settings_paths(changes):
                print("[ERROR] 설정 경로 병합 저장 실패")
                return False
            print(f"[OK] 설정 파일 업데이트 완료: {current_settings_path}")
            return True
        else:
            print("ℹ️ 업데이트할 항목이 없음")
            return False
            
    except Exception as e:
        print(f"[ERROR] 설정 업데이트 중 오류: {e}")
        return False

def print_path_info():
    """경로 정보 출력 (디버깅용)"""
    print("="*50)
    print("경로 정보")
    print("="*50)
    print(f"실행 환경: {'배포 (PyInstaller)' if is_frozen() else '개발'}")
    print(f"현재 사용자 계정: {get_current_user_account() or '설정되지 않음'}")
    print(f"기본 디렉토리: {get_app_base_dir()}")
    print(f"데이터 디렉토리: {get_app_data_dir()}")
    print(f"로그 디렉토리: {get_log_dir()}")
    print(f"로그 파일: {get_log_file_path()}")
    print(f"설정 디렉토리: {get_config_dir()}")
    print(f"데이터베이스 디렉토리: {get_db_dir()}")
    print(f"데이터베이스 파일: {get_db_file_path()}")
    print(f"토큰 파일: {get_token_file_path()}")
    print(f"AI 학습 데이터: {get_ai_learning_data_path()}")
    
    if is_frozen():
        print(f"실행 파일: {sys.executable}")
        print(f"임시 디렉토리: {getattr(sys, '_MEIPASS', 'N/A')}")
    
    print("="*50)

if __name__ == "__main__":
    print_path_info()
