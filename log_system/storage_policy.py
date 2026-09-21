"""Account-wide diagnostic budget and persistent, non-renewing DEBUG leases."""
from __future__ import annotations

import json
import gzip
import hashlib
import os
import re
import tempfile
import threading
import time
from pathlib import Path

DEFAULT_LOG_BUDGET = 512 * 1024 * 1024
_LOCK = threading.RLock()
_CACHE = {}
_COMPACTION_LOCK = threading.Lock()
_SCHEDULED = {}
# Only closed timestamp-rotated files owned by the account logger. Never active
# trading.log / trading_okx.log, unrelated files, symlinks or numbered backups.
_ROTATED = re.compile(r'^trading(?:_[A-Za-z0-9]+)?\.\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d+\.log$')


def read_policy(root):
    try:
        value = json.loads((Path(root) / 'storage_policy.json').read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def write_policy(root, updates):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        value = {**read_policy(root), **updates}
        fd, temp = tempfile.mkstemp(prefix='.storage-policy-', dir=root)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(value, handle); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, root / 'storage_policy.json')
        finally:
            if os.path.exists(temp): os.unlink(temp)
        _CACHE.pop(str(root), None)
    return value


def debug_lease(root, hours):
    if hours not in (0,24,48,72): raise ValueError('invalid_debug_duration')
    return write_policy(root, {'debug_expires_at': time.time()+hours*3600 if hours else 0})


def disk_usage(root):
    root = Path(root)
    def size(paths):
        total = 0
        for path in paths:
            try:
                if path.is_file() and not path.is_symlink(): total += path.stat().st_size
            except OSError: pass
        return total
    return {
        'log_bytes': size((root/'logs').glob('*')),
        'log_archive_bytes': size((root/'log_archives').glob('*.gz')),
        'db_bytes': size(root.glob('*.db*')) + size(root.glob('event_audit.sqlite3*')),
        'learning_bytes': size(root.glob('ai_learning_data*')) + size(root.glob('learning.sqlite3*')) + size((root/'learning_segments').glob('*')),
    }


def compact_logs(root, *, force=False, max_files=8):
    """Bounded compression of closed diagnostics; originals removed only after
    byte-for-byte digest verification and a durable archive commit. No logging
    from this function (it can be scheduled by a loguru filter).
    """
    root = Path(root).resolve()
    if not _COMPACTION_LOCK.acquire(blocking=False): return 0
    completed = 0
    try:
        budget = int(read_policy(root).get('log_budget_bytes', DEFAULT_LOG_BUDGET))
        if not force and disk_usage(root)['log_bytes'] < budget * .8: return 0
        folder = root/'log_archives'
        if folder.is_symlink() or (root/'logs').is_symlink(): raise ValueError('unsafe_log_directory')
        folder.mkdir(exist_ok=True)
        candidates = sorted((p for p in (root/'logs').glob('*.log')
                             if _ROTATED.fullmatch(p.name) and not p.is_symlink()), key=lambda p:p.name)
        for source in candidates[:max_files]:
            before = source.stat()
            fd, temporary = tempfile.mkstemp(prefix='.log-archive-', dir=folder)
            try:
                digest = hashlib.sha256()
                with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
                    with gzip.GzipFile(fileobj=out, mode='wb', mtime=0) as packed:
                        for chunk in iter(lambda: inp.read(1024*1024), b''):
                            digest.update(chunk); packed.write(chunk)
                    out.flush(); os.fsync(out.fileno())
                verified = hashlib.sha256()
                with gzip.open(temporary, 'rb') as check:
                    for chunk in iter(lambda: check.read(1024*1024), b''): verified.update(chunk)
                after = source.stat()
                if verified.digest() != digest.digest(): raise ValueError('log_archive_verification_failed')
                if (before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns):
                    raise ValueError('rotated_log_changed')
                destination = folder / (source.name + '.' + digest.hexdigest() + '.gz')
                os.replace(temporary, destination)
                if os.name == 'posix':
                    directory = os.open(folder, os.O_RDONLY)
                    try: os.fsync(directory)
                    finally: os.close(directory)
                source.unlink()
                completed += 1
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        write_policy(root, {'last_log_compression':time.time() if completed else read_policy(root).get('last_log_compression'),
                            'log_archive_error':None})
        return completed
    except Exception as exc:
        try: write_policy(root, {'log_archive_error':type(exc).__name__})
        except OSError: pass
        return completed
    finally:
        with _LOCK: _CACHE.pop(str(root),None)
        _COMPACTION_LOCK.release()


def schedule_log_compaction(root):
    key = str(Path(root).resolve())
    with _LOCK:
        last, worker = _SCHEDULED.get(key, (0,None))
        if (worker and worker.is_alive()) or time.monotonic()-last < 60: return
        worker = threading.Thread(target=compact_logs, args=(key,), daemon=True, name='log-compaction')
        _SCHEDULED[key] = (time.monotonic(),worker)
        worker.start()


def diagnostic_filter(root, record):
    """Size accounting is cached; no directory scan on each event."""
    root = Path(root).resolve()
    key = str(root)
    with _LOCK:
        now = time.time(); cached = _CACHE.get(key)
        if not cached or now-cached[0] >= 5:
            cached = (now, read_policy(root), disk_usage(root)['log_bytes'])
            _CACHE[key] = cached
        _, policy, used = cached
        if used >= int(policy.get('log_budget_bytes',DEFAULT_LOG_BUDGET)) * .8:
            schedule_log_compaction(root)
        if record['level'].no < 20 and now >= float(policy.get('debug_expires_at',0)):
            return False
        if used >= int(policy.get('log_budget_bytes',DEFAULT_LOG_BUDGET)):
            if record.get('extra',{}).get('_audit_required') and not record.get('extra',{}).get('_audit_persisted'):
                return True  # Important evidence failed: retain the diagnostic fallback, even INFO.
            # log_event already persisted important records. Raw legacy warnings are
            # also durably diverted before their diagnostic copy is suppressed.
            if record['level'].no >= 30 and not record.get('extra',{}).get('_audit_persisted'):
                from log_system.event_audit import persist, failure
                persist('diagnostic_overflow',str(record.get('message','')),getattr(record['level'],'name','WARNING'),
                        None,root=root)
                if failure(root): return True  # disk failure remains visible in fallback diagnostics
            return False
        _CACHE[key] = (cached[0], policy, used+len(str(record.get('message','')).encode('utf-8'))+100)
        return True
