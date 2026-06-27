#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch


def test_keyday_one_shot_skips_kiwoom_on_non_windows_by_default():
    from scripts import stock_keyday_one_shot as keyday

    args = SimpleNamespace(brokers="kiwoom,shinhan,miraeAsset", allow_kiwoom_nonwindows=False)
    calls = []

    def _fake_run(title, command):
        calls.append((title, command))
        return 0, "ok"

    with patch.object(keyday, "_parse_args", return_value=args), \
         patch.object(keyday.platform, "system", return_value="Darwin"), \
         patch.object(keyday, "_run_step", side_effect=_fake_run):
        assert keyday.main() == 0

    titles = [item[0] for item in calls]
    assert "READINESS:kiwoom" not in titles
    assert "READINESS:shinhan" in titles
    assert "READINESS:miraeAsset" in titles


def test_keyday_one_shot_fails_when_any_step_fails():
    from scripts import stock_keyday_one_shot as keyday

    args = SimpleNamespace(brokers="shinhan", allow_kiwoom_nonwindows=False)

    results = [
        (0, "readiness report ok"),
        (1, "precheck fail"),
        (0, "readiness ok"),
    ]

    with patch.object(keyday, "_parse_args", return_value=args), \
         patch.object(keyday.platform, "system", return_value="Darwin"), \
         patch.object(keyday, "_run_step", side_effect=results):
        assert keyday.main() == 1
