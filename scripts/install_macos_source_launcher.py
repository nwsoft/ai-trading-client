#!/usr/bin/env python3
"""Install a local-checkout desktop launcher; this is not a distributable app."""
import argparse
import json
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def install(project, destination, node):
    project=Path(project).resolve();destination=Path(destination).expanduser().resolve();node=Path(node).resolve()
    if not (project/'webui/electron/run-electron.cjs').is_file() or not node.is_file():raise ValueError('source_or_node_missing')
    candidates=[project/'deploy/mac-release/mac-arm64/NoahAI.app/Contents/Resources/icon.icns',project/'deploy/mac-release/.icon-icns/icon.icns']
    icon=next((p for p in candidates if p.is_file()),None)
    if not icon:raise ValueError('reviewed_noah_icon_missing')
    package=json.loads((project/'webui/package.json').read_text())
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.noah-launcher-',dir=destination.parent))/'NoahAI.app'
    contents=stage/'Contents';(contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
    plist={'CFBundleName':'NoahAI','CFBundleDisplayName':'NoahAI','CFBundleIdentifier':'ai.noah.local.checkout',
           'CFBundleExecutable':'launch-noahai','CFBundlePackageType':'APPL','CFBundleIconFile':'NoahAI.icns',
           'CFBundleVersion':package['version'],'CFBundleShortVersionString':package['build']['buildVersion'],
           'LSUIElement':True,'NSHighResolutionCapable':True}
    (contents/'Info.plist').write_bytes(plistlib.dumps(plist))
    shutil.copy2(icon,contents/'Resources/NoahAI.icns')
    script='''#!/bin/zsh
set -eu
umask 077
project=%s
node=%s
export PATH="${node:h}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
unset ELECTRON_RUN_AS_NODE
mkdir -p "$HOME/Library/Logs/NoahAI"
cd "$project"
exec "$node" "$project/webui/electron/run-electron.cjs" >> "$HOME/Library/Logs/NoahAI/local-launch.log" 2>&1
'''%(shlex.quote(str(project)),shlex.quote(str(node)))
    executable=contents/'MacOS/launch-noahai';executable.write_text(script);executable.chmod(0o755)
    (contents/'Resources/LOCAL_SOURCE.txt').write_text('Local development launcher, not a packaged release.\nSource: '+str(project)+'\nLogs: ~/Library/Logs/NoahAI/local-launch.log\n')
    subprocess.run(['/bin/zsh','-n',str(executable)],check=True)
    backup=None
    if destination.exists():
        backup=Path(tempfile.mkdtemp(prefix='noah-desktop-before-'))/destination.name
        shutil.move(str(destination),str(backup))
    stage.rename(destination);stage.parent.rmdir()
    return {'launcher':str(destination),'source':str(project),'version':package['build']['buildVersion'],'backup':str(backup) if backup else None}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',default=str(Path.home()/'Desktop/NoahAI.app'))
    parser.add_argument('--node',required=True)
    args=parser.parse_args()
    if sys.platform!='darwin':parser.error('macOS only')
    print(json.dumps(install(ROOT,args.destination,args.node),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
