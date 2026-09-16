# Build separately using 32-bit Python; never bundle 64-bit QAx as a substitute.
import struct
import sys

if sys.platform != "win32" or struct.calcsize("P") != 4:
    raise RuntimeError("NoahAIKiwoomHost must be built with Windows x86 Python")

a = Analysis(["scripts/kiwoom_host.py"], pathex=["."], binaries=[], datas=[],
             hiddenimports=["pykiwoom.kiwoom", "PyQt5.QAxContainer", "PyQt5.QtWidgets",
                            "log_system.log_stream"],
             excludes=["tkinter", "torch", "tensorflow", "matplotlib"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="NoahAIKiwoomHost",
          console=True, debug=False, upx=False,
          version="config/windows_kiwoom_host_version_info.txt")
