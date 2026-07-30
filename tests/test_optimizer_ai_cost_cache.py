from trading.optimizer import Optimizer


def _optimizer():
    return Optimizer(
        recorder=None,
        settings={
            "min_trade_amount": 5.0,
            "ai_cost_control": {
                "position_sizing_cache_sec": 900,
                "position_sizing_retry_cooldown_sec": 120,
                "position_sizing_price_change_bps": 100.0,
                "position_sizing_confidence_delta": 0.10,
            },
        },
    )


def _cache(optimizer, *, signal="LONG", confidence=0.8, price=100.0):
    optimizer._cache_ai_decision(
        "BTCUSDT",
        {"adjusted_position_size_factor": 0.75, "risk_level": "MODERATE"},
        {"signal": signal, "confidence": confidence, "current_price": price},
    )
    optimizer.ai_last_attempt.clear()


def test_fresh_position_sizing_cache_is_not_bypassed_by_high_confidence():
    optimizer = _optimizer()
    _cache(optimizer, confidence=0.95)

    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.95,
        {"signal": "LONG", "confidence": 0.95, "current_price": 100.0},
    ) is False


def test_position_sizing_rechecks_only_on_material_state_change():
    optimizer = _optimizer()
    _cache(optimizer)

    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.8,
        {"signal": "SHORT", "confidence": 0.8, "current_price": 100.0},
    ) is True
    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.8,
        {"signal": "LONG", "confidence": 0.8, "current_price": 101.0},
    ) is True
    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.9,
        {"signal": "LONG", "confidence": 0.9, "current_price": 100.0},
    ) is True


def test_position_sizing_failure_retry_is_cooled_down():
    optimizer = _optimizer()

    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.8,
        {"signal": "LONG", "confidence": 0.8, "current_price": 100.0},
    ) is True
    optimizer._mark_ai_attempt("BTCUSDT")
    assert optimizer._should_call_ai(
        "BTCUSDT",
        0.8,
        {"signal": "LONG", "confidence": 0.8, "current_price": 100.0},
    ) is False


def test_expired_position_sizing_cache_is_not_returned(monkeypatch):
    optimizer = _optimizer()
    _cache(optimizer)
    cached_at = optimizer.ai_cache["BTCUSDT"]["timestamp"]
    monkeypatch.setattr("time.time", lambda: cached_at + optimizer.cache_duration + 1)

    assert optimizer._get_cached_ai_decision("BTCUSDT") is None
