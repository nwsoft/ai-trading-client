#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Path Debugging Script - 경로 디버깅 스크립트"""

import sys
import os

# path_utils 임포트
from path_utils import (
    print_path_info,
    get_current_user_account,
    set_current_user_account,
    is_frozen,
    find_noahai_dir,
    get_app_data_dir,
    get_log_dir,
    get_config_dir
)

print("=" * 60)
print("🔍 NoahAI Path Debugging - 경로 디버깅")
print("=" * 60)
print()

print(f"📌 실행 환경: {'배포 (exe)' if is_frozen() else '개발 (python)'}")
print(f"📌 Python 버전: {sys.version}")
print(f"📌 실행 파일: {sys.executable}")
print()

# PyInstaller 정보
if is_frozen():
    print(f"📦 _MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    print()

# 사용자 계정 확인 및 자동 설정
current_account = get_current_user_account()
if not current_account:
    # 기존 토큰 파일에서 계정 찾기
    from path_utils import get_account_info_from_token
    user_id, token_path = get_account_info_from_token()
    if user_id:
        set_current_user_account(user_id)
        current_account = user_id
        print(f"👤 기존 계정 자동 발견: {user_id}")
        print(f"   토큰 경로: {token_path}")
    else:
        print(f"👤 현재 사용자 계정: 설정되지 않음")
        print(f"   ⚠️ 로그인 후 다시 실행하면 정확한 경로를 확인할 수 있습니다.")
else:
    print(f"👤 현재 사용자 계정: {current_account}")
print()

# Documents 폴더 스캔
print("📂 Documents 폴더 스캔:")
docs_dir = os.path.join(os.path.expanduser('~'), 'Documents')
print(f"   경로: {docs_dir}")
try:
    items = os.listdir(docs_dir)
    noah_folders = [item for item in items if item.startswith('NoahAI')]
    if noah_folders:
        print(f"   NoahAI 폴더 발견: {noah_folders}")
        for folder in noah_folders:
            folder_path = os.path.join(docs_dir, folder)
            print(f"   - {folder_path}")
            # 하위 폴더 확인
            try:
                sub_items = os.listdir(folder_path)
                print(f"     하위 항목: {len(sub_items)}개")
                for sub in sub_items[:5]:  # 최대 5개만 표시
                    print(f"       • {sub}")
            except Exception:
                pass
    else:
        print("   ⚠️ NoahAI 폴더 없음")
except Exception as e:
    print(f"   ❌ 오류: {e}")
print()

# find_noahai_dir() 결과
print("🔍 find_noahai_dir() 결과:")
noahai_dir = find_noahai_dir()
print(f"   {noahai_dir}")
print(f"   존재 여부: {os.path.exists(noahai_dir)}")
print()

# 각 디렉토리 경로
print("📁 사용될 디렉토리 경로:")
from path_utils import (
    get_reports_dir, get_assets_dir, get_cache_dir,
    get_chart_analyzer_assets_dir, get_chart_uploads_cache_dir
)
print(f"   데이터:         {get_app_data_dir()}")
print(f"   로그:           {get_log_dir()}")
print(f"   설정:           {get_config_dir()}")
print(f"   리포트:         {get_reports_dir()}")
print(f"   에셋:           {get_assets_dir()}")
print(f"   캐시:           {get_cache_dir()}")
print(f"   차트분석기:     {get_chart_analyzer_assets_dir()}")
print(f"   차트업로드:     {get_chart_uploads_cache_dir()}")
print()

# 실제 파일 존재 확인
print("📄 실제 파일 존재 확인:")
from path_utils import (
    get_log_file_path, get_db_file_path, get_token_file_path,
    get_exchange_overrides_path, get_exchange_ai_learning_data_path
)

files_to_check = [
    ("로그 파일", get_log_file_path()),
    ("DB 파일", get_db_file_path()),
    ("토큰 파일", get_token_file_path()),
    ("거래소 오버라이드", get_exchange_overrides_path()),
    ("AI 학습 (binance)", get_exchange_ai_learning_data_path('binance')),
]

for name, path in files_to_check:
    exists = os.path.exists(path)
    size = ""
    if exists:
        try:
            size_bytes = os.path.getsize(path)
            if size_bytes > 1024*1024:
                size = f" ({size_bytes/(1024*1024):.1f}MB)"
            elif size_bytes > 1024:
                size = f" ({size_bytes/1024:.1f}KB)"
            else:
                size = f" ({size_bytes}B)"
        except:
            pass
    print(f"   {name}: {'✅' if exists else '❌'} {path}{size}")

print()
print("=" * 60)
print("경로 확인 완료!")
print("=" * 60)

input("\nPress Enter to exit...")

