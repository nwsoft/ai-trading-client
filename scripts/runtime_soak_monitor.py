#!/usr/bin/env python3
"""Cross-platform NoahAI runtime and PAPER Gateway soak monitor.

The monitor records process growth and, when a loopback Gateway URL is
provided, the same runtime/workspace reads used by the Web UI.  It never writes
the Gateway token or account credentials to the report.

Windows 24-hour example (PowerShell):

  $env:NOAHAI_GATEWAY_URL = "http://127.0.0.1:3910"
  $env:NOAHAI_GATEWAY_TOKEN = "<operator-controlled 32+ character token>"
  python scripts/runtime_soak_monitor.py --pid 1234 --duration-min 1440 `
    --interval-sec 60 --require-paper --sources binance,upbit,bithumb,bybit,okx,bitget
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psutil
import requests


DEFAULT_SOURCES = ("binance", "upbit", "bithumb", "bybit", "okx", "bitget")


@dataclass
class Sample:
    ts: str
    elapsed_sec: int
    rss_mb: float
    threads: int
    open_fds: int
    gateway: dict[str, Any] | None = None


def _process(pid: int) -> psutil.Process | None:
    try:
        process = psutil.Process(pid)
        return process if process.is_running() else None
    except (psutil.Error, OSError):
        return None


def _processes_for_roots(root_pids: tuple[int, ...]) -> list[psutil.Process]:
    """Return unique live roots and descendants for Electron/one-file engines."""
    processes: dict[int, psutil.Process] = {}
    for root_pid in root_pids:
        root = _process(root_pid)
        if root is None:
            continue
        candidates = [root]
        try:
            candidates.extend(root.children(recursive=True))
        except (psutil.Error, OSError):
            pass
        for process in candidates:
            try:
                if process.is_running():
                    processes[int(process.pid)] = process
            except (psutil.Error, OSError):
                continue
    return list(processes.values())


def _read_rss_mb(pid: int, extra_pids: tuple[int, ...] = ()) -> float:
    processes = _processes_for_roots((pid, *extra_pids))
    if not processes:
        return -1.0
    total = 0
    valid = 0
    for process in processes:
        try:
            total += int(process.memory_info().rss)
            valid += 1
        except (psutil.Error, OSError):
            continue
    return round(total / (1024 * 1024), 2) if valid else -1.0


def _read_threads(pid: int, extra_pids: tuple[int, ...] = ()) -> int:
    processes = _processes_for_roots((pid, *extra_pids))
    if not processes:
        return -1
    total = 0
    valid = 0
    for process in processes:
        try:
            total += int(process.num_threads())
            valid += 1
        except (psutil.Error, OSError):
            continue
    return total if valid else -1


def _read_open_fds(pid: int, extra_pids: tuple[int, ...] = ()) -> int:
    processes = _processes_for_roots((pid, *extra_pids))
    if not processes:
        return -1
    total = 0
    valid = 0
    for process in processes:
        try:
            if hasattr(process, "num_handles"):
                total += int(process.num_handles())
                valid += 1
            elif hasattr(process, "num_fds"):
                total += int(process.num_fds())
                valid += 1
        except (psutil.Error, OSError):
            continue
    return total if valid else -1


def _pid_alive(pid: int) -> bool:
    return _process(pid) is not None


def _safe_mean(values: list[float]) -> float:
    valid = [value for value in values if value >= 0]
    return round(statistics.mean(valid), 2) if valid else -1.0


def _growth(values: list[float]) -> float:
    valid = [value for value in values if value >= 0]
    return round(valid[-1] - valid[0], 2) if len(valid) >= 2 else 0.0 if valid else -1.0


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(value for value in values if value >= 0)
    if not ordered:
        return -1.0
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * max(0.0, min(float(percentile), 100.0)) / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def _safe_error(reason: object) -> str:
    # Never serialize request headers, token values, or raw response bodies.
    return f"{type(reason).__name__}: {str(reason)}"[:240]


def _request_json(
    session: requests.Session,
    *,
    url: str,
    token: str,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.perf_counter()
    try:
        response = session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=max(1.0, float(timeout_sec)),
        )
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("gateway_response_not_object")
        return payload, {"ok": True, "status_code": response.status_code, "latency_ms": latency_ms}
    except (requests.RequestException, ValueError, json.JSONDecodeError) as reason:
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        status_code = int(getattr(getattr(reason, "response", None), "status_code", 0) or 0)
        return None, {
            "ok": False,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error": _safe_error(reason),
        }


def poll_gateway(
    session: requests.Session,
    *,
    base_url: str,
    token: str,
    sources: tuple[str, ...],
    timeout_sec: float,
    include_control_surfaces: bool = True,
) -> dict[str, Any]:
    base_url = str(base_url).rstrip("/")
    runtime_payload, runtime_meta = _request_json(
        session,
        url=f"{base_url}/api/v1/runtime/snapshot",
        token=token,
        timeout_sec=timeout_sec,
    )
    runtime_payload = runtime_payload or {}
    runtime_meta.update({
        "running_sources": list(runtime_payload.get("running_sources") or []),
        "execution_modes": dict(runtime_payload.get("execution_modes") or {}),
    })

    control_surfaces: dict[str, Any] = {}
    if include_control_surfaces:
        settings_payload, settings_meta = _request_json(
            session,
            url=f"{base_url}/api/v1/settings",
            token=token,
            timeout_sec=timeout_sec,
        )
        settings_payload = settings_payload or {}
        settings_meta["field_count"] = len(settings_payload.get("fields") or [])
        control_surfaces["settings"] = settings_meta

        strategy_payload, strategy_meta = _request_json(
            session,
            url=f"{base_url}/api/v1/strategies",
            token=token,
            timeout_sec=timeout_sec,
        )
        strategy_payload = strategy_payload or {}
        strategies = list(strategy_payload.get("strategies") or [])
        strategy_meta.update({
            "strategy_count": len(strategies),
            "version_count": sum(
                len(dict(row).get("versions") or [])
                for row in strategies if isinstance(row, dict)
            ),
            "paper_outcome_count": len(strategy_payload.get("paper_outcomes") or []),
        })
        control_surfaces["ai_custom"] = strategy_meta

    workspaces: dict[str, Any] = {}
    for source in sources:
        url = (
            f"{base_url}/api/v1/workspaces/blockchain/blockchain.source_workspaces"
            f"?source={quote(source)}&learning_offset=0&learning_limit=50"
        )
        payload, meta = _request_json(
            session, url=url, token=token, timeout_sec=timeout_sec,
        )
        payload = payload or {}
        policy = dict(payload.get("paper_position_policy") or {})
        statistics_row = dict(payload.get("paper_statistics") or {})
        paper_positions = list(payload.get("paper_positions") or [])
        paper_trades = list(payload.get("paper_trades") or [])
        active_strategies = list(payload.get("active_custom_strategies") or [])
        meta.update({
            "execution_mode": str(payload.get("execution_mode") or "").upper(),
            "paper_positions_status": str(payload.get("paper_positions_status") or ""),
            "paper_position_count": len(paper_positions),
            "paper_position_mode": str(policy.get("mode") or ""),
            "paper_position_limit": int(policy.get("limit") or 0),
            "paper_closed_count": int(statistics_row.get("closed_count") or 0),
            "paper_recent_rows": len(paper_trades),
            "active_custom_strategy_count": len(active_strategies),
            "active_custom_strategy_versions": sorted({
                str(row.get("version_id") or "").strip()
                for row in active_strategies if isinstance(row, dict) and row.get("version_id")
            }),
            "active_custom_strategy_names": [
                str(row.get("name") or row.get("strategy_key") or row.get("version_id") or "")[:160]
                for row in active_strategies[:10] if isinstance(row, dict)
            ],
            "paper_position_strategy_versions": sorted({
                str(row.get("custom_strategy_version_id") or "").strip()
                for row in paper_positions if isinstance(row, dict) and row.get("custom_strategy_version_id")
            }),
            "paper_trade_strategy_versions": sorted({
                str(row.get("version_id") or row.get("strategy_version_id") or "").strip()
                for row in paper_trades
                if isinstance(row, dict) and (row.get("version_id") or row.get("strategy_version_id"))
            }),
        })
        workspaces[source] = meta
    return {
        "runtime": runtime_meta,
        "control_surfaces": control_surfaces,
        "workspaces": workspaces,
    }


def summarize_gateway(samples: list[Sample], sources: tuple[str, ...]) -> dict[str, Any]:
    runtime_rows = [sample.gateway.get("runtime", {}) for sample in samples if sample.gateway]
    last_runtime = runtime_rows[-1] if runtime_rows else {}
    running_miss_counts = {
        source: sum(
            1 for row in runtime_rows
            if row.get("ok") and source not in set(row.get("running_sources") or [])
        )
        for source in sources
    }
    runtime_mode_mismatch_counts = {
        source: sum(
            1 for row in runtime_rows
            if row.get("ok") and str(dict(row.get("execution_modes") or {}).get(source) or "").upper() != "PAPER"
        )
        for source in sources
    }
    summary: dict[str, Any] = {
        "runtime": _latency_summary(runtime_rows),
        "control_surfaces": {},
        "workspaces": {},
        "paper_mode_mismatches": [],
    }
    summary["runtime"].update({
        "last_running_sources": list(last_runtime.get("running_sources") or []),
        "last_execution_modes": dict(last_runtime.get("execution_modes") or {}),
        "running_miss_counts": running_miss_counts,
        "paper_mode_mismatch_counts": runtime_mode_mismatch_counts,
    })
    for surface in ("settings", "ai_custom"):
        rows = [
            dict(sample.gateway.get("control_surfaces", {}).get(surface) or {})
            for sample in samples
            if sample.gateway and sample.gateway.get("control_surfaces", {}).get(surface)
        ]
        summary["control_surfaces"][surface] = _latency_summary(rows)
    for source in sources:
        rows = [
            sample.gateway.get("workspaces", {}).get(source, {})
            for sample in samples if sample.gateway
        ]
        source_summary = _latency_summary(rows)
        valid_modes = [str(row.get("execution_mode") or "").upper() for row in rows if row.get("ok")]
        position_modes = [str(row.get("paper_position_mode") or "").lower() for row in rows if row.get("ok")]
        limits = [int(row.get("paper_position_limit") or 0) for row in rows if row.get("ok")]
        positions = [int(row.get("paper_position_count") or 0) for row in rows if row.get("ok")]
        position_statuses = [str(row.get("paper_positions_status") or "") for row in rows if row.get("ok")]
        active_counts = [int(row.get("active_custom_strategy_count") or 0) for row in rows if row.get("ok")]
        successful_rows = [row for row in rows if row.get("ok")]
        active_version_presence: dict[str, int] = {}
        observed_attribution_versions: set[str] = set()
        for row in rows:
            if not row.get("ok"):
                continue
            for version_id in set(row.get("active_custom_strategy_versions") or []):
                active_version_presence[str(version_id)] = active_version_presence.get(str(version_id), 0) + 1
            observed_attribution_versions.update(map(str, row.get("paper_position_strategy_versions") or []))
            observed_attribution_versions.update(map(str, row.get("paper_trade_strategy_versions") or []))
        source_summary.update({
            "last_execution_mode": valid_modes[-1] if valid_modes else "",
            "paper_mode_mismatch_count": sum(mode != "PAPER" for mode in valid_modes),
            "last_position_mode": position_modes[-1] if position_modes else "",
            "last_position_limit": limits[-1] if limits else 0,
            "max_paper_positions": max(positions, default=0),
            "paper_position_status_failures": sum(status != "success" for status in position_statuses),
            "active_custom_strategy_empty_samples": sum(count == 0 for count in active_counts),
            "active_custom_strategy_version_presence": active_version_presence,
            "last_active_custom_strategy_names": list(successful_rows[-1].get("active_custom_strategy_names") or []) if successful_rows else [],
            "observed_paper_attribution_versions": sorted(observed_attribution_versions),
        })
        summary["workspaces"][source] = source_summary
        if valid_modes and any(mode != "PAPER" for mode in valid_modes):
            summary["paper_mode_mismatches"].append(source)
    return summary


def _latency_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(row.get("latency_ms", -1.0)) for row in rows]
    success_count = sum(1 for row in rows if row.get("ok") is True)
    failure_count = sum(1 for row in rows if row.get("ok") is False)
    return {
        "samples": len(rows),
        "success_count": success_count,
        "failure_count": failure_count,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "max_ms": round(max([value for value in latencies if value >= 0], default=-1.0), 2),
    }


def evaluate_thresholds(
    *,
    rss_growth: float,
    thread_growth: float,
    fd_growth: float,
    gateway_summary: dict[str, Any] | None,
    sources: tuple[str, ...],
    max_rss_growth_mb: float,
    max_thread_growth: int,
    max_fd_growth: int,
    runtime_p95_ms: float,
    workspace_p95_ms: float,
    require_paper: bool,
    enforce_position_limit: bool,
    expected_position_mode: str = "",
    expected_position_limit: int = 0,
    settings_p95_ms: float = 300.0,
    strategy_p95_ms: float = 300.0,
    require_active_custom_strategy: bool = False,
    expected_strategy_version: str = "",
    require_paper_attribution: bool = False,
) -> list[str]:
    failures: list[str] = []
    if rss_growth >= 0 and rss_growth > max_rss_growth_mb:
        failures.append(f"rss_growth_exceeded:{rss_growth}>{max_rss_growth_mb}")
    if thread_growth >= 0 and thread_growth > max_thread_growth:
        failures.append(f"thread_growth_exceeded:{thread_growth}>{max_thread_growth}")
    if fd_growth >= 0 and fd_growth > max_fd_growth:
        failures.append(f"handle_growth_exceeded:{fd_growth}>{max_fd_growth}")
    if gateway_summary is None:
        return failures
    runtime = dict(gateway_summary.get("runtime") or {})
    if runtime.get("failure_count", 0):
        failures.append(f"runtime_gateway_failures:{runtime['failure_count']}")
    if float(runtime.get("p95_ms", -1) or -1) > runtime_p95_ms:
        failures.append(f"runtime_p95_exceeded:{runtime['p95_ms']}>{runtime_p95_ms}")
    control_thresholds = {
        "settings": float(settings_p95_ms),
        "ai_custom": float(strategy_p95_ms),
    }
    for surface, threshold in control_thresholds.items():
        row = dict(gateway_summary.get("control_surfaces", {}).get(surface) or {})
        if row.get("failure_count", 0):
            failures.append(f"control_surface_failures:{surface}:{row['failure_count']}")
        if float(row.get("p95_ms", -1) or -1) > threshold:
            failures.append(
                f"control_surface_p95_exceeded:{surface}:{row['p95_ms']}>{threshold}"
            )
    for source in sources:
        row = dict(gateway_summary.get("workspaces", {}).get(source) or {})
        if row.get("failure_count", 0):
            failures.append(f"workspace_failures:{source}:{row['failure_count']}")
        if float(row.get("p95_ms", -1) or -1) > workspace_p95_ms:
            failures.append(f"workspace_p95_exceeded:{source}:{row['p95_ms']}>{workspace_p95_ms}")
        workspace_mode_mismatches = int(row.get("paper_mode_mismatch_count", 0) or 0)
        if require_paper and workspace_mode_mismatches:
            failures.append(f"workspace_paper_mode_mismatch:{source}:{workspace_mode_mismatches}_samples")
        elif require_paper and row.get("last_execution_mode") != "PAPER":
            failures.append(f"paper_mode_required:{source}:{row.get('last_execution_mode') or 'missing'}")
        if require_paper and int(runtime.get("running_miss_counts", {}).get(source, 0) or 0):
            failures.append(
                f"paper_source_not_running:{source}:"
                f"{runtime['running_miss_counts'][source]}_samples"
            )
        if require_paper and int(runtime.get("paper_mode_mismatch_counts", {}).get(source, 0) or 0):
            failures.append(
                f"runtime_paper_mode_mismatch:{source}:"
                f"{runtime['paper_mode_mismatch_counts'][source]}_samples"
            )
        if require_paper and int(row.get("paper_position_status_failures", 0) or 0):
            failures.append(
                f"paper_position_status_failure:{source}:"
                f"{row['paper_position_status_failures']}_samples"
            )
        if require_active_custom_strategy and int(row.get("active_custom_strategy_empty_samples", 0) or 0):
            failures.append(
                f"active_custom_strategy_missing:{source}:"
                f"{row['active_custom_strategy_empty_samples']}_samples"
            )
        if expected_strategy_version:
            present = int(
                dict(row.get("active_custom_strategy_version_presence") or {}).get(
                    expected_strategy_version, 0,
                ) or 0
            )
            successful = int(row.get("success_count", 0) or 0)
            if present < successful:
                failures.append(
                    f"expected_strategy_version_missing:{source}:"
                    f"{expected_strategy_version}:{successful - present}_samples"
                )
        if require_paper_attribution:
            observed = set(map(str, row.get("observed_paper_attribution_versions") or []))
            if expected_strategy_version and expected_strategy_version not in observed:
                failures.append(
                    f"expected_strategy_paper_attribution_missing:{source}:{expected_strategy_version}"
                )
            elif not expected_strategy_version and not observed:
                failures.append(f"paper_strategy_attribution_missing:{source}")
        reported_mode = str(row.get("last_position_mode") or "").lower()
        reported_limit = int(row.get("last_position_limit") or 0)
        if expected_position_mode and reported_mode != expected_position_mode:
            failures.append(
                f"paper_position_mode_mismatch:{source}:"
                f"{reported_mode or 'missing'}!={expected_position_mode}"
            )
        if expected_position_limit > 0 and reported_limit != expected_position_limit:
            failures.append(
                f"paper_position_limit_mismatch:{source}:"
                f"{reported_limit}!={expected_position_limit}"
            )
        limit = expected_position_limit if expected_position_limit > 0 else reported_limit
        active = int(row.get("max_paper_positions") or 0)
        if enforce_position_limit and limit > 0 and active > limit:
            failures.append(f"paper_position_limit_exceeded:{source}:{active}>{limit}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoahAI runtime/PAPER Gateway soak monitor")
    parser.add_argument("--pid", type=int, required=True, help="NoahAIEngine process PID")
    parser.add_argument(
        "--extra-pids", default="",
        help="Comma-separated additional root PIDs, normally NoahAI.exe when --pid is the external engine",
    )
    parser.add_argument("--duration-min", type=int, default=60)
    parser.add_argument("--interval-sec", type=int, default=60)
    parser.add_argument("--mem-alert-mb", type=float, default=4096.0)
    parser.add_argument("--max-rss-growth-mb", type=float, default=512.0)
    parser.add_argument("--max-thread-growth", type=int, default=32)
    parser.add_argument("--max-handle-growth", type=int, default=64)
    parser.add_argument("--gateway-url", default=os.environ.get("NOAHAI_GATEWAY_URL", ""))
    parser.add_argument("--gateway-token-env", default="NOAHAI_GATEWAY_TOKEN")
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES))
    parser.add_argument("--request-timeout-sec", type=float, default=12.0)
    parser.add_argument("--runtime-p95-ms", type=float, default=150.0)
    parser.add_argument("--workspace-p95-ms", type=float, default=300.0)
    parser.add_argument("--settings-p95-ms", type=float, default=300.0)
    parser.add_argument("--strategy-p95-ms", type=float, default=300.0)
    parser.add_argument(
        "--control-surface-every", type=int, default=5,
        help="Probe settings and AI Custom every N samples (default: every five minutes at 60s interval)",
    )
    parser.add_argument("--require-paper", action="store_true")
    parser.add_argument(
        "--enforce-position-limit", action="store_true",
        help="Fail when active PAPER positions exceed the reported cap; use only for a fresh-position soak",
    )
    parser.add_argument(
        "--expected-position-mode", choices=("focus", "multi"), default=None,
        help="Require every source to report this normalized PAPER position mode",
    )
    parser.add_argument(
        "--expected-position-limit", type=int, default=0,
        help="Require every source to report this exact PAPER position cap (focus=1, multi default=3)",
    )
    parser.add_argument(
        "--require-active-custom-strategy", action="store_true",
        help="Fail if the runtime PAPER strategy pool is empty in any sampled workspace",
    )
    parser.add_argument(
        "--expected-strategy-version", default="",
        help="Require this exact AI Custom version_id in the runtime pool for every successful sample",
    )
    parser.add_argument(
        "--require-paper-attribution", action="store_true",
        help="Require a PAPER position or closed PAPER row attributed to a custom strategy version",
    )
    parser.add_argument("--out", default="data/reports/runtime_soak_latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pid = int(args.pid)
    try:
        extra_pids = tuple(dict.fromkeys(
            int(value.strip()) for value in str(args.extra_pids).split(",") if value.strip()
        ))
    except ValueError:
        print("FAIL | --extra-pids must be comma-separated integers")
        return 2
    process_pids = tuple(dict.fromkeys((pid, *extra_pids)))
    duration_min = max(1, int(args.duration_min))
    interval_sec = max(5, int(args.interval_sec))
    max_samples = max(1, int((duration_min * 60) / interval_sec))
    sources = tuple(dict.fromkeys(
        source.strip().lower() for source in str(args.sources).split(",") if source.strip()
    ))
    invalid_sources = [source for source in sources if source not in DEFAULT_SOURCES]
    if invalid_sources or not sources:
        print(f"FAIL | invalid sources: {invalid_sources or 'empty'}")
        return 2
    missing_pids = [process_pid for process_pid in process_pids if not _pid_alive(process_pid)]
    if missing_pids:
        print(f"FAIL | pid not alive: {','.join(map(str, missing_pids))}")
        return 2

    gateway_url = str(args.gateway_url or "").strip().rstrip("/")
    gateway_token = str(os.environ.get(str(args.gateway_token_env), "") or "").strip()
    if gateway_url and len(gateway_token) < 32:
        print(f"FAIL | {args.gateway_token_env} must contain at least 32 characters")
        return 2
    if args.require_paper and not gateway_url:
        print("FAIL | --require-paper needs --gateway-url and token environment")
        return 2
    if int(args.expected_position_limit) < 0:
        print("FAIL | --expected-position-limit must be zero or greater")
        return 2
    if int(args.control_surface_every) < 1:
        print("FAIL | --control-surface-every must be at least 1")
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now()
    started_epoch = time.time()
    samples: list[Sample] = []
    alerts: list[str] = []
    session = requests.Session()

    print(
        f"RUN  | pid={pid} duration={duration_min}min interval={interval_sec}s "
        f"samples={max_samples} gateway={'on' if gateway_url else 'off'} sources={','.join(sources)}"
    )
    for index in range(max_samples):
        missing_pids = [process_pid for process_pid in process_pids if not _pid_alive(process_pid)]
        if missing_pids:
            alerts.append(f"process_exited_at_sample:{index}:{','.join(map(str, missing_pids))}")
            break
        rss_mb = _read_rss_mb(pid, extra_pids)
        threads = _read_threads(pid, extra_pids)
        open_fds = _read_open_fds(pid, extra_pids)
        gateway = poll_gateway(
            session,
            base_url=gateway_url,
            token=gateway_token,
            sources=sources,
            timeout_sec=args.request_timeout_sec,
            include_control_surfaces=index % int(args.control_surface_every) == 0,
        ) if gateway_url else None
        sample = Sample(
            ts=datetime.now().isoformat(timespec="seconds"),
            elapsed_sec=int(time.time() - started_epoch),
            rss_mb=rss_mb,
            threads=threads,
            open_fds=open_fds,
            gateway=gateway,
        )
        samples.append(sample)
        if rss_mb >= float(args.mem_alert_mb):
            alerts.append(f"high_rss:{rss_mb}MB@{sample.ts}")
        gateway_label = ""
        if gateway:
            runtime_ms = gateway["runtime"].get("latency_ms", -1)
            workspace_ms = [row.get("latency_ms", -1) for row in gateway["workspaces"].values()]
            gateway_label = f" runtime={runtime_ms}ms workspace_max={max(workspace_ms, default=-1)}ms"
        print(
            f"SAMPLE {index + 1:04d}/{max_samples} | rss={rss_mb}MB "
            f"threads={threads} handles={open_fds}{gateway_label}"
        )
        if index < max_samples - 1:
            time.sleep(interval_sec)

    session.close()
    rss_values = [sample.rss_mb for sample in samples]
    thread_values = [float(sample.threads) for sample in samples]
    fd_values = [float(sample.open_fds) for sample in samples]
    gateway_summary = summarize_gateway(samples, sources) if gateway_url else None
    threshold_failures = evaluate_thresholds(
        rss_growth=_growth(rss_values),
        thread_growth=_growth(thread_values),
        fd_growth=_growth(fd_values),
        gateway_summary=gateway_summary,
        sources=sources,
        max_rss_growth_mb=float(args.max_rss_growth_mb),
        max_thread_growth=int(args.max_thread_growth),
        max_fd_growth=int(args.max_handle_growth),
        runtime_p95_ms=float(args.runtime_p95_ms),
        workspace_p95_ms=float(args.workspace_p95_ms),
        require_paper=bool(args.require_paper),
        enforce_position_limit=bool(args.enforce_position_limit),
        expected_position_mode=str(args.expected_position_mode or ""),
        expected_position_limit=int(args.expected_position_limit),
        settings_p95_ms=float(args.settings_p95_ms),
        strategy_p95_ms=float(args.strategy_p95_ms),
        require_active_custom_strategy=bool(args.require_active_custom_strategy),
        expected_strategy_version=str(args.expected_strategy_version or "").strip(),
        require_paper_attribution=bool(args.require_paper_attribution),
    )
    failures = alerts + threshold_failures
    result = {
        "status": "FAIL" if failures else "PASS",
        "meta": {
            "pid": pid,
            "pids": list(process_pids),
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "duration_min": duration_min,
            "interval_sec": interval_sec,
            "requested_samples": max_samples,
            "collected_samples": len(samples),
            "gateway_enabled": bool(gateway_url),
            "sources": list(sources),
            "require_paper": bool(args.require_paper),
            "enforce_position_limit": bool(args.enforce_position_limit),
            "expected_position_mode": str(args.expected_position_mode or ""),
            "expected_position_limit": int(args.expected_position_limit),
            "control_surface_every": int(args.control_surface_every),
            "require_active_custom_strategy": bool(args.require_active_custom_strategy),
            "expected_strategy_version": str(args.expected_strategy_version or "").strip(),
            "require_paper_attribution": bool(args.require_paper_attribution),
        },
        "thresholds": {
            "mem_alert_mb": float(args.mem_alert_mb),
            "max_rss_growth_mb": float(args.max_rss_growth_mb),
            "max_thread_growth": int(args.max_thread_growth),
            "max_handle_growth": int(args.max_handle_growth),
            "runtime_p95_ms": float(args.runtime_p95_ms),
            "workspace_p95_ms": float(args.workspace_p95_ms),
            "settings_p95_ms": float(args.settings_p95_ms),
            "strategy_p95_ms": float(args.strategy_p95_ms),
        },
        "summary": {
            "rss_mb": {
                "start": next((value for value in rss_values if value >= 0), -1.0),
                "end": next((value for value in reversed(rss_values) if value >= 0), -1.0),
                "peak": max([value for value in rss_values if value >= 0], default=-1.0),
                "growth": _growth(rss_values),
                "avg": _safe_mean(rss_values),
            },
            "threads": {
                "avg": _safe_mean(thread_values),
                "peak": max([value for value in thread_values if value >= 0], default=-1.0),
                "growth": _growth(thread_values),
            },
            "open_fds_or_handles": {
                "avg": _safe_mean(fd_values),
                "peak": max([value for value in fd_values if value >= 0], default=-1.0),
                "growth": _growth(fd_values),
            },
            "gateway": gateway_summary,
            "failures": failures,
        },
        "samples": [asdict(sample) for sample in samples],
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    out_path.write_text(serialized, encoding="utf-8")
    latest_path = out_path.parent / "runtime_soak_latest.json"
    if latest_path != out_path:
        latest_path.write_text(serialized, encoding="utf-8")
    print(
        f"{result['status']} | rss_peak={result['summary']['rss_mb']['peak']}MB "
        f"rss_growth={result['summary']['rss_mb']['growth']}MB "
        f"samples={len(samples)} failures={len(failures)} out={out_path}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
