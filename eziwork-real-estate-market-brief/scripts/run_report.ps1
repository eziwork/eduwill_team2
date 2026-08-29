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
. (Join-Path $scriptDir "runtime_discovery.ps1")

$resolvedIntake = (Resolve-Path -LiteralPath $IntakePath).Path
$resolvedReportRoot = [System.IO.Path]::GetFullPath($ReportRoot)
New-Item -ItemType Directory -Force -Path $resolvedReportRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Resolve-EziworkRuntimePath -Kind Python -SkillRoot $skillRoot
} else {
    $PythonExe = Resolve-EziworkExecutableInput -Value $PythonExe
}
if ([string]::IsNullOrWhiteSpace($PythonExe)) { throw "PYTHON_RUNTIME_NOT_FOUND: install Python 3 or pass -PythonExe" }

if (-not $SkipPdf) {
    if ([string]::IsNullOrWhiteSpace($NodeExe)) {
        $NodeExe = Resolve-EziworkRuntimePath -Kind Node -SkillRoot $skillRoot
    } else {
        $NodeExe = Resolve-EziworkExecutableInput -Value $NodeExe
    }
    if ([string]::IsNullOrWhiteSpace($NodeExe)) { throw "NODE_RUNTIME_NOT_FOUND: install Node.js or pass -NodeExe" }
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("CODEX_NODE_MODULES"))) {
        $nodeModulesPath = Resolve-EziworkNodeModulesPath -SkillRoot $skillRoot
        if ($nodeModulesPath) {
            [Environment]::SetEnvironmentVariable("CODEX_NODE_MODULES", $nodeModulesPath, "Process")
        }
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
    platform = Get-EziworkPlatformName
    skill_root = $skillRoot
    report_root = $resolvedReportRoot
    html = $htmlPath
    pdf = if ($SkipPdf) { $null } else { $pdfPath }
    audit = $auditPath
    review = if ($SkipPdf) { $null } else { $reviewDir }
} | ConvertTo-Json -Depth 4
