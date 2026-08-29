$ErrorActionPreference = "Stop"
$skillRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$registryPath = Join-Path (Join-Path $skillRoot "references") "source-registry.json"
$collectorPath = Join-Path (Join-Path $skillRoot "scripts") "collect_molit_rtms.ps1"
$testRoot = Join-Path (Join-Path ([System.IO.Path]::GetTempPath()) "eziwork-real-estate-market-brief") "rtms-dry-run"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$tested = 0

foreach ($property in $registry.sources.PSObject.Properties) {
    $source = $property.Value
    if ([string]$source.provider -ne "MOLIT_RTMS") { continue }
    $support = @($source.supports)[0]
    $config = [ordered]@{
        source_id = $property.Name
        target = [ordered]@{
            subject_name = "검증대상"
            property_type = [string]$support.property_type
            lawd_cd = "11680"
        }
        transaction = [ordered]@{ trade_type = [string]$support.trade_type }
        scope = [ordered]@{ requested_area_min_sqm = 80; requested_area_max_sqm = 90 }
        period = [ordered]@{ molit_start_ym = "202607"; molit_end_ym = "202608" }
    }
    $configPath = Join-Path $testRoot "$($property.Name).json"
    [System.IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    $raw = & pwsh -NoProfile -File $collectorPath -ConfigPath $configPath -DryRun
    if ($LASTEXITCODE -ne 0) { throw "collector dry-run failed: $($property.Name)" }
    $result = $raw | ConvertFrom-Json
    if ($result.mode -ne "DRY_RUN") { throw "unexpected mode: $($property.Name)" }
    if ($result.service_key -ne "REDACTED") { throw "service key was not redacted: $($property.Name)" }
    if ($result.endpoint -notmatch '^https://apis\.data\.go\.kr/1613000/RTMSDataSvc') { throw "endpoint outside allowlist: $($property.Name)" }
    if ($result.source_id -ne $property.Name) { throw "route mismatch: $($property.Name)" }
    $tested++
}

if ($tested -ne 10) { throw "expected 10 RTMS dataset dry-runs, got $tested" }

$canonicalConfig = [ordered]@{
    intake_version = "1.0"
    basis_date = "2026-08-29"
    target = [ordered]@{
        name = "검증대상"
        property_type = "APT"
        lawd_cd = "11680"
    }
    transaction = [ordered]@{ trade_type = "SALE" }
    scope = [ordered]@{ requested_area_min_sqm = 84; requested_area_max_sqm = 85 }
    period = [ordered]@{ history_years = 1 }
}
$canonicalPath = Join-Path $testRoot "canonical-intake.json"
[System.IO.File]::WriteAllText($canonicalPath, ($canonicalConfig | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
$canonicalRaw = & pwsh -NoProfile -File $collectorPath -ConfigPath $canonicalPath -DryRun
if ($LASTEXITCODE -ne 0) { throw "canonical intake dry-run failed" }
$canonical = $canonicalRaw | ConvertFrom-Json
if (@($canonical.months).Count -ne 12 -or $canonical.months[0] -ne "202509" -or $canonical.months[-1] -ne "202608") {
    throw "canonical history_years did not resolve to the expected 12 months"
}
if ($canonical.target_name_contains -ne "검증대상") { throw "canonical target.name was not routed" }

"PASS: $tested RTMS dataset dry-runs and canonical intake routing"
