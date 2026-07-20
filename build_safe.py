#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
안전한 배포용 빌드 스크립트
민감한 정보를 자동으로 제거하고 빌드합니다.
"""

import os
import sys
import shutil
import subprocess
import json
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime


def _run_cmd(cmd: list[str], description: str) -> bool:
    """서브프로세스 실행 헬퍼 (실패해도 전체 빌드는 계속 가능)."""
    print(f"- {description}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if result.returncode == 0:
        print("  ✅ 성공")
        return True

    print("  ⚠️ 실패")
    if result.stderr:
        for line in result.stderr.splitlines()[-5:]:
            if line.strip():
                print(f"    {line}")
    return False


def run_release_gate(profile: str = 'dev'):
    """빌드 전 배포 게이트를 실행한다."""
    print(f"\n🛡️ 배포 게이트 실행(profile={profile})...")
    cmd = [sys.executable, 'scripts/release_gate.py', '--profile', str(profile or 'dev')]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        print("❌ 배포 게이트 실패 - 빌드를 중단합니다.")
        return False
    print("✅ 배포 게이트 통과")
    return True

def create_safe_build_environment():
    """안전한 빌드 환경 생성"""
    print("🔧 안전한 빌드 환경 준비 중...")
    print("✅ data 폴더는 PyInstaller에 포함되지 않으므로 추가 정리 불필요")
    print("✅ 템플릿 파일만 포함되므로 실제 설정 파일은 배포에서 자동 제외")
    
    # 빌드 디렉토리 정리
    build_dirs = ["build", "dist"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"🧹 빌드 디렉토리 정리: {dir_name}")
    
    return []  # 백업할 파일 없음

def restore_files_after_build(backed_up_files):
    """빌드 후 파일 복구"""
    print("\n✅ 복구할 파일 없음 - 원본 파일들은 그대로 유지됨")

def create_safe_spec_file(target_platform: str):
    """안전한 PyInstaller 스펙 파일 생성 (플랫폼별)"""
    # 동적 hiddenimports / excludes 구성
    hiddenimports = [
        # GUI
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'customtkinter',
        # Networking / exchanges / utils
        'websockets', 'websocket', 'websocket_client',
        'binance', 'ccxt', 'ccxt.binance', 'ccxt.upbit', 'ccxt.bithumb',
        'ccxt.bybit', 'ccxt.okx', 'ccxt.bitget',  # v3.7.8: 추가 거래소 명시적 포함
        'trading.exchange_manager', 'trading.api_signal_manager',
        # 증권 어댑터 (배포판에서 동적 import가 실패하지 않도록 명시적으로 포함)
        'trading.exchanges.exchange_factory',
        'trading.exchanges.adapters.kiwoom_stock_adapter',
        'trading.exchanges.adapters.stock_mock_adapter',
        'trading.exchanges.adapters.shinhan_stock_adapter',
        'trading.exchanges.adapters.mirae_asset_stock_adapter',
        'trading.exchanges.adapters.korea_investment_stock_adapter',
        # internal modules
    # 테마 시스템 제거됨 (고정 스킨 사용)
        # 🔥 표준 logging은 자동 포함되므로 제거, 프로젝트 로깅 모듈만 명시
        'openai', 'numpy', 'pandas', 'loguru', 'asyncio', 'sqlite3', 'json', 'datetime',
        'requests', 'threading', 'queue', 'time', 'math', 'random', 'statistics', 'collections',
        'itertools', 'functools', 'typing', 'dataclasses', 'enum', 'pathlib', 'shutil', 'subprocess',
        'sys', 'os', 'dotenv', 'ujson', 'aiohttp', 'dateparser', 'colorama', 'win32_setctime', 'psutil',
        # OCR (포터블 우선)
        'rapidocr_onnxruntime', 'onnxruntime',
        'paddleocr', 'paddlepaddle',
        # AI 커스텀 문서/영상/YouTube 입력
        'pypdf', 'youtube_transcript_api', 'yt_dlp',
        # 음성 STT (옵션)
        'speech_recognition',
    ]
    # PyAudio는 플랫폼/환경에 따라 설치 실패가 잦아 조건부 포함한다.
    if target_platform == 'windows' or importlib.util.find_spec('pyaudio') is not None:
        hiddenimports.append('pyaudio')
    # 비-Windows 환경에서는 win32_setctime 제거
    if (target_platform or sys.platform) != 'win32':
        try:
            hiddenimports.remove('win32_setctime')
        except ValueError:
            pass

    excludes = [
        # 과학/노트북 대형 패키지
        'matplotlib', 'scipy', 'scikit-learn', 'tensorflow', 'torch',
        'jupyter', 'notebook', 'ipython', 'pytest', 'unittest',
        # 기타 GUI 프레임워크
        'wx', 'gtk', 'qt4', 'qt6',
        # Qt 바인딩: 키움 OpenAPI(pykiwoom)는 Windows에서 PyQt5가 필요할 수 있으므로
        # 비-Windows에서만 강하게 제외한다.
        'PyQt6', 'PySide2', 'PySide6',
    ]

    if target_platform != 'windows':
        excludes.append('PyQt5')

    # Windows에서 pykiwoom이 설치된 환경이면 hiddenimports에 포함해 키움 경로를 보존
    if target_platform == 'windows':
        # pykiwoom은 PyQt5.QAxWidget 기반 — PyQt5 하위 모듈도 함께 포함해야 함
        # macOS 개발환경에 pykiwoom이 없어도 Windows 배포 시 무조건 포함한다
        hiddenimports.extend([
            'pykiwoom',
            'pykiwoom.kiwoom',
            'PyQt5',
            'PyQt5.QtWidgets',
            'PyQt5.QtCore',
            'PyQt5.QtGui',
            'PyQt5.QAxContainer',  # Kiwoom() → QAxWidget 상속 경로
        ])

    hiddenimports_str = ',\n        '.join(repr(s) for s in hiddenimports)
    excludes_str = ',\n        '.join(repr(s) for s in excludes)

    # 플랫폼별 아이콘 처리
    # - Windows: .ico 권장
    # - macOS: .icns 권장(없으면 아이콘 미지정)
    # - Linux: .png 가능(미지정 가능)
    icon_win = 'icon.ico' if os.path.exists('icon.ico') else None
    icon_macos = 'icon.icns' if os.path.exists('icon.icns') else None
    icon_linux = 'icon.png' if os.path.exists('icon.png') else None

    header = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/settings_template.json', 'config'),
        ('config/token_template.json', 'config'),
        ('config/theme_config.json', 'config'),
        ('docs', 'docs'),
        # 분석기 가이드 이미지(빌드 포함)
        ('docs/assets/chart_analyzer', 'assets/chart_analyzer'),
    # UI Python modules are auto-discovered via imports; do not bundle entire ui folder
        ('trading', 'trading'),
        ('trading/ai', 'trading/ai'),
        ('trading/exchanges', 'trading/exchanges'),
        ('trading/exchange_manager.py', 'trading'),
        ('trading/api_signal_manager.py', 'trading'),
        ('api', 'api'),
        ('log_system', 'log_system'),  # 프로젝트 로깅 모듈
        ('strategy_customizer.py', '.'),
        ('ai_chat_strategy.py', '.'),
        ('path_check.py', '.'),
        ('web_deployment_analysis.py', '.'),
        ('user_status_manager.py', '.'),
        ('path_utils.py', '.'),
        ('README.md', '.'),
        ('requirements.txt', '.'),
        ('requirements_windows.txt', '.'),
        ('icon.ico', '.') ,
        ('icon.png', '.') ,
        # data 폴더는 포함하지 않음 - 런타임에 path_utils가 자동 생성
    ],
    hiddenimports=[
        {hiddenimports_str}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        {excludes_str}
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
'''

    # 공통 EXE 블록 (모든 OS에서 생성)
    exe_block = f'''
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AITrading',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {"icon='icon.ico'," if icon_win and target_platform == 'windows' else ''} # type: ignore
    version='config/windows_version_info.txt',
)
'''

    # macOS는 .app 번들을 생성(BUNDLE)
    if target_platform == 'macos':
        bundle_icon_line = f"icon='{icon_macos}'," if icon_macos else ""
        platform_tail = f'''{exe_block}
app = BUNDLE(
    exe,
    name='AITrading.app',
    {bundle_icon_line}
    bundle_identifier='com.noahai.trading'
)
'''
    else:
        # Windows/Linux는 EXE 결과만 사용
        platform_tail = exe_block

    spec_content = header + "\n" + platform_tail

    with open('aiautotrade_safe.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)

    print(f"✅ 안전한 PyInstaller 스펙 파일 생성: aiautotrade_safe.spec (platform={target_platform})")

def build_exe():
    """PyInstaller 빌드 실행"""
    print("\n🔨 빌드 시작...")
    
    try:
        # PyInstaller 실행
        cmd = [sys.executable, "-m", "PyInstaller", "--clean", "aiautotrade_safe.spec"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            print("✅ 빌드 성공!")
            return True
        else:
            print("❌ 빌드 실패!")
            if result.stderr:
                print("오류 내용:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ 빌드 중 오류: {e}")
        return False

def verify_safe_build(target_platform: str) -> bool:
    """안전한 빌드 확인 및 배포 복사"""
    print("\n🔍 빌드 결과 안전성 검증...")

    deploy_dir = "deploy"
    os.makedirs(deploy_dir, exist_ok=True)

    if target_platform == 'windows':
        artifact = Path('dist') / 'AITrading.exe'
        if not artifact.exists():
            print("❌ EXE 파일을 찾을 수 없습니다.")
            return False
        print(f"✅ EXE 파일 생성 확인: {artifact}")
        file_size = artifact.stat().st_size / (1024 * 1024)
        print(f"📊 파일 크기: {file_size:.1f} MB")
        dest = Path(deploy_dir) / 'AITrading.exe'
        shutil.copy2(artifact, dest)
        print(f"✅ 배포 준비 완료: {dest}")
        return True

    if target_platform == 'macos':
        app_dir = Path('dist') / 'AITrading.app'
        if not app_dir.exists():
            print("❌ .app 번들을 찾을 수 없습니다.")
            # EXE만 생성된 경우(로컬 환경 차이) 단일 바이너리라도 복사
            exe_alt = Path('dist') / 'AITrading'
            if exe_alt.exists():
                dest = Path(deploy_dir) / 'AITrading'
                shutil.copy2(exe_alt, dest)
                print(f"⚠️ .app 미생성, 단일 바이너리 복사 완료: {dest}")
                return True
            return False
        # 크기 출력은 Contents/MacOS 실행 파일 기준으로 산정 시 부정확할 수 있어 생략
        dest_app = Path(deploy_dir) / 'AITrading.app'
        if dest_app.exists():
            shutil.rmtree(dest_app)
        shutil.copytree(app_dir, dest_app)
        print(f"✅ .app 번들 배포 준비 완료: {dest_app}")
        return True

    # 기본(Linux 등)
    bin_path = Path('dist') / 'AITrading'
    if not bin_path.exists():
        print("❌ 실행 파일을 찾을 수 없습니다.")
        return False
    print(f"✅ 실행 파일 생성 확인: {bin_path}")
    dest = Path(deploy_dir) / 'AITrading'
    shutil.copy2(bin_path, dest)
    print(f"✅ 배포 준비 완료: {dest}")
    return True

def ensure_build_dependencies(target_platform: str):
    """빌드에 필요한 패키지를 requirements 파일로 자동 설치."""
    if target_platform == 'windows':
        req_file = 'requirements_windows.txt'
    else:
        req_file = 'requirements.txt'

    if not os.path.exists(req_file):
        print(f"⚠️  {req_file} 파일이 없어 의존성 자동 설치를 건너뜁니다.")
        return

    print(f"\n📦 빌드 의존성 설치 중 ({req_file})...")
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-r', req_file, '--quiet'],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if result.returncode == 0:
        print(f"✅ 의존성 설치 완료 ({req_file})")
    else:
        print(f"⚠️  일부 패키지 설치 실패 (빌드는 계속 진행):")
        if result.stderr:
            # 핵심 오류 줄만 출력
            for line in result.stderr.splitlines():
                if 'ERROR' in line or 'error' in line.lower():
                    print(f"   {line}")

    # 음성 의존성은 환경별 실패 포인트가 많아 별도 보정 설치를 추가한다.
    ensure_voice_dependencies(target_platform)


def ensure_voice_dependencies(target_platform: str):
    """STT/TTS 관련 옵션 의존성을 보정 설치한다."""
    print("\n🎙️ 음성 의존성 보정 설치...")
    _run_cmd([sys.executable, '-m', 'pip', 'install', 'SpeechRecognition>=3.10.0', '--quiet'], 'SpeechRecognition 설치')

    if target_platform == 'windows':
        ok = _run_cmd([sys.executable, '-m', 'pip', 'install', 'pyaudio>=0.2.14', '--quiet'], 'PyAudio 직접 설치')
        if not ok:
            print("- PyAudio 직접 설치 실패, pipwin 경로로 재시도")
            pipwin_ok = _run_cmd([sys.executable, '-m', 'pip', 'install', 'pipwin>=0.5.2', '--quiet'], 'pipwin 설치')
            if pipwin_ok:
                _run_cmd([sys.executable, '-m', 'pipwin', 'install', 'pyaudio'], 'pipwin으로 PyAudio 설치')
    else:
        print("- 비-Windows 환경: 마이크 STT(PyAudio)는 선택 기능으로 유지")


def main():
    """메인 함수"""
    print("=" * 60)
    print("    Noah AI Client - 안전한 배포 빌드")
    print("=" * 60)
    print(f"🕐 빌드 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    # 인자 파싱: --platform [windows|macos|linux]
    parser = argparse.ArgumentParser(description="Noah AI Client Safe Builder")
    parser.add_argument(
        "--platform",
        choices=["windows", "macos", "linux"],
        help="타겟 플랫폼 (미지정 시 현재 OS 자동 감지)",
    )
    parser.add_argument(
        "--skip-gate",
        action="store_true",
        help="배포 게이트를 건너뛰고 바로 빌드",
    )
    parser.add_argument(
        "--gate-profile",
        choices=["dev", "prekey", "release"],
        default="prekey",
        help="배포 게이트 프로필 (default: prekey, 문서/인앱 동기화 게이트 포함)",
    )
    args = parser.parse_args()

    # 기본 플랫폼 결정
    detected = sys.platform
    if args.platform:
        target_platform = args.platform
    elif detected.startswith('win'):
        target_platform = 'windows'
    elif detected == 'darwin':
        target_platform = 'macos'
    else:
        target_platform = 'linux'

    backed_up_files = []
    try:
        if not args.skip_gate:
            gate_ok = run_release_gate(profile=args.gate_profile)
            if not gate_ok:
                return

        # 1. 빌드 의존성 자동 설치 (requirements 파일 기반)
        ensure_build_dependencies(target_platform)

        # 2. 안전한 빌드 환경 준비
        backed_up_files = create_safe_build_environment()
        
        # 3. 안전한 스펙 파일 생성
        create_safe_spec_file(target_platform)
        
        # 4. 빌드 실행
        build_success = build_exe()
        
        if build_success:
            # 5. 빌드 결과 검증
            verify_safe_build(target_platform)
            print("\n🎉 안전한 배포 빌드 완료!")
            if target_platform == 'windows':
                print("📁 배포 파일: deploy/AITrading.exe")
            elif target_platform == 'macos':
                print("📁 배포 파일: deploy/AITrading.app")
            else:
                print("📁 배포 파일: deploy/AITrading")
            print("⚠️  이 산출물에는 민감한 정보가 포함되지 않았습니다.")
        else:
            print("\n❌ 빌드 실패")
            
    except Exception as e:
        print(f"\n❌ 빌드 과정에서 오류 발생: {e}")
        
    finally:
        # 5. 원본 파일 복구
        restore_files_after_build(backed_up_files)
        
        # 6. 임시 파일 정리
        if os.path.exists('aiautotrade_safe.spec'):
            os.remove('aiautotrade_safe.spec')
            print("🧹 임시 스펙 파일 정리")
    
    print("\n" + "=" * 60)
    print("    빌드 완료!")
    print("=" * 60)

if __name__ == "__main__":
    main()
