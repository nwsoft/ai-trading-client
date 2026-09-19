"""PC-owned authorization for remote start/resume. No settings are accepted remotely."""
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

from trading.remote_entry_pause import gate, VENUES


def settings_revision(settings):
    # Only a digest leaves the PC, never settings, keys or strategy source.
    return hashlib.sha256(json.dumps(settings, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


class RemoteControl:
    def __init__(self, directory, context, execute):
        self.path = Path(directory) / 'remote_control_receipts.json'
        self.context, self.execute = context, execute
        self.lock = threading.RLock()
        if self.path.exists():
            stored = json.loads(self.path.read_text())
            if not isinstance(stored,dict): raise ValueError('receipt_store_invalid')
            for receipt in stored.values():
                if receipt.get('status')=='uncertain' and receipt.get('source') in VENUES:
                    self._fence(receipt['source'])

    def _fence(self, source):
        state = gate(self.path.parent)
        # Even storage failure must stop new entries in this running process.
        with state.lock:
            state.paused.add(source)
            state.set(source, True)

    def run(self, cmd, approved):
        with self.lock:
            ident = str(cmd.get('id', ''))
            if not ident or len(ident) > 80:
                raise ValueError('invalid_command')
            # Persist reservation BEFORE invoking an engine. A crash must not
            # turn an uncertain start into an automatic retry after restart.
            receipts = {}
            if self.path.exists():
                receipts = json.loads(self.path.read_text())
                if not isinstance(receipts, dict):
                    raise ValueError('receipt_store_invalid')
            if ident in receipts:
                return receipts[ident]['status']
            source, action = cmd.get('source'), cmd.get('action')
            if source not in VENUES or action not in ('start', 'resume'):
                raise ValueError('unsupported_remote_action')
            expires = cmd.get('expires')
            if not isinstance(expires, (int, float)) or not time.time() < expires <= time.time() + 180:
                raise ValueError('remote_command_expired')
            current = self.context()
            expected = approved.get(source)
            row = next((r for r in current.get('sources', []) if r['source'] == source), {})
            if not expected or expected != {'revision': current.get('revision'), 'mode': row.get('mode')}:
                raise ValueError('pc_settings_changed')
            if cmd.get('revision') != expected['revision'] or cmd.get('mode') != expected['mode'] or row.get('mode') not in ('paper', 'live'):
                raise ValueError('remote_context_mismatch')
            if (action == 'start' and row.get('running')) or (action == 'resume' and not gate(self.path.parent).state(source)['paused']):
                raise ValueError('remote_state_changed')
            receipts = {k: v for k, v in receipts.items() if v.get('expires', 0) > time.time()}
            receipts[ident] = {'status': 'uncertain', 'source': source, 'expires': expires + 86400}
            self._save(receipts)
            try:
                # Handler rechecks credentials/membership/risk/mode/config at execution.
                self.execute(cmd)
                status = 'completed'
            except Exception:
                # Fail closed: retain the entry pause even if a start was partial.
                self._fence(source)
                status = 'rejected'
            receipts[ident]['status'] = status
            try:
                self._save(receipts)
            except Exception:
                self._fence(source)
                raise
            return status

    def _save(self, receipts):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        with os.fdopen(os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as stream:
            json.dump(receipts, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, self.path)


def safe_number(value):
    if isinstance(value, bool): return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None
