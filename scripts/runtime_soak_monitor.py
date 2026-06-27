#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""런타임 소크 모니터링 도구.

목적:
- 장시간 운용 중 메모리(RSS), 스레드 수, FD 수 변화를 주기적으로 기록
- 메모리 급증/스레드 누수 재발 여부를 수치로 확인

예시:
  python3 scripts/runtime_soak_monitor.py --pid 12345 --duration-min 360 --interval-sec 60
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Sample:
    ts: str
    elapsed_sec: int
    rss_mb: float
    threads: int
    open_fds: int


def _run_cmd(cmd: List[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _read_rss_mb(pid: int) -> float:
    # macOS/Linux 공통: ps rss(KB)
    out = _run_cmd(["ps", "-o", "rss=", "-p", str(pid)])
    try:
        kb = float(out.split()[0])
        return round(kb / 1024.0, 2)
    except Exception:
        return -1.0


def _read_threads(pid: int) -> int:
    # macOS: thcount, Linux: nlwp
    out = _run_cmd(["ps", "-o", "thcount=", "-p", str(pid)])
    if not out:
        out = _run_cmd(["ps", "-o", "nlwp=", "-p", str(pid)])
    if not out:
        # macOS 추가 폴백: `ps -M`은 스레드별 라인을 출력
        table = _run_cmd(["ps", "-M", "-p", str(pid)])
        if table:
            lines = [ln for ln in table.splitlines() if ln.strip()]
            if len(lines) >= 2:
                return max(1, len(lines) - 1)
    try:
        return int(out.split()[0])
    except Exception:
        return -1


def _read_open_fds(pid: int) -> int:
    try:
        proc_fd = Path(f"/proc/{pid}/fd")
        if proc_fd.exists():
            return len(list(proc_fd.iterdir()))
    except Exception:
        pass

    out = _run_cmd(["lsof", "-p", str(pid)])
    if not out:
        return -1
    # 헤더 1줄 제외
    lines = out.splitlines()
    return max(0, len(lines) - 1)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _safe_mean(values: List[float]) -> float:
    valid = [v for v in values if v >= 0]
    if not valid:
        return -1.0
    return round(statistics.mean(valid), 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoahAI 런타임 소크 모니터")
    parser.add_argument("--pid", type=int, required=True, help="모니터링할 프로세스 PID")
    parser.add_argument("--duration-min", type=int, default=60, help="총 모니터링 시간(분)")
    parser.add_argument("--interval-sec", type=int, default=60, help="샘플링 주기(초)")
    parser.add_argument("--mem-alert-mb", type=float, default=4096.0, help="경고 RSS 임계치(MB)")
    parser.add_argument(
        "--out",
        type=str,
        default="data/reports/runtime_soak_latest.json",
        help="결과 JSON 경로",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    pid = int(args.pid)
    duration_min = max(1, int(args.duration_min))
    interval_sec = max(5, int(args.interval_sec))
    max_samples = int((duration_min * 60) / interval_sec)
    mem_alert_mb = float(args.mem_alert_mb)

    if not _pid_alive(pid):
        print(f"FAIL | pid not alive: {pid}")
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now()
    started_epoch = time.time()
    samples: List[Sample] = []
    alerts: List[str] = []

    print(
        f"RUN  | pid={pid} duration={duration_min}min interval={interval_sec}s "
        f"samples={max_samples}"
    )

    for i in range(max_samples):
        if not _pid_alive(pid):
            alerts.append(f"process_exited_at_sample:{i}")
            break

        now = datetime.now()
        elapsed = int(time.time() - started_epoch)
        rss_mb = _read_rss_mb(pid)
        threads = _read_threads(pid)
        open_fds = _read_open_fds(pid)

        sample = Sample(
            ts=now.isoformat(timespec="seconds"),
            elapsed_sec=elapsed,
            rss_mb=rss_mb,
            threads=threads,
            open_fds=open_fds,
        )
        samples.append(sample)

        if rss_mb >= mem_alert_mb:
            alerts.append(f"high_rss:{rss_mb}MB@{sample.ts}")

        print(
            f"SAMPLE {i + 1:04d}/{max_samples} | rss={rss_mb}MB "
            f"threads={threads} fds={open_fds}"
        )
        if i < max_samples - 1:
            time.sleep(interval_sec)

    ended_at = datetime.now()

    rss_values = [s.rss_mb for s in samples]
    thread_values = [float(s.threads) for s in samples]
    fd_values = [float(s.open_fds) for s in samples]

    peak_rss = max([v for v in rss_values if v >= 0], default=-1.0)
    start_rss = next((v for v in rss_values if v >= 0), -1.0)
    end_rss = next((v for v in reversed(rss_values) if v >= 0), -1.0)
    rss_growth = round(end_rss - start_rss, 2) if start_rss >= 0 and end_rss >= 0 else -1.0

    result = {
        "meta": {
            "pid": pid,
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "duration_min": duration_min,
            "interval_sec": interval_sec,
            "requested_samples": max_samples,
            "collected_samples": len(samples),
            "mem_alert_mb": mem_alert_mb,
        },
        "summary": {
            "rss_mb": {
                "start": start_rss,
                "end": end_rss,
                "peak": peak_rss,
                "growth": rss_growth,
                "avg": _safe_mean(rss_values),
            },
            "threads": {
                "avg": _safe_mean(thread_values),
                "peak": max([v for v in thread_values if v >= 0], default=-1.0),
            },
            "open_fds": {
                "avg": _safe_mean(fd_values),
                "peak": max([v for v in fd_values if v >= 0], default=-1.0),
            },
            "alerts": alerts,
        },
        "samples": [asdict(s) for s in samples],
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    latest_path = out_path.parent / "runtime_soak_latest.json"
    if latest_path != out_path:
        latest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "PASS"
    if alerts:
        status = "WARN"

    print(
        f"{status} | rss_peak={peak_rss}MB rss_growth={rss_growth}MB "
        f"samples={len(samples)} out={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
