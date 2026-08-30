param(
    [Parameter(Mandatory = $false)]
    [string]$ConfigPath = "",

    [Parameter(Mandatory = $false)]
    [string]$OutputRoot = "",

    [Parameter(Mandatory = $false)]
    [string]$ServiceKey = "",

    [Parameter(Mandatory = $false)]
    [string]$CredentialPath = "",

    [Parameter(Mandatory = $false)]
    [switch]$ServiceKeyIsEncoded,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "molit_api_key_store.ps1")

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    throw "ConfigPath is required. Use a report-specific MOLIT JSON config."
}

$configPathResolved = (Resolve-Path -LiteralPath $ConfigPath).Path
$config = Get-Content -Raw -Encoding UTF8 -LiteralPath $configPathResolved | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path (Split-Path -Parent $configPathResolved) "molit"
}

$requiredConfigFields = @(
    "lawd_cd", "start_ym", "end_ym", "apartment_name_contains",
    "exclusive_area_min_sqm", "exclusive_area_max_sqm", "api_endpoint"
)
foreach ($field in $requiredConfigFields) {
    $property = $config.PSObject.Properties[$field]
    if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        throw "Missing required config field: $field"
    }
}

if ($config.PSObject.Properties["transaction_type"] -and $config.transaction_type -ne "매매") {
    throw "This collector only supports apartment sale transactions (매매)."
}

if ([string]$config.lawd_cd -notmatch '^\d{5}$') {
    throw "lawd_cd must contain exactly five digits."
}

if ([decimal]$config.exclusive_area_min_sqm -gt [decimal]$config.exclusive_area_max_sqm) {
    throw "exclusive_area_min_sqm cannot be greater than exclusive_area_max_sqm."
}

function Get-MonthSequence {
    param(
        [string]$StartYm,
        [string]$EndYm
    )

    $start = [datetime]::ParseExact($StartYm, "yyyyMM", $null)
    $end = [datetime]::ParseExact($EndYm, "yyyyMM", $null)

    if ($start -gt $end) {
        throw "start_ym cannot be later than end_ym."
    }

    $months = [System.Collections.Generic.List[string]]::new()
    $cursor = $start
    while ($cursor -le $end) {
        $months.Add($cursor.ToString("yyyyMM"))
        $cursor = $cursor.AddMonths(1)
    }
    return $months
}

function Convert-ItemNodeToObject {
    param([System.Xml.XmlNode]$ItemNode)

    $record = [ordered]@{}
    foreach ($child in $ItemNode.ChildNodes) {
        if ($child.NodeType -eq [System.Xml.XmlNodeType]::Element) {
            $record[$child.Name] = $child.InnerText.Trim()
        }
    }
    return [pscustomobject]$record
}

function Get-FirstPropertyValue {
    param(
        [object]$Record,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $property = $Record.PSObject.Properties[$name]
        if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            return ([string]$property.Value).Trim()
        }
    }
    return ""
}

function Convert-ToNullableDecimal {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    $clean = $Value.Replace(",", "").Trim()
    $parsed = 0.0
    if ([decimal]::TryParse($clean, [ref]$parsed)) { return $parsed }
    return $null
}

function Convert-ToNullableInt64 {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    $clean = $Value.Replace(",", "").Trim()
    $parsed = [long]0
    if ([long]::TryParse($clean, [ref]$parsed)) { return $parsed }
    return $null
}

function New-NormalizedRecord {
    param(
        [object]$RawRecord,
        [string]$LawdCd,
        [string]$DealYm,
        [string]$RawFile,
        [string]$RetrievedAt
    )

    $dealYear = Get-FirstPropertyValue $RawRecord @("dealYear")
    $dealMonth = Get-FirstPropertyValue $RawRecord @("dealMonth")
    $dealDay = Get-FirstPropertyValue $RawRecord @("dealDay")
    $contractDate = ""
    if ($dealYear -and $dealMonth -and $dealDay) {
        $contractDate = "{0}-{1:D2}-{2:D2}" -f [int]$dealYear, [int]$dealMonth, [int]$dealDay
    }

    $dealAmountRaw = Get-FirstPropertyValue $RawRecord @("dealAmount")
    $dealAmount10k = Convert-ToNullableInt64 $dealAmountRaw
    $priceKrw = if ($null -ne $dealAmount10k) { $dealAmount10k * 10000 } else { $null }

    $areaRaw = Get-FirstPropertyValue $RawRecord @("excluUseAr")
    $area = Convert-ToNullableDecimal $areaRaw
    $cancelMarker = Get-FirstPropertyValue $RawRecord @("cdealType")

    return [pscustomobject][ordered]@{
        source_id = "MOLIT_APT_TRADE_DETAIL"
        retrieved_at = $RetrievedAt
        lawd_cd = $LawdCd
        query_deal_ym = $DealYm
        contract_date = $contractDate
        apartment_name = Get-FirstPropertyValue $RawRecord @("aptNm")
        legal_dong = Get-FirstPropertyValue $RawRecord @("umdNm")
        lot_number = Get-FirstPropertyValue $RawRecord @("jibun")
        road_name = Get-FirstPropertyValue $RawRecord @("roadNm")
        exclusive_area_sqm = $area
        floor = Get-FirstPropertyValue $RawRecord @("floor")
        deal_amount_10k_krw = $dealAmount10k
        deal_amount_krw = $priceKrw
        build_year = Get-FirstPropertyValue $RawRecord @("buildYear")
        transaction_method = Get-FirstPropertyValue $RawRecord @("dealingGbn")
        cancellation_marker = $cancelMarker
        cancellation_date = Get-FirstPropertyValue $RawRecord @("cdealDay")
        registration_date = Get-FirstPropertyValue $RawRecord @("rgstDate")
        apartment_dong = Get-FirstPropertyValue $RawRecord @("aptDong")
        agent_district = Get-FirstPropertyValue $RawRecord @("estateAgentSggNm")
        buyer_type = Get-FirstPropertyValue $RawRecord @("buyerGbn")
        seller_type = Get-FirstPropertyValue $RawRecord @("slerGbn")
        raw_source_file = $RawFile
    }
}

function Invoke-MolitRequest {
    param(
        [string]$Uri,
        [int]$MaxAttempts = 2
    )

    $lastError = $null
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60
        } catch {
            $lastError = $_
            if ($attempt -ge $MaxAttempts) { break }
            Start-Sleep -Seconds 2
        }
    }

    throw "MOLIT request failed after $MaxAttempts attempts: $($lastError.Exception.Message)"
}

$months = Get-MonthSequence -StartYm $config.start_ym -EndYm $config.end_ym

if ($DryRun) {
    [pscustomobject]@{
        mode = "DRY_RUN"
        test_name = $config.test_name
        endpoint = $config.api_endpoint
        lawd_cd = $config.lawd_cd
        months = ($months -join ",")
        apartment_filter = $config.apartment_name_contains
        area_filter_sqm = "$($config.exclusive_area_min_sqm)~$($config.exclusive_area_max_sqm)"
        output_root = $OutputRoot
        service_key = "REDACTED"
    } | ConvertTo-Json -Depth 5
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ServiceKey)) {
    $ServiceKey = Get-MolitApiKey -CredentialPath $CredentialPath
}

if ([string]::IsNullOrWhiteSpace($ServiceKey)) {
    $fixedPath = Get-MolitApiKeyCredentialPath -CredentialPath $CredentialPath
    throw "MOLIT_API_KEY_REQUIRED: 국토교통부 실거래 API 인증키가 없습니다. 채팅에서 키를 입력받아 현재 운영체제의 사용자 보안 저장소에 저장한 뒤 다시 실행하세요. Windows 기본경로: $fixedPath"
}

$escapedServiceKey = if ($ServiceKeyIsEncoded) {
    $ServiceKey
} else {
    [uri]::EscapeDataString($ServiceKey)
}

$rawDir = Join-Path $OutputRoot "raw"
$normalizedDir = Join-Path $OutputRoot "normalized"
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null
New-Item -ItemType Directory -Force -Path $normalizedDir | Out-Null

$retrievedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
$allRawRecords = [System.Collections.Generic.List[object]]::new()
$allNormalizedRecords = [System.Collections.Generic.List[object]]::new()
$requestLog = [System.Collections.Generic.List[object]]::new()

foreach ($month in $months) {
    $pageNo = 1
    $pageSize = 1000
    $monthCollected = 0
    $totalCount = $null

    do {
        $query = "serviceKey=$escapedServiceKey&LAWD_CD=$($config.lawd_cd)&DEAL_YMD=$month&pageNo=$pageNo&numOfRows=$pageSize"
        $requestUrl = "$($config.api_endpoint)?$query"
        $safeRequestUrl = "$($config.api_endpoint)?serviceKey=REDACTED&LAWD_CD=$($config.lawd_cd)&DEAL_YMD=$month&pageNo=$pageNo&numOfRows=$pageSize"

        $response = Invoke-MolitRequest -Uri $requestUrl
        $rawFileName = "apt_trade_$($config.lawd_cd)_${month}_p${pageNo}.xml"
        $rawFilePath = Join-Path $rawDir $rawFileName
        [System.IO.File]::WriteAllText($rawFilePath, $response.Content, [System.Text.UTF8Encoding]::new($false))

        [xml]$xml = $response.Content
        $resultCodeNode = $xml.SelectSingleNode("//resultCode")
        $resultMsgNode = $xml.SelectSingleNode("//resultMsg")
        $resultCode = if ($resultCodeNode) { $resultCodeNode.InnerText } else { "" }
        $resultMsg = if ($resultMsgNode) { $resultMsgNode.InnerText } else { "" }

        if ($resultCode -notin @("00", "000", "0", "")) {
            throw "API error: code=$resultCode, message=$resultMsg, month=$month, page=$pageNo"
        }

        $totalCountNode = $xml.SelectSingleNode("//totalCount")
        if ($totalCountNode) { $totalCount = [int]$totalCountNode.InnerText }

        $itemNodes = $xml.SelectNodes("//item")
        $pageCount = 0
        foreach ($itemNode in $itemNodes) {
            $rawRecord = Convert-ItemNodeToObject -ItemNode $itemNode
            $allRawRecords.Add($rawRecord)
            $normalized = New-NormalizedRecord -RawRecord $rawRecord -LawdCd $config.lawd_cd -DealYm $month -RawFile $rawFileName -RetrievedAt $retrievedAt
            $allNormalizedRecords.Add($normalized)
            $pageCount++
        }

        $monthCollected += $pageCount
        $requestLog.Add([pscustomobject]@{
            month = $month
            page = $pageNo
            returned_rows = $pageCount
            total_count = $totalCount
            request_url_redacted = $safeRequestUrl
            raw_file = $rawFileName
            result_code = $resultCode
            result_message = $resultMsg
        })

        $pageNo++
    } while ($null -ne $totalCount -and $monthCollected -lt $totalCount)
}

$allCsvPath = Join-Path $normalizedDir "molit_apt_trade_all_region_rows.csv"
$allJsonPath = Join-Path $normalizedDir "molit_apt_trade_all_region_rows.json"
$targetCsvPath = Join-Path $normalizedDir "molit_apt_trade_target_rows.csv"
$targetJsonPath = Join-Path $normalizedDir "molit_apt_trade_target_rows.json"
$manifestPath = Join-Path $OutputRoot "collection_manifest.json"

$allNormalizedRecords | Export-Csv -LiteralPath $allCsvPath -NoTypeInformation -Encoding UTF8
$allNormalizedRecords | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $allJsonPath -Encoding UTF8

$targetRows = @($allNormalizedRecords | Where-Object {
    $_.apartment_name -like "*$($config.apartment_name_contains)*" -and
    $null -ne $_.exclusive_area_sqm -and
    $_.exclusive_area_sqm -ge [decimal]$config.exclusive_area_min_sqm -and
    $_.exclusive_area_sqm -le [decimal]$config.exclusive_area_max_sqm
})

$targetRows | Export-Csv -LiteralPath $targetCsvPath -NoTypeInformation -Encoding UTF8
$targetRows | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $targetJsonPath -Encoding UTF8

$manifest = [ordered]@{
    test_name = $config.test_name
    dataset = $config.api_dataset
    data_go_kr_id = $config.api_data_go_kr_id
    endpoint = $config.api_endpoint
    retrieved_at = $retrievedAt
    query = [ordered]@{
        lawd_cd = $config.lawd_cd
        lawd_name = $config.lawd_name
        start_ym = $config.start_ym
        end_ym = $config.end_ym
        apartment_name_contains = $config.apartment_name_contains
        exclusive_area_min_sqm = $config.exclusive_area_min_sqm
        exclusive_area_max_sqm = $config.exclusive_area_max_sqm
    }
    row_counts = [ordered]@{
        all_region_rows = $allNormalizedRecords.Count
        target_rows = $targetRows.Count
    }
    files = [ordered]@{
        raw_directory = $rawDir
        all_rows_csv = $allCsvPath
        all_rows_json = $allJsonPath
        target_rows_csv = $targetCsvPath
        target_rows_json = $targetJsonPath
    }
    requests = $requestLog
    service_key_logged = $false
}

$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[pscustomobject]@{
    status = "COMPLETED"
    all_region_rows = $allNormalizedRecords.Count
    target_rows = $targetRows.Count
    output_root = $OutputRoot
    manifest = $manifestPath
} | ConvertTo-Json -Depth 4
