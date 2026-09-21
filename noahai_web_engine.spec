# -*- mode: python ; coding: utf-8 -*-
"""Independent PyInstaller policy for the UI-neutral Web engine sidecar."""

import sys


block_cipher = None

if sys.platform.startswith("win"):
    from build_safe import WINDOWS_VC_RUNTIME_NAMES, resolve_windows_vc_runtime_binaries
    _vc_runtime_binaries = resolve_windows_vc_runtime_binaries()
else:
    WINDOWS_VC_RUNTIME_NAMES = frozenset()
    _vc_runtime_binaries = []


a = Analysis(
    ["web_platform/launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config/web_ui_feature_inventory.json", "config"),
        ("config/settings_template.json", "config"),
        ("config/token_template.json", "config"),
        ("config/theme_config.json", "config"),
        ("data/finance_products", "data/finance_products"),
        ("docs/USER_GUIDE.md", "docs"),
        ("docs/USER_MANUAL_SECTIONS.json", "docs"),
        ("docs/NOTIFICATION_INTEGRATIONS_GUIDE.md", "docs"),
        ("docs/REMOTE_MANAGEMENT_GUIDE_V39141.md", "docs"),
        ("icon.ico", "."),
        ("icon.png", "."),
    ],
    hiddenimports=[
        "websockets", "websocket", "binance",
        "ccxt", "ccxt.binance", "ccxt.upbit", "ccxt.bithumb",
        "ccxt.bybit", "ccxt.okx", "ccxt.bitget",
        "trading.exchange_manager", "trading.api_signal_manager",
        "trading.ai_custom_features", "trading.user_indicator_language",
        "trading.strategy_package", "trading.strategy_quality_report",
        "trading.signed_strategy_webhook", "trading.notifications", "referral_account_proof",
        "trading.remote_entry_pause", "web_platform.remote_monitor", "api.telemetry_batch",
        "trading.event_contract", "trading.decision_storage", "trading.learning_storage",
        "trading.contract_rejections",
        "trading.storage_maintenance", "log_system.event_audit", "log_system.storage_policy",
        "trading.exchanges.exchange_factory",
        "trading.exchanges.adapters.kiwoom_stock_adapter",
        "trading.exchanges.adapters.kiwoom_process_proxy",
        "trading.exchanges.adapters.stock_mock_adapter",
        "trading.exchanges.adapters.shinhan_stock_adapter",
        "trading.exchanges.adapters.mirae_asset_stock_adapter",
        "trading.exchanges.adapters.korea_investment_stock_adapter",
        "openai", "numpy", "pandas", "loguru", "dotenv", "ujson",
        "aiohttp", "dateparser", "colorama", "win32_setctime", "psutil",
        "rapidocr_onnxruntime", "onnxruntime",
        "pypdf", "youtube_transcript_api", "yt_dlp",
        *(["paddleocr", "paddle", "speech_recognition", "pyaudio"] if sys.platform.startswith("win") else []),
        # pykiwoom and PyQt5/QAxContainer are packaged only in the dedicated
        # Windows x86 NoahAIKiwoomHost.exe, never in this x64 engine.
    ],
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "main", "ui", "customtkinter", "tkinter", "tkinter.ttk",
        "tkinter.messagebox", "utils.auto_update_manager",
        "matplotlib", "scipy", "scikit-learn", "tensorflow", "torch",
        "jupyter", "notebook", "ipython", "pytest", "unittest", "wx", "gtk",
        "qt4", "qt6", "PyQt5", "PyQt6", "PySide2", "PySide6", "pykiwoom",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)


def _basename(entry_name):
    return str(entry_name).replace("\\", "/").rsplit("/", 1)[-1].lower()


def _is_vc_runtime(entry_name):
    basename = _basename(entry_name)
    return basename == "concrt140.dll" or (
        basename.endswith(".dll") and basename.startswith(("msvcp140", "vcruntime140"))
    )


a.binaries = [entry for entry in a.binaries if not _is_vc_runtime(entry[0])]
a.binaries += [(name, source, "BINARY") for name, source in _vc_runtime_binaries]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="NoahAIEngine" if sys.platform.startswith("win") else "noahai-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=not sys.platform.startswith("win"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico" if sys.platform.startswith("win") else None,
    version="config/windows_version_info.txt" if sys.platform.startswith("win") else None,
)
