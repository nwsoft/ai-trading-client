#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빌드 검증 스크립트
PyInstaller 빌드 시 필수 파일들이 제대로 포함되는지 확인
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath):
    """파일 존재 여부 확인"""
    return os.path.exists(filepath)

def check_folder_exists(folderpath):
    """폴더 존재 여부 확인"""
    return os.path.isdir(folderpath)

def verify_build_structure():
    """빌드에 필요한 구조 검증"""

    print("=" * 60)
    print("🔍 NoahAI 빌드 구조 검증")
    print("=" * 60)

    base_path = Path(__file__).parent

    # 필수 파일 체크
    required_files = [
        'main.py',
        'path_utils.py',
        'strategy_customizer.py',
        'ai_chat_strategy.py',
        'aiautotrade.spec',
        'config/settings_template.json',
        'config/token_template.json',
        'config/theme_config.json',
        'utils/time_sync.py',
        'utils/admin_utils.py',
        'utils/fixed_colors.py',
    ]

    # 필수 폴더 체크
    required_folders = [
        'api',
        'config',
        'trading',
        'trading/ai',
        'trading/exchanges',
        'ui',
        'log_system',
        'utils',
        'docs',
    ]

    print("\n📁 필수 폴더 확인:")
    folder_ok = True
    for folder in required_folders:
        folder_path = base_path / folder
        exists = check_folder_exists(folder_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {folder}")
        if not exists:
            folder_ok = False

    print("\n📄 필수 파일 확인:")
    file_ok = True
    for file in required_files:
        file_path = base_path / file
        exists = check_file_exists(file_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {file}")
        if not exists:
            file_ok = False

    # utils 폴더 상세 검증
    print("\n🔍 utils 폴더 상세 확인:")
    utils_path = base_path / 'utils'
    if check_folder_exists(utils_path):
        utils_files = list(utils_path.glob('*.py'))
        print(f"  📦 총 {len(utils_files)}개 파일:")
        for file in sorted(utils_files):
            print(f"     - {file.name}")
    else:
        print("  ❌ utils 폴더가 존재하지 않습니다!")

    # aiautotrade.spec 검증
    print("\n📋 aiautotrade.spec 검증:")
    spec_path = base_path / 'aiautotrade.spec'
    if check_file_exists(spec_path):
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec_content = f.read()

        checks = {
            "utils 폴더 포함": "('utils', 'utils')" in spec_content,
            "config 폴더 포함": "('config/settings_template.json', 'config')" in spec_content,
            "trading 폴더 포함": "('trading', 'trading')" in spec_content,
            "api 폴더 포함": "('api', 'api')" in spec_content,
            "log_system 폴더 포함": "('log_system', 'log_system')" in spec_content,
        }

        for check_name, check_result in checks.items():
            status = "✅" if check_result else "❌"
            print(f"  {status} {check_name}")
            if not check_result:
                file_ok = False
    else:
        print("  ❌ aiautotrade.spec 파일이 존재하지 않습니다!")
        file_ok = False

    # 시간 동기화 기능 import 테스트
    print("\n🧪 시간 동기화 모듈 import 테스트:")
    try:
        from utils.time_sync import ensure_time_sync, check_time_sync, get_binance_server_time, sync_windows_time
        print("  ✅ utils.time_sync 모듈 import 성공")
        print("     - ensure_time_sync()")
        print("     - check_time_sync()")
        print("     - get_binance_server_time()")
        print("     - sync_windows_time()")
    except ImportError as e:
        print(f"  ❌ utils.time_sync 모듈 import 실패: {e}")
        file_ok = False

    # 최종 결과
    print("\n" + "=" * 60)
    if folder_ok and file_ok:
        print("✅ 모든 검증 통과! 빌드 준비 완료")
        print("=" * 60)
        print("\n다음 명령어로 빌드 실행:")
        print("  pyinstaller aiautotrade.spec")
        return 0
    else:
        print("❌ 검증 실패! 누락된 파일/폴더를 확인하세요")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(verify_build_structure())
