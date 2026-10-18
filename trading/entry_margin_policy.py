"""Entry-only margin acknowledgement. Never retries orders or changes a live position."""

def requested_margin(settings):
    value = str(settings.get("default_margin_type", "ISOLATED")).upper()
    if value == "CROSS": value = "CROSSED"
    if value not in {"ISOLATED", "CROSSED"}: raise ValueError("margin_mode_invalid")
    return value


def confirm_entry_margin(client, symbol, settings):
    method = getattr(client, "set_margin_type", None)
    if not callable(method): return False
    try: return method(symbol, requested_margin(settings)) is True
    except Exception: return False
