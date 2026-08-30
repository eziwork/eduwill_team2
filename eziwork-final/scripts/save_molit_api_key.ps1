param(
    [Parameter(Mandatory = $false)]
    [string]$CredentialPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "molit_api_key_store.ps1")

$serviceKey = [Console]::In.ReadToEnd().Trim()
if ([string]::IsNullOrWhiteSpace($serviceKey)) {
    throw "MOLIT_API_KEY_REQUIRED: 표준 입력으로 인증키를 전달해야 합니다."
}

$result = Save-MolitApiKey -ServiceKey $serviceKey -CredentialPath $CredentialPath
$serviceKey = $null
$result | ConvertTo-Json -Depth 4
