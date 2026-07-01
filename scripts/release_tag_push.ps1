param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    [string]$Branch = "main",
    [string]$CommitMessage = "",
    [switch]$SkipCommit,
    [switch]$PushBranch,
    [switch]$SkipReleaseUpload
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Error "[RELEASE_TAG] $Message"
    exit 1
}

function RunGit([string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        Fail ("git " + ($GitArgs -join " ") + " failed")
    }
}

function Get-RepoSlugFromRemote([string]$RemoteUrl) {
    if ($RemoteUrl -match '^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$') {
        return "$($Matches[1])/$($Matches[2])"
    }
    if ($RemoteUrl -match '^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$') {
        return "$($Matches[1])/$($Matches[2])"
    }
    Fail "origin remote must point to github.com (current: $RemoteUrl)"
}

Write-Host "[RELEASE_TAG] Start"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is not installed"
}

if (-not (Test-Path ".git")) {
    Fail ".git not found. Run this in the client git working tree"
}

$inside = (& git rev-parse --is-inside-work-tree 2>$null)
if ($LASTEXITCODE -ne 0 -or $inside.Trim() -ne "true") {
    Fail "current directory is not a git work tree"
}

$tag = $Version
if (-not $tag.StartsWith("v")) {
    $tag = "v$Version"
}

if ($tag -notmatch '^v\d+\.\d+\.\d+\.\d+$') {
    Fail "version format must look like v3.8.9.24"
}

$venvPython = Join-Path ".venv" "Scripts\python.exe"
$pythonCmd = if (Test-Path $venvPython) { $venvPython } else { "python" }

if (-not (Get-Command $pythonCmd -ErrorAction SilentlyContinue)) {
    Fail "python not found (checked: $pythonCmd)"
}

$releaseVersion = (& $pythonCmd -c "from config.app_version import RELEASE_VERSION; print(RELEASE_VERSION)" 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($releaseVersion)) {
    Fail "failed to read RELEASE_VERSION from config/app_version.py"
}

$releaseVersion = $releaseVersion.Trim()
$expectedTag = "v$releaseVersion"
if ($tag -ne $expectedTag) {
    Fail "tag/version mismatch. requested=$tag, RELEASE_VERSION=$expectedTag"
}

Write-Host "[RELEASE_TAG] RELEASE_VERSION=$expectedTag"
Write-Host "[RELEASE_TAG] Running doc consistency check..."
& $pythonCmd scripts/doc_consistency_check.py
if ($LASTEXITCODE -ne 0) {
    Fail "doc consistency check failed. fix docs/app version sync first"
}

$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    Fail "origin remote not configured"
}

Write-Host "[RELEASE_TAG] origin=$origin"
Write-Host "[RELEASE_TAG] tag=$tag"
$repoSlug = Get-RepoSlugFromRemote $origin
Write-Host "[RELEASE_TAG] repo=$repoSlug"

if (-not $SkipCommit) {
    $status = (& git status --porcelain)
    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Host "[RELEASE_TAG] No local changes to commit"
    } else {
        if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
            $CommitMessage = "release: $tag"
        }
        RunGit @("add", "-A")
        RunGit @("commit", "-m", $CommitMessage)
        Write-Host "[RELEASE_TAG] Committed changes"
    }
}

$existingTag = (& git tag --list $tag)
if (-not [string]::IsNullOrWhiteSpace($existingTag)) {
    Fail "tag already exists locally: $tag"
}

RunGit @("tag", $tag)
Write-Host "[RELEASE_TAG] Created tag $tag"

if ($PushBranch) {
    RunGit @("push", "origin", $Branch)
    Write-Host "[RELEASE_TAG] Pushed branch $Branch"
}

RunGit @("push", "origin", $tag)
Write-Host "[RELEASE_TAG] Pushed tag $tag"

if (-not $SkipReleaseUpload) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Fail "gh CLI is required for release asset upload. Install GitHub CLI or use -SkipReleaseUpload"
    }

    Write-Host "[RELEASE_TAG] Generating release assets..."
    & $pythonCmd scripts/generate_release_assets.py --out-dir deploy --exe deploy/AITrading.exe --repo $repoSlug
    if ($LASTEXITCODE -ne 0) {
        Fail "failed to generate deploy/version.txt, release_notes.md, release-manifest.json"
    }

    $assets = @("deploy/AITrading.exe", "deploy/version.txt", "deploy/release_notes.md", "deploy/release-manifest.json")
    foreach ($a in $assets) {
        if (-not (Test-Path $a)) {
            Fail "release asset missing: $a"
        }
    }

    $exists = $false
    try {
        & gh release view $tag --repo $repoSlug 1>$null 2>$null
        $exists = ($LASTEXITCODE -eq 0)
    } catch {
        $exists = $false
    }

    if ($exists) {
        Write-Host "[RELEASE_TAG] Release exists. Uploading assets with overwrite..."
        & gh release upload $tag @assets --repo $repoSlug --clobber
        if ($LASTEXITCODE -ne 0) {
            Fail "gh release upload failed"
        }
    } else {
        Write-Host "[RELEASE_TAG] Creating release and uploading assets..."
        & gh release create $tag @assets --repo $repoSlug --title $tag --notes-file "deploy/release_notes.md"
        if ($LASTEXITCODE -ne 0) {
            Fail "gh release create failed"
        }
    }
}

Write-Host "[RELEASE_TAG] Done. Tag push and GitHub release asset upload completed."
