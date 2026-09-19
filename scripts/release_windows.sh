#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
powershell.exe -ExecutionPolicy Bypass -File ".\\scripts\\release_windows.ps1" "$@"
