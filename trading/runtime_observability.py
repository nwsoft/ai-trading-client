"""Source-tagged runtime status: transitions immediately, heartbeat at most 5m."""
import time


def emit_regime_observation(owner, source, observed, confirmed, changed):
    """Local diagnostic only; never synthesize an outbound market transition."""
    code = ('regime_changed' if changed else
            'regime_pending_confirmation' if observed != confirmed else 'regime_unchanged')
    emit_runtime_status(owner, source, code,
                        f"시장국면 관찰: {observed} · 확정: {confirmed} · 상태: {code}")


def emit_runtime_status(owner, source, code, message, *, level="INFO", interval=300):
    now = time.monotonic()
    states = getattr(owner, "_runtime_notice_states", None)
    if states is None:
        states = {}
        owner._runtime_notice_states = states
    # Candidate/market-data/regime stages alternate in a healthy cycle. Keep
    # independent throttles so the new regime diagnostics do not flood INFO.
    category = ('regime' if str(code).startswith('regime_') else
                'market_data' if str(code).startswith('market_data_') else 'runtime')
    key = (source, category)
    previous = states.get(key)
    if previous and previous[0] == code and now - previous[1] < interval:
        return False
    from log_system.log_adapter import log_event
    try:
        from trading.execution_mode import resolve_crypto_execution_mode
        from trading.exchanges.venue_capabilities import CRYPTO_VENUE_ORDER
        kwargs = {}
        if source in CRYPTO_VENUE_ORDER:
            kwargs['execution_mode'] = resolve_crypto_execution_mode(getattr(owner, 'settings', {}), source).value
        log_event("analysis", message, exchange=source, level=level, **kwargs)
        states[key] = (code, now)
        return True
    except Exception:
        # A broken presentation sink must not interrupt position management.
        return False
