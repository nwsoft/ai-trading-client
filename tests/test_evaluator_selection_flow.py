import os
import time
from types import SimpleNamespace

import pytest

from trading.evaluator import Evaluator


class _DummyAnalyzer:
    def __init__(self):
        self.settings = {}
        self.binance_client = None


def test_select_trading_coins_skips_fallback_when_target_already_met(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})

    analyze_calls = []

    def fake_analyze_candidate_coins_by_exchange(exchange, exchange_client=None, adjustment_factor=1.0):
        analyze_calls.append(adjustment_factor)
        return [
            {"symbol": "BTCUSDT", "overall_score": 91.0},
            {"symbol": "ETHUSDT", "overall_score": 88.0},
        ]

    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        fake_analyze_candidate_coins_by_exchange,
    )
    monkeypatch.setattr(evaluator, "_select_final_coins", lambda coins, num_alt, num_major, regime: list(coins))
    monkeypatch.setattr(evaluator, "_evaluate_coins_with_ai", lambda valid, selected: [])

    selected = evaluator.select_trading_coins(num_alt=1, num_major=1, regime="normal", exchange="binance")

    assert len(selected) == 2
    assert analyze_calls == [1.0]
    assert all(item["selection_status"] == "scored" for item in selected)
    assert all(item["execution_eligible"] is True for item in selected)


def test_select_trading_coins_keeps_scored_partial_results_without_retrying_smaller_pools(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    analyze_calls = []

    def fake_analyze_candidate_coins_by_exchange(exchange, exchange_client=None, adjustment_factor=1.0):
        analyze_calls.append(adjustment_factor)
        return [{"symbol": "BTCUSDT", "overall_score": 91.0, "is_major": True}]

    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        fake_analyze_candidate_coins_by_exchange,
    )
    monkeypatch.setattr(evaluator, "_select_final_coins", lambda coins, num_alt, num_major, regime: list(coins))
    monkeypatch.setattr(evaluator, "_evaluate_coins_with_ai", lambda *args, **kwargs: [])

    selected = evaluator.select_trading_coins(
        num_alt=1,
        num_major=1,
        regime="normal",
        exchange="binance",
    )

    assert analyze_calls == [1.0]
    assert [item["symbol"] for item in selected] == ["BTCUSDT"]
    assert selected[0]["selection_status"] == "scored_partial"
    assert selected[0]["selection_reason"] == "partial_candidate_selection"
    assert selected[0]["execution_eligible"] is True


def test_fetch_ticker_data_considers_symbols_beyond_exchange_info_first_hundred():
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    symbols = [f"C{index}USDT" for index in range(101)]

    class _TickerClient:
        def get_all_24h_tickers(self):
            return [
                {"symbol": symbol, "quoteVolume": index + 1}
                for index, symbol in enumerate(symbols)
            ]

    evaluator.binance_client = _TickerClient()

    tickers = evaluator._fetch_ticker_data(symbols)

    assert len(tickers) == 101
    assert tickers[-1]["symbol"] == "C100USDT"


def test_binance_candidate_analysis_sorts_all_valid_perpetual_tickers_before_top_hundred(
    monkeypatch,
    tmp_path,
):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    regular = [f"C{index}USDT" for index in range(100)]
    all_valid = regular + ["BTCUSDT"]

    class _Client:
        def get_exchange_info(self):
            return {
                "symbols": [
                    {
                        "symbol": symbol,
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                    }
                    for symbol in all_valid
                ]
                + [
                    {
                        "symbol": "STOPUSDT",
                        "status": "BREAK",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                    },
                    {
                        "symbol": "QUARTERUSDT",
                        "status": "TRADING",
                        "contractType": "CURRENT_QUARTER",
                        "quoteAsset": "USDT",
                    },
                ]
            }

        def get_all_24h_tickers(self):
            return [
                {
                    "symbol": symbol,
                    "quoteVolume": 1_000_000 if symbol == "BTCUSDT" else 100 + index,
                    "volume": 10,
                    "count": 1000,
                    "priceChange": 1,
                    "priceChangePercent": 1,
                }
                for index, symbol in enumerate(all_valid)
            ]

        def get_klines(self, symbol, interval, limit):
            return [[0, 1, 2, 0.5, 1.5, 10]] * max(1, limit)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("trading.evaluator.symbol_validator.is_valid_symbol", lambda exchange, symbol: True)
    evaluator.binance_client = _Client()

    candidates = evaluator._analyze_candidate_coins()
    symbols = [item["symbol"] for item in candidates]

    assert len(candidates) == 100
    assert "BTCUSDT" in symbols
    assert "STOPUSDT" not in symbols
    assert "QUARTERUSDT" not in symbols
    btc = next(item for item in candidates if item["symbol"] == "BTCUSDT")
    assert btc["is_major"] is True


def test_binance_ticker_file_cache_is_not_retimestamped_when_only_read(monkeypatch, tmp_path):
    evaluator = Evaluator(
        analyzer=_DummyAnalyzer(),
        recorder=None,
        settings={"market_ticker_cache_ttl_seconds": 30},
    )
    calls = {"tickers": 0}

    class _Client:
        def get_exchange_info(self):
            return {
                "symbols": [{
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USDT",
                }]
            }

        def get_all_24h_tickers(self):
            calls["tickers"] += 1
            return [{"symbol": "BTCUSDT", "quoteVolume": 1_000_000}]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("trading.evaluator.get_cache_dir", lambda: str(tmp_path / "account-cache"))
    monkeypatch.setattr("trading.evaluator.symbol_validator.is_valid_symbol", lambda exchange, symbol: True)
    evaluator.binance_client = _Client()
    evaluator._analyze_candidate_coins()
    ticker_path = tmp_path / "account-cache/ticker_data.json"
    old_mtime = time.time() - 10
    os.utime(ticker_path, (old_mtime, old_mtime))

    evaluator._analyze_candidate_coins()

    assert calls["tickers"] == 1
    assert os.path.getmtime(ticker_path) == old_mtime


def test_binance_selection_cache_is_account_scoped_not_working_directory(monkeypatch, tmp_path):
    account_cache = tmp_path / "Teayu" / "cache"
    monkeypatch.setattr("trading.evaluator.get_cache_dir", lambda: str(account_cache))

    exchange_info, backup, tickers = Evaluator._binance_selection_cache_paths()

    assert exchange_info == str(account_cache / "exchange_info.json")
    assert backup == str(account_cache / "backup_symbols.json")
    assert tickers == str(account_cache / "ticker_data.json")
    assert "nwsoft" not in exchange_info


def test_failed_selection_is_not_reused_from_singleflight_cache(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    calls = {"count": 0}

    def produce(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return evaluator._fallback_to_major_coins(1, exchange="binance")
        return [{
            "symbol": "BTCUSDT",
            "overall_score": 82.0,
            "selection_status": "scored",
            "execution_eligible": True,
        }]

    monkeypatch.setattr(evaluator, "_select_trading_coins_impl", produce)

    first = evaluator.select_trading_coins(0, 1, exchange="binance")
    second = evaluator.select_trading_coins(0, 1, exchange="binance")

    assert first[0]["selection_status"] == "fallback_unscored"
    assert second[0]["selection_status"] == "scored"
    assert calls["count"] == 2


def test_select_trading_coins_returns_non_executable_reference_symbols_only_when_data_unavailable(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    analyze_calls = []

    def fake_analyze_candidate_coins_by_exchange(exchange, exchange_client=None, adjustment_factor=1.0):
        analyze_calls.append(adjustment_factor)
        return []

    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        fake_analyze_candidate_coins_by_exchange,
    )

    selected = evaluator.select_trading_coins(
        num_alt=1,
        num_major=1,
        regime="normal",
        exchange="binance",
    )

    assert analyze_calls == [1.0]
    assert len(selected) == 2
    assert all(item["selection_status"] == "fallback_unscored" for item in selected)
    assert all(item["execution_eligible"] is False for item in selected)


def test_select_trading_coins_does_not_promote_unscored_symbols_with_fabricated_points(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        lambda *args, **kwargs: [{"symbol": "BTCUSDT"}],
    )
    monkeypatch.setattr(
        evaluator,
        "_select_final_coins",
        lambda coins, num_alt, num_major, regime: ["BTCUSDT"],
    )

    selected = evaluator.select_trading_coins(
        num_alt=0,
        num_major=1,
        regime="normal",
        exchange="binance",
    )

    assert selected[0]["overall_score"] is None
    assert selected[0]["selection_status"] == "fallback_unscored"
    assert selected[0]["execution_eligible"] is False


def test_coin_selection_score_is_normalized_to_hundred_point_scale(monkeypatch):
    evaluator = Evaluator(analyzer=_DummyAnalyzer(), recorder=None, settings={})
    monkeypatch.setattr(evaluator, "calculate_technical_indicators", lambda symbol: None)
    monkeypatch.setattr(evaluator, "_get_funding_rate", lambda symbol: 0.0001)
    monkeypatch.setattr(
        evaluator,
        "_get_open_interest",
        lambda symbol: {"open_interest": 1000.0, "oi_change_pct": 3.0},
    )

    result = evaluator._calculate_altcoin_scores(
        {
            "symbol": "BTCUSDT",
            "is_major": True,
            "priceChange": 10.0,
            "priceChangePercent": 12.0,
            "quoteVolume": 10_000_000.0,
            "count": 1_000_000,
        },
        {},
    )

    assert result["calculation_valid"] is True
    assert 0.0 <= result["overall_score"] <= 100.0


def test_candidate_scoring_never_waits_for_per_symbol_network_enrichment(monkeypatch):
    evaluator = Evaluator(
        analyzer=_DummyAnalyzer(),
        recorder=None,
        settings={"coin_selection_stage_timeout_seconds": 1},
    )

    def unexpected_network_call(*args, **kwargs):
        raise AssertionError("candidate score worker must use the shared ticker snapshot only")

    monkeypatch.setattr(evaluator, "calculate_technical_indicators", unexpected_network_call)
    monkeypatch.setattr(evaluator, "_get_funding_rate", unexpected_network_call)
    monkeypatch.setattr(evaluator, "_get_open_interest", unexpected_network_call)

    result = evaluator._calculate_trading_scores([
        {
            "symbol": "BTCUSDT",
            "is_major": True,
            "priceChange": 10.0,
            "priceChangePercent": 12.0,
            "quoteVolume": 10_000_000.0,
            "count": 1_000_000,
        }
    ])

    assert len(result) == 1
    assert result[0]["overall_score"] is not None
    assert result[0]["technical_score"] is None
    assert result[0]["technical_data_available"] is False


@pytest.mark.parametrize(
    "exchange",
    ["binance", "upbit", "bithumb", "bybit", "bitget", "okx"],
)
def test_full_candidate_batch_scores_instead_of_safe_fallback_when_enrichment_is_slow(
    monkeypatch,
    exchange,
):
    evaluator = Evaluator(
        analyzer=_DummyAnalyzer(),
        recorder=None,
        settings={"coin_selection_stage_timeout_seconds": 1},
    )
    evaluator._set_selection_context(exchange)

    def unexpected_network_call(*args, **kwargs):
        raise AssertionError("optional per-symbol enrichment must not run in scoring workers")

    monkeypatch.setattr(evaluator, "calculate_technical_indicators", unexpected_network_call)
    monkeypatch.setattr(evaluator, "_get_funding_rate", unexpected_network_call)
    monkeypatch.setattr(evaluator, "_get_open_interest", unexpected_network_call)
    candidates = [
        {
            "symbol": (
                f"KRW-C{index}"
                if exchange == "upbit"
                else f"C{index}/KRW"
                if exchange == "bithumb"
                else f"C{index}/USDT:USDT"
                if exchange in {"bybit", "bitget", "okx"}
                else f"C{index}USDT"
            ),
            "is_major": False,
            "priceChange": float(index % 3 - 1),
            "priceChangePercent": float(index % 10 + 1),
            "quoteVolume": float(1_000_000 + index * 50_000),
            "count": 5_000 + index * 100,
        }
        for index in range(30)
    ]

    result = evaluator._calculate_trading_scores(candidates)

    assert len(result) == 30
    assert all(item["overall_score"] is not None for item in result)
    assert all(item["technical_score"] is None for item in result)


def test_okx_futures_derives_quote_turnover_when_ccxt_omits_quote_volume():
    evaluator = Evaluator(
        analyzer=_DummyAnalyzer(),
        recorder=None,
        settings={
            "futures_selection": {
                "okx": {
                    "max_candidates": 20,
                    "min_quote_volume": 15_000_000,
                    "volatility_max": 25.0,
                }
            }
        },
    )

    class _RawOkx:
        id = "okx"
        markets = {
            "BTC/USDT:USDT": {
                "symbol": "BTC/USDT:USDT",
                "base": "BTC",
                "quote": "USDT",
                "active": True,
                "swap": True,
                "future": False,
                "contract": True,
                "type": "swap",
            }
        }

        def fetch_tickers(self, symbols):
            assert symbols == ["BTC/USDT:USDT"]
            return {
                "BTC/USDT:USDT": {
                    "symbol": "BTC/USDT:USDT",
                    "last": 25_000.0,
                    # OKX/CCXT exposes vol24h contract count as baseVolume;
                    # the raw volCcy24h is the actual base-currency quantity.
                    "baseVolume": 2_500_000.0,
                    "quoteVolume": None,
                    "percentage": None,
                    "info": {
                        "instType": "SWAP",
                        "last": "25000",
                        "open24h": "24500",
                        "vol24h": "2500000",
                        "volCcy24h": "1000",
                    },
                }
            }

    client = SimpleNamespace(exchange_name="okx", exchange=_RawOkx())
    evaluator._set_selection_context("okx", client)

    candidates = evaluator._analyze_candidate_coins_ccxt_futures(client)

    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "BTC/USDT:USDT"
    assert candidates[0]["quoteVolume"] == 25_000_000.0
    assert candidates[0]["priceChangePercent"] == pytest.approx(2.0408163265)


@pytest.mark.parametrize(
    ("exchange_name", "market", "ticker", "expected"),
    [
        (
            "bybit",
            {"contract": True},
            {"quoteVolume": 31_000_000, "baseVolume": 1_000, "last": 25_000},
            31_000_000,
        ),
        (
            "bitget",
            {"contract": True},
            {"info": {"turnover24h": "29000000"}, "last": 25_000},
            29_000_000,
        ),
        (
            "upbit",
            {"contract": False},
            {"baseVolume": 1_000, "last": 25_000},
            25_000_000,
        ),
    ],
)
def test_quote_turnover_normalization_preserves_other_venue_contracts(
    exchange_name, market, ticker, expected
):
    assert Evaluator._ticker_quote_volume(
        ticker,
        exchange_name=exchange_name,
        market=market,
    ) == expected


def test_okx_derivative_never_treats_contract_count_as_base_volume():
    ticker = {
        "quoteVolume": None,
        "baseVolume": 2_500_000,
        "last": 25_000,
        "info": {"instType": "SWAP", "vol24h": "2500000"},
    }
    assert Evaluator._ticker_quote_volume(
        ticker,
        exchange_name="okx",
        market={"contract": True},
    ) == 0.0


def test_identical_failed_selection_is_persisted_only_once_per_audit_interval(monkeypatch):
    class _Recorder:
        def __init__(self):
            self.calls = []

        def save_coin_selection(self, **payload):
            self.calls.append(payload)
            return len(self.calls)

    recorder = _Recorder()
    evaluator = Evaluator(
        analyzer=_DummyAnalyzer(),
        recorder=recorder,
        settings={"coin_selection_failure_persist_interval_seconds": 900},
    )
    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        lambda *args, **kwargs: [],
    )
    now = {"value": 1_000.0}
    monkeypatch.setattr("trading.evaluator.time.time", lambda: now["value"])

    evaluator.select_trading_coins(0, 1, exchange="okx")
    now["value"] = 1_100.0
    evaluator.select_trading_coins(0, 1, exchange="okx")
    now["value"] = 1_901.0
    evaluator.select_trading_coins(0, 1, exchange="okx")

    assert len(recorder.calls) == 2
    assert all(call["selection_status"] == "fallback_unscored" for call in recorder.calls)
