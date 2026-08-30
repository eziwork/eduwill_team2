param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $false)]
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "molit_api_key_store.ps1")

function Add-Issue {
    param(
        [System.Collections.Generic.List[object]]$List,
        [string]$Code,
        [string]$Field,
        [string]$Message,
        [string]$Question = ""
    )

    $List.Add([pscustomobject][ordered]@{
        code = $Code
        field = $Field
        message = $Message
        blocking_question = if ([string]::IsNullOrWhiteSpace($Question)) { $null } else { $Question }
    })
}

function Test-YearMonth {
    param([string]$Value)
    if ($Value -notmatch '^\d{6}$') { return $false }
    $parsed = [datetime]::MinValue
    return [datetime]::TryParseExact($Value, "yyyyMM", $null, [Globalization.DateTimeStyles]::None, [ref]$parsed)
}

$resolved = (Resolve-Path -LiteralPath $ConfigPath).Path
$config = Get-Content -LiteralPath $resolved -Raw -Encoding UTF8 | ConvertFrom-Json
$errors = [System.Collections.Generic.List[object]]::new()
$warnings = [System.Collections.Generic.List[object]]::new()

if ($null -eq $config.target -or [string]::IsNullOrWhiteSpace([string]$config.target.complex_name)) {
    Add-Issue $errors "Q01_COMPLEX_REQUIRED" "target.complex_name" "단지명이 필요합니다." "어느 부동산을 분석할까요? 단지명과 지역을 함께 알려주세요."
}

$tradeType = [string]$config.transaction.trade_type
if ([string]::IsNullOrWhiteSpace($tradeType)) {
    Add-Issue $errors "Q05_TRADE_TYPE_REQUIRED" "transaction.trade_type" "거래유형이 필요합니다." "어떤 거래유형을 분석할까요? 매매, 전세, 월세 중에서 알려주세요."
} elseif ($tradeType -notin @("SALE", "JEONSE", "MONTHLY_RENT")) {
    Add-Issue $errors "INVALID_TRADE_TYPE" "transaction.trade_type" "허용값은 SALE, JEONSE, MONTHLY_RENT입니다."
}

$buildingMode = [string]$config.scope.building_mode
if ([string]::IsNullOrWhiteSpace($buildingMode) -or $buildingMode -eq "UNSET") {
    Add-Issue $errors "Q06_BUILDING_SCOPE_REQUIRED" "scope.building_mode" "동 범위를 결정해야 합니다." "전체 동과 특정 동 중 어느 범위로 수집할까요?"
} elseif ($buildingMode -notin @("ALL", "SELECTED")) {
    Add-Issue $errors "INVALID_BUILDING_MODE" "scope.building_mode" "허용값은 ALL 또는 SELECTED입니다."
} elseif ($buildingMode -eq "SELECTED" -and @($config.scope.building_names).Count -eq 0) {
    Add-Issue $errors "Q07_BUILDINGS_REQUIRED" "scope.building_names" "특정 동 모드에는 동 번호가 필요합니다." "수집할 동 번호를 알려주세요. 여러 동은 쉼표로 구분할 수 있습니다."
}

$areaMode = [string]$config.scope.area_mode
if ([string]::IsNullOrWhiteSpace($areaMode) -or $areaMode -eq "UNSET") {
    Add-Issue $errors "Q09_AREA_SCOPE_REQUIRED" "scope.area_mode" "면적 범위를 결정해야 합니다." "모든 면적과 특정 면적 중 어느 범위로 수집할까요?"
} elseif ($areaMode -notin @("ALL", "SELECTED")) {
    Add-Issue $errors "INVALID_AREA_MODE" "scope.area_mode" "허용값은 ALL 또는 SELECTED입니다."
} elseif ($areaMode -eq "SELECTED") {
    $hasRequestedValues = @($config.scope.requested_area_values).Count -gt 0
    $hasSelectedOptions = @($config.scope.selected_area_options).Count -gt 0
    $hasRange = $null -ne $config.scope.requested_area_min_sqm -and $null -ne $config.scope.requested_area_max_sqm
    if (-not ($hasRequestedValues -or $hasSelectedOptions -or $hasRange)) {
        Add-Issue $errors "Q10_AREA_REQUIRED" "scope.requested_area_values" "특정 면적 모드에는 면적값 또는 확정 면적형이 필요합니다." "원하는 면적을 전용면적 또는 공급면적 기준과 함께 알려주세요."
    }
}

if ($null -ne $config.scope.requested_area_min_sqm -and $null -ne $config.scope.requested_area_max_sqm) {
    if ([decimal]$config.scope.requested_area_min_sqm -le 0 -or [decimal]$config.scope.requested_area_max_sqm -le 0) {
        Add-Issue $errors "INVALID_AREA_RANGE" "scope.requested_area_min_sqm" "면적은 0보다 커야 합니다."
    } elseif ([decimal]$config.scope.requested_area_min_sqm -gt [decimal]$config.scope.requested_area_max_sqm) {
        Add-Issue $errors "INVALID_AREA_RANGE" "scope.requested_area_min_sqm" "최소면적은 최대면적보다 클 수 없습니다."
    }
}

$permissionMode = [string]$config.collection.permission_mode
if ([string]::IsNullOrWhiteSpace($permissionMode)) { $permissionMode = "RESEARCH_SAMPLE" }
if ($permissionMode -notin @("RESEARCH_SAMPLE", "AUTHORIZED_FULL")) {
    Add-Issue $errors "INVALID_PERMISSION_MODE" "collection.permission_mode" "허용값은 RESEARCH_SAMPLE 또는 AUTHORIZED_FULL입니다."
}
if ($permissionMode -eq "AUTHORIZED_FULL" -and [string]::IsNullOrWhiteSpace([string]$config.collection.written_permission_reference)) {
    Add-Issue $errors "Q17_PERMISSION_REFERENCE_REQUIRED" "collection.written_permission_reference" "전체수집에는 허가 근거 식별값이 필요합니다." "반복 수집 허가가 확인됐다면 허가 문서나 계약의 내부 식별값을 알려주세요."
}

if ($null -ne $config.collection.max_detail_pages -and [int]$config.collection.max_detail_pages -lt 0) {
    Add-Issue $errors "INVALID_DETAIL_LIMIT" "collection.max_detail_pages" "상세 조회 한도는 0 이상이어야 합니다."
}
if ($permissionMode -eq "RESEARCH_SAMPLE" -and [int]$config.collection.max_detail_pages -gt 10) {
    Add-Issue $warnings "SAMPLE_DETAIL_LIMIT" "collection.max_detail_pages" "RESEARCH_SAMPLE 상세 조회는 최대 10개로 낮춰야 합니다."
}

$historyYears = 0
$hasValidHistoryYears = $false
if ($null -eq $config.period -or -not [int]::TryParse([string]$config.period.history_years, [ref]$historyYears)) {
    Add-Issue $errors "Q20_PERIOD_REQUIRED" "period.history_years" "실거래 분석기간을 선택해야 합니다." "실거래 분석기간을 선택해주세요: 1년, 3년, 5년, 7년 중 하나를 입력해주세요. 빠른 기본 분석은 1년입니다."
} elseif ($historyYears -notin @(1, 3, 5, 7)) {
    Add-Issue $errors "INVALID_HISTORY_YEARS" "period.history_years" "허용 기간은 1년, 3년, 5년, 7년입니다."
} else {
    $hasValidHistoryYears = $true
}

if ($null -ne $config.period) {
    $startYm = [string]$config.period.molit_start_ym
    $endYm = [string]$config.period.molit_end_ym
    $hasStart = -not [string]::IsNullOrWhiteSpace($startYm)
    $hasEnd = -not [string]::IsNullOrWhiteSpace($endYm)
    if ($hasStart -xor $hasEnd) {
        Add-Issue $errors "INVALID_PERIOD" "period" "시작월과 종료월은 함께 입력하거나 둘 다 비워야 합니다."
    } elseif ($hasStart -and $hasEnd) {
        if (-not (Test-YearMonth $startYm) -or -not (Test-YearMonth $endYm)) {
            Add-Issue $errors "INVALID_PERIOD" "period" "국토부 조회월은 yyyyMM 형식이어야 합니다."
        } else {
            $start = [datetime]::ParseExact($startYm, "yyyyMM", $null)
            $end = [datetime]::ParseExact($endYm, "yyyyMM", $null)
            if ($start -gt $end) {
                Add-Issue $errors "INVALID_PERIOD_ORDER" "period" "시작월은 종료월보다 늦을 수 없습니다."
            } elseif ($hasValidHistoryYears) {
                $monthDifference = (($end.Year - $start.Year) * 12) + ($end.Month - $start.Month)
                if ($monthDifference -ne ($historyYears * 12)) {
                    Add-Issue $errors "PERIOD_SPAN_MISMATCH" "period" "선택 연수는 현재 잠정월과 그 이전 완결월을 포함한 조회기간과 일치해야 합니다."
                }
            }
        }
    }

    $naverScope = [string]$config.period.naver_scope
    if (-not [string]::IsNullOrWhiteSpace($naverScope) -and $naverScope -ne "CURRENT_SNAPSHOT") {
        Add-Issue $errors "INVALID_NAVER_PERIOD_SCOPE" "period.naver_scope" "네이버 매물 수집 범위는 CURRENT_SNAPSHOT만 지원합니다."
    }
}

$sources = if ($null -ne $config.collection -and $null -ne $config.collection.PSObject.Properties["sources"]) {
    @($config.collection.sources | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
} else {
    @()
}
if ($sources.Count -eq 0) {
    Add-Issue $errors "SOURCES_REQUIRED" "collection.sources" "하나 이상의 수집 출처가 필요합니다."
}
foreach ($source in $sources) {
    if ([string]$source -notin @("MOLIT", "NAVER_PAY_LAND")) {
        Add-Issue $errors "INVALID_SOURCE" "collection.sources" "지원 출처는 MOLIT와 NAVER_PAY_LAND입니다."
    }
}

if ($sources -contains "MOLIT") {
    $credentialPath = Get-MolitApiKeyCredentialPath
    if (-not (Test-MolitApiKeyAvailable -CredentialPath $credentialPath)) {
        Add-Issue $errors "Q18_MOLIT_API_KEY_REQUIRED" "credential_store.molit_api_key" "국토교통부 실거래 API 인증키가 저장되어 있지 않거나 현재 사용자 보안 저장소에서 읽을 수 없습니다." "국토교통부 실거래 API 인증키가 없습니다. 공공데이터포털에서 발급받은 인증키를 이 채팅에 입력해주세요. 키는 응답에 다시 표시하지 않고 Windows DPAPI 또는 macOS 키체인에 저장한 뒤 다음 실행부터 재사용하겠습니다."
    }
}

if ($tradeType -ne "SALE" -and $sources -contains "MOLIT") {
    Add-Issue $warnings "MOLIT_ROUTE_REQUIRED" "transaction.trade_type" "번들 국토부 수집기는 아파트 매매 전용입니다. 해당 거래유형에 맞는 공식 데이터셋을 먼저 선택해야 합니다."
}
if ($buildingMode -eq "SELECTED" -and $sources -contains "MOLIT") {
    Add-Issue $warnings "MOLIT_BUILDING_POLICY" "scope.building_names" "국토부 동 정보는 누락될 수 있습니다. 단지·면적 전체 집계와 동 정보 보유 거래 참고표를 분리하세요."
}

$result = [pscustomobject][ordered]@{
    status = if ($errors.Count -eq 0) { "VALID" } else { "INVALID" }
    config_path = $resolved
    error_count = $errors.Count
    warning_count = $warnings.Count
    errors = $errors
    warnings = $warnings
}

$json = $result | ConvertTo-Json -Depth 8
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $outputParent = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($outputParent)) {
        New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
    }
    Set-Content -LiteralPath $OutputPath -Value $json -Encoding UTF8
}

$json
if ($errors.Count -gt 0) { exit 2 }
