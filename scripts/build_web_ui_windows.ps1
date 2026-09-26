param(
    [switch]$SkipTests,
    [switch]$SkipNpmCi,
    [switch]$SkipEngineBuild,
    [switch]$AllowMissingKiwoomHost
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$originalLocation = Get-Location

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host "[WEB_UI_BUILD] $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit=$LASTEXITCODE)" }
}

function Invoke-NpmAuditWithRetry {
    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        Write-Host "[WEB_UI_BUILD] Web dependency audit attempt $attempt/$maxAttempts"
        & npm --prefix webui audit --audit-level=high
        if ($LASTEXITCODE -eq 0) { return }

        if ($attempt -eq $maxAttempts) {
            throw "Web dependency audit failed after $maxAttempts attempts (exit=$LASTEXITCODE)"
        }

        Start-Sleep -Seconds (5 * $attempt)
    }
}

function Invoke-KiwoomX86Python([string[]]$Arguments) {
    $configured = [string]$env:NOAHAI_PYTHON_X86
    if ($configured) {
        if (-not (Test-Path -LiteralPath $configured)) {
            throw "NOAHAI_PYTHON_X86 does not exist: $configured"
        }
        & $configured @Arguments
        return
    }
    & py -3.11-32 @Arguments
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Repair-ExistingManifestPreviousAsset([string]$Root, [string]$Version) {
    $manifestPath = Join-Path $Root "deploy\release-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { return }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if (-not $manifest.previous_published_asset -or -not $manifest.assets -or -not $manifest.assets.installer) { return }
    if ([version]$manifest.version -ge [version]$Version) { return }

    $previousPath = Join-Path $Root ([string]$manifest.previous_published_asset.path).Replace('/', '\')
    if (Test-Path -LiteralPath $previousPath) { return }

    $installerName = [string]$manifest.assets.installer.name
    $installerPath = Join-Path $Root "deploy\web-release\$installerName"
    if (-not (Test-Path -LiteralPath $installerPath)) { return }

    $installer = Get-Item -LiteralPath $installerPath
    $manifest.previous_published_asset = [ordered]@{
        version = [string]$manifest.version
        release_label = [string]$manifest.release_label
        path = "deploy/web-release/$installerName"
        size = $installer.Length
        sha256 = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        purpose = "previous_published_windows_build"
    }
    Write-Utf8NoBom $manifestPath ($manifest | ConvertTo-Json -Depth 8)
}

function Get-NodeJsonValue([string]$Expression) {
    $value = & node -p $Expression
    if ($LASTEXITCODE -ne 0) { throw "Node JSON query failed: $Expression" }
    return (($value | Out-String).Trim())
}

function Get-ReleaseSourceFingerprint([string]$Root) {
    $fingerprint = & python scripts/release_source_fingerprint.py --root $Root
    if ($LASTEXITCODE -ne 0) { throw "Release source fingerprint failed" }
    $value = (($fingerprint | Out-String).Trim()).ToLowerInvariant()
    if ($value -notmatch '^[0-9a-f]{64}$') { throw "Invalid release source fingerprint: $value" }
    return $value
}

function Get-SourceRevision([string]$Root) {
    $revision = & git -C $Root rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { return "unavailable" }
    return (($revision | Out-String).Trim())
}

function Test-SourceWorktreeDirty([string]$Root) {
    $status = & git -C $Root status --porcelain=v1 2>$null
    if ($LASTEXITCODE -ne 0) { return $true }
    return [bool](($status | Out-String).Trim())
}

function Clear-ElectronBuildStaging([string]$Root) {
    $releaseDir = Join-Path $Root "webui\release"
    foreach ($name in @("win-unpacked", "win-unpacked.tmp")) {
        $path = Join-Path $releaseDir $name
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

function Get-ExistingManifest([string]$Root) {
    $manifestPath = Join-Path $Root "deploy\release-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $null }
    return Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
}

function Get-PreviousPublishedAsset([string]$Root, [string]$Version, $ExistingManifest) {
    if ($ExistingManifest -and $ExistingManifest.version -eq $Version -and $ExistingManifest.previous_published_asset) {
        $asset = $ExistingManifest.previous_published_asset
        $path = Join-Path $Root ([string]$asset.path).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path)) { throw "Previous published asset missing: $path" }
        $item = Get-Item -LiteralPath $path
        return [ordered]@{
            version = [string]$asset.version
            release_label = [string]$asset.release_label
            path = [string]$asset.path
            size = $item.Length
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
            purpose = "previous_published_windows_build"
        }
    }

    $releaseDir = Join-Path $Root "deploy\web-release"
    $versionPattern = [regex]'NoahAI-(\d+\.\d+\.\d+\.\d+)-Setup\.exe$'
    $candidates = @(
        Get-ChildItem -LiteralPath $releaseDir -Filter "NoahAI-*-Setup.exe" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $match = $versionPattern.Match($_.Name)
            if ($match.Success) {
                [pscustomobject]@{
                    VersionText = $match.Groups[1].Value
                    VersionObject = [version]$match.Groups[1].Value
                    Item = $_
                }
            }
        } |
        Where-Object { $_.VersionObject -lt [version]$Version } |
        Sort-Object VersionObject -Descending
    )
    if (-not $candidates -or $candidates.Count -eq 0) {
        throw "Previous published asset missing in deploy\web-release"
    }
    $chosen = $candidates[0]
    return [ordered]@{
        version = $chosen.VersionText
        release_label = "v$($chosen.VersionText)"
        path = "deploy/web-release/$($chosen.Item.Name)"
        size = $chosen.Item.Length
        sha256 = (Get-FileHash -LiteralPath $chosen.Item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        purpose = "previous_published_windows_build"
    }
}

function Initialize-PendingReleaseManifest([string]$Root, [string]$Version, [string]$ReleaseLabel, [string]$UpdaterVersion, $ExistingManifest) {
    $manifestPath = Join-Path $Root "deploy\release-manifest.json"
    $deployVersionPath = Join-Path $Root "deploy\version.txt"
    if ($ExistingManifest -and $ExistingManifest.version -eq $Version -and $ExistingManifest.build_status -eq "pending_windows_rebuild") { return }

    $previousPublishedAsset = Get-PreviousPublishedAsset $Root $Version $ExistingManifest
    $installerName = "NoahAI-$Version-Setup.exe"
    $releaseBase = "https://github.com/nwsoft/ai-trading-client/releases/download/v$Version"
    $manifest = [ordered]@{
        version = $Version
        release_label = $ReleaseLabel
        channel = "stable"
        generated_at = [DateTime]::UtcNow.ToString("o")
        source_fingerprint = $null
        source_revision = Get-SourceRevision $Root
        source_worktree_dirty = Test-SourceWorktreeDirty $Root
        source_archive_authoritative = $false
        build_status = "pending_windows_rebuild"
        publish_ready = $false
        notes_file = "release_notes.md"
        verification = [ordered]@{
            sha256_required = $true
            authenticode_required = $false
            source = "github_release_manifest"
        }
        assets = [ordered]@{
            installer = [ordered]@{
                name = $installerName
                size = 0
                sha256 = ""
                download_url = "$releaseBase/$installerName"
            }
            latest_yml = [ordered]@{
                name = "latest.yml"
                size = 0
                sha256 = ""
                download_url = "$releaseBase/latest.yml"
            }
            blockmap = [ordered]@{
                name = "$installerName.blockmap"
                size = 0
                sha256 = ""
                download_url = "$releaseBase/$installerName.blockmap"
            }
            engine_sidecar = [ordered]@{
                name = "NoahAIEngine.exe"
                size = 0
                sha256 = ""
                distribution = "embedded_in_installer"
            }
            kiwoom_host = [ordered]@{
                name = "NoahAIKiwoomHost.exe"
                size = 0
                sha256 = ""
                pe_machine = "0x14c"
                supported = $false
                distribution = "embedded_in_installer"
            }
        }
        update_contract = [ordered]@{
            provider = "electron_updater_github"
            metadata = "latest.yml"
            product_version = $Version
            updater_semver = $UpdaterVersion
            version_mapping = "A.B.C.D -> A.B.(C*100+D); D=0..99"
            check_policy = "automatic_on_app_start"
            download_policy = "user_approved"
            install_policy = "user_approved_safe_shutdown_restart"
            user_actions = @("download", "install_and_restart")
            legacy_single_exe_updater = "retired_after_v3.9.0.10"
        }
        previous_published_asset = $previousPublishedAsset
        external_gates = @(
            "auto_update_from_previous_release",
            "windows_install_upgrade_rollback",
            "settings_general_save_close_restart",
            "settings_credentials_preserved",
            "broker_and_exchange_e2e",
            "paper_24_72h"
        )
    }
    Write-Utf8NoBom $manifestPath ($manifest | ConvertTo-Json -Depth 8)
    Write-Utf8NoBom $deployVersionPath $Version
}

try {
    Set-Location $repoRoot
    if (-not $IsWindows -and $env:OS -ne "Windows_NT") { throw "Windows build host is required" }
    foreach ($commandName in @("python", "node", "npm")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) { throw "$commandName is required" }
    }
    $nodeVersion = [version]((& node -p "process.versions.node").Trim())
    if ($nodeVersion -lt [version]"22.12.0") { throw "Node.js 22.12.0 or newer is required (actual=$nodeVersion)" }

    $version = (& python -c "from config.app_version import RELEASE_VERSION; print(RELEASE_VERSION)").Trim()
    $releaseLabel = (& python -c "from config.app_version import RELEASE_BUILD_LABEL; print(RELEASE_BUILD_LABEL)").Trim()
    $versionMatch = [regex]::Match($version, '^(\d+)\.(\d+)\.(\d+)\.(\d+)$')
    if (-not $versionMatch.Success) { throw "RELEASE_VERSION must use A.B.C.D product format (actual=$version)" }
    if ([version]$version -lt [version]"3.9.1.0") { throw "Electron Web UI release requires RELEASE_VERSION >= 3.9.1.0 (actual=$version)" }
    $revision = [int]$versionMatch.Groups[4].Value
    if ($revision -gt 99) { throw "RELEASE_VERSION revision D must be 0..99 for updater SemVer mapping (actual=$revision)" }
    $updaterPatch = ([int]$versionMatch.Groups[3].Value * 100) + $revision
    $updaterVersion = "$($versionMatch.Groups[1].Value).$($versionMatch.Groups[2].Value).$updaterPatch"
    $packageVersion = Get-NodeJsonValue "require('./webui/package.json').version"
    $packageLockVersion = Get-NodeJsonValue "require('./webui/package-lock.json').version"
    $packageLockRootVersion = Get-NodeJsonValue "require('./webui/package-lock.json').packages[''].version"
    $packageBuildVersion = Get-NodeJsonValue "require('./webui/package.json').build.buildVersion"
    $packageArtifactName = Get-NodeJsonValue "require('./webui/package.json').build.win.artifactName"
    if ($packageVersion -ne $updaterVersion) { throw "Electron updater version mismatch: expected=$updaterVersion actual=$packageVersion" }
    if ($packageLockVersion -ne $updaterVersion -or $packageLockRootVersion -ne $updaterVersion) {
        throw "Electron package-lock updater version mismatch: expected=$updaterVersion"
    }
    if ($packageBuildVersion -ne $version) { throw "Windows buildVersion mismatch: expected=$version actual=$packageBuildVersion" }
    $expectedArtifact = "NoahAI-$version-Setup.`${ext}"
    if ($packageArtifactName -ne $expectedArtifact) { throw "Windows artifactName mismatch: expected=$expectedArtifact actual=$packageArtifactName" }
    Invoke-Checked "Export exact legacy manual contract" { & python scripts/export_legacy_manual_sections.py }
    Invoke-Checked "Export canonical venue registry" { & python scripts/export_strategy_venue_registry.py }
    Repair-ExistingManifestPreviousAsset $repoRoot $version
    $existingManifest = Get-ExistingManifest $repoRoot
    Initialize-PendingReleaseManifest $repoRoot $version $releaseLabel $updaterVersion $existingManifest
    $existingManifest = Get-ExistingManifest $repoRoot

    $inputFingerprint = Get-ReleaseSourceFingerprint $repoRoot
    # Provider regression uses the exact electron-updater from package-lock.
    if (-not $SkipNpmCi) { Invoke-Checked "Install locked Web dependencies" { & npm --prefix webui ci } }
    if (-not $SkipTests) {
        Invoke-Checked "Python focused Web UI regression" { & python -m pytest -q tests/test_web_platform_3910.py }
        Invoke-Checked "Python full regression" { & python -m pytest -q }
        Invoke-Checked "Python source and release preflight" { & python scripts/active_source_audit.py }
        Invoke-Checked "Documentation and version consistency" { & python scripts/doc_consistency_check.py }
    }
    Invoke-Checked "Web production typecheck/build" { & npm --prefix webui run build }
    Invoke-Checked "Web dependency audit" { Invoke-NpmAuditWithRetry }

    Invoke-Checked "UI-neutral sidecar spec audit" { & python scripts/verify_web_engine_bundle.py --spec-only }
    Invoke-Checked "Windows VC143 preflight" { & python -c "import build_safe; build_safe.resolve_windows_vc_runtime_binaries()" }
    if (-not $SkipEngineBuild) {
        Invoke-Checked "Build Python engine sidecar" { & python -m PyInstaller --clean --noconfirm noahai_web_engine.spec }
    } elseif (-not (Test-Path -LiteralPath "dist\NoahAIEngine.exe")) {
        throw "SkipEngineBuild requires dist\NoahAIEngine.exe"
    }
    Invoke-Checked "Built sidecar legacy UI module audit" { & python scripts/verify_web_engine_bundle.py }
    Invoke-Checked "Built sidecar desktop bootstrap API smoke" { & python scripts/smoke_web_engine.py "dist\NoahAIEngine.exe" }

    $engineSource = (Resolve-Path "dist\NoahAIEngine.exe").Path
    $engineDir = Join-Path $repoRoot "deploy\web-engine"
    New-Item -ItemType Directory -Path $engineDir -Force | Out-Null
    Copy-Item -LiteralPath $engineSource -Destination (Join-Path $engineDir "NoahAIEngine.exe") -Force
    # OpenAPI+ is a separate x86 COM server. A spawned x64 engine cannot load it.
    # Strict builds must package the host. Operator override can publish the
    # current crypto/Web candidate while leaving Kiwoom as an external gate.
    $kiwoomHostPath = "dist\NoahAIKiwoomHost.exe"
    $kiwoomReady = $false
    Invoke-KiwoomX86Python @("-c", "import struct, PyInstaller, pykiwoom.kiwoom; from PyQt5 import QAxContainer; assert struct.calcsize('P') == 4")
    if ($LASTEXITCODE -eq 0) {
        Invoke-Checked "Build dedicated Kiwoom x86 host" { Invoke-KiwoomX86Python @("-m", "PyInstaller", "--clean", "--noconfirm", "noahai_kiwoom_host.spec") }
        Invoke-Checked "Verify Kiwoom host PE architecture" { & python -c "from pathlib import Path; from trading.exchanges.adapters.kiwoom_host_launcher import pe_machine; assert pe_machine(Path('dist/NoahAIKiwoomHost.exe')) == 0x14c" }
        $kiwoomReady = $true
    } elseif ($AllowMissingKiwoomHost) {
        Write-Warning "Kiwoom x86 host build environment is unavailable. Publishing without NoahAIKiwoomHost.exe by operator override; Kiwoom remains an external gate."
    } else {
        throw "Kiwoom x86 Python and dependencies preflight failed (exit=$LASTEXITCODE). Install Windows Python 3.11 x86 with PyInstaller, PyQt5(QAxContainer), and pykiwoom, or rerun with -AllowMissingKiwoomHost for an operator override."
    }
    if ($kiwoomReady) {
        Invoke-Checked "Kiwoom host authenticated IPC and adapter startup smoke" { & python scripts/smoke_kiwoom_host.py $kiwoomHostPath }
        Copy-Item -LiteralPath $kiwoomHostPath -Destination (Join-Path $engineDir "NoahAIKiwoomHost.exe") -Force
    } else {
        Remove-Item -LiteralPath (Join-Path $engineDir "NoahAIKiwoomHost.exe") -Force -ErrorAction SilentlyContinue
    }
    $engineHash = (Get-FileHash -LiteralPath (Join-Path $engineDir "NoahAIEngine.exe") -Algorithm SHA256).Hash.ToLowerInvariant()
    $kiwoomDeployPath = Join-Path $engineDir "NoahAIKiwoomHost.exe"
    $kiwoomHash = if ($kiwoomReady) { (Get-FileHash -LiteralPath $kiwoomDeployPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }

    Clear-ElectronBuildStaging $repoRoot
    Invoke-Checked "Build Electron NSIS installer" { & npm --prefix webui run desktop:dist }
    $packagedKiwoomHost = Join-Path $repoRoot "webui\release\win-unpacked\resources\engine\NoahAIKiwoomHost.exe"
    if ($kiwoomReady) {
        if (-not (Test-Path -LiteralPath $packagedKiwoomHost)) { throw "Electron package is missing NoahAIKiwoomHost.exe" }
        Invoke-Checked "Verify packaged Kiwoom host PE architecture" { & python -c "from pathlib import Path; from trading.exchanges.adapters.kiwoom_host_launcher import pe_machine; assert pe_machine(Path(r'$packagedKiwoomHost')) == 0x14c" }
        $packagedKiwoomHash = (Get-FileHash -LiteralPath $packagedKiwoomHost -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($packagedKiwoomHash -ne $kiwoomHash) { throw "Packaged Kiwoom host SHA-256 mismatch" }
    }
    $installer = Get-ChildItem -Path "webui\release" -Filter "NoahAI-$version-Setup.exe" | Select-Object -First 1
    if (-not $installer) { throw "NSIS installer was not produced" }
    $latestYml = Join-Path $repoRoot "webui\release\latest.yml"
    if (-not (Test-Path -LiteralPath $latestYml)) { throw "electron-updater latest.yml was not produced" }
    $latestText = Get-Content -LiteralPath $latestYml -Raw
    $latestVersionMatch = [regex]::Match($latestText, '(?m)^version:\s*["'']?([^"''\s]+)')
    if (-not $latestVersionMatch.Success -or $latestVersionMatch.Groups[1].Value -ne $updaterVersion) {
        throw "latest.yml updater version mismatch: expected=$updaterVersion actual=$($latestVersionMatch.Groups[1].Value)"
    }
    $blockmap = Get-ChildItem -Path "webui\release" -Filter "NoahAI-$version-Setup.exe.blockmap" | Select-Object -First 1
    if (-not $blockmap) { throw "electron-updater blockmap was not produced" }
    $installerHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $latestYmlHash = (Get-FileHash -LiteralPath $latestYml -Algorithm SHA256).Hash.ToLowerInvariant()
    $blockmapHash = (Get-FileHash -LiteralPath $blockmap.FullName -Algorithm SHA256).Hash.ToLowerInvariant()

    $previousPublishedAsset = Get-PreviousPublishedAsset $repoRoot $version $existingManifest

    $releaseDir = Join-Path $repoRoot "deploy\web-release"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    Copy-Item -LiteralPath $installer.FullName -Destination (Join-Path $releaseDir $installer.Name) -Force
    Copy-Item -LiteralPath $latestYml -Destination (Join-Path $releaseDir "latest.yml") -Force
    Copy-Item -LiteralPath $blockmap.FullName -Destination (Join-Path $releaseDir $blockmap.Name) -Force

    $releaseBase = "https://github.com/nwsoft/ai-trading-client/releases/download/v$version"
    $sourceFingerprint = Get-ReleaseSourceFingerprint $repoRoot
    if ($sourceFingerprint -ne $inputFingerprint) { throw "Source changed during build; rebuild the candidate." }
    $manifest = [ordered]@{
        version = $version
        release_label = $releaseLabel
        channel = "stable"
        generated_at = [DateTime]::UtcNow.ToString("o")
        source_fingerprint = $sourceFingerprint
        source_revision = Get-SourceRevision $repoRoot
        source_worktree_dirty = Test-SourceWorktreeDirty $repoRoot
        source_archive_authoritative = $false
        build_status = "windows_automated_checks_passed"
        automated_checks_passed = (-not $SkipTests -and -not $SkipEngineBuild -and -not $AllowMissingKiwoomHost)
        publish_ready = (-not $SkipTests -and -not $SkipEngineBuild -and -not $AllowMissingKiwoomHost)
        notes_file = "release_notes.md"
        verification = [ordered]@{
            sha256_required = $true
            authenticode_required = $false
            source = "github_release_manifest"
        }
        assets = [ordered]@{
            installer = [ordered]@{
                name = $installer.Name
                size = $installer.Length
                sha256 = $installerHash
                download_url = "$releaseBase/$($installer.Name)"
            }
            latest_yml = [ordered]@{
                name = "latest.yml"
                size = (Get-Item -LiteralPath $latestYml).Length
                sha256 = $latestYmlHash
                download_url = "$releaseBase/latest.yml"
            }
            blockmap = [ordered]@{
                name = $blockmap.Name
                size = $blockmap.Length
                sha256 = $blockmapHash
                download_url = "$releaseBase/$($blockmap.Name)"
            }
            engine_sidecar = [ordered]@{
                name = "NoahAIEngine.exe"
                size = (Get-Item -LiteralPath (Join-Path $engineDir "NoahAIEngine.exe")).Length
                sha256 = $engineHash
                distribution = "embedded_in_installer"
            }
            kiwoom_host = [ordered]@{
                name = "NoahAIKiwoomHost.exe"
                size = if ($kiwoomReady) { (Get-Item -LiteralPath $kiwoomDeployPath).Length } else { 0 }
                sha256 = $kiwoomHash
                pe_machine = "0x14c"
                supported = $kiwoomReady
                distribution = "embedded_in_installer"
            }
        }
        update_contract = [ordered]@{
            provider = "electron_updater_github"
            metadata = "latest.yml"
            product_version = $version
            updater_semver = $updaterVersion
            version_mapping = "A.B.C.D -> A.B.(C*100+D); D=0..99"
            check_policy = "automatic_on_app_start"
            download_policy = "user_approved"
            install_policy = "user_approved_safe_shutdown_restart"
            user_actions = @("download", "install_and_restart")
            legacy_single_exe_updater = "retired_after_v3.9.0.10"
        }
        previous_published_asset = $previousPublishedAsset
        external_validation_status = "pending"
        external_validation = if ($existingManifest -and $existingManifest.version -eq $version -and $existingManifest.external_validation) {
            @($existingManifest.external_validation)
        } elseif ($existingManifest -and $existingManifest.version -eq $version -and $existingManifest.external_gates) {
            @($existingManifest.external_gates)
        } else {
            @(
                "auto_update_from_previous_release",
                "windows_install_upgrade_rollback",
                "settings_general_save_close_restart",
                "settings_credentials_preserved",
                "broker_and_exchange_e2e",
                "paper_24_72h"
            )
        }
    }
    $manifestPath = Join-Path $repoRoot "deploy\release-manifest.json"
    Write-Utf8NoBom $manifestPath ($manifest | ConvertTo-Json -Depth 8)

    Write-Host "[WEB_UI_BUILD] SUCCESS"
    Write-Host "[WEB_UI_BUILD] engine=$engineSource"
    Write-Host "[WEB_UI_BUILD] engine_sha256=$engineHash"
    Write-Host "[WEB_UI_BUILD] kiwoom_host=$kiwoomDeployPath"
    Write-Host "[WEB_UI_BUILD] kiwoom_host_sha256=$kiwoomHash"
    Write-Host "[WEB_UI_BUILD] installer=$($installer.FullName)"
    Write-Host "[WEB_UI_BUILD] installer_sha256=$installerHash"
    Write-Host "[WEB_UI_BUILD] blockmap_sha256=$blockmapHash"
    Write-Host "[WEB_UI_BUILD] manifest=$manifestPath"
    Write-Host "[WEB_UI_BUILD] build_status=windows_automated_checks_passed; publish_ready=$($manifest.publish_ready)."
    Write-Host "[WEB_UI_BUILD] Account, live-order, OCX login, upgrade UX, and soak checks are recorded as non-blocking external validation."
} finally {
    Set-Location $originalLocation
}
