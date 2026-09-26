param(
    [switch]$SkipTests,
    [switch]$SkipNpmCi,
    [switch]$SkipEngineBuild,
    [switch]$AllowMissingKiwoomHost,
    [string]$Repo = "nwsoft/ai-trading-client"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$buildArgs = @()
if ($SkipTests) { $buildArgs += "-SkipTests" }
if ($SkipNpmCi) { $buildArgs += "-SkipNpmCi" }
if ($SkipEngineBuild) { $buildArgs += "-SkipEngineBuild" }
if ($AllowMissingKiwoomHost) { $buildArgs += "-AllowMissingKiwoomHost" }
& powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_windows.ps1") @buildArgs
if ($LASTEXITCODE -ne 0) { throw "NoahAI Windows build failed; release skipped" }

$releaseArgs = @("-Repo", $Repo)
& powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\release_windows.ps1") @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "NoahAI Windows release failed" }
