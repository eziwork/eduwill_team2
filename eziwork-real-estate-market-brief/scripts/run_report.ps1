param(
    [Parameter(Mandatory = $true)][string]$IntakePath,
    [Parameter(Mandatory = $true)][string]$ReportRoot,
    [string]$OfficialRowsPath = "",
    [string]$OfficialManifestPath = "",
    [string]$ListingsPath = "",
    [string]$PythonExe = "",
    [string]$NodeExe = "",
    [switch]$SkipPdf
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptDir
$resolvedIntake = (Resolve-Path -LiteralPath $IntakePath).Path
$resolvedReportRoot = [System.IO.Path]::GetFullPath($ReportRoot)
New-Item -ItemType Directory -Force -Path $resolvedReportRoot | Out-Null
$profileCandidates = [System.Collections.Generic.List[string]]::new()
$profileCandidates.Add([Environment]::GetFolderPath("UserProfile"))
if ($skillRoot -match '^(?<profile>[A-Za-z]:\\Users\\[^\\]+)') { $profileCandidates.Add($Matches.profile) }
$bundleRoot = $null
foreach ($profileCandidate in @($profileCandidates | Select-Object -Unique)) {
    $candidateRoot = Join-Path $profileCandidate ".cache\codex-runtimes\codex-primary-runtime\dependencies"
    if (Test-Path -LiteralPath $candidateRoot -PathType Container) { $bundleRoot = $candidateRoot; break }
}
if ($null -eq $bundleRoot) { $bundleRoot = Join-Path $profileCandidates[0] ".cache\codex-runtimes\codex-primary-runtime\dependencies" }
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $PythonExe = if ($null -ne $pythonCommand) { $pythonCommand.Source } else { Join-Path $bundleRoot "python\python.exe" }
}
if ([string]::IsNullOrWhiteSpace($NodeExe)) {
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $NodeExe = if ($null -ne $nodeCommand) { $nodeCommand.Source } else { Join-Path $bundleRoot "node\bin\node.exe" }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw "PYTHON_RUNTIME_NOT_FOUND: $PythonExe" }
if (-not (Test-Path -LiteralPath $NodeExe -PathType Leaf)) { throw "NODE_RUNTIME_NOT_FOUND: $NodeExe" }
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("CODEX_NODE_MODULES"))) {
    $bundledNodeModules = Join-Path $bundleRoot "node\node_modules"
    if (Test-Path -LiteralPath $bundledNodeModules -PathType Container) {
        [Environment]::SetEnvironmentVariable("CODEX_NODE_MODULES", $bundledNodeModules, "Process")
    }
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "COMMAND_FAILED: $Executable exited with code $LASTEXITCODE"
    }
}

Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "validate_intake.py"), $resolvedIntake)
Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "plan_sources.py"), $resolvedIntake, "--output", (Join-Path $resolvedReportRoot "source-plan.json"))

$prepareArguments = @(
    (Join-Path $scriptDir "prepare_report.py"),
    "--intake", $resolvedIntake,
    "--report-root", $resolvedReportRoot
)
if (-not [string]::IsNullOrWhiteSpace($OfficialRowsPath)) {
    $prepareArguments += @("--official-rows", (Resolve-Path -LiteralPath $OfficialRowsPath).Path)
}
if (-not [string]::IsNullOrWhiteSpace($OfficialManifestPath)) {
    $prepareArguments += @("--official-manifest", (Resolve-Path -LiteralPath $OfficialManifestPath).Path)
}
if (-not [string]::IsNullOrWhiteSpace($ListingsPath)) {
    $prepareArguments += @("--listings", (Resolve-Path -LiteralPath $ListingsPath).Path)
}
Invoke-Checked -Executable $PythonExe -Arguments $prepareArguments

$requestPath = Join-Path $resolvedReportRoot "report-request.json"
$auditPath = Join-Path $resolvedReportRoot "evidence-audit.json"
$htmlPath = Join-Path $resolvedReportRoot "report.html"
$pdfPath = Join-Path $resolvedReportRoot "report.pdf"
$reviewDir = Join-Path $resolvedReportRoot "review"

Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "audit_evidence.py"), $requestPath, "--output", $auditPath)
Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "build_report.py"), $requestPath, "--output", $htmlPath, "--audit-output", $auditPath)
Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "validate_report.py"), $htmlPath, "--request", $requestPath)

if (-not $SkipPdf) {
    Invoke-Checked -Executable $NodeExe -Arguments @((Join-Path $scriptDir "render_report.mjs"), "--input", $htmlPath, "--output", $pdfPath)
    Invoke-Checked -Executable $PythonExe -Arguments @((Join-Path $scriptDir "validate_pdf.py"), $pdfPath, "--request", $requestPath, "--html", $htmlPath)
    Invoke-Checked -Executable $NodeExe -Arguments @((Join-Path $scriptDir "render_review.mjs"), "--input", $htmlPath, "--output-dir", $reviewDir)
}

[pscustomobject][ordered]@{
    status = "COMPLETED"
    skill_root = $skillRoot
    report_root = $resolvedReportRoot
    html = $htmlPath
    pdf = if ($SkipPdf) { $null } else { $pdfPath }
    audit = $auditPath
    review = if ($SkipPdf) { $null } else { $reviewDir }
} | ConvertTo-Json -Depth 4
