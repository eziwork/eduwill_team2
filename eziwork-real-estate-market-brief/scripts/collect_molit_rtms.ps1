param(
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [string]$OutputRoot = "",
    [string]$ServiceKey = "",
    [string]$CredentialPath = "",
    [switch]$ServiceKeyIsEncoded,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "provider_secret_store.ps1")

function Get-ConfigValue {
    param([object]$Object, [string[]]$Paths)
    foreach ($path in $Paths) {
        $current = $Object
        $found = $true
        foreach ($part in $path.Split('.')) {
            if ($null -eq $current -or $null -eq $current.PSObject.Properties[$part]) {
                $found = $false
                break
            }
            $current = $current.$part
        }
        if ($found -and $null -ne $current -and -not [string]::IsNullOrWhiteSpace([string]$current)) {
            return $current
        }
    }
    return $null
}

function Get-MonthSequence {
    param([string]$StartYm, [string]$EndYm)
    $start = [datetime]::ParseExact($StartYm, "yyyyMM", $null)
    $end = [datetime]::ParseExact($EndYm, "yyyyMM", $null)
    if ($start -gt $end) { throw "RTMS_CONFIG_INVALID: start_ym cannot be later than end_ym." }
    $months = [System.Collections.Generic.List[string]]::new()
    for ($cursor = $start; $cursor -le $end; $cursor = $cursor.AddMonths(1)) {
        $months.Add($cursor.ToString("yyyyMM"))
    }
    return @($months)
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
    param([object]$Record, [string[]]$Names)
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
    $parsed = [decimal]0
    if ([decimal]::TryParse($Value.Replace(",", "").Trim(), [ref]$parsed)) { return $parsed }
    return $null
}

function Convert-TenThousandWonToKrw {
    param([string]$Value)
    $parsed = Convert-ToNullableDecimal -Value $Value
    if ($null -eq $parsed) { return $null }
    return [long]([decimal]$parsed * 10000)
}

function Convert-ToContractDate {
    param([object]$Record)
    $year = Get-FirstPropertyValue $Record @("dealYear", "contractYear")
    $month = Get-FirstPropertyValue $Record @("dealMonth", "contractMonth")
    $day = Get-FirstPropertyValue $Record @("dealDay", "contractDay")
    if ($year -and $month -and $day) {
        try { return "{0}-{1:D2}-{2:D2}" -f [int]$year, [int]$month, [int]$day } catch { return "" }
    }
    return ""
}

function New-NormalizedRecord {
    param(
        [object]$RawRecord,
        [string]$SourceId,
        [string]$PropertyType,
        [string]$RequestedTradeType,
        [string]$LawdCd,
        [string]$DealYm,
        [string]$RawFile,
        [string]$RetrievedAt
    )

    $monthlyRentRaw = Get-FirstPropertyValue $RawRecord @("monthlyRent")
    $monthlyRentKrw = Convert-TenThousandWonToKrw $monthlyRentRaw
    $actualTradeType = if ($SourceId -match '_RENT$') {
        if ($null -ne $monthlyRentKrw -and $monthlyRentKrw -gt 0) { "MONTHLY_RENT" } else { "JEONSE" }
    } else { "SALE" }
    $cancelMarker = Get-FirstPropertyValue $RawRecord @("cdealType", "cancelDealType")
    $cancelDate = Get-FirstPropertyValue $RawRecord @("cdealDay", "cancelDealDay")
    $exclusiveArea = Convert-ToNullableDecimal (Get-FirstPropertyValue $RawRecord @("excluUseAr", "exclusiveArea", "buildingAr", "totalFloorAr"))
    $landArea = Convert-ToNullableDecimal (Get-FirstPropertyValue $RawRecord @("dealArea", "landArea", "plottageAr", "landAr"))

    return [pscustomobject][ordered]@{
        source_id = $SourceId
        source_type = "OFFICIAL_PRIMARY"
        adapter_version = "rtms-generic-1"
        retrieved_at = $RetrievedAt
        property_type = $PropertyType
        requested_trade_type = $RequestedTradeType
        trade_type = $actualTradeType
        lawd_cd = $LawdCd
        query_deal_ym = $DealYm
        contract_date = Convert-ToContractDate $RawRecord
        property_name = Get-FirstPropertyValue $RawRecord @("aptNm", "offiNm", "mhouseNm", "buildingName", "bldNm", "houseType")
        legal_dong = Get-FirstPropertyValue $RawRecord @("umdNm", "emdNm")
        lot_number = Get-FirstPropertyValue $RawRecord @("jibun", "landLot")
        road_name = Get-FirstPropertyValue $RawRecord @("roadNm", "roadName")
        exclusive_area_sqm = $exclusiveArea
        land_area_sqm = $landArea
        floor = Get-FirstPropertyValue $RawRecord @("floor")
        deal_amount_krw = Convert-TenThousandWonToKrw (Get-FirstPropertyValue $RawRecord @("dealAmount"))
        deposit_krw = Convert-TenThousandWonToKrw (Get-FirstPropertyValue $RawRecord @("deposit"))
        monthly_rent_krw = $monthlyRentKrw
        build_year = Get-FirstPropertyValue $RawRecord @("buildYear")
        transaction_method = Get-FirstPropertyValue $RawRecord @("dealingGbn")
        contract_type = Get-FirstPropertyValue $RawRecord @("contractType")
        contract_term = Get-FirstPropertyValue $RawRecord @("contractTerm")
        renewal_right_used = Get-FirstPropertyValue $RawRecord @("useRRRight")
        land_category = Get-FirstPropertyValue $RawRecord @("jimok")
        land_use = Get-FirstPropertyValue $RawRecord @("landUse")
        use_zone = Get-FirstPropertyValue $RawRecord @("landUseZone", "useZone")
        road_condition = Get-FirstPropertyValue $RawRecord @("roadCondition")
        building_use = Get-FirstPropertyValue $RawRecord @("buildingUse")
        cancellation_marker = $cancelMarker
        cancellation_date = $cancelDate
        cancelled = (-not [string]::IsNullOrWhiteSpace($cancelMarker) -or -not [string]::IsNullOrWhiteSpace($cancelDate))
        registration_date = Get-FirstPropertyValue $RawRecord @("rgstDate")
        apartment_dong = Get-FirstPropertyValue $RawRecord @("aptDong")
        agent_district = Get-FirstPropertyValue $RawRecord @("estateAgentSggNm")
        raw_source_file = $RawFile
    }
}

function Invoke-RtmsRequest {
    param([string]$Uri, [int]$MaxAttempts = 2)
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60
        } catch {
            if ($attempt -ge $MaxAttempts) {
                throw "MOLIT_HTTP_FAILURE: request failed after $MaxAttempts attempts."
            }
            Start-Sleep -Seconds 2
        }
    }
}

$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$config = Get-Content -LiteralPath $resolvedConfig -Raw -Encoding UTF8 | ConvertFrom-Json
$registryPath = Join-Path (Split-Path -Parent $scriptDir) "references\source-registry.json"
$registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json

$propertyType = ([string](Get-ConfigValue $config @("property_type", "target.property_type"))).ToUpperInvariant()
$tradeType = ([string](Get-ConfigValue $config @("trade_type", "transaction.trade_type"))).ToUpperInvariant()
$lawdCd = [string](Get-ConfigValue $config @("lawd_cd", "target.lawd_cd"))
$startYm = [string](Get-ConfigValue $config @("start_ym", "period.molit_start_ym"))
$endYm = [string](Get-ConfigValue $config @("end_ym", "period.molit_end_ym"))
$sourceId = [string](Get-ConfigValue $config @("source_id"))

if ([string]::IsNullOrWhiteSpace($startYm) -and [string]::IsNullOrWhiteSpace($endYm)) {
    $basisDateText = [string](Get-ConfigValue $config @("basis_date"))
    $historyYearsText = [string](Get-ConfigValue $config @("period.history_years"))
    $historyYears = 0
    $basisDate = [datetime]::MinValue
    $basisDateValid = [datetime]::TryParseExact(
        $basisDateText,
        "yyyy-MM-dd",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None,
        [ref]$basisDate
    )
    $historyYearsValid = [int]::TryParse($historyYearsText, [ref]$historyYears) -and $historyYears -in @(1, 3, 5, 7)
    if ($basisDateValid -and $historyYearsValid) {
        $endYm = $basisDate.ToString("yyyyMM")
        $startYm = $basisDate.AddMonths(-(12 * $historyYears - 1)).ToString("yyyyMM")
    }
}

if ($propertyType -notin @("APT", "ROWHOUSE", "DETACHED_HOUSE", "OFFICETEL", "LAND", "COMMERCIAL")) {
    throw "RTMS_CONFIG_INVALID: unsupported property_type=$propertyType"
}
if ($tradeType -notin @("SALE", "JEONSE", "MONTHLY_RENT")) {
    throw "RTMS_CONFIG_INVALID: unsupported trade_type=$tradeType"
}
if ($lawdCd -notmatch '^\d{5}$') { throw "RTMS_CONFIG_INVALID: lawd_cd must contain five digits." }
if ($startYm -notmatch '^\d{6}$' -or $endYm -notmatch '^\d{6}$') {
    throw "RTMS_CONFIG_INVALID: start_ym and end_ym must use yyyyMM."
}

if ([string]::IsNullOrWhiteSpace($sourceId)) {
    foreach ($property in $registry.sources.PSObject.Properties) {
        foreach ($support in @($property.Value.supports)) {
            if ([string]$support.property_type -eq $propertyType -and [string]$support.trade_type -eq $tradeType) {
                $sourceId = $property.Name
                break
            }
        }
        if ($sourceId) { break }
    }
}

$sourceProperty = $registry.sources.PSObject.Properties[$sourceId]
if ($null -eq $sourceProperty -or [string]$sourceProperty.Value.provider -ne "MOLIT_RTMS") {
    throw "RTMS_ROUTE_UNAVAILABLE: no registered official RTMS route for $propertyType/$tradeType."
}
$source = $sourceProperty.Value
$endpoint = ([string]$source.host).TrimEnd('/') + [string]$source.path
if ($endpoint -notmatch '^https://apis\.data\.go\.kr/1613000/RTMSDataSvc[A-Za-z]+/getRTMSDataSvc[A-Za-z]+$') {
    throw "RTMS_REGISTRY_INVALID: endpoint is outside the allowlist."
}

$months = Get-MonthSequence -StartYm $startYm -EndYm $endYm
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path (Split-Path -Parent $resolvedConfig) "molit"
}
$targetName = [string](Get-ConfigValue $config @("target_name_contains", "apartment_name_contains", "target.name", "target.subject_name", "target.complex_name"))
$lotContains = [string](Get-ConfigValue $config @("lot_number_contains", "target.lot_number_hint"))
$areaMinRaw = Get-ConfigValue $config @("exclusive_area_min_sqm", "scope.requested_area_min_sqm")
$areaMaxRaw = Get-ConfigValue $config @("exclusive_area_max_sqm", "scope.requested_area_max_sqm")
$areaMin = if ($null -ne $areaMinRaw) { [decimal]$areaMinRaw } else { $null }
$areaMax = if ($null -ne $areaMaxRaw) { [decimal]$areaMaxRaw } else { $null }
if ($null -ne $areaMin -and $null -ne $areaMax -and $areaMin -gt $areaMax) {
    throw "RTMS_CONFIG_INVALID: exclusive_area_min_sqm cannot exceed exclusive_area_max_sqm."
}

if ($DryRun) {
    [pscustomobject][ordered]@{
        mode = "DRY_RUN"
        source_id = $sourceId
        dataset_id = [string]$source.dataset_id
        endpoint = $endpoint
        property_type = $propertyType
        trade_type = $tradeType
        lawd_cd = $lawdCd
        months = $months
        target_name_contains = $targetName
        lot_number_contains = $lotContains
        area_min_sqm = $areaMin
        area_max_sqm = $areaMax
        output_root = [System.IO.Path]::GetFullPath($OutputRoot)
        service_key = "REDACTED"
    } | ConvertTo-Json -Depth 6
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ServiceKey)) {
    $ServiceKey = Get-ProviderSecret -Provider DATA_GO_KR -CredentialPath $CredentialPath
}
if ([string]::IsNullOrWhiteSpace($ServiceKey)) {
    $fixedPath = Get-ProviderSecretPath -Provider DATA_GO_KR -CredentialPath $CredentialPath
    throw "DATA_GO_KR_SERVICE_KEY_REQUIRED: save the key to $fixedPath and retry."
}
$appearsPercentEncoded = $ServiceKey -match '%[0-9A-Fa-f]{2}'
$escapedServiceKey = if ($ServiceKeyIsEncoded -or $appearsPercentEncoded) { $ServiceKey } else { [uri]::EscapeDataString($ServiceKey) }

$rawDir = Join-Path $OutputRoot "raw"
$normalizedDir = Join-Path $OutputRoot "normalized"
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null
New-Item -ItemType Directory -Force -Path $normalizedDir | Out-Null
$retrievedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
$allRaw = [System.Collections.Generic.List[object]]::new()
$allNormalized = [System.Collections.Generic.List[object]]::new()
$requests = [System.Collections.Generic.List[object]]::new()
$safePrefix = $sourceId.ToLowerInvariant()

foreach ($month in $months) {
    $pageNo = 1
    $pageSize = 1000
    $monthCollected = 0
    $totalCount = $null
    do {
        $query = "serviceKey=$escapedServiceKey&LAWD_CD=$lawdCd&DEAL_YMD=$month&pageNo=$pageNo&numOfRows=$pageSize"
        $requestUrl = "$endpoint`?$query"
        $safeUrl = "$endpoint`?serviceKey=REDACTED&LAWD_CD=$lawdCd&DEAL_YMD=$month&pageNo=$pageNo&numOfRows=$pageSize"
        $response = Invoke-RtmsRequest -Uri $requestUrl
        $rawFileName = "${safePrefix}_${lawdCd}_${month}_p${pageNo}.xml"
        $rawFilePath = Join-Path $rawDir $rawFileName
        [System.IO.File]::WriteAllText($rawFilePath, $response.Content, [System.Text.UTF8Encoding]::new($false))

        [xml]$xml = $response.Content
        $resultCode = [string]($xml.SelectSingleNode("//resultCode").InnerText)
        $resultMessage = [string]($xml.SelectSingleNode("//resultMsg").InnerText)
        if ($resultCode -notin @("00", "000", "0", "")) {
            throw "MOLIT_API_ERROR: code=$resultCode message=$resultMessage month=$month page=$pageNo"
        }
        $totalNode = $xml.SelectSingleNode("//totalCount")
        if ($totalNode) { $totalCount = [int]$totalNode.InnerText }
        $pageCount = 0
        foreach ($node in @($xml.SelectNodes("//item"))) {
            $rawRecord = Convert-ItemNodeToObject -ItemNode $node
            $allRaw.Add($rawRecord)
            $allNormalized.Add((New-NormalizedRecord -RawRecord $rawRecord -SourceId $sourceId -PropertyType $propertyType -RequestedTradeType $tradeType -LawdCd $lawdCd -DealYm $month -RawFile $rawFileName -RetrievedAt $retrievedAt))
            $pageCount++
        }
        $monthCollected += $pageCount
        $requests.Add([pscustomobject][ordered]@{
            month = $month
            page = $pageNo
            returned_rows = $pageCount
            total_count = $totalCount
            request_url_redacted = $safeUrl
            raw_file = $rawFileName
            raw_sha256 = (Get-FileHash -LiteralPath $rawFilePath -Algorithm SHA256).Hash.ToLowerInvariant()
            result_code = $resultCode
            result_message = $resultMessage
        })
        $pageNo++
    } while ($null -ne $totalCount -and $monthCollected -lt $totalCount)
}

$targetRows = @($allNormalized | Where-Object {
    $row = $_
    $matchesTrade = $row.trade_type -eq $tradeType
    $matchesName = [string]::IsNullOrWhiteSpace($targetName) -or [string]::IsNullOrWhiteSpace([string]$row.property_name) -or $row.property_name -like "*$targetName*"
    $matchesLot = [string]::IsNullOrWhiteSpace($lotContains) -or $row.lot_number -like "*$lotContains*"
    $matchesMin = $null -eq $areaMin -or ($null -ne $row.exclusive_area_sqm -and [decimal]$row.exclusive_area_sqm -ge $areaMin)
    $matchesMax = $null -eq $areaMax -or ($null -ne $row.exclusive_area_sqm -and [decimal]$row.exclusive_area_sqm -le $areaMax)
    $matchesTrade -and $matchesName -and $matchesLot -and $matchesMin -and $matchesMax
})

$allJsonPath = Join-Path $normalizedDir "rtms_all_region_rows.json"
$targetJsonPath = Join-Path $normalizedDir "rtms_target_rows.json"
$rawJsonPath = Join-Path $rawDir "raw_records.json"
$allCsvPath = Join-Path $normalizedDir "rtms_all_region_rows.csv"
$targetCsvPath = Join-Path $normalizedDir "rtms_target_rows.csv"
$manifestPath = Join-Path $OutputRoot "collection_manifest.json"

[System.IO.File]::WriteAllText($rawJsonPath, (ConvertTo-Json -InputObject @($allRaw) -Depth 8), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($allJsonPath, (ConvertTo-Json -InputObject @($allNormalized) -Depth 8), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($targetJsonPath, (ConvertTo-Json -InputObject @($targetRows) -Depth 8), [System.Text.UTF8Encoding]::new($false))
if ($allNormalized.Count -gt 0) { $allNormalized | Export-Csv -LiteralPath $allCsvPath -NoTypeInformation -Encoding UTF8 }
if ($targetRows.Count -gt 0) { $targetRows | Export-Csv -LiteralPath $targetCsvPath -NoTypeInformation -Encoding UTF8 }

$manifest = [pscustomobject][ordered]@{
    schema_version = 1
    adapter_version = "rtms-generic-1"
    source_id = $sourceId
    source_type = "OFFICIAL_PRIMARY"
    dataset_id = [string]$source.dataset_id
    endpoint = $endpoint
    retrieved_at = $retrievedAt
    query = [pscustomobject][ordered]@{
        lawd_cd = $lawdCd
        start_ym = $startYm
        end_ym = $endYm
        property_type = $propertyType
        trade_type = $tradeType
        target_name_contains = $targetName
        lot_number_contains = $lotContains
        exclusive_area_min_sqm = $areaMin
        exclusive_area_max_sqm = $areaMax
    }
    row_counts = [pscustomobject][ordered]@{
        all_region_rows = $allNormalized.Count
        requested_trade_type_rows = @($allNormalized | Where-Object { $_.trade_type -eq $tradeType }).Count
        target_rows = $targetRows.Count
        valid_target_rows = @($targetRows | Where-Object { -not $_.cancelled }).Count
        cancelled_target_rows = @($targetRows | Where-Object { $_.cancelled }).Count
    }
    files = [pscustomobject][ordered]@{
        raw_directory = [System.IO.Path]::GetFullPath($rawDir)
        raw_records_json = [System.IO.Path]::GetFullPath($rawJsonPath)
        all_rows_json = [System.IO.Path]::GetFullPath($allJsonPath)
        target_rows_json = [System.IO.Path]::GetFullPath($targetJsonPath)
        all_rows_csv = if (Test-Path $allCsvPath) { [System.IO.Path]::GetFullPath($allCsvPath) } else { $null }
        target_rows_csv = if (Test-Path $targetCsvPath) { [System.IO.Path]::GetFullPath($targetCsvPath) } else { $null }
    }
    requests = @($requests)
    service_key_logged = $false
    quality_status = "COMPLETE"
}
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))
$ServiceKey = $null

[pscustomobject][ordered]@{
    status = "COMPLETED"
    source_id = $sourceId
    all_region_rows = $allNormalized.Count
    target_rows = $targetRows.Count
    valid_target_rows = @($targetRows | Where-Object { -not $_.cancelled }).Count
    output_root = [System.IO.Path]::GetFullPath($OutputRoot)
    manifest = [System.IO.Path]::GetFullPath($manifestPath)
} | ConvertTo-Json -Depth 5
