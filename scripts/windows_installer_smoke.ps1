param(
    [Parameter(Mandatory = $true)][string]$Hashmarks,
    [Parameter(Mandatory = $true)][string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $root "install.ps1"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("hashmarks-windows-installer-smoke-" + [guid]::NewGuid().ToString("N"))
$bundle = Join-Path $tempRoot "release bundle"
$installDir = Join-Path $tempRoot "install target"
$asset = Join-Path $bundle "hashmarks-windows-x86_64.exe"
$checksum = "$asset.sha256"
$target = Join-Path $installDir "hashmarks.exe"
$previousUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$previousProcessPath = $env:Path

function Write-InstallerChecksum {
    param([Parameter(Mandatory = $true)][string]$Path)
    $digest = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $Path -Value "$digest  hashmarks-windows-x86_64.exe" -Encoding utf8
}

function Assert-InstalledVersion {
    $reported = @(& $target --version)
    if ($LASTEXITCODE -ne 0 -or $reported.Count -ne 1 -or $reported[0] -ne "hashmarks version $Version") {
        throw "installed Windows standalone version mismatch: $($reported -join ', ')"
    }
}

try {
    New-Item -ItemType Directory -Force -Path $bundle, $installDir | Out-Null
    Copy-Item -LiteralPath $Hashmarks -Destination $asset
    Write-InstallerChecksum -Path $checksum

    $env:HASHMARKS_DOWNLOAD_BASE_URL = $bundle
    $env:HASHMARKS_INSTALL_DIR = $installDir
    $env:HASHMARKS_VERSION = $Version
    Remove-Item Env:HASHMARKS_SKIP_PATH_UPDATE -ErrorAction SilentlyContinue

    & $installer
    Assert-InstalledVersion

    $resolved = Get-Command hashmarks -CommandType Application -ErrorAction Stop
    if ([IO.Path]::GetFullPath($resolved.Source) -ine [IO.Path]::GetFullPath($target)) {
        throw "Windows installer PATH binding mismatch: $($resolved.Source)"
    }
    $qualifiedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash

    $env:HASHMARKS_VERSION = "v$Version"
    & $installer
    Assert-InstalledVersion
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $qualifiedHash) {
        throw "same-version Windows upgrade changed qualified bytes"
    }

    $env:HASHMARKS_VERSION = "0.0.0"
    $failed = $false
    try {
        & $installer
    }
    catch {
        $failed = $true
    }
    if (-not $failed) {
        throw "Windows installer accepted a requested-version mismatch"
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $qualifiedHash) {
        throw "requested-version failure replaced the working Windows binary"
    }

    $env:HASHMARKS_VERSION = "latest"
    Set-Content -LiteralPath $checksum -Value "$('0' * 64)  hashmarks-windows-x86_64.exe" -Encoding utf8
    $failed = $false
    try {
        & $installer
    }
    catch {
        $failed = $true
    }
    if (-not $failed) {
        throw "Windows installer accepted a wrong standalone checksum"
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $qualifiedHash) {
        throw "checksum failure replaced the working Windows binary"
    }

    Write-InstallerChecksum -Path $checksum
    Set-Content -LiteralPath $checksum -Value "$((Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant())  wrong.exe" -Encoding utf8
    $failed = $false
    try {
        & $installer
    }
    catch {
        $failed = $true
    }
    if (-not $failed) {
        throw "Windows installer accepted checksum authority for another asset name"
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $qualifiedHash) {
        throw "checksum-name failure replaced the working Windows binary"
    }

    Write-Output "Hashmarks Windows installer smoke: PASS"
}
finally {
    [Environment]::SetEnvironmentVariable("Path", $previousUserPath, "User")
    $env:Path = $previousProcessPath
    Remove-Item Env:HASHMARKS_DOWNLOAD_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:HASHMARKS_INSTALL_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:HASHMARKS_VERSION -ErrorAction SilentlyContinue
    Remove-Item Env:HASHMARKS_SKIP_PATH_UPDATE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
