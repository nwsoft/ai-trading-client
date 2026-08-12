from __future__ import annotations

from ui.service_tab_policy import (
    format_exchange_scope_label,
    format_trading_runtime_status,
    get_service_tab_order,
)
from ui.windows_menu_guard import LazyWindowsDropdownMenu


class _Owner:
    def after_idle(self, callback):
        callback()


class _FakeMenu:
    created = 0
    live = 0

    def __init__(self, _master=None, **_kwargs):
        type(self).created += 1
        type(self).live += 1
        self.commands = []
        self.destroyed = False

    def add_command(self, *, label, command):
        self.commands.append((label, command))

    def bind(self, *_args, **_kwargs):
        return None

    def post(self, *_args):
        return None

    def unpost(self):
        return None

    def destroy(self):
        if not self.destroyed:
            self.destroyed = True
            type(self).live -= 1


def test_lazy_dropdown_allocates_only_while_open(monkeypatch):
    import ui.windows_menu_guard as guard

    _FakeMenu.created = 0
    _FakeMenu.live = 0
    selected = []
    monkeypatch.setattr(guard.tk, "Menu", _FakeMenu)
    dropdown = LazyWindowsDropdownMenu(
        master=_Owner(),
        values=["kimi-k3", "kimi-k2.6"],
        command=selected.append,
    )

    assert _FakeMenu.created == 0
    assert _FakeMenu.live == 0

    dropdown.open(10, 20)
    assert _FakeMenu.created == 1
    assert _FakeMenu.live == 1
    dropdown._native_menu.commands[0][1]()
    assert selected == ["kimi-k3"]
    assert _FakeMenu.live == 0
    assert dropdown._native_menu is None

    dropdown.open(10, 20)
    dropdown.destroy()
    assert _FakeMenu.live == 0


def test_only_one_native_dropdown_can_exist_process_wide(monkeypatch):
    import ui.windows_menu_guard as guard

    _FakeMenu.created = 0
    _FakeMenu.live = 0
    monkeypatch.setattr(guard.tk, "Menu", _FakeMenu)
    first = LazyWindowsDropdownMenu(master=_Owner(), values=["a"])
    second = LazyWindowsDropdownMenu(master=_Owner(), values=["b"])
    first.open(0, 0)
    second.open(0, 0)

    assert _FakeMenu.created == 2
    assert _FakeMenu.live == 1
    assert first._native_menu is None
    second.destroy()
    assert _FakeMenu.live == 0


def test_multi_exchange_header_is_scope_not_single_exchange_claim():
    assert format_exchange_scope_label(["binance"], "binance") == "거래소: BINANCE"
    assert (
        format_exchange_scope_label(
            ["binance", "upbit", "bithumb", "bybit", "okx", "bitget"],
            "binance",
        )
        == "거래소: 6곳 · 기준 BINANCE"
    )


def test_bottom_status_distinguishes_saved_scope_from_running_workers():
    enabled = {"binance", "upbit", "bithumb", "bybit", "okx", "bitget"}
    assert format_trading_runtime_status(enabled, set()) == "자동매매: 정지 (0/6 실행)"
    assert format_trading_runtime_status(enabled, {"binance", "okx"}) == "자동매매: 부분 실행 (2/6)"


def test_financial_intelligence_is_before_every_exchange_tab():
    order = get_service_tab_order(
        "blockchain",
        ["BINANCE", "UPBIT", "BITHUMB", "BYBIT", "OKX", "BITGET"],
    )
    intelligence_index = order.index("금융 인텔리전스")
    assert all(intelligence_index < order.index(exchange) for exchange in order[-6:])
