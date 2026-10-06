#!/usr/bin/env python3
"""Inventory project Markdown and validate local document links.

Excludes generated installers, dependencies, account data, temporary checkouts
and test reports. Archives are inventoried as history, not current releases.
Semantic policy is checked separately by doc_consistency_check.py.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def audit() -> dict:
    args = ['rg', '--files', '-g', '*.md']
    for excluded in ('**/node_modules/**', '**/.venv/**', 'tmp/**', 'data/**',
                     'webui/release/**', 'build/**', 'dist/**', 'reports/**'):
        args += ['-g', '!' + excluded]
    names = sorted(subprocess.check_output(args, cwd=ROOT, text=True).splitlines())
    broken = []
    checked = 0
    documents = []
    for name in names:
        path = ROOT / name
        text = path.read_text(encoding='utf-8')
        documents.append({'path': name, 'archive': '/archive/' in name,
                          'lines': len(text.splitlines())})
        # Code examples are not navigation; keep line numbers stable.
        text = re.sub(r'```[^\n]*\n.*?```', lambda m: '\n' * m[0].count('\n'), text, flags=re.S)
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
            target = match[1].strip()
            if target.startswith('<'):
                target = target.split('>', 1)[0][1:]
            else:
                target = re.split(r'\s+[\"\']', target, maxsplit=1)[0]
            parts = urlsplit(target)
            if parts.scheme or parts.netloc or not parts.path.lower().endswith('.md'):
                continue
            checked += 1
            if not (path.parent / unquote(parts.path)).is_file():
                broken.append({'file': name, 'line': text[:match.start()].count('\n') + 1,
                               'target': target})
    return {'result': 'PASS' if not broken else 'FAIL', 'documents': len(names),
            'local_markdown_links_checked': checked, 'broken_links': broken,
            'inventory': documents,
            'boundary': 'Local Markdown file targets only. External URLs, anchors and full document semantics are not certified.'}


if __name__ == '__main__':
    result = audit()
    output = ROOT / 'reports/v3925-markdown-inventory-20261006.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'inventory'}, ensure_ascii=False))
    raise SystemExit(0 if result['result'] == 'PASS' else 1)
