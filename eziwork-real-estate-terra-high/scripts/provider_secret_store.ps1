$script:ProviderUserProfile = [Environment]::GetFolderPath("UserProfile")
$script:ProviderSecretRoot = [System.IO.Path]::Combine($script:ProviderUserProfile, ".codex", "secrets", "eziwork-real-estate-market-brief")
$script:LegacyProviderSecretRoots = @(
    [System.IO.Path]::Combine($script:ProviderUserProfile, ".codex", "secrets", "korea-property-market-report")
)

function Get-ProviderPlatformName {
    param([string]$PlatformOverride = "")
    if (-not [string]::IsNullOrWhiteSpace($PlatformOverride)) {
        $normalized = $PlatformOverride.Trim().ToLowerInvariant()
        if ($normalized -in @("windows", "win32")) { return "Windows" }
        if ($normalized -in @("macos", "mac", "darwin", "osx")) { return "MacOS" }
        if ($normalized -eq "linux") { return "Linux" }
        throw "UNSUPPORTED_PLATFORM_OVERRIDE: $PlatformOverride"
    }
    if ($IsWindows) { return "Windows" }
    if ($IsMacOS) { return "MacOS" }
    if ($IsLinux) { return "Linux" }
    return "Unknown"
}

function Get-ProviderStorageMode {
    param([string]$PlatformOverride = "")
    switch (Get-ProviderPlatformName -PlatformOverride $PlatformOverride) {
        "Windows" { return "WINDOWS_DPAPI_CURRENT_USER" }
        "MacOS" { return "MACOS_KEYCHAIN_CURRENT_USER" }
        default { return "ENVIRONMENT_VARIABLE_ONLY" }
    }
}

function Get-ProviderDefinition {
    param([Parameter(Mandatory = $true)][string]$Provider)
    $normalized = $Provider.Trim().ToUpperInvariant()
    $definitions = @{
        DATA_GO_KR = @{ env = "DATA_GO_KR_SERVICE_KEY"; file = "data-go-kr.dpapi" }
        JUSO = @{ env = "JUSO_CONFM_KEY"; file = "juso.dpapi" }
        VWORLD = @{ env = "VWORLD_API_KEY"; file = "vworld.dpapi" }
        KOSIS = @{ env = "KOSIS_API_KEY"; file = "kosis.dpapi" }
        LICENSED_LISTING = @{ env = "LICENSED_LISTING_API_KEY"; file = "licensed-listing.dpapi" }
    }
    if (-not $definitions.ContainsKey($normalized)) {
        throw "UNSUPPORTED_PROVIDER: $Provider"
    }
    return [pscustomobject]@{
        name = $normalized
        environment_variable = $definitions[$normalized].env
        file_name = $definitions[$normalized].file
        keychain_service = "com.eziwork.real-estate-market-brief.$($normalized.ToLowerInvariant())"
        keychain_account = "$([Environment]::UserName):$normalized"
    }
}

function Get-ProviderSecretPath {
    param(
        [Parameter(Mandatory = $true)][string]$Provider,
        [string]$CredentialPath = ""
    )
    if (-not [string]::IsNullOrWhiteSpace($CredentialPath)) {
        return [System.IO.Path]::GetFullPath($CredentialPath)
    }
    $definition = Get-ProviderDefinition -Provider $Provider
    return Join-Path $script:ProviderSecretRoot $definition.file_name
}

function Get-ProviderSecretHint {
    param([Parameter(Mandatory = $true)][string]$Provider)
    $definition = Get-ProviderDefinition -Provider $Provider
    $platform = Get-ProviderPlatformName
    if ($platform -eq "Windows") {
        return "run save_provider_api_key.ps1 or set $($definition.environment_variable)"
    }
    if ($platform -eq "MacOS") {
        return "run save_provider_api_key.ps1 to use macOS Keychain or set $($definition.environment_variable)"
    }
    return "set $($definition.environment_variable)"
}

function Save-ProviderSecret {
    param(
        [Parameter(Mandatory = $true)][string]$Provider,
        [Parameter(Mandatory = $true)][string]$Secret,
        [string]$CredentialPath = ""
    )
    $definition = Get-ProviderDefinition -Provider $Provider
    $trimmed = $Secret.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        throw "PROVIDER_SECRET_EMPTY: $($definition.name)"
    }
    $platform = Get-ProviderPlatformName
    if ($platform -eq "Windows") {
        $resolvedPath = Get-ProviderSecretPath -Provider $definition.name -CredentialPath $CredentialPath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedPath) | Out-Null
        $secure = ConvertTo-SecureString -String $trimmed -AsPlainText -Force
        $encrypted = ConvertFrom-SecureString -SecureString $secure
        [System.IO.File]::WriteAllText($resolvedPath, $encrypted, [System.Text.UTF8Encoding]::new($false))
        return [pscustomobject][ordered]@{
            status = "SAVED"
            provider = $definition.name
            credential_path = $resolvedPath
            storage = "WINDOWS_DPAPI_CURRENT_USER"
        }
    }
    if ($platform -eq "MacOS") {
        if (-not [string]::IsNullOrWhiteSpace($CredentialPath)) {
            throw "MACOS_CREDENTIAL_FILE_UNSUPPORTED: use Keychain or $($definition.environment_variable)"
        }
        $security = Get-Command security -CommandType Application -ErrorAction SilentlyContinue
        if ($null -eq $security) { throw "MACOS_KEYCHAIN_UNAVAILABLE: /usr/bin/security was not found" }
        & $security.Path add-generic-password -U -a $definition.keychain_account -s $definition.keychain_service -w $trimmed | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "MACOS_KEYCHAIN_SAVE_FAILED: $($definition.name)" }
        return [pscustomobject][ordered]@{
            status = "SAVED"
            provider = $definition.name
            credential_path = "keychain://$($definition.keychain_service)/$($definition.keychain_account)"
            storage = "MACOS_KEYCHAIN_CURRENT_USER"
        }
    }
    throw "SECURE_STORAGE_UNAVAILABLE: set $($definition.environment_variable) instead"
}

function Get-ProviderSecret {
    param(
        [Parameter(Mandatory = $true)][string]$Provider,
        [string]$CredentialPath = ""
    )
    $definition = Get-ProviderDefinition -Provider $Provider
    $environmentValue = [Environment]::GetEnvironmentVariable($definition.environment_variable)
    if (-not [string]::IsNullOrWhiteSpace($environmentValue)) {
        return $environmentValue.Trim()
    }
    $platform = Get-ProviderPlatformName
    if ($platform -eq "MacOS") {
        if (-not [string]::IsNullOrWhiteSpace($CredentialPath)) {
            throw "MACOS_CREDENTIAL_FILE_UNSUPPORTED: use Keychain or $($definition.environment_variable)"
        }
        $security = Get-Command security -CommandType Application -ErrorAction SilentlyContinue
        if ($null -eq $security) { return $null }
        $value = & $security.Path find-generic-password -a $definition.keychain_account -s $definition.keychain_service -w 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return (($value | Out-String).Trim())
    }
    if ($platform -ne "Windows") { return $null }

    $resolvedPath = Get-ProviderSecretPath -Provider $definition.name -CredentialPath $CredentialPath
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf) -and $definition.name -eq "DATA_GO_KR" -and [string]::IsNullOrWhiteSpace($CredentialPath)) {
        foreach ($legacyRoot in $script:LegacyProviderSecretRoots) {
            foreach ($legacyName in @("data-go-kr.dpapi", "molit-api-key.dpapi")) {
                $legacy = Join-Path $legacyRoot $legacyName
                if (Test-Path -LiteralPath $legacy -PathType Leaf) {
                    $resolvedPath = $legacy
                    break
                }
            }
            if (Test-Path -LiteralPath $resolvedPath -PathType Leaf) { break }
        }
    }
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) { return $null }

    $encrypted = (Get-Content -LiteralPath $resolvedPath -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($encrypted)) { return $null }
    $secure = ConvertTo-SecureString -String $encrypted
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Test-ProviderSecretAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$Provider,
        [string]$CredentialPath = ""
    )
    try {
        $value = Get-ProviderSecret -Provider $Provider -CredentialPath $CredentialPath
        return -not [string]::IsNullOrWhiteSpace($value)
    } catch {
        return $false
    }
}
