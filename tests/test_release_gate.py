#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch


def test_release_gate_dev_allows_non_required_readiness_failure():
    from scripts import release_gate

    # TEST_STOCK, MODE_MATRIX, READINESS
    results = [
        SimpleNamespace(returncode=0, stdout="tests ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="readiness fail", stderr=""),
    ]

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="dev", readiness_account="")), \
         patch.object(release_gate.subprocess, "run", side_effect=results):
        assert release_gate.main() == 0


def test_release_gate_release_requires_readiness():
    from scripts import release_gate

    # TEST_STOCK, MODE_MATRIX, MOCK_HARDENING, EXCHANGE_READINESS_REPORT,
    # DOC_CONSISTENCY, SYNC_GUARD, MULTI_EXCHANGE_STABILITY, READINESS
    results = [
        SimpleNamespace(returncode=0, stdout="tests ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="mock ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="readiness report ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="doc consistency ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="sync guard ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="multi exchange ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="readiness fail", stderr=""),
    ]

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="release", readiness_account="ExplicitQA")), \
         patch.object(release_gate.subprocess, "run", side_effect=results):
        assert release_gate.main() == 1


def test_release_gate_prekey_requires_prekey_chain():
    from scripts import release_gate

    # TEST_STOCK, MODE_MATRIX, MOCK_HARDENING, EXCHANGE_READINESS_REPORT,
    # DOC_CONSISTENCY, SYNC_GUARD, MULTI_EXCHANGE_STABILITY, READINESS
    results = [
        SimpleNamespace(returncode=0, stdout="tests ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="mock ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="readiness report fail", stderr=""),
        SimpleNamespace(returncode=0, stdout="doc consistency skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="sync guard skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="multi exchange skip", stderr=""),
        SimpleNamespace(returncode=0, stdout="readiness skip", stderr=""),
    ]

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="prekey", readiness_account="")), \
         patch.object(release_gate.subprocess, "run", side_effect=results):
        assert release_gate.main() == 1


def test_release_gate_prekey_allows_non_required_readiness_failure():
    from scripts import release_gate

    results = [
        SimpleNamespace(returncode=0, stdout="tests ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="matrix ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="mock ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="readiness report ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="doc consistency ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="sync guard ok", stderr=""),
        SimpleNamespace(returncode=0, stdout="multi exchange ok", stderr=""),
        SimpleNamespace(returncode=1, stdout="readiness fail", stderr=""),
    ]

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="prekey", readiness_account="")), \
         patch.object(release_gate.subprocess, "run", side_effect=results):
        assert release_gate.main() == 0


def test_release_gate_dev_readiness_is_offline():
    from scripts import release_gate

    commands = []

    def _run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="dev", readiness_account="")), \
         patch.object(release_gate.subprocess, "run", side_effect=_run):
        assert release_gate.main() == 0

    readiness = next(command for command in commands if any("stock_live_readiness_run.py" in part for part in command))
    assert "--offline" in readiness
    assert "--account" not in readiness


def test_release_gate_release_passes_only_explicit_readiness_account():
    from scripts import release_gate

    commands = []

    def _run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch.object(release_gate, "_parse_args", return_value=SimpleNamespace(profile="release", readiness_account="ExplicitQA")), \
         patch.object(release_gate.subprocess, "run", side_effect=_run):
        assert release_gate.main() == 0

    readiness = next(command for command in commands if any("stock_live_readiness_run.py" in part for part in command))
    assert readiness[-2:] == ["--account", "ExplicitQA"]
