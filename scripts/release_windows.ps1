param([string]$Repo = "nwsoft/ai-trading-client")

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$venvScripts = Join-Path $repoRoot ".venv\Scripts"
if (Test-Path -LiteralPath $venvScripts) {
    $env:Path = (Resolve-Path $venvScripts).Path + ";" + $env:Path
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\publish_web_ui_windows_release.ps1") -Repo $Repo
if ($LASTEXITCODE -ne 0) { throw "NoahAI Windows release failed" }
