"""Windows x64 -> packaged x86 authenticated IPC/adapter startup smoke, no login."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading.exchanges.adapters.kiwoom_host_launcher import start_32bit_host


def main():
    host = Path(sys.argv[1]).resolve()
    os.environ["NOAHAI_KIWOOM_HOST"] = str(host)
    process, connection = start_32bit_host({"user_id": "", "password": "", "cert_password": ""})
    try:
        connection.send(None)
        process.join(10)
        if process.is_alive() or process.exitcode != 0:
            raise RuntimeError(f"Host clean shutdown failed: {process.exitcode}")
    finally:
        connection.close()
        if process.is_alive():
            process.terminate()
    print("KIWOOM HOST IPC READY + CLEAN SHUTDOWN PASS (OCX/login not tested)")


if __name__ == "__main__":
    main()
