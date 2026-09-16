"""Shared fail-closed credential presence rules for Web UI and runtime gates."""

from __future__ import annotations

from typing import Any


_PLACEHOLDERS = {
    "", "none", "null", "undefined", "redacted", "<redacted>",
    "masked", "미설정", "설정안됨", "notconfigured", "notset",
}


def credential_value_present(value: Any) -> bool:
    """Return true only for a real, non-placeholder credential value.

    UI masks and migration placeholders must never authorize an account query or
    make the client claim that a key is configured.
    """
    if value is None or isinstance(value, bool):
        return False
    text = str(value).strip()
    compact = text.lower().replace(" ", "").replace("_", "").replace("-", "")
    if compact in _PLACEHOLDERS:
        return False
    if text and set(text) <= {"*", "•", "·", "x", "X"}:
        return False
    return bool(text)


def all_credentials_present(*values: Any) -> bool:
    return bool(values) and all(credential_value_present(value) for value in values)


def stock_credentials_present(source: str, config: Any) -> bool:
    """Fail closed for each supported broker's actual login contract."""
    if not isinstance(config, dict):
        return False
    normalized = str(source or "").replace("_", "").strip().lower()
    if normalized == "kiwoom":
        # OpenAPI+ may discover the account after login, but an ID alone or an
        # account number alone is not a configured login in NoahAI.
        return all_credentials_present(config.get("id") or config.get("user_id"), config.get("password"))
    return all_credentials_present(config.get("app_key"), config.get("app_secret"), config.get("account_no"))
