"""Validate/install an operator-reviewed recipient registry. Never contacts recipients."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading.finance_connections import validate_recipient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-directory', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with Path(args.registry).open('rb') as stream:
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        parser.error('registry_too_large')
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) > 100:
        parser.error('registry_invalid')
    rows = [validate_recipient(r) for r in rows]
    if len({r['id'] for r in rows}) != len(rows):
        parser.error('duplicate_recipient')
    print(json.dumps({'validated_count': len(rows), 'enabled_count': sum(r['enabled'] for r in rows), 'applied': args.apply, 'network_called': False}))
    if not args.apply:
        return
    directory = Path(args.data_directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'finance_recipients.json'
    previous = target.read_bytes() if target.exists() else None
    def write_private(path, data):
        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    if previous is not None:
        write_private(directory / ('finance_recipients.before-' + secrets.token_hex(8) + '.json'), previous)
    temp = directory / ('finance_recipients.' + secrets.token_hex(8) + '.tmp')
    try:
        write_private(temp, json.dumps(rows, ensure_ascii=False, indent=2).encode())
        if (target.read_bytes() if target.exists() else None) != previous:
            raise RuntimeError('registry_changed_retry')
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
