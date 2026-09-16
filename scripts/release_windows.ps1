param(
    [switch]$AllowPendingExternalGates,
    [switch]$PublishStableWithPendingExternalGates,
    [string]$Repo = "nwsoft/ai-trading-client"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$venvScripts = Join-Path $repoRoot ".venv\Scripts"
if (Test-Path -LiteralPath $venvScripts) {
    $env:Path = (Resolve-Path $venvScripts).Path + ";" + $env:Path
}

$argsList = @("-ConfirmExternalGates", "-Repo", $Repo)
if ($AllowPendingExternalGates -and -not $PublishStableWithPendingExternalGates) {
    # Explicit opt-in test publication. This is the only wrapper path that
    # publishes a prerelease and leaves GitHub latest unchanged.
    $argsList += "-AllowPendingExternalGates"
} else {
    # Normal user distribution remains visible to installed clients even when
    # environment-specific account/soak evidence is still recorded as pending.
    $argsList += "-AllowPendingExternalGates"
    $argsList += "-PublishStableWithPendingExternalGates"
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\publish_web_ui_windows_release.ps1") @argsList
if ($LASTEXITCODE -ne 0) { throw "NoahAI Windows release failed" }
