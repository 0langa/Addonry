[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExtensionPath,
    [string]$ScenarioPath,
    [string]$ReportPath,
    [string]$FirefoxPath,
    [switch]$Headed,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = 'Stop'
$webExtVersion = '10.6.0'
$seleniumVersion = '4.47.0'
$script:AddonryDevstorageRoot = $null

function Get-AddonryRuntimeRoot {
    if ($env:ADDONRY_RUNTIME_ROOT) {
        return [System.IO.Path]::GetFullPath($env:ADDONRY_RUNTIME_ROOT)
    }
    $candidates = foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
        if (-not $drive.IsReady) { continue }
        $devstorage = Join-Path $drive.RootDirectory.FullName 'agent-devstorage'
        $identityPath = Join-Path $devstorage 'DRIVE-IDENTITY.json'
        $contractPath = Join-Path $devstorage 'README.md'
        if (-not (Test-Path -LiteralPath $identityPath) -or -not (Test-Path -LiteralPath $contractPath)) { continue }
        try {
            $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
            [void](Get-Content -LiteralPath $contractPath -Raw)
            $priority = switch ($identity.role) {
                'fast-primary' { 0 }
                'bulk-secondary' { 1 }
                default { 2 }
            }
            [pscustomobject]@{ Root = $devstorage; Priority = $priority }
        } catch {
            continue
        }
    }
    $selected = $candidates | Sort-Object Priority | Select-Object -First 1
    if ($selected) {
        $script:AddonryDevstorageRoot = $selected.Root
        return Join-Path $selected.Root 'shared-cache\Addonry\cache\runtime'
    }
    return Join-Path $env:LOCALAPPDATA 'Addonry\runtime'
}

function Write-AddonryRoutingLog([string]$Destination, [string]$Reason) {
    if (-not $script:AddonryDevstorageRoot) { return }
    $janitor = Join-Path $script:AddonryDevstorageRoot '_janitor'
    New-Item -ItemType Directory -Force -Path $janitor | Out-Null
    $provider = if ($env:CLAUDE_PLUGIN_ROOT) { 'claude' } elseif ($env:KIMI_PLUGIN_ROOT) { 'kimi' } else { 'codex' }
    $line = "{0} {1} Addonry {2} {3}" -f [DateTimeOffset]::Now.ToString('o'), $provider, $Destination, $Reason
    Add-Content -LiteralPath (Join-Path $janitor 'routing.log') -Value $line
}

$extension = [System.IO.Path]::GetFullPath($ExtensionPath)
if (-not (Test-Path -LiteralPath (Join-Path $extension 'manifest.json'))) {
    throw "manifest.json not found in $extension"
}
$scenario = if ($ScenarioPath) {
    [System.IO.Path]::GetFullPath($ScenarioPath)
} else {
    Join-Path $extension 'tests\firefox_e2e.py'
}
if (-not (Test-Path -LiteralPath $scenario)) {
    throw "Firefox scenario not found: $scenario"
}
$report = if ($ReportPath) {
    [System.IO.Path]::GetFullPath($ReportPath)
} else {
    Join-Path $extension '.addonry\firefox-verification.json'
}
$firefox = if ($FirefoxPath) {
    [System.IO.Path]::GetFullPath($FirefoxPath)
} else {
    @(
        "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
        "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe",
        "$env:LOCALAPPDATA\Mozilla Firefox\firefox.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $firefox -or -not (Test-Path -LiteralPath $firefox)) {
    throw 'Mozilla Firefox executable was not found.'
}

$runtimeRoot = Get-AddonryRuntimeRoot
$packageRoot = Join-Path $runtimeRoot "web-ext-$webExtVersion"
$packageJson = Join-Path $packageRoot 'node_modules\web-ext\package.json'
$npmCache = Join-Path $runtimeRoot 'npm-cache'
$uvCache = Join-Path $runtimeRoot 'uv-cache'
$seleniumCache = Join-Path $runtimeRoot 'selenium-cache'
$artifactsRoot = Join-Path $runtimeRoot 'firefox-runs'
foreach ($path in @($runtimeRoot, $packageRoot, $npmCache, $uvCache, $seleniumCache, $artifactsRoot)) {
    if (Test-Path -LiteralPath (Join-Path $path 'KEEP')) { throw "KEEP blocks Firefox runtime path: $path" }
}
New-Item -ItemType Directory -Force -Path $runtimeRoot, $npmCache, $uvCache, $seleniumCache, $artifactsRoot | Out-Null

$webExtEntry = $null
if (Test-Path -LiteralPath $packageJson) {
    try {
        $package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
        $bin = if ($package.bin -is [string]) { $package.bin } else { $package.bin.'web-ext' }
        if ($package.version -eq $webExtVersion -and $bin) {
            $webExtEntry = Join-Path (Split-Path -Parent $packageJson) $bin
        }
    } catch {
        $webExtEntry = $null
    }
}
if (-not $webExtEntry -or -not (Test-Path -LiteralPath $webExtEntry)) {
    if ($script:AddonryDevstorageRoot) {
        Write-AddonryRoutingLog -Destination $packageRoot -Reason "web-ext-$webExtVersion runtime install"
    } else {
        Write-Warning "external devstorage unavailable; using $runtimeRoot"
    }
    $env:NPM_CONFIG_CACHE = $npmCache
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'npm is required. Install current Node.js LTS and retry.' }
    $installLog = Join-Path $runtimeRoot 'web-ext-install.log'
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $npm.Source install --prefix $packageRoot --no-save --omit=dev --ignore-scripts --no-audit --no-fund "web-ext@$webExtVersion" *> $installLog
    $installExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($installExitCode -ne 0 -or -not (Test-Path -LiteralPath $packageJson)) {
        throw "Failed to install pinned web-ext runtime. Inspect $installLog"
    }
    $package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
    $bin = if ($package.bin -is [string]) { $package.bin } else { $package.bin.'web-ext' }
    $webExtEntry = Join-Path (Split-Path -Parent $packageJson) $bin
}

$lintId = [guid]::NewGuid().ToString('N')
$lintRoot = Join-Path $artifactsRoot "lint-$lintId"
$lintSource = Join-Path $lintRoot 'source'
$lintLog = Join-Path $artifactsRoot "lint-$lintId.log"
New-Item -ItemType Directory -Force -Path $lintRoot | Out-Null
$packageScript = Join-Path $PSScriptRoot 'package_extension.py'
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& python $packageScript $extension --target firefox --output-dir $lintRoot --overwrite --no-record *> (Join-Path $lintRoot 'package.log')
$packageExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($packageExitCode -ne 0) {
    throw "Firefox lint package preparation failed. Inspect $lintRoot"
}
$lintPackage = Get-ChildItem -LiteralPath $lintRoot -Filter '*-firefox.zip' -File | Select-Object -First 1
if (-not $lintPackage) { throw "Firefox lint package not found in $lintRoot" }
Expand-Archive -LiteralPath $lintPackage.FullName -DestinationPath $lintSource
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& node $webExtEntry lint --source-dir $lintSource --warnings-as-errors *> $lintLog
$lintExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($lintExitCode -ne 0) {
    throw "Firefox web-ext lint failed. Inspect $lintLog and $lintSource"
}
[System.IO.Directory]::Delete($lintRoot, $true)

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { throw 'uv is required for isolated Selenium Firefox verification.' }
if ($script:AddonryDevstorageRoot) {
    Write-AddonryRoutingLog -Destination $artifactsRoot -Reason 'real Firefox Selenium verification artifacts'
} else {
    Write-Warning "external devstorage unavailable; using $runtimeRoot"
}
$env:UV_CACHE_DIR = $uvCache
$env:SE_CACHE_PATH = $seleniumCache
$env:SE_AVOID_STATS = 'true'
$pythonScript = Join-Path $PSScriptRoot 'verify_firefox_extension.py'
$arguments = @(
    'run', '--with', "selenium==$seleniumVersion", 'python', $pythonScript,
    '--extension', $extension,
    '--firefox', $firefox,
    '--scenario', $scenario,
    '--report', $report,
    '--artifacts-root', $artifactsRoot
)
if ($Headed) { $arguments += '--headed' }
if ($KeepArtifacts) { $arguments += '--keep-artifacts' }
& $uv.Source @arguments
$exitCode = $LASTEXITCODE
if ($exitCode -eq 0 -and (Test-Path -LiteralPath $lintLog)) {
    [System.IO.File]::Delete($lintLog)
}
exit $exitCode
