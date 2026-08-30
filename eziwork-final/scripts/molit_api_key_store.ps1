$scriptPathForHome = [System.IO.Path]::GetFullPath($PSScriptRoot)
$script:IsWindowsPlatform = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
$script:IsMacOSPlatform = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::OSX)
$scriptUserHome = if ($script:IsWindowsPlatform -and $scriptPathForHome -match '^([A-Za-z]:\\Users\\[^\\]+)') {
    $Matches[1]
} else {
    [Environment]::GetFolderPath("UserProfile")
}
$scriptSecretDir = Join-Path (Join-Path (Join-Path $scriptUserHome ".codex") "secrets") "create-korean-real-estate-client-brief"
$script:MolitApiKeyDefaultPath = Join-Path $scriptSecretDir "molit-api-key.dpapi"
$script:MolitKeychainService = "eziwork-final.molit-api-key"
$script:MolitKeychainAccount = [Environment]::UserName

function Get-MolitApiKeyCredentialPath {
    param([string]$CredentialPath = "")

    if (-not [string]::IsNullOrWhiteSpace($CredentialPath)) {
        return $CredentialPath
    }
    return $script:MolitApiKeyDefaultPath
}

function Save-MolitApiKey {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ServiceKey,

        [string]$CredentialPath = ""
    )

    $trimmed = $ServiceKey.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        throw "MOLIT API key cannot be empty."
    }

    if ($script:IsMacOSPlatform) {
        $security = "/usr/bin/security"
        if (-not (Test-Path -LiteralPath $security -PathType Leaf)) {
            throw "macOS security command was not found."
        }
        & $security add-generic-password -U -a $script:MolitKeychainAccount -s $script:MolitKeychainService -w $trimmed 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to save the MOLIT API key to the macOS Keychain."
        }
        return [pscustomobject][ordered]@{
            status = "SAVED"
            credential_path = "macOS Keychain:$($script:MolitKeychainService)/$($script:MolitKeychainAccount)"
            storage = "MACOS_KEYCHAIN_CURRENT_USER"
        }
    }

    if (-not $script:IsWindowsPlatform) {
        throw "Persistent MOLIT API key storage is supported on Windows and macOS only. Use DATA_GO_KR_SERVICE_KEY on this platform."
    }

    $resolvedPath = Get-MolitApiKeyCredentialPath -CredentialPath $CredentialPath
    $parent = Split-Path -Parent $resolvedPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $secure = ConvertTo-SecureString -String $trimmed -AsPlainText -Force
    $encrypted = ConvertFrom-SecureString -SecureString $secure
    [System.IO.File]::WriteAllText($resolvedPath, $encrypted, [System.Text.UTF8Encoding]::new($false))

    return [pscustomobject][ordered]@{
        status = "SAVED"
        credential_path = $resolvedPath
        storage = "WINDOWS_DPAPI_CURRENT_USER"
    }
}

function Get-MolitApiKey {
    param([string]$CredentialPath = "")

    $environmentKey = [Environment]::GetEnvironmentVariable("DATA_GO_KR_SERVICE_KEY")
    if (-not [string]::IsNullOrWhiteSpace($environmentKey)) {
        return $environmentKey.Trim()
    }

    if ($script:IsMacOSPlatform) {
        $security = "/usr/bin/security"
        if (-not (Test-Path -LiteralPath $security -PathType Leaf)) {
            return $null
        }
        $key = (& $security find-generic-password -a $script:MolitKeychainAccount -s $script:MolitKeychainService -w 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$key)) {
            return $null
        }
        return ([string]$key).Trim()
    }

    if (-not $script:IsWindowsPlatform) {
        return $null
    }

    $resolvedPath = Get-MolitApiKeyCredentialPath -CredentialPath $CredentialPath
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        return $null
    }

    $encrypted = (Get-Content -LiteralPath $resolvedPath -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($encrypted)) {
        return $null
    }

    $secure = ConvertTo-SecureString -String $encrypted
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Test-MolitApiKeyAvailable {
    param([string]$CredentialPath = "")

    try {
        $key = Get-MolitApiKey -CredentialPath $CredentialPath
        return -not [string]::IsNullOrWhiteSpace($key)
    } catch {
        return $false
    }
}
