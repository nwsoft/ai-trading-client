#!/usr/bin/env python3
"""Read the exact, version-scoped acceptance snapshot without running a release."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_plan(root: Path, version: str) -> dict:
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version):
        raise ValueError('Expected A.B.C.D version')
    path = root / 'docs/DEPLOY_CHECKLIST.md'
    marker = f'<!-- patch-test-plan-version: {version} -->'
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    if text.count(marker) != 1:
        raise ValueError('Expected exactly one version-scoped acceptance plan')
    body = text.split(marker, 1)[1]
    if '<!-- patch-test-plan-end -->' not in body:
        raise ValueError('Acceptance plan end marker missing')
    body = body.split('<!-- patch-test-plan-end -->', 1)[0]
    if '<!-- patch-test-plan-version:' in body:
        raise ValueError('Acceptance plan crosses another version marker')
    items = []
    seen = set()
    for line in body.splitlines():
        if not re.match(r'^- \[', line):
            continue
        match = re.fullmatch(r'- \[([ xX])\] ([A-Z][A-Z0-9-]*):\s*(\S.*)', line)
        if not match:
            raise ValueError('Acceptance row must contain a checkbox, unique ID and description')
        checked, gate_id, description = match.groups()
        if gate_id in seen:
            raise ValueError(f'Duplicate acceptance ID: {gate_id}')
        seen.add(gate_id)
        items.append({'id': gate_id, 'status': 'complete' if checked.lower() == 'x' else 'pending',
                      'description': description})
    if not {'WIN-BUILD', 'ROLLBACK'}.issubset(seen):
        raise ValueError('Required WIN-BUILD / ROLLBACK gates missing')
    pending = [item['id'] for item in items if item['status'] == 'pending']
    return {'version': version, 'plan': path.name, 'scope': 'release_checklist_snapshot',
            'plan_sha256': hashlib.sha256(raw).hexdigest(),
            'status': 'pending' if pending else 'complete', 'pending_count': len(pending),
            'pending_ids': pending, 'items': items}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    try:
        snapshot = read_plan(args.root, args.version)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Acceptance plan invalid: {exc}\n')
    # ASCII transport survives English/Korean Windows console code pages.
    print(json.dumps(snapshot, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
