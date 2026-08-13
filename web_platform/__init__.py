"""NoahAI v3.9.1.0 Web UI transition platform.

The package is intentionally isolated from the legacy CustomTkinter runtime.
Importing it must not create windows, exchange clients, or trading workers.
"""

from .contracts import CONTRACT_SCHEMA_VERSION

__all__ = ["CONTRACT_SCHEMA_VERSION"]
