$ErrorActionPreference = "Stop"
$skillRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scripts = Join-Path $skillRoot "scripts"
. (Join-Path $scripts "runtime_discovery.ps1")
. (Join-Path $scripts "provider_secret_store.ps1")

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$windowsPython = @(Get-EziworkRuntimeRelativeCandidates -Kind Python -PlatformOverride Windows)
$macPython = @(Get-EziworkRuntimeRelativeCandidates -Kind Python -PlatformOverride MacOS)
$windowsNode = @(Get-EziworkRuntimeRelativeCandidates -Kind Node -PlatformOverride Windows)
$macNode = @(Get-EziworkRuntimeRelativeCandidates -Kind Node -PlatformOverride MacOS)
$macCommands = @(Get-EziworkCommandNames -Kind Python -PlatformOverride MacOS)

Assert-True ($windowsPython -contains "python/python.exe") "Windows Python candidate is missing"
Assert-True ($windowsNode -contains "node/bin/node.exe") "Windows Node candidate is missing"
Assert-True ($macPython -contains "python/bin/python3") "macOS Python 3 candidate is missing"
Assert-True ($macNode -contains "node/bin/node") "macOS Node candidate is missing"
Assert-True ($macCommands[0] -eq "python3") "macOS must prefer python3"
Assert-True ((Get-ProviderStorageMode -PlatformOverride Windows) -eq "WINDOWS_DPAPI_CURRENT_USER") "Windows storage mode mismatch"
Assert-True ((Get-ProviderStorageMode -PlatformOverride MacOS) -eq "MACOS_KEYCHAIN_CURRENT_USER") "macOS storage mode mismatch"
Assert-True ((Get-ProviderStorageMode -PlatformOverride Linux) -eq "ENVIRONMENT_VARIABLE_ONLY") "Linux storage mode mismatch"

$pythonPath = Resolve-EziworkRuntimePath -Kind Python -SkillRoot $skillRoot
$nodePath = Resolve-EziworkRuntimePath -Kind Node -SkillRoot $skillRoot
Assert-True (-not [string]::IsNullOrWhiteSpace($pythonPath)) "Current-platform Python runtime was not resolved"
Assert-True (-not [string]::IsNullOrWhiteSpace($nodePath)) "Current-platform Node runtime was not resolved"

"PASS: Windows/macOS runtime candidates and credential storage modes"
