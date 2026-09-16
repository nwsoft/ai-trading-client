param(
    [Parameter(Mandatory=$true)]
    [switch]$ConfirmExternalGates,
    [switch]$AllowPendingExternalGates,
    [switch]$PublishStableWithPendingExternalGates,
    [string]$Repo = "nwsoft/ai-trading-client"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$originalLocation = Get-Location

function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Release asset missing: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne ([string]$Expected).ToLowerInvariant()) {
        throw "SHA-256 mismatch: $Path expected=$Expected actual=$actual"
    }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Get-ReleaseSourceFingerprint([string]$Root) {
    $fingerprint = & python scripts/release_source_fingerprint.py --root $Root
    if ($LASTEXITCODE -ne 0) { throw "Release source fingerprint failed" }
    $value = (($fingerprint | Out-String).Trim()).ToLowerInvariant()
    if ($value -notmatch '^[0-9a-f]{64}$') { throw "Invalid release source fingerprint: $value" }
    return $value
}

function Assert-RemoteDigest([string]$Tag, [string]$Path) {
    $item = Get-Item -LiteralPath $Path
    $payload = (& gh release view $Tag --repo $Repo --json assets) | ConvertFrom-Json
    $remote = @($payload.assets | Where-Object { $_.name -eq $item.Name }) | Select-Object -First 1
    if (-not $remote) { throw "Remote release asset missing: $($item.Name)" }
    $expected = "sha256:" + (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $remoteSize = [int64]$remote.size
    $localSize = [int64]$item.Length
    $remoteDigest = ([string]$remote.digest).ToLowerInvariant()
    if ($remoteSize -ne $localSize -or $remoteDigest -ne $expected) {
        throw "Remote digest mismatch: $($item.Name)"
    }
}

function Assert-ParityLedgerComplete([string]$Root) {
    $ledgerPath = Join-Path $Root "docs\WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md"
    if (-not (Test-Path -LiteralPath $ledgerPath)) { throw "1:1 parity ledger missing: $ledgerPath" }
    $ledger = Get-Content -LiteralPath $ledgerPath -Raw
    if ($ledger -match '\[ \] OPEN' -or $ledger -match '\[~\] (SOURCE|MAC)') {
        throw "1:1 parity ledger is incomplete. Every required row must be [x] VERIFIED before release publishing."
    }
    $requiredRows = @("LOGIN-01", "BC-01", "STOCK-01", "PORT-01", "LIFE-01", "ANALYST-01", "SET-01", "MAN-01")
    foreach ($rowId in $requiredRows) {
        if ($ledger -notmatch "(?m)^\|\s*$([regex]::Escape($rowId))\s*\|") {
            throw "1:1 parity ledger required row missing: $rowId"
        }
    }
}

function Get-PatchPlanPath([string]$Root, [string]$Version) {
    $parts = $Version.Split(".")
    if ($parts.Count -ne 4) { throw "Unsupported version format: $Version" }
    $prefix = "V$($parts[0])$($parts[1])$($parts[2])$($parts[3])_"
    $docsDir = Join-Path $Root "docs"
    $matches = @(Get-ChildItem -LiteralPath $docsDir -Filter "$prefix*_TEST_PLAN.md" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($matches.Count -eq 0) { return $null }
    if ($matches.Count -gt 1) { throw "Multiple patch test plans found for v$Version`: $($matches.Name -join ', ')" }
    return $matches[0].FullName
}

function Assert-PatchPlanComplete([string]$Root, [string]$Version) {
    $planPath = Get-PatchPlanPath $Root $Version
    if (-not $planPath) { throw "v$Version patch test plan missing: docs\V*_TEST_PLAN.md" }
    $plan = Get-Content -LiteralPath $planPath -Raw
    # macOS signing/install evidence does not attest to Windows (or vice versa).
    $plan = [regex]::Replace($plan, '(?m)^- \[[xX ]\] (?:VERIFIED[ :]+)?MAC-[^\r\n]*(?:\r?\n|$)', '')
    if ($plan -match '(?m)^- \[ \]') {
        throw "v$Version patch test plan is incomplete: $([IO.Path]::GetFileName($planPath)) has unchecked rows."
    }
    $checklistRows = [regex]::Matches($plan, '(?m)^- \[[xX ]\].+$')
    if ($checklistRows.Count -eq 0) {
        throw "v$Version patch test plan has no verification rows"
    }
    foreach ($row in $checklistRows) {
        if ($row.Value -notmatch '^- \[[xX]\] VERIFIED(?:\s|:)') {
            throw "v$Version patch test plan contains a checked row without VERIFIED evidence: $($row.Value)"
        }
    }
    foreach ($gateId in @("WIN-BUILD", "ROLLBACK")) {
        if ($plan -notmatch [regex]::Escape($gateId)) { throw "v$Version required patch gate missing: $gateId" }
    }
}

try {
    Set-Location $repoRoot
    if (-not $ConfirmExternalGates) { throw "ConfirmExternalGates is required" }
    foreach ($commandName in @("python", "gh", "git")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) { throw "$commandName is required" }
    }
    & gh auth status --hostname github.com
    if ($LASTEXITCODE -ne 0) { throw "GitHub CLI authentication failed" }

    $version = (& python -c "from config.app_version import RELEASE_VERSION; print(RELEASE_VERSION)").Trim()
    $externalGatesPending = $false
    try {
        $planPath = Get-PatchPlanPath $repoRoot $version
        if ($planPath) { Assert-PatchPlanComplete $repoRoot $version }
        else { Assert-ParityLedgerComplete $repoRoot }
    } catch {
        if (-not $AllowPendingExternalGates) { throw }
        $externalGatesPending = $true
        Write-Warning "External gate plan is incomplete, but AllowPendingExternalGates was supplied. Publishing the locally built candidate by operator override. Reason: $($_.Exception.Message)"
    }
    if ($PublishStableWithPendingExternalGates -and -not $externalGatesPending) {
        Write-Warning "PublishStableWithPendingExternalGates was supplied, but all release gates are already complete. Publishing the normal stable release."
    }
    $manifestPath = Join-Path $repoRoot "deploy\release-manifest.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.version -ne $version) { throw "Manifest version mismatch" }
    if ($manifest.automated_checks_passed -ne $true) { throw "Official publication requires a fresh build without skipped tests/engine/host." }
    $currentFingerprint = Get-ReleaseSourceFingerprint $repoRoot
    if (-not $manifest.source_fingerprint -or $manifest.source_fingerprint -ne $currentFingerprint) {
        throw "Windows candidate is stale for the current source. Run build_web_ui_windows.ps1 again."
    }
    $approvableStates = @("built_windows_unverified", "windows_external_gates_pending", "windows_stable_external_gates_pending", "windows_verified_release_candidate")
    if ($manifest.build_status -notin $approvableStates) { throw "Run build_web_ui_windows.ps1 first" }

    $releaseDir = Join-Path $repoRoot "deploy\web-release"
    $installerPath = Join-Path $releaseDir $manifest.assets.installer.name
    $latestPath = Join-Path $releaseDir $manifest.assets.latest_yml.name
    $blockmapPath = Join-Path $releaseDir $manifest.assets.blockmap.name
    Assert-Hash $installerPath $manifest.assets.installer.sha256
    Assert-Hash $latestPath $manifest.assets.latest_yml.sha256
    Assert-Hash $blockmapPath $manifest.assets.blockmap.sha256
    Assert-Hash (Join-Path $repoRoot "deploy\web-engine\NoahAIEngine.exe") $manifest.assets.engine_sidecar.sha256
    if (-not $manifest.assets.kiwoom_host -or $manifest.assets.kiwoom_host.supported -ne $true) {
        throw "Stable/prerelease publication requires the packaged Kiwoom x86 host"
    }
    $kiwoomHostPath = Join-Path $repoRoot "deploy\web-engine\NoahAIKiwoomHost.exe"
    Assert-Hash $kiwoomHostPath $manifest.assets.kiwoom_host.sha256
    & python -c "from pathlib import Path; from trading.exchanges.adapters.kiwoom_host_launcher import pe_machine; assert pe_machine(Path(r'$kiwoomHostPath')) == 0x14c"
    if ($LASTEXITCODE -ne 0) { throw "Kiwoom host PE architecture verification failed" }

    $latestText = Get-Content -LiteralPath $latestPath -Raw
    if ($latestText -notmatch [regex]::Escape($manifest.assets.installer.name)) {
        throw "latest.yml does not reference the built installer"
    }
    $latestVersionMatch = [regex]::Match($latestText, '(?m)^version:\s*["'']?([^"''\s]+)')
    if (-not $manifest.update_contract.updater_semver) { throw "Manifest updater_semver is missing" }
    if (-not $latestVersionMatch.Success -or $latestVersionMatch.Groups[1].Value -ne $manifest.update_contract.updater_semver) {
        throw "latest.yml updater version mismatch"
    }
    $releaseNotes = Get-Content -LiteralPath (Join-Path $repoRoot "deploy\release_notes.md") -Raw
    if ($releaseNotes -notmatch [regex]::Escape("v$version")) {
        throw "Release notes do not describe v$version"
    }

    $publishAsPrerelease = $externalGatesPending -and -not $PublishStableWithPendingExternalGates
    # No implicit remote-main target: prove the exact build inputs are committed
    # and available remotely before creating or changing any release.
    $releaseTarget = (& python scripts/verify_release_provenance.py --root $repoRoot --repo $Repo --phase preflight | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $releaseTarget -notmatch '^[0-9a-f]{40}$') { throw "Release source provenance failed" }
    if ($publishAsPrerelease) {
        $manifest.build_status = "windows_external_gates_pending"
        $manifest.publish_ready = $false
        $manifest.channel = "prerelease"
        $manifest | Add-Member -NotePropertyName windows_gate_override -NotePropertyValue "AllowPendingExternalGates" -Force
    } elseif ($externalGatesPending) {
        $manifest.build_status = "windows_stable_external_gates_pending"
        $manifest.publish_ready = $true
        $manifest.channel = "stable"
        $manifest | Add-Member -NotePropertyName windows_gate_override -NotePropertyValue "PublishStableWithPendingExternalGates" -Force
    } else {
        $manifest.build_status = "windows_verified_release_candidate"
        $manifest.publish_ready = $true
        $manifest.channel = "stable"
        $manifest | Add-Member -NotePropertyName windows_gate_confirmed_at -NotePropertyValue ([DateTime]::UtcNow.ToString("o")) -Force
        $manifest.PSObject.Properties.Remove("windows_gate_override")
    }
    Write-Utf8NoBom $manifestPath ($manifest | ConvertTo-Json -Depth 8)

    $tag = "v$version"
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & gh release view $tag --repo $Repo 1>$null 2>$null
        $releaseExists = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (-not $releaseExists) {
        # Keep partial uploads invisible to the updater.
        & gh release create $tag --repo $Repo --target $releaseTarget --draft --title $tag --notes-file "deploy/release_notes.md"
        if ($LASTEXITCODE -ne 0) { throw "GitHub draft release creation failed" }
    }
    # GitHub draft releases do not create their Git ref until publication. Create
    # the verified lightweight tag explicitly so provenance can be checked before
    # any immutable asset upload. A conflicting existing tag is never forced.
    $tagRefSpec = "{0}:refs/tags/{1}" -f $releaseTarget, $tag
    & git push origin $tagRefSpec
    if ($LASTEXITCODE -ne 0) { throw "Release tag creation failed or conflicts with an existing tag" }
    & python scripts/verify_release_provenance.py --root $repoRoot --repo $Repo --phase tagged
    if ($LASTEXITCODE -ne 0) { throw "Release tag does not attest to the built source" }
    $assets = @($installerPath, $latestPath, $blockmapPath, $manifestPath)
    $remoteRelease = (& gh release view $tag --repo $Repo --json assets) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect release assets" }
    foreach ($asset in @($installerPath, $latestPath, $blockmapPath)) {
        $name = [IO.Path]::GetFileName($asset)
        $remote = @($remoteRelease.assets | Where-Object { $_.name -eq $name })
        if ($remote.Count -gt 0) {
            # Candidate promotion may reuse identical binaries, never replace them.
            Assert-RemoteDigest $tag $asset
        } else {
            & gh release upload $tag $asset --repo $Repo
            if ($LASTEXITCODE -ne 0) { throw "GitHub immutable asset upload failed: $name" }
            Assert-RemoteDigest $tag $asset
        }
    }
    # Verification metadata changes when a tested prerelease is promoted.
    & gh release upload $tag $manifestPath --repo $Repo --clobber
    if ($LASTEXITCODE -ne 0) { throw "GitHub manifest upload failed" }
    foreach ($asset in $assets) { Assert-RemoteDigest $tag $asset }
    if ($publishAsPrerelease) {
        & gh release edit $tag --repo $Repo --draft=false --prerelease --latest=false --notes-file "deploy/release_notes.md"
    } else {
        & gh release edit $tag --repo $Repo --draft=false --prerelease=false --latest --notes-file "deploy/release_notes.md"
    }
    if ($LASTEXITCODE -ne 0) { throw "GitHub release promotion failed" }
    if (-not $publishAsPrerelease) {
        & python scripts/verify_release_provenance.py --root $repoRoot --repo $Repo --phase published
        if ($LASTEXITCODE -ne 0) { throw "Release was published but public ordering/update verification failed; do not report success or rewrite tags" }
    }
    Write-Host "[WEB_UI_RELEASE] SUCCESS tag=$tag assets=$($assets.Count)"
} finally {
    Set-Location $originalLocation
}
