"""Fail closed on drift from the successful v20 Windows dependency set."""
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import argparse
import platform
import struct
import sys
ROOT = Path(__file__).resolve().parents[1]

def mismatches(lock, lookup=version):
    errors = []
    for line in lock.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        try:
            actual = lookup(name)
        except PackageNotFoundError:
            actual = 'missing'
        if actual != expected:
            errors.append(f'{name}: expected {expected}, actual {actual}')
    return errors

def main():
    p = argparse.ArgumentParser()
    p.add_argument('target', choices=['windows', 'kiwoom_x86'])
    target = p.parse_args().target
    bits = 32 if target == 'kiwoom_x86' else 64
    errors = mismatches(ROOT / f'requirements_{target}.lock.txt')
    if sys.platform != 'win32' or platform.python_version() != '3.11.9' or struct.calcsize('P') * 8 != bits:
        errors.append(f'Expected Windows Python 3.11.9 {bits}-bit')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Verified {target} dependencies and architecture')
if __name__ == '__main__':
    main()
