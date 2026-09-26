Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-HashmarksEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Default
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function Assert-HashmarksReleaseVersion {
    param([Parameter(Mandatory = $true)][string]$Version)
    if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
        throw "hashmarks installer: invalid release version: $Version"
    }
}

function Copy-HashmarksReleaseFile {
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if ($Base -match '^https?://') {
        Invoke-WebRequest -UseBasicParsing -Uri "$($Base.TrimEnd('/'))/$Name" -OutFile $Destination
        return
    }

    if ($Base -match '^file://') {
        $uri = [Uri]"$($Base.TrimEnd('/'))/$Name"
        Copy-Item -LiteralPath $uri.LocalPath -Destination $Destination
        return
    }

    Copy-Item -LiteralPath (Join-Path $Base $Name) -Destination $Destination
}

function Ensure-HashmarksUserPath {
    param([Parameter(Mandatory = $true)][string]$InstallDir)

    if ($env:HASHMARKS_SKIP_PATH_UPDATE -eq "1") {
        return $false
    }

    $normalized = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $entries = @($userPath.Split(';') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    $present = $false
    foreach ($entry in $entries) {
        if ([IO.Path]::GetFullPath($entry).TrimEnd('\') -ieq $normalized) {
            $present = $true
            break
        }
    }
    if (-not $present) {
        $newUserPath = if ($entries.Count -eq 0) {
            $normalized
        }
        else {
            "$normalized;$($entries -join ';')"
        }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }

    $processEntries = @($env:Path.Split(';') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $processPresent = $false
    foreach ($entry in $processEntries) {
        try {
            if ([IO.Path]::GetFullPath($entry).TrimEnd('\') -ieq $normalized) {
                $processPresent = $true
                break
            }
        }
        catch {
            continue
        }
    }
    if (-not $processPresent) {
        $env:Path = "$normalized;$env:Path"
    }
    return (-not $present)
}

$repository = Get-HashmarksEnvironmentValue -Name "HASHMARKS_REPOSITORY" -Default "Hugloss/Hashmarks"
$version = Get-HashmarksEnvironmentValue -Name "HASHMARKS_VERSION" -Default "latest"

if ($version -eq "latest") {
    $requestedVersion = ""
}
else {
    $requestedVersion = $version
    if ($requestedVersion.StartsWith("v")) {
        $requestedVersion = $requestedVersion.Substring(1)
    }
    Assert-HashmarksReleaseVersion -Version $requestedVersion
}

if ($env:OS -ne "Windows_NT") {
    throw "hashmarks installer: install.ps1 supports Windows only"
}

$architecture = $env:PROCESSOR_ARCHITECTURE
if ($architecture -notin @("AMD64", "x86_64")) {
    throw "hashmarks installer: unsupported architecture: $architecture"
}

$asset = "hashmarks-windows-x86_64.exe"
if (-not [string]::IsNullOrWhiteSpace($env:HASHMARKS_DOWNLOAD_BASE_URL)) {
    $base = $env:HASHMARKS_DOWNLOAD_BASE_URL.TrimEnd('/', '\')
}
elseif ($version -eq "latest") {
    $base = "https://github.com/$repository/releases/latest/download"
}
else {
    $tag = if ($version.StartsWith("v")) { $version } else { "v$version" }
    $base = "https://github.com/$repository/releases/download/$tag"
}

if (-not [string]::IsNullOrWhiteSpace($env:HASHMARKS_INSTALL_DIR)) {
    $installDir = $env:HASHMARKS_INSTALL_DIR
}
elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    $installDir = Join-Path $env:LOCALAPPDATA "Hashmarks\bin"
}
else {
    $installDir = Join-Path $HOME ".local\bin"
}

$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("hashmarks-install-" + [guid]::NewGuid().ToString("N"))
$candidate = $null
$backup = $null
try {
    [IO.Directory]::CreateDirectory($tempDir) | Out-Null
    $binary = Join-Path $tempDir $asset
    $checksum = Join-Path $tempDir "$asset.sha256"
    Copy-HashmarksReleaseFile -Base $base -Name $asset -Destination $binary
    Copy-HashmarksReleaseFile -Base $base -Name "$asset.sha256" -Destination $checksum

    $lines = @(Get-Content -LiteralPath $checksum -Encoding UTF8)
    if ($lines.Count -ne 1) {
        throw "hashmarks installer: checksum asset must contain exactly one entry"
    }
    if ($lines[0] -notmatch '^([0-9A-Fa-f]{64})\s+\*?(hashmarks-windows-x86_64\.exe)$') {
        throw "hashmarks installer: invalid SHA-256 checksum asset"
    }
    $expected = $Matches[1].ToLowerInvariant()
    $checksumAsset = $Matches[2]
    if ($checksumAsset -ne $asset) {
        throw "hashmarks installer: checksum entry names $checksumAsset, expected $asset"
    }

    $actual = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "hashmarks installer: SHA-256 verification failed"
    }

    [IO.Directory]::CreateDirectory($installDir) | Out-Null
    $target = Join-Path $installDir "hashmarks.exe"
    if ((Test-Path -LiteralPath $target) -and (Get-Item -LiteralPath $target).PSIsContainer) {
        throw "hashmarks installer: install target exists but is not a file: $target"
    }

    $candidate = Join-Path $installDir (".hashmarks-install." + [guid]::NewGuid().ToString("N") + ".exe")
    Copy-Item -LiteralPath $binary -Destination $candidate

    $reported = @(& $candidate --version 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "hashmarks installer: downloaded binary failed version smoke test"
    }
    if ($reported.Count -ne 1 -or $reported[0] -notmatch '^hashmarks version ([0-9]+\.[0-9]+\.[0-9]+)$') {
        throw "hashmarks installer: downloaded binary returned an invalid release version"
    }
    $reportedVersion = $Matches[1]
    if (-not [string]::IsNullOrWhiteSpace($requestedVersion) -and $reportedVersion -ne $requestedVersion) {
        throw "hashmarks installer: requested version $requestedVersion but downloaded binary reports $reportedVersion"
    }

    if (Test-Path -LiteralPath $target) {
        $backup = "$target.hashmarks-backup"
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Force
        }
        [IO.File]::Replace($candidate, $target, $backup, $true)
        $candidate = $null
        Remove-Item -LiteralPath $backup -Force
        $backup = $null
    }
    else {
        Move-Item -LiteralPath $candidate -Destination $target
        $candidate = $null
    }

    $pathAdded = Ensure-HashmarksUserPath -InstallDir $installDir

    Write-Output "Hashmarks installed: $target"
    if ($pathAdded) {
        Write-Output "Added $installDir to your user PATH."
    }
    elseif ($env:HASHMARKS_SKIP_PATH_UPDATE -eq "1") {
        Write-Output "PATH update skipped. Add $installDir to PATH to run hashmarks by name."
    }

    $resolved = Get-Command hashmarks -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $resolved) {
        $resolvedPath = [IO.Path]::GetFullPath($resolved.Source)
        if ($resolvedPath -ine [IO.Path]::GetFullPath($target)) {
            Write-Warning "hashmarks on PATH resolves to $resolvedPath; installed target is $target"
        }
    }

    if ($null -ne (Get-Command opencode -ErrorAction SilentlyContinue)) {
        Write-Output "OpenCode detected. From the target repository run: hashmarks install --opencode"
    }
}
finally {
    if ($null -ne $candidate -and (Test-Path -LiteralPath $candidate)) {
        Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $backup -and (Test-Path -LiteralPath $backup)) {
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
