[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExtensionPath,

    [string]$ChromePath,

    [string]$ProfileDirectory,

    [ValidateRange(0, 60)]
    [int]$CountdownSeconds = 10,

    [ValidateRange(1, 120)]
    [int]$ExitTimeoutSeconds = 30,

    [switch]$AuthorizedRestart,

    [switch]$LaunchIfClosed,

    [switch]$PlanOnly,

    [switch]$AllowVolatilePath
)

$ErrorActionPreference = 'Stop'

function Resolve-ChromeExecutable {
    param([string]$RequestedPath)

    if ($RequestedPath) {
        $resolved = (Resolve-Path -LiteralPath $RequestedPath).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "Chrome executable not found: $RequestedPath"
        }
        return $resolved
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw 'Google Chrome executable not found in standard Windows locations.'
}

function Get-MatchingChromeProcesses {
    param([string]$ExecutablePath)

    $normalized = [IO.Path]::GetFullPath($ExecutablePath)
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
            Where-Object {
                $_.ExecutablePath -and
                [string]::Equals(
                    [IO.Path]::GetFullPath($_.ExecutablePath),
                    $normalized,
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
}

function Write-Result {
    param(
        [string]$State,
        [bool]$WasRunning,
        [string]$ResolvedExtension,
        [string]$ResolvedChrome,
        [string[]]$LaunchArguments,
        [string]$Detail,
        [string]$ProductName,
        [string]$ProductVersion,
        [string]$Persistence = 'unknown-until-browser-verified'
    )

    [ordered]@{
        state = $State
        detail = $Detail
        extensionPath = $ResolvedExtension
        chromePath = $ResolvedChrome
        chromeWasRunning = $WasRunning
        profileDirectory = if ($ProfileDirectory) { $ProfileDirectory } else { $null }
        browserProduct = $ProductName
        browserVersion = $ProductVersion
        persistence = $Persistence
        sessionRestoreRequested = $LaunchArguments -contains '--restore-last-session'
        launchArguments = $LaunchArguments
        timestamp = [DateTimeOffset]::UtcNow.ToString('o')
    } | ConvertTo-Json -Depth 4
}

$resolvedExtension = (Resolve-Path -LiteralPath $ExtensionPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedExtension 'manifest.json') -PathType Leaf)) {
    throw "Extension directory has no manifest.json: $resolvedExtension"
}

$volatilePatterns = @(
    '\\.codex\\plugins\\cache\\',
    '\\.claude\\plugins\\cache\\',
    '\\AppData\\Local\\Temp\\',
    '\\Temp\\'
)
if (-not $AllowVolatilePath) {
    foreach ($pattern in $volatilePatterns) {
        if ($resolvedExtension -match $pattern) {
            throw "Refusing volatile extension path: $resolvedExtension. Copy extension to durable user storage first."
        }
    }
}

$resolvedChrome = Resolve-ChromeExecutable -RequestedPath $ChromePath
$versionInfo = (Get-Item -LiteralPath $resolvedChrome).VersionInfo
$productName = [string]$versionInfo.ProductName
$productVersion = [string]$versionInfo.ProductVersion
$majorVersion = if ($productVersion -match '^(\d+)') { [int]$Matches[1] } else { 0 }
$isUnsupportedBrandedChrome = $productName -eq 'Google Chrome' -and $majorVersion -ge 137

$loadArgument = if ($resolvedExtension.Contains(' ')) {
    "--load-extension=`"$resolvedExtension`""
} else {
    "--load-extension=$resolvedExtension"
}
$arguments = @($loadArgument, '--restore-last-session')
if ($ProfileDirectory) {
    $arguments += if ($ProfileDirectory.Contains(' ')) {
        "--profile-directory=`"$ProfileDirectory`""
    } else {
        "--profile-directory=$ProfileDirectory"
    }
}

$initialProcesses = @(Get-MatchingChromeProcesses -ExecutablePath $resolvedChrome)
$wasRunning = $initialProcesses.Count -gt 0

if ($isUnsupportedBrandedChrome) {
    Write-Result -State 'blocked-branded-chrome-load-extension-unsupported' -WasRunning $wasRunning `
        -ResolvedExtension $resolvedExtension -ResolvedChrome $resolvedChrome -LaunchArguments @() `
        -ProductName $productName -ProductVersion $productVersion -Persistence 'not-installed' `
        -Detail 'Google Chrome 137+ ignores --load-extension in branded release builds. No browser process changed. Use chrome://extensions Developer Mode > Load unpacked for this normal profile, or choose an isolated Chromium/Chrome for Testing profile for automated loading.'
    if ($PlanOnly) {
        exit 0
    }
    exit 5
}

if ($PlanOnly) {
    Write-Result -State 'plan-only' -WasRunning $wasRunning -ResolvedExtension $resolvedExtension `
        -ResolvedChrome $resolvedChrome -LaunchArguments $arguments -ProductName $productName `
        -ProductVersion $productVersion `
        -Detail 'No browser process changed.'
    exit 0
}

if (-not $wasRunning -and -not $LaunchIfClosed) {
    Write-Result -State 'staged-browser-was-closed' -WasRunning $false -ResolvedExtension $resolvedExtension `
        -ResolvedChrome $resolvedChrome -LaunchArguments $arguments -ProductName $productName `
        -ProductVersion $productVersion `
        -Detail 'Chrome was closed, so Addonry did not launch it unexpectedly. Run helper with -LaunchIfClosed or start Chrome with reported arguments.'
    exit 0
}

if ($wasRunning -and -not $AuthorizedRestart) {
    Write-Result -State 'blocked-restart-not-authorized' -WasRunning $true -ResolvedExtension $resolvedExtension `
        -ResolvedChrome $resolvedChrome -LaunchArguments $arguments -ProductName $productName `
        -ProductVersion $productVersion `
        -Detail 'Chrome is running. Explicit -AuthorizedRestart is required before closing windows.'
    exit 2
}

if ($wasRunning) {
    if ($CountdownSeconds -gt 0) {
        Write-Warning "Chrome will close gracefully in $CountdownSeconds second(s). Tabs will be requested for restore; unsaved forms, calls, and downloads cannot be guaranteed."
        for ($remaining = $CountdownSeconds; $remaining -gt 0; $remaining--) {
            Write-Progress -Activity 'Preparing Chrome extension restart' -Status "Closing in $remaining second(s)" `
                -PercentComplete ((($CountdownSeconds - $remaining) / $CountdownSeconds) * 100)
            Start-Sleep -Seconds 1
        }
        Write-Progress -Activity 'Preparing Chrome extension restart' -Completed
    }

    $initialIds = @($initialProcesses | ForEach-Object { [int]$_.ProcessId })
    $windowProcesses = @(
        $initialIds |
            ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
            Where-Object { $_.MainWindowHandle -ne 0 }
    )
    foreach ($process in $windowProcesses) {
        [void]$process.CloseMainWindow()
    }

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($ExitTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 250
        $remainingProcesses = @(Get-MatchingChromeProcesses -ExecutablePath $resolvedChrome)
    } while ($remainingProcesses.Count -gt 0 -and [DateTimeOffset]::UtcNow -lt $deadline)

    if ($remainingProcesses.Count -gt 0) {
        Write-Result -State 'blocked-chrome-did-not-exit' -WasRunning $true -ResolvedExtension $resolvedExtension `
            -ResolvedChrome $resolvedChrome -LaunchArguments $arguments -ProductName $productName `
            -ProductVersion $productVersion `
            -Detail 'Chrome did not exit after graceful window close. No force-kill was attempted. Close remaining Chrome/background process, then retry.'
        exit 3
    }
}

Start-Process -FilePath $resolvedChrome -ArgumentList $arguments | Out-Null

$launchDeadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
$flagObserved = $false
do {
    Start-Sleep -Milliseconds 250
    $launchedProcesses = @(Get-MatchingChromeProcesses -ExecutablePath $resolvedChrome)
    $flagObserved = @(
        $launchedProcesses |
            Where-Object {
                $_.CommandLine -and (
                    $_.CommandLine.Contains("--load-extension=$resolvedExtension") -or
                    $_.CommandLine.Contains("--load-extension=`"$resolvedExtension`"")
                )
            }
    ).Count -gt 0
} while (-not $flagObserved -and [DateTimeOffset]::UtcNow -lt $launchDeadline)

if (-not $flagObserved) {
    Write-Result -State 'launched-load-flag-unconfirmed' -WasRunning $wasRunning -ResolvedExtension $resolvedExtension `
        -ResolvedChrome $resolvedChrome -LaunchArguments $arguments -ProductName $productName `
        -ProductVersion $productVersion `
        -Detail 'Chrome launched, but process command line did not confirm extension load flag. Verify in Chrome before claiming installed.'
    exit 4
}

Write-Result -State 'load-flag-observed-browser-verification-required' -WasRunning $wasRunning `
    -ResolvedExtension $resolvedExtension -ResolvedChrome $resolvedChrome -LaunchArguments $arguments `
    -ProductName $productName -ProductVersion $productVersion `
    -Detail 'Browser process command line contains extension load flag. This is not installation proof. Verify extension ID, enabled state, source path, and representative behavior through browser-level tooling before claiming installed.'
