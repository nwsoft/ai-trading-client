param(
    [string]$GateProfile = "prekey",
    [string]$ChangedFiles = "docs/CHANGELOG.md,docs/USER_GUIDE.md,USER_GUIDE_AI_EXECUTION.md,ui/widgets/user_manual_widget.py",
    [int]$ReadinessTimeoutSec = 8,
    [switch]$UseGitDiff
)

$ErrorActionPreference = "Stop"

Write-Host "[BUILD_WRAPPER] Windows safe build wrapper"

if ($UseGitDiff) {
    if (-not (Test-Path ".git")) {
        Write-Host "[BUILD_WRAPPER] .git not found. Falling back to SYNC_GUARD_CHANGED_FILES injection."
        $env:SYNC_GUARD_CHANGED_FILES = $ChangedFiles
    } else {
        Write-Host "[BUILD_WRAPPER] .git detected. Using git diff mode for SYNC_GUARD."
        Remove-Item Env:SYNC_GUARD_CHANGED_FILES -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "[BUILD_WRAPPER] Stable mode: injecting SYNC_GUARD_CHANGED_FILES (skip git diff variability)."
    $env:SYNC_GUARD_CHANGED_FILES = $ChangedFiles
}

$env:EXCHANGE_READINESS_TIMEOUT_SEC = [string]$ReadinessTimeoutSec

Write-Host "[BUILD_WRAPPER] GateProfile=$GateProfile"
Write-Host "[BUILD_WRAPPER] EXCHANGE_READINESS_TIMEOUT_SEC=$($env:EXCHANGE_READINESS_TIMEOUT_SEC)"
if ($env:SYNC_GUARD_CHANGED_FILES) {
    Write-Host "[BUILD_WRAPPER] SYNC_GUARD_CHANGED_FILES=$($env:SYNC_GUARD_CHANGED_FILES)"
}

python build_safe.py --platform windows --gate-profile $GateProfile
exit $LASTEXITCODE
