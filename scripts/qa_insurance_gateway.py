"""Temporary synthetic-only gateway for real React -> API -> encrypted storage QA.

Run with .venv/bin/python scripts/qa_insurance_gateway.py (loopback port 4199).
No production account, secrets, trading engine or external AI is constructed.
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import uvicorn
    from trading.insurance_workspace import InsuranceWorkspace
    from web_platform.gateway import create_gateway_app
    with tempfile.TemporaryDirectory(prefix="noah-insurance-qa-") as directory:
        store = InsuranceWorkspace(Path(directory), "synthetic-browser-qa")
        services = SimpleNamespace(insurance_workspace=lambda: store, runtime_snapshot=lambda: {})
        app = create_gateway_app(token="synthetic-insurance-browser-qa-token", application_services=services)
        try:
            uvicorn.run(app, host="127.0.0.1", port=4199, access_log=False, log_level="warning")
        finally:
            store.lock()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
