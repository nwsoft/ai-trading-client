param(
    [string]$Version = "",
    [ValidateSet("prekey", "release")]
    [string]$GateProfile = "prekey",
    [int]$ReadinessTimeoutSec = 8,
    [string]$CommitMessage = "",
    [switch]$UseGitDiff,
    [switch]$AllowDirtyWorkingTree,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$originalLocation = Get-Location
$transcriptStarted = $false
$scriptExitCode = 0
$createReleaseCommit = $false

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host "[BUILD_RELEASE] $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit=$LASTEXITCODE)"
    }
}

try {
    Set-Location $repoRoot
    New-Item -ItemType Directory -Path "deploy" -Force | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logPath = Join-Path $repoRoot "deploy\build-release-$timestamp.log"
    Start-Transcript -Path $logPath -Force | Out-Null
    $transcriptStarted = $true

    Write-Host "[BUILD_RELEASE] Noah AI Windows build + release"
    Write-Host "[BUILD_RELEASE] root=$repoRoot"
    Write-Host "[BUILD_RELEASE] log=$logPath"

    if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
        throw "Windows build host is required"
    }
    foreach ($commandName in @("python", "git")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
            throw "$commandName is not installed or not available in PATH"
        }
    }
    if (-not $BuildOnly -and -not (Get-Command "gh" -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI is required. Install gh and run 'gh auth login --hostname github.com --web'."
    }

    $configuredVersion = (& python -c "from config.app_version import RELEASE_VERSION; print(RELEASE_VERSION)").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($configuredVersion)) {
        throw "failed to read RELEASE_VERSION"
    }
    if ([string]::IsNullOrWhiteSpace($Version)) {
        $Version = $configuredVersion
    }
    $Version = $Version.TrimStart("v")
    if ($Version -ne $configuredVersion) {
        throw "version mismatch: requested=$Version config=$configuredVersion"
    }
    Write-Host "[BUILD_RELEASE] version=$Version profile=$GateProfile"

    Invoke-Checked "Tcl/Tk preflight" {
        & python -c "import build_safe; raise SystemExit(0 if build_safe.validate_windows_tkinter_build_runtime() else 1)"
    }
    Invoke-Checked "VC143 preflight" {
        & python -c "import build_safe; build_safe.resolve_windows_vc_runtime_binaries()"
    }

    if (-not $BuildOnly) {
        Invoke-Checked "GitHub authentication preflight" {
            & gh auth status --hostname github.com
        }
        $tagName = "v$Version"
        $localTagExists = -not [string]::IsNullOrWhiteSpace((& git tag --list $tagName))
        $remoteTagLine = (& git ls-remote --tags origin $tagName 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) {
            throw "failed to query remote tag $tagName"
        }
        $tagExists = $localTagExists -or -not [string]::IsNullOrWhiteSpace($remoteTagLine)

        $unmerged = (& git diff --name-only --diff-filter=U)
        if (-not [string]::IsNullOrWhiteSpace($unmerged)) {
            throw "unmerged files detected. Resolve conflicts before release: $unmerged"
        }

        $workingTree = (& git status --porcelain)
        if (-not [string]::IsNullOrWhiteSpace($workingTree)) {
            if (-not $tagExists) {
                $createReleaseCommit = $true
                Write-Host "[BUILD_RELEASE] New tag ${tagName}: verified source changes will be committed after a successful build."
            } elseif (-not $AllowDirtyWorkingTree) {
                throw (
                    "tag $tagName already exists and the working tree is dirty. Commit the source separately, " +
                    "or use -AllowDirtyWorkingTree only for an intentional same-tag emergency asset replacement."
                )
            } else {
                Write-Warning "[BUILD_RELEASE] Existing tag emergency mode: dirty source will not move $tagName."
            }
        }
    }

    $buildArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts\build_windows_safe.ps1",
        "-GateProfile", $GateProfile,
        "-ReadinessTimeoutSec", [string]$ReadinessTimeoutSec
    )
    if ($UseGitDiff) {
        $buildArgs += "-UseGitDiff"
    }
    Invoke-Checked "Windows build and local artifact verification" {
        & powershell @buildArgs
    }

    $exePath = (Resolve-Path "deploy\AITrading.exe").Path
    $exeItem = Get-Item -LiteralPath $exePath
    $exeSha = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeItem.VersionInfo.ProductVersion.Trim() -ne $Version) {
        throw "built EXE ProductVersion mismatch: exe=$($exeItem.VersionInfo.ProductVersion) expected=$Version"
    }
    Write-Host "[BUILD_RELEASE] local artifact verified: size=$($exeItem.Length) sha256=$exeSha"

    if (-not $BuildOnly -and $createReleaseCommit) {
        if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
            $CommitMessage = "release: v$Version"
        }
        Invoke-Checked "Create verified release source commit" {
            & git add -A
            if ($LASTEXITCODE -eq 0) {
                & git commit -m $CommitMessage
            }
        }
        Write-Host "[BUILD_RELEASE] release source committed: $CommitMessage"
    }

    if ($BuildOnly) {
        Write-Host "[BUILD_RELEASE] BuildOnly complete. No GitHub state was changed."
        Write-Host "[BUILD_RELEASE] SUCCESS sha256=$exeSha"
    } else {
        Invoke-Checked "GitHub release upload and remote digest verification" {
            & powershell -ExecutionPolicy Bypass -File "scripts\release_tag_push.ps1" -Version $Version -SkipCommit
        }

        $releaseUrl = (& gh release view "v$Version" --repo "nwsoft/ai-trading-client" --json url --jq ".url").Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($releaseUrl)) {
            throw "release completed but final release URL lookup failed"
        }
        Write-Host "[BUILD_RELEASE] SUCCESS"
        Write-Host "[BUILD_RELEASE] release=$releaseUrl"
        Write-Host "[BUILD_RELEASE] sha256=$exeSha"
    }
} catch {
    Write-Host "[BUILD_RELEASE] FAILED: $($_.Exception.Message)" -ForegroundColor Red
    $scriptExitCode = 1
} finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
    Set-Location $originalLocation
}

exit $scriptExitCode
