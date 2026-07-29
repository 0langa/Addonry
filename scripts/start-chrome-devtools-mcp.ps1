[CmdletBinding()]
param(
    [ValidateSet('isolated', 'auto-connect', 'browser-url')]
    [string]$Mode = $(if ($env:ADDONRY_CHROME_MODE) { $env:ADDONRY_CHROME_MODE } else { 'isolated' }),
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$packageVersion = '1.6.0'

function Get-AddonryRuntimeRoot {
    if ($env:ADDONRY_RUNTIME_ROOT) {
        return [System.IO.Path]::GetFullPath($env:ADDONRY_RUNTIME_ROOT)
    }

    $bestDrive = [System.IO.DriveInfo]::GetDrives() |
        Where-Object { $_.IsReady -and $_.Name -ne 'C:\' -and $_.AvailableFreeSpace -gt 100GB } |
        Sort-Object AvailableFreeSpace -Descending |
        Select-Object -First 1
    if ($bestDrive) {
        return Join-Path $bestDrive.RootDirectory.FullName 'devtmp\Addonry\runtime'
    }

    foreach ($candidate in @($env:PLUGIN_DATA, $env:CLAUDE_PLUGIN_DATA, $env:KIMI_PLUGIN_DATA)) {
        if ($candidate) {
            return Join-Path ([System.IO.Path]::GetFullPath($candidate)) 'runtime'
        }
    }

    return Join-Path $env:LOCALAPPDATA 'Addonry\runtime'
}

function Write-AddonryError([string]$Message) {
    [Console]::Error.WriteLine("Addonry Chrome DevTools MCP: $Message")
}

$runtimeRoot = Get-AddonryRuntimeRoot
$packageRoot = Join-Path $runtimeRoot "chrome-devtools-mcp-$packageVersion"
$packageJson = Join-Path $packageRoot 'node_modules\chrome-devtools-mcp\package.json'
$entryPoint = Join-Path $packageRoot 'node_modules\chrome-devtools-mcp\build\src\bin\chrome-devtools-mcp.js'
$npmCache = Join-Path $runtimeRoot 'npm-cache'
$installLog = Join-Path $runtimeRoot 'chrome-devtools-mcp-install.log'

New-Item -ItemType Directory -Force -Path $runtimeRoot, $npmCache | Out-Null
$env:NPM_CONFIG_CACHE = $npmCache
$env:CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS = '1'
$env:CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS = '1'

$installedVersion = $null
if (Test-Path -LiteralPath $packageJson) {
    try {
        $installedVersion = (Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json).version
    }
    catch {
        $installedVersion = $null
    }
}

if ($installedVersion -ne $packageVersion -or -not (Test-Path -LiteralPath $entryPoint)) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-AddonryError 'npm is required. Install current Node.js LTS and retry.'
        exit 1
    }

    # Windows PowerShell turns native stderr notices into terminating errors when
    # ErrorActionPreference is Stop. Keep complete npm output in file and judge
    # success only from process exit code plus expected entry point.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $npm.Source install --prefix $packageRoot --no-save --omit=dev --ignore-scripts "chrome-devtools-mcp@$packageVersion" *> $installLog
    $installExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($installExitCode -ne 0 -or -not (Test-Path -LiteralPath $entryPoint)) {
        Write-AddonryError "failed to install pinned runtime; inspect $installLog"
        exit 1
    }
}

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-AddonryError 'node is required. Install current Node.js LTS and retry.'
    exit 1
}

if ($SelfTest) {
    & $node.Source $entryPoint --version
    exit $LASTEXITCODE
}

$serverArgs = @('--no-usage-statistics')
switch ($Mode) {
    'isolated' {
        $serverArgs += '--isolated'
    }
    'auto-connect' {
        $serverArgs += '--autoConnect'
    }
    'browser-url' {
        if (-not $env:ADDONRY_CHROME_BROWSER_URL) {
            Write-AddonryError 'ADDONRY_CHROME_BROWSER_URL is required for browser-url mode.'
            exit 2
        }
        $serverArgs += "--browser-url=$($env:ADDONRY_CHROME_BROWSER_URL)"
    }
}

& $node.Source $entryPoint @serverArgs
exit $LASTEXITCODE
