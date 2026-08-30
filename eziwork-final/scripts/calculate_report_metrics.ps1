param(
    [Parameter(Mandatory = $true)]
    [string]$MolitRowsPath,

    [Parameter(Mandatory = $true)]
    [string]$NaverSnapshotPath,

    [Parameter(Mandatory = $true)]
    [string]$ReportDate,

    [Parameter(Mandatory = $true)]
    [string]$FinalCompleteMonth,

    [Parameter(Mandatory = $true)]
    [string]$ReportId,

    [Parameter(Mandatory = $false)]
    [ValidateSet(1, 3, 5, 7)]
    [int]$HistoryYears = 1,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Get-ObjectValue {
    param(
        [object]$Object,
        [string[]]$Names
    )

    if ($null -eq $Object) { return $null }
    foreach ($name in $Names) {
        $property = $Object.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value -and [string]$property.Value -ne "") {
            return $property.Value
        }
    }
    return $null
}

function Get-Median {
    param([object[]]$Values)

    $sorted = @($Values | Where-Object { $null -ne $_ } | ForEach-Object { [decimal]$_ } | Sort-Object)
    if ($sorted.Count -eq 0) { return $null }
    $middle = [int][math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2 -eq 1) { return [decimal]$sorted[$middle] }
    return [decimal](($sorted[$middle - 1] + $sorted[$middle]) / 2)
}

function Get-PercentChange {
    param(
        [object]$Current,
        [object]$Previous
    )

    if ($null -eq $Current -or $null -eq $Previous -or [decimal]$Previous -eq 0) { return $null }
    return [math]::Round((([decimal]$Current - [decimal]$Previous) / [decimal]$Previous) * 100, 2)
}

function Convert-MolitRow {
    param([object]$Row)

    $dateText = [string](Get-ObjectValue $Row @("contract_date"))
    $contractDate = [datetime]::MinValue
    if (-not [datetime]::TryParse($dateText, [ref]$contractDate)) { return $null }

    $amount = Get-ObjectValue $Row @("deal_amount_krw")
    if ($null -eq $amount) {
        $tenThousand = Get-ObjectValue $Row @("deal_amount_10k_krw", "deal_amount_manwon")
        if ($null -ne $tenThousand) { $amount = [int64]$tenThousand * 10000 }
    }
    if ($null -eq $amount -or [int64]$amount -le 0) { return $null }

    $marker = [string](Get-ObjectValue $Row @("cancellation_marker", "cancellation_yn"))
    $cancelDate = [string](Get-ObjectValue $Row @("cancellation_date"))
    $normalMarkers = @("", "N", "0", "FALSE", "False", "false")
    $isCancelled = (-not [string]::IsNullOrWhiteSpace($cancelDate)) -or ($marker -notin $normalMarkers)

    return [pscustomobject][ordered]@{
        contract_date = $contractDate.Date
        contract_date_text = $contractDate.ToString("yyyy-MM-dd")
        deal_amount_krw = [int64]$amount
        exclusive_area_sqm = Get-ObjectValue $Row @("exclusive_area_sqm", "exclusive_area_m2")
        floor = Get-ObjectValue $Row @("floor")
        apartment_dong = Get-ObjectValue $Row @("apartment_dong", "building")
        transaction_method = Get-ObjectValue $Row @("transaction_method", "deal_type")
        registration_date = Get-ObjectValue $Row @("registration_date")
        raw_source_file = Get-ObjectValue $Row @("raw_source_file")
        is_cancelled = $isCancelled
        cancellation_date = if ([string]::IsNullOrWhiteSpace($cancelDate)) { $null } else { $cancelDate }
    }
}

function Get-PeriodStats {
    param(
        [object[]]$Rows,
        [datetime]$StartMonth,
        [int]$MonthCount
    )

    $endExclusive = $StartMonth.AddMonths($MonthCount)
    $periodRows = @($Rows | Where-Object {
        $_.contract_date -ge $StartMonth -and $_.contract_date -lt $endExclusive
    })
    $prices = @($periodRows | ForEach-Object { $_.deal_amount_krw })

    return [pscustomobject][ordered]@{
        start_month = $StartMonth.ToString("yyyy-MM")
        end_month = $endExclusive.AddMonths(-1).ToString("yyyy-MM")
        month_count = $MonthCount
        trade_count = $periodRows.Count
        monthly_average_trade_count = [math]::Round($periodRows.Count / [decimal]$MonthCount, 4)
        median_deal_amount_krw = Get-Median $prices
    }
}

$reportDateValue = [datetime]::MinValue
if (-not [datetime]::TryParseExact($ReportDate, "yyyy-MM-dd", $null, [Globalization.DateTimeStyles]::None, [ref]$reportDateValue)) {
    throw "ReportDate must use yyyy-MM-dd."
}

$finalMonthDate = [datetime]::MinValue
if (-not [datetime]::TryParseExact($FinalCompleteMonth, "yyyy-MM", $null, [Globalization.DateTimeStyles]::None, [ref]$finalMonthDate)) {
    throw "FinalCompleteMonth must use yyyy-MM."
}
if ($finalMonthDate -ge [datetime]::new($reportDateValue.Year, $reportDateValue.Month, 1)) {
    throw "FinalCompleteMonth must be earlier than the report month."
}

$molitRaw = Get-Content -LiteralPath (Resolve-Path -LiteralPath $MolitRowsPath).Path -Raw -Encoding UTF8 | ConvertFrom-Json
$naverRaw = Get-Content -LiteralPath (Resolve-Path -LiteralPath $NaverSnapshotPath).Path -Raw -Encoding UTF8 | ConvertFrom-Json
$molitInputRows = if ($null -ne $molitRaw.PSObject.Properties["observations"]) { @($molitRaw.observations) } else { @($molitRaw) }

$normalizedRows = @(
    foreach ($rawRow in $molitInputRows) {
        $normalized = Convert-MolitRow $rawRow
        if ($null -ne $normalized) { $normalized }
    }
)

$analysisStart = $reportDateValue.AddYears(-$HistoryYears).Date
$analysisEndExclusive = $reportDateValue.Date.AddDays(1)
$rowsInPeriod = @($normalizedRows | Where-Object {
    $_.contract_date -ge $analysisStart -and $_.contract_date -lt $analysisEndExclusive
})
$validRowsInPeriod = @($rowsInPeriod | Where-Object { -not $_.is_cancelled } | Sort-Object contract_date)
$cancelledRowsInPeriod = @($rowsInPeriod | Where-Object { $_.is_cancelled })
$pricesInPeriod = @($validRowsInPeriod | ForEach-Object { $_.deal_amount_krw })
$latest = $validRowsInPeriod | Sort-Object contract_date -Descending | Select-Object -First 1

$oneYearStart = $reportDateValue.AddYears(-1).Date
$rowsInOneYear = @($normalizedRows | Where-Object {
    $_.contract_date -ge $oneYearStart -and $_.contract_date -lt $analysisEndExclusive
})
$validRowsInOneYear = @($rowsInOneYear | Where-Object { -not $_.is_cancelled } | Sort-Object contract_date)
$cancelledRowsInOneYear = @($rowsInOneYear | Where-Object { $_.is_cancelled })
$pricesInOneYear = @($validRowsInOneYear | ForEach-Object { $_.deal_amount_krw })

$recent12Start = $finalMonthDate.AddMonths(-11)
$selectedCompleteMonthCount = $HistoryYears * 12
$selectedCompleteStart = $finalMonthDate.AddMonths(-($selectedCompleteMonthCount - 1))
$recent3Start = $finalMonthDate.AddMonths(-2)
$previous3Start = $finalMonthDate.AddMonths(-5)
$validCompleteRows = @($normalizedRows | Where-Object {
    -not $_.is_cancelled -and $_.contract_date -ge $selectedCompleteStart -and $_.contract_date -lt $finalMonthDate.AddMonths(1)
})

$recent3 = Get-PeriodStats $validCompleteRows $recent3Start 3
$previous3 = Get-PeriodStats $validCompleteRows $previous3Start 3
$recent12 = Get-PeriodStats $validCompleteRows $recent12Start 12

$monthly = [System.Collections.Generic.List[object]]::new()
$previousMedian = $null
for ($i = 0; $i -lt $selectedCompleteMonthCount; $i++) {
    $monthStart = $selectedCompleteStart.AddMonths($i)
    $monthEnd = $monthStart.AddMonths(1)
    $monthRows = @($validCompleteRows | Where-Object {
        $_.contract_date -ge $monthStart -and $_.contract_date -lt $monthEnd
    })
    $monthPrices = @($monthRows | ForEach-Object { $_.deal_amount_krw })
    $monthMedian = Get-Median $monthPrices
    $change = if ($null -ne $monthMedian -and $null -ne $previousMedian) { [int64]($monthMedian - $previousMedian) } else { $null }
    $changePct = Get-PercentChange $monthMedian $previousMedian

    $monthly.Add([pscustomobject][ordered]@{
        contract_month = $monthStart.ToString("yyyy-MM")
        trade_count = $monthRows.Count
        min_deal_amount_krw = if ($monthRows.Count -gt 0) { [int64]($monthPrices | Measure-Object -Minimum).Minimum } else { $null }
        median_deal_amount_krw = $monthMedian
        max_deal_amount_krw = if ($monthRows.Count -gt 0) { [int64]($monthPrices | Measure-Object -Maximum).Maximum } else { $null }
        average_deal_amount_krw = if ($monthRows.Count -gt 0) { [int64][math]::Round(($monthPrices | Measure-Object -Average).Average) } else { $null }
        previous_month_median_change_krw = $change
        previous_month_median_change_pct = $changePct
        aggregation_status = if ($monthRows.Count -gt 0) { "확정" } else { "거래없음" }
    })
    $previousMedian = $monthMedian
}

$naverSnapshot = if ($null -ne $naverRaw.PSObject.Properties["market_snapshot"]) { $naverRaw.market_snapshot } else { $naverRaw }
$listingGroups = @($naverRaw.listing_groups)
$groupPrices = @(
    foreach ($group in $listingGroups) {
        $value = Get-ObjectValue $group @("representative_asking_price_krw", "representative_price_krw")
        if ($null -ne $value -and [int64]$value -gt 0) { [int64]$value }
    }
)

$askMin = Get-ObjectValue $naverSnapshot @("min_asking_price_krw")
$askMedian = Get-ObjectValue $naverSnapshot @("median_asking_price_krw")
$askMax = Get-ObjectValue $naverSnapshot @("max_asking_price_krw")
if ($groupPrices.Count -gt 0) {
    if ($null -eq $askMin) { $askMin = [int64]($groupPrices | Measure-Object -Minimum).Minimum }
    if ($null -eq $askMedian) { $askMedian = Get-Median $groupPrices }
    if ($null -eq $askMax) { $askMax = [int64]($groupPrices | Measure-Object -Maximum).Maximum }
}

$rawAdCount = Get-ObjectValue $naverSnapshot @("raw_ad_count", "target_raw_ad_count")
if ($null -eq $rawAdCount -and $listingGroups.Count -gt 0) {
    $rawAdCount = ($listingGroups | ForEach-Object {
        $count = Get-ObjectValue $_ @("ad_count", "raw_ad_count")
        if ($null -eq $count) { 1 } else { [int]$count }
    } | Measure-Object -Sum).Sum
}
$deduplicatedCount = Get-ObjectValue $naverSnapshot @("deduplicated_listing_count")
if ($null -eq $deduplicatedCount -and $listingGroups.Count -gt 0) { $deduplicatedCount = $listingGroups.Count }

$latestAmount = if ($null -eq $latest) { $null } else { [int64]$latest.deal_amount_krw }
$latestDate = if ($null -eq $latest) { $null } else { $latest.contract_date_text }
$latestAgeDays = if ($null -eq $latest) { $null } else { ($reportDateValue.Date - $latest.contract_date).Days }
$latestGap = if ($null -ne $latestAmount -and $null -ne $askMin) { [int64]$askMin - $latestAmount } else { $null }
$latestGapPct = Get-PercentChange $askMin $latestAmount
$marketGap = if ($null -ne $recent3.median_deal_amount_krw -and $null -ne $askMedian) { [int64]$askMedian - [int64]$recent3.median_deal_amount_krw } else { $null }
$marketGapPct = Get-PercentChange $askMedian $recent3.median_deal_amount_krw
$burdenRatio = if ($null -ne $deduplicatedCount -and [decimal]$recent3.monthly_average_trade_count -gt 0) {
    [math]::Round([decimal]$deduplicatedCount / [decimal]$recent3.monthly_average_trade_count, 2)
} else { $null }

$priceChangePct = Get-PercentChange $recent3.median_deal_amount_krw $previous3.median_deal_amount_krw
$volumeChangeVsPrevious3 = Get-PercentChange $recent3.monthly_average_trade_count $previous3.monthly_average_trade_count
$volumeChangeVsRecent12 = Get-PercentChange $recent3.monthly_average_trade_count $recent12.monthly_average_trade_count

$priceDirection = if ($null -eq $priceChangePct) { "판단 유보" } elseif ($priceChangePct -gt 3) { "상승" } elseif ($priceChangePct -lt -3) { "하락" } else { "보합" }
$activityVsPrevious3 = if ($null -eq $volumeChangeVsPrevious3) { "판단 유보" } elseif ($recent3.trade_count -eq 0) { "거래 없음" } elseif ($volumeChangeVsPrevious3 -ge 20) { "활발" } elseif ($volumeChangeVsPrevious3 -le -20) { "둔화" } else { "보통" }
$activityVsRecent12 = if ($null -eq $volumeChangeVsRecent12) { "판단 유보" } elseif ($recent3.trade_count -eq 0) { "거래 없음" } elseif ($volumeChangeVsRecent12 -ge 20) { "활발" } elseif ($volumeChangeVsRecent12 -le -20) { "둔화" } else { "보통" }
$freshness = if ($null -eq $latestAgeDays) { "거래 없음" } elseif ($latestAgeDays -le 90) { "최근" } elseif ($latestAgeDays -le 180) { "주의" } else { "오래됨" }
$sampleStatus = if ($recent3.trade_count -ge 3) { "충분" } elseif ($recent3.trade_count -gt 0) { "주의" } else { "부족" }

$currentMonthStart = [datetime]::new($reportDateValue.Year, $reportDateValue.Month, 1)
$currentMonthTradeCount = @($validRowsInPeriod | Where-Object { $_.contract_date -ge $currentMonthStart }).Count
$dataStatus = if ($recent3.trade_count -lt 3) { "표본부족" } elseif ($currentMonthTradeCount -gt 0) { "잠정" } else { "확정" }

$qualityFlags = [System.Collections.Generic.List[string]]::new()
if ($recent3.trade_count -lt 3) { $qualityFlags.Add("최근 3개월 유효 거래가 3건 미만입니다.") }
if ($currentMonthTradeCount -gt 0) { $qualityFlags.Add("보고서 현재월 거래는 잠정치입니다.") }
$qualityStatus = [string](Get-ObjectValue $naverSnapshot @("quality_status"))
if ($qualityStatus -in @("SAMPLE_ONLY", "PARTIAL", "FAILED")) { $qualityFlags.Add("네이버 수집 품질상태: $qualityStatus") }
if ($null -eq $burdenRatio) { $qualityFlags.Add("최근 3개월 월평균 거래량이 0이거나 없어 매물 부담 지표를 산정하지 않았습니다.") }
if ($null -eq $marketGapPct) { $qualityFlags.Add("최근 3개월 실거래 중앙값이 없어 공식 호가 격차율을 산정하지 않았습니다.") }

$recentTransactions = [System.Collections.Generic.List[object]]::new()
$rank = 1
foreach ($row in @($validRowsInPeriod | Sort-Object contract_date -Descending | Select-Object -First 10)) {
    $recentTransactions.Add([pscustomobject][ordered]@{
        rank = $rank
        contract_date = $row.contract_date_text
        deal_amount_krw = $row.deal_amount_krw
        exclusive_area_sqm = $row.exclusive_area_sqm
        floor = $row.floor
        apartment_dong = $row.apartment_dong
        transaction_method = $row.transaction_method
        registration_date = $row.registration_date
        data_status = if ($row.contract_date -ge $currentMonthStart) { "잠정" } else { "유효" }
        raw_source_file = $row.raw_source_file
    })
    $rank++
}

$chartMode = if ($HistoryYears -eq 1) { "INDIVIDUAL_TRANSACTIONS" } else { "MONTHLY_MEDIAN" }
$chartPoints = [System.Collections.Generic.List[object]]::new()
if ($chartMode -eq "INDIVIDUAL_TRANSACTIONS") {
    foreach ($row in $validRowsInPeriod) {
        $chartPoints.Add([pscustomobject][ordered]@{
            date = $row.contract_date_text
            label = $row.contract_date_text
            price_krw = $row.deal_amount_krw
            trade_count = 1
        })
    }
} else {
    foreach ($row in @($monthly | Where-Object { $null -ne $_.median_deal_amount_krw })) {
        $chartPoints.Add([pscustomobject][ordered]@{
            date = "$($row.contract_month)-01"
            label = $row.contract_month
            price_krw = $row.median_deal_amount_krw
            trade_count = $row.trade_count
        })
    }
}

$result = [pscustomobject][ordered]@{
    report_id = $ReportId
    generated_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    calculation_policy = [ordered]@{
        history_years = $HistoryYears
        allowed_history_years = @(1, 3, 5, 7)
        analysis_start_date = $analysisStart.ToString("yyyy-MM-dd")
        analysis_end_date = $reportDateValue.ToString("yyyy-MM-dd")
        final_complete_month = $finalMonthDate.ToString("yyyy-MM")
        selected_complete_month_count = $selectedCompleteMonthCount
        current_month_is_provisional = $true
        cancelled_transactions_excluded = $true
        naver_prices_use_group_representatives = $true
        naver_listing_scope = "CURRENT_SNAPSHOT"
    }
    price_summary = [ordered]@{
        latest_contract_date = $latestDate
        latest_deal_amount_krw = $latestAmount
        history_years = $HistoryYears
        trade_count_period = $validRowsInPeriod.Count
        min_deal_amount_period_krw = if ($pricesInPeriod.Count -gt 0) { [int64]($pricesInPeriod | Measure-Object -Minimum).Minimum } else { $null }
        median_deal_amount_period_krw = Get-Median $pricesInPeriod
        max_deal_amount_period_krw = if ($pricesInPeriod.Count -gt 0) { [int64]($pricesInPeriod | Measure-Object -Maximum).Maximum } else { $null }
        average_deal_amount_period_krw = if ($pricesInPeriod.Count -gt 0) { [int64][math]::Round(($pricesInPeriod | Measure-Object -Average).Average) } else { $null }
        cancelled_count_period = $cancelledRowsInPeriod.Count
        trade_count_1y = $validRowsInOneYear.Count
        min_deal_amount_1y_krw = if ($pricesInOneYear.Count -gt 0) { [int64]($pricesInOneYear | Measure-Object -Minimum).Minimum } else { $null }
        median_deal_amount_1y_krw = Get-Median $pricesInOneYear
        max_deal_amount_1y_krw = if ($pricesInOneYear.Count -gt 0) { [int64]($pricesInOneYear | Measure-Object -Maximum).Maximum } else { $null }
        average_deal_amount_1y_krw = if ($pricesInOneYear.Count -gt 0) { [int64][math]::Round(($pricesInOneYear | Measure-Object -Average).Average) } else { $null }
        cancelled_count_1y = $cancelledRowsInOneYear.Count
        current_month_trade_count = $currentMonthTradeCount
        data_status = $dataStatus
    }
    monthly_price_trend = $monthly
    recent_transactions = $recentTransactions
    chart_series = [ordered]@{
        mode = $chartMode
        points = $chartPoints
    }
    market_period_comparison = [ordered]@{
        recent_3_months = $recent3
        previous_3_months = $previous3
        recent_12_months = $recent12
        price_change_pct_vs_previous_3m = $priceChangePct
        volume_change_pct_vs_previous_3m = $volumeChangeVsPrevious3
        volume_change_pct_vs_recent_12m = $volumeChangeVsRecent12
    }
    naver_market_snapshot = [ordered]@{
        raw_ad_count = $rawAdCount
        deduplicated_listing_count = $deduplicatedCount
        min_asking_price_krw = $askMin
        median_asking_price_krw = $askMedian
        max_asking_price_krw = $askMax
        snapshot_at = Get-ObjectValue $naverSnapshot @("snapshot_at", "snapshot_at_kst")
        quality_status = $qualityStatus
    }
    combined_metrics = [ordered]@{
        latest_trade_to_min_ask_gap_krw = $latestGap
        latest_trade_to_min_ask_gap_pct = $latestGapPct
        recent_3m_median_to_current_ask_median_gap_krw = $marketGap
        recent_3m_median_to_current_ask_median_gap_pct = $marketGapPct
        listing_burden_ratio = $burdenRatio
    }
    market_interpretation = [ordered]@{
        price_direction = $priceDirection
        activity_vs_previous_3m = $activityVsPrevious3
        activity_vs_recent_12m = $activityVsRecent12
        latest_trade_age_days = $latestAgeDays
        latest_trade_freshness = $freshness
        sample_sufficiency = $sampleStatus
    }
    quality_flags = $qualityFlags
}

$outputParent = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outputParent)) {
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$result | ConvertTo-Json -Depth 12
