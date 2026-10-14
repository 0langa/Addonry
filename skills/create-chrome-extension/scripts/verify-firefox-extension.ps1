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
$webExtVersion = '10.7.0'
# web-ext 10.7.0 pins fx-runner 1.6.0, which pins shell-quote 1.10.0 (GHSA-pqg4-j6r4-53mv, fixed in 1.11.0).
# fx-runner 1.7.0 changes no code besides moving that pin to 1.11.0, so force the same version. Drop this
# once web-ext depends on fx-runner 1.7.0 or later. node-forge (GHSA-86w9-cpqp-85rv, via @devicefarmer/adbkit)
# has no patched release; adbkit only loads for `web-ext run --target=firefox-android`, which this helper never calls.
$webExtOverrides = [ordered]@{ 'shell-quote' = '1.11.0' }
$seleniumVersion = '4.47.0'

function Get-AddonryRuntimeRoot {
    if ($env:ADDONRY_RUNTIME_ROOT) {
        return [System.IO.Path]::GetFullPath($env:ADDONRY_RUNTIME_ROOT)
    }
    # Runtime packages are startup inputs and must remain available without an external drive.
    return Join-Path $env:LOCALAPPDATA 'Addonry\runtime'
}

function Get-WebExtOverrideMismatch {
    param([string]$Root, [System.Collections.IDictionary]$Overrides)
    foreach ($name in $Overrides.Keys) {
        $installed = $null
        $manifest = Join-Path $Root "node_modules\$name\package.json"
        if (Test-Path -LiteralPath $manifest) {
            try { $installed = (Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).version } catch { $installed = $null }
        }
        if ($installed -ne $Overrides[$name]) { "$name $installed, expected $($Overrides[$name])" }
    }
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
$artifactsRoot = Join-Path $runtimeRoot 'firefox-runs'
foreach ($path in @($runtimeRoot, $packageRoot, $artifactsRoot)) {
    if (Test-Path -LiteralPath (Join-Path $path 'KEEP')) { throw "KEEP blocks Firefox runtime path: $path" }
}
New-Item -ItemType Directory -Force -Path $runtimeRoot, $artifactsRoot | Out-Null

$webExtEntry = $null
if (Test-Path -LiteralPath $packageJson) {
    try {
        $package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
        $bin = if ($package.bin -is [string]) { $package.bin } else { $package.bin.'web-ext' }
        if ($package.version -eq $webExtVersion -and $bin -and -not (Get-WebExtOverrideMismatch $packageRoot $webExtOverrides)) {
            $webExtEntry = Join-Path (Split-Path -Parent $packageJson) $bin
        }
    } catch {
        $webExtEntry = $null
    }
}
if (-not $webExtEntry -or -not (Test-Path -LiteralPath $webExtEntry)) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'npm is required. Install current Node.js LTS and retry.' }
    $installLog = Join-Path $runtimeRoot 'web-ext-install.log'
    # npm reads overrides only from the root package.json, so the runtime folder gets its own.
    $runtimeManifest = [ordered]@{
        name = 'addonry-web-ext-runtime'
        private = $true
        dependencies = [ordered]@{ 'web-ext' = $webExtVersion }
        overrides = $webExtOverrides
    }
    New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $packageRoot 'package.json'), ($runtimeManifest | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    # Keep the explicit spec: on Windows, a bare `npm install --prefix <dir>` installs the current directory.
    & $npm.Source install --prefix $packageRoot --no-save --omit=dev --ignore-scripts --no-audit --no-fund "web-ext@$webExtVersion" *> $installLog
    $installExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($installExitCode -ne 0 -or -not (Test-Path -LiteralPath $packageJson)) {
        throw "Failed to install pinned web-ext runtime. Inspect $installLog"
    }
    $overrideMismatch = @(Get-WebExtOverrideMismatch $packageRoot $webExtOverrides)
    if ($overrideMismatch.Count) {
        throw "npm did not apply the web-ext runtime overrides ($($overrideMismatch -join '; ')). Inspect $installLog"
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
