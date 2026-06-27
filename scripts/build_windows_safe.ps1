param(
    [string]$GateProfile = "prekey",
    [string]$ChangedFiles = "docs/CHANGELOG.md,docs/USER_GUIDE.md,USER_GUIDE_AI_EXECUTION.md,ui/widgets/user_manual_widget.py",
    [int]$ReadinessTimeoutSec = 8
)

$ErrorActionPreference = "Stop"

Write-Host "[BUILD_WRAPPER] Windows safe build wrapper"

if (-not (Test-Path ".git")) {
    Write-Host "[BUILD_WRAPPER] .git not found. Injecting SYNC_GUARD_CHANGED_FILES for strict gate."
    $env:SYNC_GUARD_CHANGED_FILES = $ChangedFiles
} else {
    Write-Host "[BUILD_WRAPPER] .git detected. SYNC_GUARD will use git diff by default."
}

$env:EXCHANGE_READINESS_TIMEOUT_SEC = [string]$ReadinessTimeoutSec

Write-Host "[BUILD_WRAPPER] GateProfile=$GateProfile"
Write-Host "[BUILD_WRAPPER] EXCHANGE_READINESS_TIMEOUT_SEC=$($env:EXCHANGE_READINESS_TIMEOUT_SEC)"
if ($env:SYNC_GUARD_CHANGED_FILES) {
    Write-Host "[BUILD_WRAPPER] SYNC_GUARD_CHANGED_FILES=$($env:SYNC_GUARD_CHANGED_FILES)"
}

python build_safe.py --platform windows --gate-profile $GateProfile
exit $LASTEXITCODE
