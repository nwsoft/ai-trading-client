"""Offline regression entrypoint for v3.9.1.45 feedback (not live-account E2E)."""
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def deny_network(*args, **kwargs):
    raise RuntimeError("Network disabled for offline feedback verification")


if __name__ == "__main__":
    import pytest
    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    raise SystemExit(pytest.main(sys.argv[1:] or [
        str(ROOT / "tests/test_v39146_feedback_contracts.py"),
        str(ROOT / "tests/test_market_regime_notification_paths.py"),
        "-q",
    ]))
