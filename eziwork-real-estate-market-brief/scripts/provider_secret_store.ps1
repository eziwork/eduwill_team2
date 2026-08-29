$script:ProviderSecretRoot = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".codex\secrets\eziwork-real-estate-market-brief"
$script:LegacyProviderSecretRoots = @(
    (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".codex\secrets\korea-property-market-report")
)

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
