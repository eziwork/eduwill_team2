function Get-EziworkPlatformName {
    param([string]$PlatformOverride = "")
    if (-not [string]::IsNullOrWhiteSpace($PlatformOverride)) {
        $normalized = $PlatformOverride.Trim().ToLowerInvariant()
        if ($normalized -in @("windows", "win32")) { return "Windows" }
        if ($normalized -in @("macos", "mac", "darwin", "osx")) { return "MacOS" }
        if ($normalized -in @("linux")) { return "Linux" }
        throw "UNSUPPORTED_PLATFORM_OVERRIDE: $PlatformOverride"
    }
    if ($IsWindows) { return "Windows" }
    if ($IsMacOS) { return "MacOS" }
    if ($IsLinux) { return "Linux" }
    return "Unknown"
}

function Join-EziworkPath {
    param([Parameter(Mandatory = $true)][string[]]$Parts)
    if ($Parts.Count -eq 0) { return "" }
    $result = $Parts[0]
    for ($index = 1; $index -lt $Parts.Count; $index++) {
        $result = Join-Path -Path $result -ChildPath $Parts[$index]
    }
    return $result
}

function Get-EziworkCommandNames {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Python", "Node")][string]$Kind,
        [string]$PlatformOverride = ""
    )
    $platform = Get-EziworkPlatformName -PlatformOverride $PlatformOverride
    if ($Kind -eq "Node") { return @("node") }
    if ($platform -eq "Windows") { return @("python", "python3") }
    return @("python3", "python")
}

function Get-EziworkRuntimeRelativeCandidates {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Python", "Node")][string]$Kind,
        [string]$PlatformOverride = ""
    )
    $platform = Get-EziworkPlatformName -PlatformOverride $PlatformOverride
    if ($Kind -eq "Python") {
        if ($platform -eq "Windows") { return @("python/python.exe", "python/bin/python.exe") }
        return @("python/bin/python3", "python/bin/python", "python/python3", "python/python")
    }
    if ($platform -eq "Windows") { return @("node/bin/node.exe", "node/node.exe") }
    return @("node/bin/node", "node/node")
}

function Get-EziworkBundleRoots {
    param([string]$SkillRoot = "")
    $roots = [System.Collections.Generic.List[string]]::new()
    foreach ($variableName in @("CODEX_RUNTIME_DEPENDENCIES", "CODEX_WORKSPACE_DEPENDENCIES")) {
        $configured = [Environment]::GetEnvironmentVariable($variableName)
        if (-not [string]::IsNullOrWhiteSpace($configured)) {
            $roots.Add([System.IO.Path]::GetFullPath($configured))
        }
    }
    $profiles = [System.Collections.Generic.List[string]]::new()
    $userProfile = [Environment]::GetFolderPath("UserProfile")
    if (-not [string]::IsNullOrWhiteSpace($userProfile)) { $profiles.Add($userProfile) }
    if ((Get-EziworkPlatformName) -eq "Windows" -and $SkillRoot -match '^(?<profile>[A-Za-z]:\\Users\\[^\\]+)') {
        $profiles.Add($Matches.profile)
    }
    foreach ($profile in @($profiles | Select-Object -Unique)) {
        $roots.Add((Join-EziworkPath -Parts @($profile, ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies")))
    }
    return @($roots | Select-Object -Unique)
}

function Test-EziworkExecutable {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        & $Path --version *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Resolve-EziworkRuntimePath {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Python", "Node")][string]$Kind,
        [string]$SkillRoot = ""
    )
    foreach ($name in Get-EziworkCommandNames -Kind $Kind) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            $candidate = if (-not [string]::IsNullOrWhiteSpace($command.Path)) { $command.Path } else { $command.Source }
            if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-EziworkExecutable -Path $candidate)) {
                return $candidate
            }
        }
    }
    $relativeCandidates = Get-EziworkRuntimeRelativeCandidates -Kind $Kind
    foreach ($root in Get-EziworkBundleRoots -SkillRoot $SkillRoot) {
        foreach ($relative in $relativeCandidates) {
            $parts = @($root) + @($relative -split '/')
            $candidate = Join-EziworkPath -Parts $parts
            if (Test-EziworkExecutable -Path $candidate) { return $candidate }
        }
    }
    return $null
}

function Resolve-EziworkExecutableInput {
    param([Parameter(Mandatory = $true)][string]$Value)
    if (Test-Path -LiteralPath $Value -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Value).Path
    }
    $command = Get-Command $Value -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $candidate = if (-not [string]::IsNullOrWhiteSpace($command.Path)) { $command.Path } else { $command.Source }
        if (Test-EziworkExecutable -Path $candidate) { return $candidate }
    }
    return $null
}

function Resolve-EziworkNodeModulesPath {
    param([string]$SkillRoot = "")
    $configured = [Environment]::GetEnvironmentVariable("CODEX_NODE_MODULES")
    if (-not [string]::IsNullOrWhiteSpace($configured) -and (Test-Path -LiteralPath $configured -PathType Container)) {
        return [System.IO.Path]::GetFullPath($configured)
    }
    foreach ($root in Get-EziworkBundleRoots -SkillRoot $SkillRoot) {
        foreach ($relative in @("node/node_modules", "node/lib/node_modules")) {
            $candidate = Join-EziworkPath -Parts (@($root) + @($relative -split '/'))
            if (Test-Path -LiteralPath $candidate -PathType Container) { return $candidate }
        }
    }
    return $null
}
