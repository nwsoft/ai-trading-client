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
import ctypes
import hashlib
import struct
from pathlib import Path
from datetime import datetime


def _configure_console_output() -> None:
    """Keep Windows cp949 consoles from crashing on emoji/status glyph output."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


_configure_console_output()


WINDOWS_VC_RUNTIME_REQUIRED = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)
WINDOWS_VC_RUNTIME_OPTIONAL = (
    "concrt140.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "vcruntime140_threads.dll",
)
WINDOWS_VC_RUNTIME_NAMES = frozenset(
    WINDOWS_VC_RUNTIME_REQUIRED + WINDOWS_VC_RUNTIME_OPTIONAL
)
WINDOWS_VC_RUNTIME_ENV = "NOAHAI_VC_RUNTIME_DIR"
MINIMUM_ONNX_VC_LINKER = (14, 40)
WINDOWS_TKINTER_REQUIRED_MODULES = (
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "customtkinter",
)
PYINSTALLER_BLOCKING_MESSAGES = (
    "tkinter installation is broken",
    "missing module named tkinter",
    "missing module named _tkinter",
)


def is_windows_vc_runtime_name(entry_name: str) -> bool:
    """번들 경로와 무관하게 VC14 런타임 DLL 계열을 식별한다."""
    basename = str(entry_name).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return basename == "concrt140.dll" or (
        basename.endswith(".dll")
        and basename.startswith(("msvcp140", "vcruntime140"))
    )


def _read_pe_linker_version(file_path: Path) -> tuple[int, int]:
    """PE Optional Header에서 바이너리를 만든 링커 버전을 읽는다."""
    with file_path.open("rb") as pe_file:
        header = pe_file.read(4096)
    if len(header) < 64 or header[:2] != b"MZ":
        raise RuntimeError(f"PE 파일이 아닙니다: {file_path}")
    pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
    if pe_offset + 28 > len(header) or header[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise RuntimeError(f"PE 헤더를 읽을 수 없습니다: {file_path}")
    optional_header = pe_offset + 24
    return header[optional_header + 2], header[optional_header + 3]


def _find_onnxruntime_binary() -> Path:
    """onnxruntime을 import하지 않고 Windows pybind 바이너리 위치를 찾는다."""
    spec = importlib.util.find_spec("onnxruntime")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("onnxruntime 설치 위치를 찾을 수 없습니다.")
    for package_dir in map(Path, spec.submodule_search_locations):
        candidate = package_dir / "capi" / "onnxruntime_pybind11_state.pyd"
        if candidate.is_file():
            return candidate
    raise RuntimeError("onnxruntime_pybind11_state.pyd를 찾을 수 없습니다.")


def required_vc_runtime_version() -> tuple[int, int, int, int]:
    """현재 ONNX Runtime 링커보다 오래되지 않은 VC 런타임 하한을 계산한다."""
    linker = _read_pe_linker_version(_find_onnxruntime_binary())
    minimum = max(MINIMUM_ONNX_VC_LINKER, linker)
    if minimum[0] != 14:
        raise RuntimeError(f"지원하지 않는 ONNX Runtime MSVC 링커 버전: {minimum}")
    return minimum[0], minimum[1], 0, 0


def _windows_file_version(file_path: Path) -> tuple[int, int, int, int]:
    """Windows VERSIONINFO의 FileVersion을 외부 패키지 없이 읽는다."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("VC 런타임 버전 확인은 Windows 빌드 호스트에서만 실행할 수 있습니다.")

    version_api = ctypes.windll.version
    size = version_api.GetFileVersionInfoSizeW(str(file_path), None)
    if not size:
        raise RuntimeError(f"VERSIONINFO가 없는 VC 런타임입니다: {file_path}")
    buffer = ctypes.create_string_buffer(size)
    if not version_api.GetFileVersionInfoW(str(file_path), 0, size, buffer):
        raise RuntimeError(f"VERSIONINFO를 읽을 수 없습니다: {file_path}")

    value = ctypes.c_void_p()
    value_len = ctypes.c_uint()
    if not version_api.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_len)):
        raise RuntimeError(f"고정 버전 정보를 읽을 수 없습니다: {file_path}")

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32),
            ("dwProductVersionLS", ctypes.c_uint32),
            ("dwFileFlagsMask", ctypes.c_uint32),
            ("dwFileFlags", ctypes.c_uint32),
            ("dwFileOS", ctypes.c_uint32),
            ("dwFileType", ctypes.c_uint32),
            ("dwFileSubtype", ctypes.c_uint32),
            ("dwFileDateMS", ctypes.c_uint32),
            ("dwFileDateLS", ctypes.c_uint32),
        ]

    info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    if info.dwSignature != 0xFEEF04BD:
        raise RuntimeError(f"잘못된 VERSIONINFO 서명입니다: {file_path}")
    return (
        info.dwFileVersionMS >> 16,
        info.dwFileVersionMS & 0xFFFF,
        info.dwFileVersionLS >> 16,
        info.dwFileVersionLS & 0xFFFF,
    )


def _vc_runtime_candidate_dirs() -> list[Path]:
    """공식 Visual Studio VC143 CRT 재배포 디렉터리 후보를 최신순으로 찾는다."""
    candidates: list[Path] = []
    target_arch = "x64" if struct.calcsize("P") == 8 else "x86"
    explicit = os.environ.get(WINDOWS_VC_RUNTIME_ENV, "").strip()
    if explicit:
        candidates.append(Path(explicit))

    tools_redist = os.environ.get("VCToolsRedistDir", "").strip()
    if tools_redist:
        redist_root = Path(tools_redist)
        candidates.extend((redist_root / target_arch / "Microsoft.VC143.CRT", redist_root))

    program_roots = {
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
    }
    for raw_root in filter(None, program_roots):
        vs_root = Path(raw_root) / "Microsoft Visual Studio" / "2022"
        candidates.extend(
            vs_root.glob(f"*/VC/Redist/MSVC/*/{target_arch}/Microsoft.VC143.CRT")
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.resolve(strict=False)).lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(candidate)
    # 명시 경로는 항상 우선하고, 자동 탐색 경로는 최근 수정본을 우선한다.
    if explicit and unique:
        return unique[:1] + sorted(
            unique[1:], key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True
        )
    return sorted(
        unique, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True
    )


def validate_vc_runtime_dir(
    runtime_dir: Path,
    minimum_version: tuple[int, int, int, int],
) -> list[tuple[str, str]]:
    """VC143 DLL이 완전하고 동일 계열이며 ONNX 링커 이상인지 확인한다."""
    missing = [name for name in WINDOWS_VC_RUNTIME_REQUIRED if not (runtime_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"필수 VC143 DLL 누락({runtime_dir}): {', '.join(missing)}")

    selected = [
        (name, runtime_dir / name)
        for name in WINDOWS_VC_RUNTIME_REQUIRED + WINDOWS_VC_RUNTIME_OPTIONAL
        if (runtime_dir / name).is_file()
    ]
    versions = {name: _windows_file_version(path) for name, path in selected}
    too_old = {name: version for name, version in versions.items() if version < minimum_version}
    if too_old:
        details = ", ".join(f"{name}={'.'.join(map(str, version))}" for name, version in too_old.items())
        raise RuntimeError(
            f"ONNX Runtime 링커 {minimum_version[0]}.{minimum_version[1]}보다 오래된 VC 런타임: {details}"
        )

    release_lines = {version[:3] for version in versions.values()}
    if len(release_lines) != 1:
        details = ", ".join(f"{name}={'.'.join(map(str, version))}" for name, version in versions.items())
        raise RuntimeError(f"서로 다른 VC 런타임 세트가 섞여 있습니다: {details}")
    return [(name, str(path)) for name, path in selected]


def resolve_windows_vc_runtime_binaries() -> list[tuple[str, str]]:
    """빌드 아키텍처에 맞는 공식 단일 VC143 런타임 세트를 확정한다."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("Windows VC 런타임 수집은 Windows 빌드 호스트에서만 실행합니다.")
    minimum = required_vc_runtime_version()
    errors: list[str] = []
    accepted: list[tuple[tuple[int, int, int, int], Path, list[tuple[str, str]]]] = []
    explicit = os.environ.get(WINDOWS_VC_RUNTIME_ENV, "").strip()
    explicit_normalized = str(Path(explicit).resolve(strict=False)).lower() if explicit else ""
    for candidate in _vc_runtime_candidate_dirs():
        is_explicit = bool(
            explicit_normalized
            and str(candidate.resolve(strict=False)).lower() == explicit_normalized
        )
        try:
            binaries = validate_vc_runtime_dir(candidate, minimum)
            version = _windows_file_version(Path(binaries[0][1]))
            accepted.append((version, candidate, binaries))
            if is_explicit:
                break
        except RuntimeError as exc:
            errors.append(str(exc))
            if is_explicit:
                break
    if accepted:
        # 환경변수로 지정한 세트는 그대로 사용한다. 자동 탐색은 파일 버전이 가장
        # 높은 공식 세트를 선택해 디렉터리 수정 시각에 의존하지 않는다.
        version, candidate, binaries = accepted[0] if explicit_normalized else max(
            accepted, key=lambda item: item[0]
        )
        print(
            "✅ Windows VC143 런타임 단일 세트: "
            f"{candidate} · {'.'.join(map(str, version))} · ONNX linker >= {minimum[0]}.{minimum[1]}"
        )
        return binaries
    detail = "\n  - ".join(errors) if errors else "공식 VC143 CRT 디렉터리를 찾지 못했습니다."
    raise RuntimeError(
        "Windows 빌드를 중단합니다. 최신 Visual Studio 2022 Build Tools의 "
        "VC143 Redistributable(빌드 Python과 같은 x86/x64)을 설치하거나 "
        f"{WINDOWS_VC_RUNTIME_ENV}에 Microsoft.VC143.CRT 경로를 지정하세요.\n  - {detail}"
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_windows_vc_runtime_archive(
    artifact: Path,
    expected_binaries: list[tuple[str, str]],
) -> bool:
    """완성 EXE에 중첩/구형 VC DLL이 없고 검증 세트만 루트에 있는지 확인한다."""
    try:
        from PyInstaller.archive.readers import CArchiveReader

        archive = CArchiveReader(str(artifact))
        runtime_entries: dict[str, list[str]] = {}
        for entry_name in archive.toc:
            normalized = entry_name.replace("\\", "/")
            basename = normalized.rsplit("/", 1)[-1].lower()
            if is_windows_vc_runtime_name(normalized):
                runtime_entries.setdefault(basename, []).append(normalized)

        nested = [
            entry
            for entries in runtime_entries.values()
            for entry in entries
            if "/" in entry
        ]
        if nested:
            raise RuntimeError("하위 폴더 VC 런타임 잔존: " + ", ".join(sorted(nested)))

        expected_names = {name.lower() for name, _ in expected_binaries}
        unexpected = sorted(set(runtime_entries) - expected_names)
        if unexpected:
            raise RuntimeError("검증 세트 밖 VC 런타임 잔존: " + ", ".join(unexpected))

        for required in WINDOWS_VC_RUNTIME_REQUIRED:
            if runtime_entries.get(required) != [required]:
                raise RuntimeError(f"{required}가 EXE 루트에 정확히 한 개 존재하지 않습니다.")

        for name, source in expected_binaries:
            bundled = archive.extract(name)
            source_hash = hashlib.sha256(Path(source).read_bytes()).hexdigest()
            if _sha256_bytes(bundled) != source_hash:
                raise RuntimeError(f"{name}의 번들 SHA-256이 검증한 VC143 원본과 다릅니다.")
        print("✅ EXE VC 런타임 검증: 하위 중복 0개 · 공식 단일 세트 SHA-256 일치")
        return True
    except Exception as exc:
        print(f"❌ EXE VC 런타임 검증 실패: {exc}")
        return False


def validate_windows_tkinter_build_runtime() -> bool:
    """Reject build hosts where PyInstaller cannot initialize and collect Tcl/Tk."""
    try:
        import _tkinter
        import tkinter

        interpreter = tkinter.Tcl()
        patch_level = interpreter.eval("info patchlevel")
        library_path = interpreter.eval("info library")
        print(f"✅ Windows Tcl/Tk 빌드 런타임: {patch_level} · {library_path}")
        return True
    except Exception as exc:
        print(
            "❌ Windows Tcl/Tk 초기화 실패 - tkinter가 빠진 EXE 생성을 중단합니다. "
            f"Python Tcl/Tk 설치 및 빌드 프로세스의 파일 접근 권한을 확인하세요: {exc}"
        )
        return False


def verify_windows_tkinter_archive(artifact: Path) -> bool:
    """Ensure the packaged GUI has both Python modules and native Tcl/Tk payloads."""
    try:
        from PyInstaller.archive.readers import CArchiveReader

        archive = CArchiveReader(str(artifact))
        archive_entries = {
            str(entry).replace("\\", "/").lower() for entry in archive.toc
        }
        required_entries = {
            "_tkinter.pyd",
            "_tcl_data/init.tcl",
            "_tk_data/tk.tcl",
        }
        missing_entries = sorted(required_entries - archive_entries)
        if missing_entries:
            raise RuntimeError("필수 Tcl/Tk 파일 누락: " + ", ".join(missing_entries))

        pyz = archive.open_embedded_archive("PYZ.pyz")
        pyz_modules = set(pyz.toc)
        missing_modules = sorted(
            module for module in WINDOWS_TKINTER_REQUIRED_MODULES if module not in pyz_modules
        )
        if missing_modules:
            raise RuntimeError("필수 GUI 모듈 누락: " + ", ".join(missing_modules))

        print("✅ EXE Tkinter 검증: Python 모듈 · _tkinter.pyd · Tcl/Tk 데이터 포함")
        return True
    except Exception as exc:
        print(f"❌ EXE Tkinter 검증 실패: {exc}")
        return False


def find_blocking_pyinstaller_messages(*outputs: str) -> list[str]:
    """Return unique PyInstaller lines that describe a non-runnable GUI build."""
    matches: list[str] = []
    seen: set[str] = set()
    for output in outputs:
        for raw_line in str(output or "").splitlines():
            line = raw_line.strip()
            lowered = line.lower()
            if any(pattern in lowered for pattern in PYINSTALLER_BLOCKING_MESSAGES):
                if line and line not in seen:
                    seen.add(line)
                    matches.append(line)
    return matches


def verify_windows_executable_version(artifact: Path) -> bool:
    """Verify the PE version resource matches config.app_version.RELEASE_VERSION."""
    try:
        from config.app_version import RELEASE_VERSION

        expected = tuple(int(part) for part in str(RELEASE_VERSION).split("."))
        actual = _windows_file_version(artifact)
        if actual != expected:
            raise RuntimeError(
                f"EXE FileVersion 불일치: actual={'.'.join(map(str, actual))}, "
                f"expected={RELEASE_VERSION}"
            )
        print(f"✅ EXE 버전 검증: {RELEASE_VERSION}")
        return True
    except Exception as exc:
        print(f"❌ EXE 버전 검증 실패: {exc}")
        return False


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
    print("✅ 사용자 데이터는 제외하고 생활금융 기본 카탈로그만 명시적으로 포함")
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

def create_safe_spec_file(target_platform: str, output_path: str = 'aiautotrade_safe.spec'):
    """단일 정책으로 PyInstaller 스펙 파일을 생성한다."""
    vc_runtime_binaries: list[tuple[str, str]] = []
    if target_platform == 'windows':
        if not validate_windows_tkinter_build_runtime():
            raise RuntimeError("Windows Tcl/Tk 빌드 런타임 검증에 실패했습니다.")
        vc_runtime_binaries = resolve_windows_vc_runtime_binaries()

    # 동적 hiddenimports / excludes 구성
    hiddenimports = [
        # GUI
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'customtkinter',
        # Networking / exchanges / utils
        'websockets', 'websocket', 'websocket_client',
        'binance', 'ccxt', 'ccxt.binance', 'ccxt.upbit', 'ccxt.bithumb',
        'ccxt.bybit', 'ccxt.okx', 'ccxt.bitget',  # v3.7.8: 추가 거래소 명시적 포함
        'trading.exchange_manager', 'trading.api_signal_manager',
        'trading.ai_custom_features', 'trading.user_indicator_language',
        'trading.strategy_package', 'trading.strategy_quality_report',
        'trading.signed_strategy_webhook',
        'referral_account_proof',
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
    if target_platform != 'windows':
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

    vc_runtime_policy = ""
    if target_platform == 'windows':
        runtime_names = repr(tuple(sorted(WINDOWS_VC_RUNTIME_NAMES)))
        runtime_rows = ",\n    ".join(
            repr((name, source, 'BINARY'))
            for name, source in vc_runtime_binaries
        )
        vc_runtime_policy = f'''\n# PyQt5-Qt5와 pandas가 포함한 구형 VC 런타임을 모두 제거한다.
# Kiwoom용 PyQt5/QAxContainer는 보존하고, 빌드 아키텍처와 같은 공식 VC143 세트만
# _MEI 루트에 한 번 수집해 ONNX Runtime과 Qt가 같은 런타임을 사용하게 한다.
_NOAHAI_VC_RUNTIME_NAMES = frozenset({runtime_names})

def _noahai_bundle_basename(entry_name):
    return str(entry_name).replace('\\\\', '/').rsplit('/', 1)[-1].lower()

def _noahai_is_vc_runtime(entry_name):
    basename = _noahai_bundle_basename(entry_name)
    return basename == 'concrt140.dll' or (
        basename.endswith('.dll')
        and basename.startswith(('msvcp140', 'vcruntime140'))
    )

a.binaries = [
    entry for entry in a.binaries
    if not _noahai_is_vc_runtime(entry[0])
]
a.binaries += [
    {runtime_rows}
]
'''

    # 플랫폼별 아이콘 처리
    # - Windows: .ico 권장
    # - macOS: .icns 권장(없으면 아이콘 미지정)
    # - Linux: .png 가능(미지정 가능)
    icon_win = 'icon.ico' if os.path.exists('icon.ico') else None
    icon_macos = 'icon.icns' if os.path.exists('icon.icns') else None
    icon_linux = 'icon.png' if os.path.exists('icon.png') else None

    header = f'''# -*- mode: python ; coding: utf-8 -*-
# AUTO-GENERATED BY build_safe.py. 직접 수정하지 마세요.

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/settings_template.json', 'config'),
        ('config/token_template.json', 'config'),
        ('config/theme_config.json', 'config'),
        ('data/finance_products', 'data/finance_products'),
        ('docs', 'docs'),
        # Python 소스는 Analysis/hiddenimports가 수집한다. datas로 중복 번들하지 않는다.
        ('README.md', '.'),
        ('requirements.txt', '.'),
        ('requirements_windows.txt', '.'),
        ('icon.ico', '.') ,
        ('icon.png', '.') ,
        # 사용자 data는 제외하고 위의 읽기 전용 금융상품 기본 카탈로그만 포함
    ],
    hiddenimports=[
        {hiddenimports_str}
    ],
    hookspath=['hooks'],
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
{vc_runtime_policy}
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

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(spec_content)

    print(f"✅ 안전한 PyInstaller 스펙 파일 생성: {output_path} (platform={target_platform})")
    return output_path

def build_exe():
    """PyInstaller 빌드 실행"""
    print("\n🔨 빌드 시작...")
    
    try:
        # PyInstaller 실행
        cmd = [sys.executable, "-m", "PyInstaller", "--clean", "aiautotrade_safe.spec"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        warning_path = Path("build") / "aiautotrade_safe" / "warn-aiautotrade_safe.txt"
        warning_text = ""
        if warning_path.is_file():
            warning_text = warning_path.read_text(encoding="utf-8", errors="ignore")
        blocking_messages = find_blocking_pyinstaller_messages(
            result.stdout,
            result.stderr,
            warning_text,
        )
        
        if result.returncode == 0 and not blocking_messages:
            print("✅ 빌드 성공!")
            return True

        print("❌ 빌드 실패!")
        if blocking_messages:
            print("치명적인 PyInstaller 경고:")
            for message in blocking_messages:
                print(f"  - {message}")
        elif result.stderr:
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
        expected_vc_runtime = resolve_windows_vc_runtime_binaries()
        if not verify_windows_vc_runtime_archive(artifact, expected_vc_runtime):
            print("❌ VC 런타임 충돌 가능성이 남아 있어 배포 복사를 중단합니다.")
            return False
        if not verify_windows_tkinter_archive(artifact):
            print("❌ Tkinter/CustomTkinter 누락으로 배포 복사를 중단합니다.")
            return False
        if not verify_windows_executable_version(artifact):
            print("❌ EXE 버전 불일치로 배포 복사를 중단합니다.")
            return False
        print(f"✅ EXE 파일 생성 확인: {artifact}")
        file_size = artifact.stat().st_size / (1024 * 1024)
        print(f"📊 파일 크기: {file_size:.1f} MB")
        dest = Path(deploy_dir) / 'AITrading.exe'
        temp_dest = dest.with_suffix(dest.suffix + ".tmp")
        try:
            shutil.copy2(artifact, temp_dest)
            if temp_dest.stat().st_size != artifact.stat().st_size:
                raise RuntimeError("deploy 임시 파일 크기가 빌드 산출물과 다릅니다.")
            os.replace(temp_dest, dest)
        finally:
            temp_dest.unlink(missing_ok=True)
        print(f"✅ 배포 SHA-256: {_sha256_file(dest)}")
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

def ensure_build_dependencies(target_platform: str) -> bool:
    """빌드에 필요한 패키지를 requirements 파일로 자동 설치."""
    if target_platform == 'windows':
        req_file = 'requirements_windows.txt'
    else:
        req_file = 'requirements.txt'

    if not os.path.exists(req_file):
        print(f"❌ {req_file} 파일이 없어 배포 의존성을 보장할 수 없습니다.")
        return False

    print(f"\n📦 빌드 의존성 설치 중 ({req_file})...")
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-r', req_file, '--quiet'],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if result.returncode == 0:
        print(f"✅ 의존성 설치 완료 ({req_file})")
    else:
        print("❌ 일부 패키지 설치 실패:")
        if result.stderr:
            # 핵심 오류 줄만 출력
            for line in result.stderr.splitlines():
                if 'ERROR' in line or 'error' in line.lower():
                    print(f"   {line}")

    # 음성 의존성은 환경별 실패 포인트가 많아 별도 보정 설치를 추가한다.
    ensure_voice_dependencies(target_platform)

    missing = [
        module_name
        for module_name in ("PyInstaller",)
        if importlib.util.find_spec(module_name) is None
    ]
    if missing:
        print(
            "❌ 배포 필수 모듈 누락: "
            + ", ".join(missing)
            + " · 최종 사용자에게 설치를 전가하지 않기 위해 빌드를 중단합니다."
        )
        return False
    print("✅ 배포 필수 모듈 확인: PyInstaller")
    return result.returncode == 0


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


def main() -> int:
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
                return 1

        # 1. 빌드 의존성 자동 설치 (requirements 파일 기반)
        if not ensure_build_dependencies(target_platform):
            print("❌ 빌드 의존성 계약을 충족하지 못해 빌드를 중단합니다.")
            return 1

        # 2. 안전한 빌드 환경 준비
        backed_up_files = create_safe_build_environment()
        
        # 3. 안전한 스펙 파일 생성
        create_safe_spec_file(target_platform)
        
        # 4. 빌드 실행
        build_success = build_exe()
        
        if not build_success:
            print("\n❌ 빌드 실패")
            return 1

        # 5. 빌드 결과 검증. VC 게이트 실패를 성공으로 표시하지 않는다.
        if not verify_safe_build(target_platform):
            print("\n❌ 빌드 산출물 검증 실패 - 배포를 중단합니다.")
            return 1
        print("\n🎉 안전한 배포 빌드 완료!")
        if target_platform == 'windows':
            print("📁 배포 파일: deploy/AITrading.exe")
        elif target_platform == 'macos':
            print("📁 배포 파일: deploy/AITrading.app")
        else:
            print("📁 배포 파일: deploy/AITrading")
        print("⚠️  이 산출물에는 민감한 정보가 포함되지 않았습니다.")
            
    except Exception as e:
        print(f"\n❌ 빌드 과정에서 오류 발생: {e}")
        return 1
        
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
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
