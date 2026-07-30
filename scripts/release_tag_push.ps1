param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    [string]$Branch = "main",
    [string]$CommitMessage = "",
    [switch]$SkipCommit,
    [switch]$PushBranch,
    [switch]$StrictBranchPush,
    [switch]$SkipReleaseUpload,
    [switch]$RequireAuthenticode
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

function TryRunGit([string[]]$GitArgs) {
    & git @GitArgs
    return ($LASTEXITCODE -eq 0)
}

function Invoke-GhWithRetry([scriptblock]$Command, [string]$Label, [int]$MaxAttempts = 4, [int]$InitialDelaySec = 2) {
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        & $Command
        if ($LASTEXITCODE -eq 0) {
            if ($attempt -gt 1) {
                Write-Host "[RELEASE_TAG] $Label recovered on attempt $attempt/$MaxAttempts"
            }
            return $true
        }

        if ($attempt -lt $MaxAttempts) {
            $delay = [Math]::Min(30, $InitialDelaySec * [Math]::Pow(2, $attempt - 1))
            Write-Warning "[RELEASE_TAG] $Label failed (attempt $attempt/$MaxAttempts). retrying in $delay sec..."
            Start-Sleep -Seconds $delay
            continue
        }
    }
    return $false
}

function Test-GhReleaseExists([string]$Tag, [string]$RepoSlug) {
    try {
        & gh release view $Tag --repo $RepoSlug 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
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
    $unmerged = @()
    $conflictArtifacts = @()
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        $statusLines = $status -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $unmerged = $statusLines | Where-Object { $_ -match '^(UU|AA|DD|AU|UA|DU|UD)\s' }
        $conflictArtifacts = @(
            $statusLines | Where-Object {
                $line = $_
                $xy = if ($line.Length -ge 2) { $line.Substring(0, 2) } else { "" }
                $isDeleteEntry = ($xy -match 'D')
                $isConflictFile = ($line -match '_Conflict\.' -or $line -match '\.orig$')
                $isConflictFile -and (-not $isDeleteEntry)
            }
        )
    }

    if ($unmerged.Count -gt 0) {
        Fail ("unmerged files detected. resolve merge conflicts first:`n" + ($unmerged -join "`n"))
    }

    if ($conflictArtifacts.Count -gt 0) {
        Fail ("conflict artifact files detected. clean or ignore these before release:`n" + ($conflictArtifacts -join "`n"))
    }

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
if ([string]::IsNullOrWhiteSpace($existingTag)) {
    RunGit @("tag", $tag)
    Write-Host "[RELEASE_TAG] Created tag $tag"
} else {
    Write-Warning "[RELEASE_TAG] Local tag already exists: $tag (continuing)"
}

$localTagObject = (& git rev-list -n 1 $tag 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($localTagObject)) {
    Fail "failed to resolve local tag object for $tag"
}

$remoteTagLine = (& git ls-remote --tags origin $tag 2>$null | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($remoteTagLine)) {
    RunGit @("push", "origin", $tag)
    Write-Host "[RELEASE_TAG] Pushed tag $tag"
} else {
    $remoteTagObject = ($remoteTagLine -split "\s+")[0]
    if ($remoteTagObject -ne $localTagObject) {
        Fail "remote tag already exists with different object: $tag (local=$localTagObject, remote=$remoteTagObject)"
    }
    Write-Host "[RELEASE_TAG] Remote tag already exists and matches local: $tag"
}

if ($PushBranch) {
    if (TryRunGit @("push", "origin", $Branch)) {
        Write-Host "[RELEASE_TAG] Pushed branch $Branch"
    } else {
        if ($StrictBranchPush) {
            Fail "git push origin $Branch failed"
        }
        Write-Warning "[RELEASE_TAG] Branch push failed (likely non-fast-forward). Tag/release upload will continue."
    }
}

if (-not $SkipReleaseUpload) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Fail "gh CLI is required for release asset upload. Install GitHub CLI or use -SkipReleaseUpload"
    }

    $exePath = Join-Path (Get-Location) "deploy/AITrading.exe"
    if (-not (Test-Path $exePath)) {
        Fail "release executable missing: deploy/AITrading.exe"
    }
    $exeProductVersion = (Get-Item $exePath).VersionInfo.ProductVersion
    if ([string]::IsNullOrWhiteSpace($exeProductVersion) -or $exeProductVersion.Trim() -ne $releaseVersion) {
        Fail "EXE ProductVersion mismatch. exe=$exeProductVersion RELEASE_VERSION=$releaseVersion. Rebuild on Windows before upload."
    }
    $signature = Get-AuthenticodeSignature -FilePath $exePath
    if ($RequireAuthenticode) {
        if ($signature.Status -ne "Valid" -or -not $signature.SignerCertificate) {
            Fail "AITrading.exe must have a valid Windows Authenticode signature before release upload. status=$($signature.Status)"
        }
        Write-Host "[RELEASE_TAG] Authenticode required and valid: $($signature.SignerCertificate.Subject)"
    } else {
        if ($signature.Status -eq "Valid" -and $signature.SignerCertificate) {
            $subject = $signature.SignerCertificate.Subject
            $issuer = $signature.SignerCertificate.Issuer
            if ($subject -eq $issuer) {
                Write-Warning "[RELEASE_TAG] Self-signed Authenticode detected (subject=issuer). For external distribution, unsigned or CA-signed is recommended."
            } else {
                Write-Host "[RELEASE_TAG] Authenticode present: $subject"
            }
        } else {
            Write-Host "[RELEASE_TAG] Unsigned executable allowed (RequireAuthenticode not set)."
        }
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

    $exists = Test-GhReleaseExists -Tag $tag -RepoSlug $repoSlug

    if (-not $exists) {
        Write-Host "[RELEASE_TAG] Creating release..."
        $created = Invoke-GhWithRetry -Label "gh release create" -Command {
            & gh release create $tag --repo $repoSlug --title $tag --notes-file "deploy/release_notes.md"
        }

        if (-not $created) {
            # GitHub API 5xx can fail after side effects; re-check release presence.
            if (-not (Test-GhReleaseExists -Tag $tag -RepoSlug $repoSlug)) {
                Fail "gh release create failed"
            }
            Write-Warning "[RELEASE_TAG] release create returned failure but release exists. continuing to asset upload."
        }
    } else {
        Write-Host "[RELEASE_TAG] Release exists. Reusing existing release."
    }

    Write-Host "[RELEASE_TAG] Syncing release notes body..."
    $notesSynced = Invoke-GhWithRetry -Label "gh release edit --notes-file" -Command {
        & gh release edit $tag --repo $repoSlug --notes-file "deploy/release_notes.md"
    }
    if (-not $notesSynced) {
        Fail "gh release edit failed"
    }

    Write-Host "[RELEASE_TAG] Uploading assets with overwrite..."
    $uploaded = Invoke-GhWithRetry -Label "gh release upload" -Command {
        & gh release upload $tag @assets --repo $repoSlug --clobber
    }

    if (-not $uploaded) {
        Fail "gh release upload failed"
    }
}

Write-Host "[RELEASE_TAG] Done. Tag push and GitHub release asset upload completed."
