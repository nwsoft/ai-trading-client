"""Authenticated local IPC to the separately packaged 32-bit OpenAPI+ host.

The desktop/engine stays 64-bit. Credentials travel through stdin and the
authenticated loopback connection, never command-line arguments or files.
"""
from __future__ import annotations

import json
import multiprocessing.connection
import os
from pathlib import Path
import struct
import subprocess
import sys


def pe_machine(path: Path) -> int:
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError("kiwoom_host_invalid_executable")
        handle.seek(60)
        offset = struct.unpack("<I", handle.read(4))[0]
        handle.seek(offset)
        if handle.read(4) != b"PE\0\0":
            raise ValueError("kiwoom_host_invalid_executable")
        return struct.unpack("<H", handle.read(2))[0]


class ExternalHostProcess:
    def __init__(self, process):
        self.process = process

    def is_alive(self):
        return self.process.poll() is None

    @property
    def exitcode(self):
        return self.process.poll()

    def join(self, timeout=None):
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass

    def terminate(self):
        self.process.terminate()


def start_32bit_host(config: dict):
    override = os.environ.get("NOAHAI_KIWOOM_HOST", "")
    host = Path(override) if override else Path(sys.executable).parent / "NoahAIKiwoomHost.exe"
    if not host.is_file():
        raise RuntimeError("kiwoom_32bit_host_missing: 키움 OpenAPI+ 전용 32비트 호스트가 설치되지 않았습니다. 호스트가 포함된 설치본으로 재설치하세요. API 키나 네트워크 오류가 아닙니다.")
    if pe_machine(host) != 0x14C:
        raise RuntimeError("kiwoom_host_architecture_mismatch: 키움 호스트는 32비트(x86)여야 합니다. 64비트 엔진 재설치만으로 해결되지 않습니다.")
    authkey = os.urandom(32)
    listener = multiprocessing.connection.Listener(("127.0.0.1", 0), authkey=authkey)
    # Listener has no public accept timeout. Its AF_INET socket owns startup
    # only; RPC deadlines continue to use Connection.poll in the shared proxy.
    listener._listener._socket.settimeout(30)
    process = None
    try:
        from path_utils import get_log_dir
        diagnostic_path = Path(get_log_dir()) / "kiwoom_host_events.jsonl"
        diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "NOAHAI_KIWOOM_DIAGNOSTIC_LOG": str(diagnostic_path),
                       "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen([str(host.resolve())], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=environment,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        bootstrap = {"address": listener.address, "authkey": authkey.hex(), "config": config}
        process.stdin.write((json.dumps(bootstrap) + "\n").encode("utf-8"))
        process.stdin.close()
        connection = listener.accept()
        try:
            if not connection.poll(30):
                raise RuntimeError("kiwoom_host_ready_timeout")
            ready_id, ready_ok, ready_message = connection.recv()
            if ready_id != 0 or not ready_ok or ready_message != "kiwoom_host_ready_v1":
                raise RuntimeError("kiwoom_host_ready_failed")
        except BaseException:
            connection.close()
            raise
        return ExternalHostProcess(process), connection
    except Exception as exc:
        exitcode = process.poll() if process is not None else None
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise RuntimeError(f"kiwoom_32bit_host_start_failed:{type(exc).__name__}:exit={exitcode}: 키움 전용 호스트 초기화에 실패했습니다. logs/kiwoom_host_events.jsonl 및 Windows 응용 프로그램 오류 기록을 확인하세요.") from None
    finally:
        listener.close()


def main():
    if sys.platform != "win32" or struct.calcsize("P") != 4:
        raise SystemExit("Kiwoom host requires Windows x86 Python")
    bootstrap = json.loads(sys.stdin.buffer.readline(65536))
    connection = multiprocessing.connection.Client(tuple(bootstrap["address"]), authkey=bytes.fromhex(bootstrap["authkey"]))
    from .kiwoom_process_proxy import _kiwoom_process_main
    _kiwoom_process_main(connection, bootstrap["config"], ready_handshake=True)
