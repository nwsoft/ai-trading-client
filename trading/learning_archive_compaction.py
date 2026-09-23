"""Lossless streaming compaction of closed legacy learning archives only."""
import gzip
import hashlib
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_ARCHIVE = re.compile(r'^ai_learning_data_(binance|okx|bybit|bitget|upbit|bithumb|coinone)_archive_(\d{8})\.(jsonl|json)$')


def candidates(root):
    today = datetime.now().strftime('%Y%m%d')
    result = []
    for p in Path(root).glob('ai_learning_data_*_archive_*'):
        match = _ARCHIVE.fullmatch(p.name)
        try:
            if match and match[2] < today and not p.is_symlink() and p.is_file() and time.time()-p.stat().st_mtime > 60:
                result.append(p)
        except FileNotFoundError:
            continue  # A concurrent committed conversion is not a status error.
    return sorted(result)


@contextmanager
def _account_lock(root):
    path = root/'.learning_compaction.lock'
    if path.is_symlink(): raise ValueError('unsafe_compaction_lock')
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def compact_one(source, progress=lambda size: None):
    source = Path(source)
    with _account_lock(source.parent):
        # A killed worker leaves its source intact and may leave an incomplete
        # temporary. OS lock proves no other compatible writer owns these files.
        for orphan in source.parent.glob('.learning-pack-*'):
            if re.fullmatch(r'\.learning-pack-[a-z0-9_]{8}', orphan.name) and not orphan.is_symlink() and orphan.is_file():
                orphan.unlink()
        return _compact_one(source, progress)


def _compact_one(source, progress):
    """Commit gzip only after decompression SHA-256 matches source bytes.

    Replacing the closed plain file is recoverable by gzip decompression. Never
    operates on current JSON/journal, a trading DB, today's archive or symlinks.
    """
    source = Path(source)
    if source not in candidates(source.parent):
        raise ValueError('not_closed_learning_archive')
    before = source.stat()
    signature = lambda s: (s.st_ino, s.st_size, s.st_mtime_ns)
    destination = source.with_name(source.name + '.gz')
    if destination.is_symlink(): raise ValueError('unsafe_archive_destination')
    fd, temporary = tempfile.mkstemp(prefix='.learning-pack-', dir=source.parent)
    try:
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            with gzip.GzipFile(fileobj=out, mode='wb', compresslevel=6, mtime=0) as packed:
                for chunk in iter(lambda: inp.read(1024*1024), b''):
                    packed.write(chunk); digest.update(chunk); total += len(chunk)
                    progress(total)
            out.flush(); os.fsync(out.fileno())
        verify = hashlib.sha256()
        with gzip.open(temporary, 'rb') as inp:
            for chunk in iter(lambda: inp.read(1024*1024), b''): verify.update(chunk)
        if verify.digest() != digest.digest() or signature(source.stat()) != signature(before):
            raise ValueError('learning_archive_changed_or_corrupt')
        # A leftover committed archive after a crash must agree before replacing.
        if destination.exists():
            prior = hashlib.sha256()
            with gzip.open(destination, 'rb') as inp:
                for chunk in iter(lambda: inp.read(1024*1024), b''): prior.update(chunk)
            if prior.digest() != digest.digest(): raise ValueError('learning_archive_destination_conflict')
        os.replace(temporary, destination)
        if os.name == 'posix':
            directory = os.open(source.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        if source.is_symlink() or signature(source.stat()) != signature(before):
            raise ValueError('learning_archive_changed_after_commit')
        source.unlink()
        return {'source_bytes':total, 'archive_bytes':destination.stat().st_size,
                'saved_bytes':total-destination.stat().st_size, 'sha256':digest.hexdigest()}
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
