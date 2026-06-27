#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch


def test_source_invariants_pass_on_current_code():
    from scripts import multi_exchange_stability_check as check

    assert check._check_source_invariants() == []


def test_main_fails_when_invariant_check_fails():
    from scripts import multi_exchange_stability_check as check

    args = SimpleNamespace(skip_compile=True, skip_pytest=True, no_write_report=True)

    with patch.object(check, "_parse_args", return_value=args), \
         patch.object(check, "_check_source_invariants", return_value=["legacy fallback found"]):
        assert check.main() == 1


def test_main_passes_when_all_steps_skipped_and_invariants_ok():
    from scripts import multi_exchange_stability_check as check

    args = SimpleNamespace(skip_compile=True, skip_pytest=True, no_write_report=True)

    with patch.object(check, "_parse_args", return_value=args), \
         patch.object(check, "_check_source_invariants", return_value=[]):
        assert check.main() == 0
