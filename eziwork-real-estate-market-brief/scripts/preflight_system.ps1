param([ValidateSet("Json", "Text")][string]$Format = "Text")

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "provider_secret_store.ps1")

$requiredFiles = @(
    "validate_intake.py",
    "plan_sources.py",
    "collect_molit_rtms.ps1",
    "prepare_report.py",
    "build_report.py",
    "render_report.mjs",
    "validate_pdf.py"
)
$missingFiles = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $scriptDir $_) -PathType Leaf) })
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$pwshCommand = Get-Command pwsh -ErrorAction SilentlyContinue
$profileCandidates = [System.Collections.Generic.List[string]]::new()
$profileCandidates.Add([Environment]::GetFolderPath("UserProfile"))
if ($skillRoot -match '^(?<profile>[A-Za-z]:\\Users\\[^\\]+)') { $profileCandidates.Add($Matches.profile) }
$bundleRoot = $null
foreach ($profileCandidate in @($profileCandidates | Select-Object -Unique)) {
    $candidateRoot = Join-Path $profileCandidate ".cache\codex-runtimes\codex-primary-runtime\dependencies"
    if (Test-Path -LiteralPath $candidateRoot -PathType Container) { $bundleRoot = $candidateRoot; break }
}
if ($null -eq $bundleRoot) { $bundleRoot = Join-Path $profileCandidates[0] ".cache\codex-runtimes\codex-primary-runtime\dependencies" }
$bundledPython = Join-Path $bundleRoot "python\python.exe"
$bundledNode = Join-Path $bundleRoot "node\bin\node.exe"
$pythonAvailable = $null -ne $pythonCommand -or (Test-Path -LiteralPath $bundledPython -PathType Leaf)
$nodeAvailable = $null -ne $nodeCommand -or (Test-Path -LiteralPath $bundledNode -PathType Leaf)
$credentialAvailable = Test-ProviderSecretAvailable -Provider DATA_GO_KR

$failures = [System.Collections.Generic.List[string]]::new()
if ($missingFiles.Count -gt 0) { $failures.Add("missing required files: $($missingFiles -join ', ')") }
if ($null -eq $pwshCommand) { $failures.Add("PowerShell 7 (pwsh) is unavailable") }

$status = if ($failures.Count -gt 0) {
    "BLOCKED"
} elseif (-not $pythonAvailable -or -not $nodeAvailable -or -not $credentialAvailable) {
    "ACTION_REQUIRED"
} else {
    "READY"
}

$result = [pscustomobject][ordered]@{
    status = $status
    skill_root = Split-Path -Parent $scriptDir
    runtimes = [pscustomobject][ordered]@{
        pwsh = $null -ne $pwshCommand
        python = $pythonAvailable
        node = $nodeAvailable
        python_path = if ($null -ne $pythonCommand) { $pythonCommand.Source } elseif ($pythonAvailable) { $bundledPython } else { $null }
        node_path = if ($null -ne $nodeCommand) { $nodeCommand.Source } elseif ($nodeAvailable) { $bundledNode } else { $null }
    }
    data_go_kr_credential_configured = $credentialAvailable
    missing_files = $missingFiles
    failures = @($failures)
    notes = @(
        "demo intake may continue without a credential",
        "credential presence does not prove dataset approval, validity, or remaining quota",
        "Codex bundled Python/Node may be used when PATH runtimes are absent"
    )
}

if ($Format -eq "Json") {
    $result | ConvertTo-Json -Depth 6
} else {
    "$status · python=$pythonAvailable · node=$nodeAvailable · molit_credential=$credentialAvailable"
}
