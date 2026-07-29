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
$puppeteerVersion = '25.4.0'

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
        return Join-Path $selected.Root 'shared-cache\Addonry\cache\runtime'
    }
    return Join-Path $env:LOCALAPPDATA 'Addonry\runtime'
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
$npmCache = Join-Path $runtimeRoot 'npm-cache'
$installLog = Join-Path $runtimeRoot 'puppeteer-core-install.log'
$profilesRoot = Join-Path $runtimeRoot 'test-profiles'
New-Item -ItemType Directory -Force -Path $runtimeRoot, $npmCache, $profilesRoot | Out-Null

$installedVersion = $null
if (Test-Path -LiteralPath $packageJson) {
    try { $installedVersion = (Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json).version } catch { $installedVersion = $null }
}
if ($installedVersion -ne $puppeteerVersion) {
    $env:NPM_CONFIG_CACHE = $npmCache
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'npm is required. Install current Node.js LTS and retry.' }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $npm.Source install --prefix $packageRoot --no-save --omit=dev --ignore-scripts "puppeteer-core@$puppeteerVersion" *> $installLog
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
