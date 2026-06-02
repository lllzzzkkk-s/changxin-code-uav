[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HandoffPackage,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-fA-F0-9]{64}$')]
    [string]$HandoffSha256,

    [string[]]$ArtifactPackage = @(),

    [string[]]$ArtifactSha256 = @(),

    [string]$EvidenceRoot = "C:\changxin-evidence",

    [string]$WslEvidenceDir = "/tmp/changxin-distributed-fleet-evidence",

    [string]$WslDistro = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param(
        [string]$Name,
        [string]$Expected
    )
    Write-Host ""
    Write-Host "STEP: $Name"
    Write-Host "EXPECTED: $Expected"
}

function Write-Pass {
    param([string]$Message)
    Write-Host "PASS: $Message"
}

function Stop-Fail {
    param([string]$Message)
    Write-Host "FAIL: $Message" -ForegroundColor Red
    throw $Message
}

function Get-ArchiveItem {
    param([string]$PathValue)
    $item = Get-Item -LiteralPath $PathValue -ErrorAction Stop
    if (-not $item.PSIsContainer -and $item.Name.EndsWith(".tar.gz", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $item
    }
    Stop-Fail "archive must be a readable .tar.gz file: $PathValue"
}

function Assert-Hash {
    param(
        [System.IO.FileInfo]$Item,
        [string]$ExpectedHash
    )
    $actual = (Get-FileHash -LiteralPath $Item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash.ToLowerInvariant()) {
        Stop-Fail "sha256 mismatch for $($Item.FullName): expected $ExpectedHash got $actual"
    }
    return $actual
}

function Convert-ToBashSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Invoke-WslPath {
    param(
        [string]$WindowsPath,
        [string[]]$WslBaseArgs
    )
    $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
    if ($fullPath -match '^([A-Za-z]):\\?(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $tail = $Matches[2].Replace('\', '/')
        if ($tail) {
            return "/mnt/$drive/$tail"
        }
        return "/mnt/$drive"
    }
    $converted = & wsl.exe @WslBaseArgs -- wslpath -a $WindowsPath
    if ($LASTEXITCODE -ne 0) {
        Stop-Fail "wslpath failed for $WindowsPath"
    }
    return ($converted | Select-Object -Last 1).Trim()
}

if ($ArtifactPackage.Count -ne $ArtifactSha256.Count) {
    Stop-Fail "ArtifactPackage and ArtifactSha256 must have the same count; pass one sha256 per artifact package"
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$wslScript = Join-Path $repoRoot "tools\unit_receiving_wsl2.sh"
if (-not (Test-Path -LiteralPath $wslScript -PathType Leaf)) {
    Stop-Fail "missing WSL2 receiving script: $wslScript"
}

$logsDir = Join-Path $EvidenceRoot "logs"
$incomingDir = Join-Path $logsDir "incoming"
New-Item -ItemType Directory -Force -Path $logsDir, $incomingDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$transcriptPath = Join-Path $logsDir "unit-receiving-$timestamp-powershell.log"
$bridgeLog = Join-Path $logsDir "unit-receiving-$timestamp-wsl2.log"
$manifestPath = Join-Path $logsDir "unit-receiving-$timestamp-windows-manifest.json"

Start-Transcript -Path $transcriptPath -Force | Out-Null
try {
    Write-Step "Windows intake scope" "PowerShell receives files, verifies hashes, checks paths, and starts WSL2 only."
    Write-Pass "No Windows-native ROS commands or repository Python commands are run by this script."

    Write-Step "Check input archives" "handoff and artifact inputs are readable .tar.gz files."
    $handoffItem = Get-ArchiveItem -PathValue $HandoffPackage
    $artifactItems = @()
    foreach ($pathValue in $ArtifactPackage) {
        $artifactItems += Get-ArchiveItem -PathValue $pathValue
    }
    Write-Pass "validated $($artifactItems.Count + 1) archive path(s)"

    Write-Step "Verify SHA256" "computed hashes exactly match the operator-supplied expected values."
    $handoffHash = Assert-Hash -Item $handoffItem -ExpectedHash $HandoffSha256
    $artifactHashes = @()
    for ($index = 0; $index -lt $artifactItems.Count; $index++) {
        $artifactHashes += Assert-Hash -Item $artifactItems[$index] -ExpectedHash $ArtifactSha256[$index]
    }
    Write-Pass "all supplied archive hashes matched"

    Write-Step "Stage files for WSL2" "archives are copied under C:\changxin-evidence\logs\incoming for stable /mnt/c access."
    $stagedHandoff = Join-Path $incomingDir $handoffItem.Name
    Copy-Item -LiteralPath $handoffItem.FullName -Destination $stagedHandoff -Force
    $stagedArtifacts = @()
    foreach ($artifact in $artifactItems) {
        $target = Join-Path $incomingDir $artifact.Name
        Copy-Item -LiteralPath $artifact.FullName -Destination $target -Force
        $stagedArtifacts += $target
    }
    Write-Pass "staged handoff package and $($stagedArtifacts.Count) artifact package(s)"

    $wslBaseArgs = @()
    if ($WslDistro.Trim()) {
        $wslBaseArgs += @("-d", $WslDistro.Trim())
    }
    $null = & wsl.exe @wslBaseArgs -- true
    if ($LASTEXITCODE -ne 0) {
        Stop-Fail "WSL2 is not available or the selected distribution failed to start"
    }

    $wslRepoRoot = Invoke-WslPath -WindowsPath $repoRoot -WslBaseArgs $wslBaseArgs
    $wslHandoff = Invoke-WslPath -WindowsPath $stagedHandoff -WslBaseArgs $wslBaseArgs
    $wslLogDir = Invoke-WslPath -WindowsPath $logsDir -WslBaseArgs $wslBaseArgs
    $wslArtifacts = @()
    foreach ($stagedArtifact in $stagedArtifacts) {
        $wslArtifacts += Invoke-WslPath -WindowsPath $stagedArtifact -WslBaseArgs $wslBaseArgs
    }

    $manifest = [ordered]@{
        schema = "WindowsSafeUnitReceivingIntake.v1"
        repo_root = $repoRoot
        evidence_root = $EvidenceRoot
        windows_log_dir = $logsDir
        wsl_evidence_dir = $WslEvidenceDir
        handoff = [ordered]@{
            original_path = $handoffItem.FullName
            staged_path = $stagedHandoff
            sha256 = $handoffHash
            wsl_path = $wslHandoff
        }
        artifact_packages = @()
        scope = "PowerShell only performs intake, sha256 checks, path checks, and WSL2 launch"
    }
    for ($index = 0; $index -lt $stagedArtifacts.Count; $index++) {
        $manifest.artifact_packages += [ordered]@{
            original_path = $artifactItems[$index].FullName
            staged_path = $stagedArtifacts[$index]
            sha256 = $artifactHashes[$index]
            wsl_path = $wslArtifacts[$index]
        }
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Pass "wrote Windows intake manifest: $manifestPath"

    Write-Step "Start WSL2 verifier" "WSL2 bash verifies handoff package, optional artifact packages, phase gate, and goal evidence."
    $artifactArgs = @()
    foreach ($wslArtifact in $wslArtifacts) {
        $artifactArgs += "--artifact-package"
        $artifactArgs += $wslArtifact
    }
    $quotedArtifactArgs = ($artifactArgs | ForEach-Object { Convert-ToBashSingleQuoted $_ }) -join " "
    $bashCommand = @(
        "cd $(Convert-ToBashSingleQuoted $wslRepoRoot)",
        "bash tools/unit_receiving_wsl2.sh --handoff-package $(Convert-ToBashSingleQuoted $wslHandoff) --evidence-dir $(Convert-ToBashSingleQuoted $WslEvidenceDir) --log-dir $(Convert-ToBashSingleQuoted $wslLogDir) $quotedArtifactArgs"
    ) -join " && "

    & wsl.exe @wslBaseArgs -- bash -lc $bashCommand 2>&1 | Tee-Object -FilePath $bridgeLog
    $wslExit = $LASTEXITCODE
    if ($wslExit -ne 0) {
        Stop-Fail "WSL2 verifier failed with exit code $wslExit; see $bridgeLog"
    }
    Write-Pass "WSL2 verifier completed; see $bridgeLog"
    Write-Host ""
    Write-Host "FINAL PASS: receiving kit completed without Windows-native ROS or repo Python."
    Write-Host "WINDOWS LOGS: $logsDir"
    Write-Host "WSL EVIDENCE: $WslEvidenceDir"
}
finally {
    Stop-Transcript | Out-Null
}
