"""Source-tagged runtime status: transitions immediately, heartbeat at most 5m."""
import time


def emit_runtime_status(owner, source, code, message, *, level="INFO", interval=300):
    now = time.monotonic()
    states = getattr(owner, "_runtime_notice_states", None)
    if states is None:
        states = {}
        owner._runtime_notice_states = states
    previous = states.get(source)
    if previous and previous[0] == code and now - previous[1] < interval:
        return False
    from log_system.log_adapter import log_event
    try:
        log_event("analysis", message, exchange=source, level=level)
        states[source] = (code, now)
        return True
    except Exception:
        # A broken presentation sink must not interrupt position management.
        return False
