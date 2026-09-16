param(
    [switch]$SkipTests,
    [switch]$SkipNpmCi,
    [switch]$SkipEngineBuild,
    [switch]$AllowMissingKiwoomHost
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$venvScripts = Join-Path $repoRoot ".venv\Scripts"
if (Test-Path -LiteralPath $venvScripts) {
    $env:Path = (Resolve-Path $venvScripts).Path + ";" + $env:Path
}

$argsList = @()
if ($SkipTests) { $argsList += "-SkipTests" }
if ($SkipNpmCi) { $argsList += "-SkipNpmCi" }
if ($SkipEngineBuild) { $argsList += "-SkipEngineBuild" }
if ($AllowMissingKiwoomHost) { $argsList += "-AllowMissingKiwoomHost" }

& powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_web_ui_windows.ps1") @argsList
if ($LASTEXITCODE -ne 0) { throw "NoahAI Windows build failed" }
