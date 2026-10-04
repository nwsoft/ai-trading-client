#!/usr/bin/env python3
"""Fail closed on missing branding or different PE icon resource payloads.

These hashes identify the existing tracked NoahAI logo, not generated substitutes.
Resource IDs and group ordering can change during packaging; image bytes cannot.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_HASHES = {
    'icon.ico': 'd9cd39ecfc52d0f1b37f9760130fb1edf96259c26fc7b429b49194caa67c2519',
    'icon.png': 'bc47272288999dfd627b62acb39bf79dec213448f1afa0db9bf28d1764a4030c',
    'webui/public/icon.png': 'bc47272288999dfd627b62acb39bf79dec213448f1afa0db9bf28d1764a4030c',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ico_payloads(data):
    if len(data) < 6:
        raise ValueError('Invalid ICO header')
    reserved, kind, count = struct.unpack_from('<HHH', data)
    if reserved or kind != 1 or not count or len(data) < 6 + count * 16:
        raise ValueError('Invalid ICO directory')
    payloads = []
    sizes = set()
    for index in range(count):
        width, height, colors, zero, planes, bits, size, offset = struct.unpack_from('<BBBBHHII', data, 6 + index * 16)
        width, height = width or 256, height or 256
        if zero or not size or offset < 6 + count * 16 or offset + size > len(data):
            raise ValueError('Invalid ICO image bounds')
        payloads.append(data[offset:offset + size])
        sizes.add((width, height))
    if not {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes:
        raise ValueError('ICO is missing required Windows sizes')
    with Image.open(io.BytesIO(data)) as icon:
        for size in sizes:
            icon.ico.getimage(size).load()
    return payloads


def verify_assets(root=ROOT):
    root = Path(root)
    for relative, expected in CANONICAL_HASHES.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing regular branding asset: ' + relative)
        data = path.read_bytes()
        if digest(data) != expected:
            raise ValueError('Branding differs from the approved NoahAI logo: ' + relative)
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if relative.endswith('.png') and (image.format != 'PNG' or image.size != (636, 500)):
                raise ValueError('Invalid NoahAI PNG: ' + relative)
    ico_payloads((root / 'icon.ico').read_bytes())
    package = json.loads((root / 'webui/package.json').read_text(encoding='utf-8'))['build']
    for section, key, expected in (
        ('win', 'icon', '../icon.ico'), ('mac', 'icon', '../icon.png'),
        ('nsis', 'installerIcon', '../icon.ico'), ('nsis', 'uninstallerIcon', '../icon.ico'),
    ):
        if package[section].get(key) != expected:
            raise ValueError(f'Packaging must use tracked branding: {section}.{key}')
    return dict(CANONICAL_HASHES)


def pe_icon_groups(path):
    import pefile
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        resources = {}
        for kind in getattr(pe, 'DIRECTORY_ENTRY_RESOURCE', type('Empty', (), {'entries': []})()).entries:
            if kind.id not in (3, 14):
                continue
            for resource in kind.directory.entries:
                for language in resource.directory.entries:
                    entry = language.data.struct
                    resources[(kind.id, resource.id, language.id)] = pe.get_data(entry.OffsetToData, entry.Size)
        groups = []
        for (kind, resource_id, language), data in resources.items():
            if kind != 14:
                continue
            reserved, icon_type, count = struct.unpack_from('<HHH', data)
            if reserved or icon_type != 1 or not count or len(data) != 6 + count * 14:
                raise ValueError('Invalid PE icon group: ' + str(path))
            images = []
            for index in range(count):
                *_, size, icon_id = struct.unpack_from('<BBBBHHIH', data, 6 + index * 14)
                image = resources.get((3, icon_id, language))
                if image is None or len(image) != size:
                    raise ValueError('Missing or truncated PE icon image: ' + str(path))
                images.append(image)
            groups.append((resource_id, language, images))
        return groups
    finally:
        pe.close()


def verify_executable(path, icon):
    expected = sorted(digest(payload) for payload in ico_payloads(Path(icon).read_bytes()))
    groups = pe_icon_groups(path)
    matches = [(resource_id, language) for resource_id, language, images in groups
               if sorted(digest(payload) for payload in images) == expected]
    # The first group is the shell-visible application/installer icon.
    if not groups or (groups[0][0], groups[0][1]) not in matches:
        raise ValueError('Primary PE icon is not the correct NoahAI icon (Electron/NSIS default prohibited): ' + str(path))
    return {'name': Path(path).name, 'sha256': digest(Path(path).read_bytes()),
            'matching_groups': matches, 'image_count': len(expected), 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--exe', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'assets': verify_assets(args.root), 'executables': [
        verify_executable(path, args.root / 'icon.ico') for path in args.exe]}
    body = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(body, encoding='utf-8')
    print(body)


if __name__ == '__main__':
    main()
