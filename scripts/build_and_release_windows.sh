#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
powershell.exe -ExecutionPolicy Bypass -File ".\\scripts\\build_and_release_windows.ps1" "$@"
