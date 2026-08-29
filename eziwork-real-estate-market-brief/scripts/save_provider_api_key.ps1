param(
    [Parameter(Mandatory = $true)][ValidateSet("DATA_GO_KR", "JUSO", "VWORLD", "KOSIS", "LICENSED_LISTING")][string]$Provider,
    [string]$CredentialPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "provider_secret_store.ps1")

try { [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$secret = [Console]::In.ReadToEnd().Trim()
if ([string]::IsNullOrWhiteSpace($secret)) {
    throw "PROVIDER_SECRET_REQUIRED: 표준 입력으로 인증키를 전달해야 합니다."
}
$result = Save-ProviderSecret -Provider $Provider -Secret $secret -CredentialPath $CredentialPath
$secret = $null
$result | ConvertTo-Json -Depth 4
