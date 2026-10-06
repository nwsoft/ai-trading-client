"""Restore the hash-pinned published installer on a clean build machine."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.app_version import RELEASE_VERSION, PUBLIC_RELEASE_VERSION


def restore(root: Path):
    baseline=json.loads((root/'config/published_release_baselines.json').read_text(encoding='utf-8'))['releases'][PUBLIC_RELEASE_VERSION]
    manifest_path=root/'deploy/release-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig')) if manifest_path.is_file() else {'version':PUBLIC_RELEASE_VERSION,'assets':{'installer':baseline}}
    if manifest.get('version')==RELEASE_VERSION:
        asset=dict(manifest.get('previous_published_asset') or {})
        version=str(asset.get('version') or '')
        name=Path(str(asset.get('path') or '').replace('\\','/')).name
    else:
        version=str(manifest.get('version') or '')
        asset=dict((manifest.get('assets') or {}).get('installer') or {})
        name=str(asset.get('name') or '')
    if asset.get('sha256')!=baseline.get('sha256') or asset.get('size')!=baseline.get('size'):
        raise RuntimeError('Baseline differs from committed published hash/size')
    expected_name=f'NoahAI-{PUBLIC_RELEASE_VERSION}-Setup.exe'
    if version!=PUBLIC_RELEASE_VERSION or name!=expected_name or version==RELEASE_VERSION:
        raise RuntimeError('Previous published baseline identity mismatch')
    digest=str(asset.get('sha256') or '').lower()
    size=int(asset.get('size') or 0)
    url=f'https://github.com/nwsoft/ai-trading-client/releases/download/v{version}/{name}'
    if not re.fullmatch('[0-9a-f]{64}',digest) or not 0<size<=2*1024**3 or (asset.get('download_url') and asset['download_url']!=url):
        raise RuntimeError('Published baseline hash/size/URL missing or invalid')
    destination=root/'deploy/web-release'/name
    def verify(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
        if path.stat().st_size!=size or h.hexdigest()!=digest:
            raise RuntimeError('Published baseline size/hash mismatch')
    cached=destination.exists()
    if cached:
        verify(destination)
    else:
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix('.exe.downloading')
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'NoahAI-build-baseline-verifier'})
            downloaded=0
            with urllib.request.urlopen(request,timeout=60) as response, temporary.open('wb') as output:
                while chunk:=response.read(1024**2):
                    downloaded+=len(chunk)
                    if downloaded>size:raise RuntimeError('Published baseline exceeds pinned size')
                    output.write(chunk)
            verify(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    report={'version':version,'name':name,'size':size,'sha256':digest,'verified':True,'cached':cached,'source':url}
    (root/'reports').mkdir(exist_ok=True)
    (root/'reports/previous-release-baseline.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    print(json.dumps(restore(parser.parse_args().root)))
