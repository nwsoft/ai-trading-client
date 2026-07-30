from trading.stock_analysis_service import select_stock_universe


class _Adapter:
    def get_stock_list(self, market):
        prefix = "1" if market == "KOSPI" else "2"
        return [
            {
                "code": f"{prefix}{index:05d}",
                "trade_value": float(index) * 1_000_000,
                "status": "ok",
            }
            for index in range(1, 7)
        ]

    def get_etf_list(self):
        return [
            {
                "code": f"3{index:05d}",
                "trade_value": float(index) * 2_000_000,
                "status": "ok",
            }
            for index in range(1, 7)
        ]


def test_stock_universe_honors_user_configured_symbols():
    selected = select_stock_universe(
        _Adapter(),
        configured_symbols=["005930", "005930", "000660"],
        asset_mode="etf",
    )
    assert selected[:2] == ["005930", "000660"]
    assert len(selected) == 8


def test_stock_universe_all_mode_balances_stocks_and_etfs():
    selected = select_stock_universe(_Adapter(), asset_mode="all", limit=8)

    assert len(selected) == 8
    assert sum(code.startswith("3") for code in selected) == 4
    assert sum(not code.startswith("3") for code in selected) == 4
    assert any(code.startswith("1") for code in selected)
    assert any(code.startswith("2") for code in selected)


def test_stock_universe_asset_mode_selects_only_requested_class():
    assert all(
        not code.startswith("3")
        for code in select_stock_universe(_Adapter(), asset_mode="stock", limit=8)
    )
    assert all(
        code.startswith("3")
        for code in select_stock_universe(_Adapter(), asset_mode="etf", limit=8)
    )


def test_stock_universe_excludes_halted_items():
    class HaltedAdapter(_Adapter):
        def get_etf_list(self):
            return [
                {"code": "300001", "trade_value": 999_000_000, "status": "halted"},
                {"code": "300002", "trade_value": 1_000_000, "status": "ok"},
            ]

    assert select_stock_universe(
        HaltedAdapter(), asset_mode="etf", limit=8
    ) == ["300002"]
