"""Secret-free host lifecycle breadcrumbs (no credentials or API payloads)."""
import json
import os
from datetime import datetime, timezone


def record_stage(stage: str, *, error_type: str = "", log_path: str | None = None) -> None:
    path = log_path or os.environ.get("NOAHAI_KIWOOM_DIAGNOSTIC_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                                     "pid": os.getpid(), "stage": stage,
                                     "error_type": error_type}) + "\n")
    except OSError:
        pass
