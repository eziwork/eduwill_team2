param([ValidateSet("Json", "Text")][string]$Format = "Text")

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "runtime_discovery.ps1")
. (Join-Path $scriptDir "provider_secret_store.ps1")

$requiredFiles = @(
    "runtime_discovery.ps1",
    "provider_secret_store.ps1",
    "validate_intake.py",
    "plan_sources.py",
    "collect_molit_rtms.ps1",
    "prepare_report.py",
    "build_report.py",
    "browser_runtime.mjs",
    "check_render_runtime.mjs",
    "render_report.mjs",
    "render_review.mjs",
    "validate_pdf.py"
)
$missingFiles = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $scriptDir $_) -PathType Leaf) })
$platform = Get-EziworkPlatformName
$pwshCommand = Get-Command pwsh -CommandType Application -ErrorAction SilentlyContinue
$pythonPath = Resolve-EziworkRuntimePath -Kind Python -SkillRoot $skillRoot
$nodePath = Resolve-EziworkRuntimePath -Kind Node -SkillRoot $skillRoot
$nodeModulesPath = Resolve-EziworkNodeModulesPath -SkillRoot $skillRoot
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("CODEX_NODE_MODULES")) -and $nodeModulesPath) {
    [Environment]::SetEnvironmentVariable("CODEX_NODE_MODULES", $nodeModulesPath, "Process")
}

$renderRuntime = [pscustomobject][ordered]@{ ready = $false; platform = $platform; browser_path = $null; browser_source = $null; error = "Node.js is unavailable" }
if ($nodePath) {
    $probeOutput = & $nodePath (Join-Path $scriptDir "check_render_runtime.mjs") 2>&1
    $probeExitCode = $LASTEXITCODE
    try {
        $renderRuntime = ($probeOutput | Out-String).Trim() | ConvertFrom-Json
    } catch {
        $renderRuntime = [pscustomobject][ordered]@{
            ready = $false
            platform = $platform
            browser_path = $null
            browser_source = $null
            error = "Render runtime probe returned invalid output (exit $probeExitCode)"
        }
    }
}

$credentialAvailable = Test-ProviderSecretAvailable -Provider DATA_GO_KR
$failures = [System.Collections.Generic.List[string]]::new()
if ($missingFiles.Count -gt 0) { $failures.Add("missing required files: $($missingFiles -join ', ')") }
if ($null -eq $pwshCommand) { $failures.Add("PowerShell 7 (pwsh) is unavailable") }
if (-not $pythonPath) { $failures.Add("Python 3 runtime is unavailable") }

$status = if ($failures.Count -gt 0) {
    "BLOCKED"
} elseif (-not $nodePath -or -not $renderRuntime.ready -or -not $credentialAvailable) {
    "ACTION_REQUIRED"
} else {
    "READY"
}

$result = [pscustomobject][ordered]@{
    status = $status
    platform = $platform
    skill_root = $skillRoot
    runtimes = [pscustomobject][ordered]@{
        pwsh = $null -ne $pwshCommand
        python = -not [string]::IsNullOrWhiteSpace($pythonPath)
        node = -not [string]::IsNullOrWhiteSpace($nodePath)
        python_path = $pythonPath
        node_path = $nodePath
        node_modules_path = $nodeModulesPath
    }
    rendering = $renderRuntime
    credentials = [pscustomobject][ordered]@{
        data_go_kr_configured = $credentialAvailable
        storage = Get-ProviderStorageMode
    }
    missing_files = $missingFiles
    failures = @($failures)
    notes = @(
        "demo intake may continue without a credential",
        "-SkipPdf may continue without Node.js or a browser",
        "credential presence does not prove dataset approval, validity, or remaining quota",
        "Windows uses DPAPI; macOS uses the current user's Keychain",
        "Codex bundled Python, Node.js, and node_modules are used when discoverable"
    )
}

if ($Format -eq "Json") {
    $result | ConvertTo-Json -Depth 7
} else {
    "$status · platform=$platform · python=$(-not [string]::IsNullOrWhiteSpace($pythonPath)) · node=$(-not [string]::IsNullOrWhiteSpace($nodePath)) · render=$($renderRuntime.ready) · molit_credential=$credentialAvailable"
}
