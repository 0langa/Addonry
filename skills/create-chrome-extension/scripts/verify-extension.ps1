[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExtensionPath,
    [string]$ScenarioPath,
    [string]$ReportPath,
    [switch]$Headed,
    [switch]$CaptureScreenshot,
    [switch]$KeepProfile
)

$ErrorActionPreference = 'Stop'
$puppeteerVersion = '25.9.0'
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

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $chrome) {
    throw 'Google Chrome executable was not found.'
}

$runtimeRoot = Get-AddonryRuntimeRoot
$packageRoot = Join-Path $runtimeRoot "puppeteer-core-$puppeteerVersion"
$packageJson = Join-Path $packageRoot 'node_modules\puppeteer-core\package.json'
$packageEntryPoint = $null
$npmCache = Join-Path $runtimeRoot 'npm-cache'
$installLog = Join-Path $runtimeRoot 'puppeteer-core-install.log'
$profilesRoot = Join-Path $runtimeRoot 'test-profiles'
New-Item -ItemType Directory -Force -Path $runtimeRoot, $npmCache, $profilesRoot | Out-Null

$installedVersion = $null
if (Test-Path -LiteralPath $packageJson) {
    try {
        $package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
        $installedVersion = $package.version
        if ($package.main) {
            $packageEntryPoint = Join-Path (Split-Path -Parent $packageJson) $package.main
        }
    } catch {
        $installedVersion = $null
        $packageEntryPoint = $null
    }
}
if ($installedVersion -ne $puppeteerVersion -or -not $packageEntryPoint -or -not (Test-Path -LiteralPath $packageEntryPoint)) {
    if ($script:AddonryDevstorageRoot) {
        Write-AddonryRoutingLog -Destination $packageRoot -Reason "puppeteer-core-$puppeteerVersion runtime install"
    }
    else {
        Write-Warning "external devstorage unavailable; using $runtimeRoot"
    }
    $env:NPM_CONFIG_CACHE = $npmCache
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'npm is required. Install current Node.js LTS and retry.' }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $npm.Source install --prefix $packageRoot --no-save --omit=dev --ignore-scripts --no-audit --no-fund "puppeteer-core@$puppeteerVersion" *> $installLog
    $installExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($installExitCode -ne 0 -or -not (Test-Path -LiteralPath $packageJson)) {
        throw "Failed to install pinned Puppeteer Core runtime. Inspect $installLog"
    }
}

$env:NODE_PATH = Join-Path $packageRoot 'node_modules'
$env:ADDONRY_TEST_PROFILES_ROOT = $profilesRoot
$argsList = @(
    (Join-Path $PSScriptRoot 'verify_extension.cjs'),
    '--extension', $extension,
    '--chrome', $chrome
)
if ($ScenarioPath) { $argsList += @('--scenario', [System.IO.Path]::GetFullPath($ScenarioPath)) }
if ($ReportPath) { $argsList += @('--report', [System.IO.Path]::GetFullPath($ReportPath)) }
if ($Headed) { $argsList += '--headed' }
if ($CaptureScreenshot) { $argsList += '--screenshot' }
if ($KeepProfile) { $argsList += '--keep-profile' }

node @argsList
exit $LASTEXITCODE
