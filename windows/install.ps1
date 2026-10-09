param(
    [switch]$InstallDriver,
    [switch]$NoStartup,
    [switch]$FullMode
)

$ErrorActionPreference = "Stop"

$AppName = "XiaomiRemotePresenter"
$InstallDir = Join-Path $env:LOCALAPPDATA $AppName
$LibDir = Join-Path $InstallDir "Lib"
$TempDir = Join-Path $env:TEMP "xiaomi-remote-presenter-setup"
$AhiUrl = "https://github.com/evilC/AutoHotInterception/releases/download/v0.9.1/AutoHotInterception.zip"
$InterceptionUrl = "https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip"
$AhiSha256 = "de0ce42887c810c78d936a2c1d8e89a2dc8652a53a0acf983963af25e0b2cde3"
$InterceptionSha256 = "ad038963d6413055765128b0b931f6e765147c9916dba79e65d872b261f9af10"

function Get-AutoHotkeyExe {
    $candidates = @(
        "$env:ProgramFiles\AutoHotkey\v2\AutoHotkey64.exe",
        "$env:ProgramFiles\AutoHotkey\UX\AutoHotkeyUX.exe",
        "$env:LOCALAPPDATA\Programs\AutoHotkey\v2\AutoHotkey64.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command AutoHotkey.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$AhkExe = Get-AutoHotkeyExe
if (-not $AhkExe) {
    throw "AutoHotkey v2 was not found. Install AutoHotkey v2 first, then rerun this script."
}

Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $TempDir | Out-Null
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $LibDir -Force | Out-Null

$AhiZip = Join-Path $TempDir "AutoHotInterception.zip"
$InterceptionZip = Join-Path $TempDir "Interception.zip"
Invoke-WebRequest $AhiUrl -OutFile $AhiZip
Invoke-WebRequest $InterceptionUrl -OutFile $InterceptionZip

if ((Get-FileHash $AhiZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AhiSha256) {
    throw "AutoHotInterception archive SHA-256 mismatch."
}
if ((Get-FileHash $InterceptionZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $InterceptionSha256) {
    throw "Interception archive SHA-256 mismatch."
}

$AhiExtract = Join-Path $TempDir "ahi"
$InterceptionExtract = Join-Path $TempDir "interception"
Expand-Archive $AhiZip -DestinationPath $AhiExtract -Force
Expand-Archive $InterceptionZip -DestinationPath $InterceptionExtract -Force

Copy-Item (Join-Path $AhiExtract "AHK v2\Lib\AutoHotInterception.ahk") $LibDir -Force
Copy-Item (Join-Path $AhiExtract "AHK v2\Lib\CLR.ahk") $LibDir -Force
Copy-Item (Join-Path $AhiExtract "AHK v2\AutoHotInterception.dll") $InstallDir -Force
New-Item -ItemType Directory -Path (Join-Path $LibDir "x64") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $LibDir "x86") -Force | Out-Null
Copy-Item (Join-Path $InterceptionExtract "Interception\library\x64\interception.dll") (Join-Path $LibDir "x64\interception.dll") -Force
Copy-Item (Join-Path $InterceptionExtract "Interception\library\x86\interception.dll") (Join-Path $LibDir "x86\interception.dll") -Force

# SAFE profile is the default. Full presenter mapping is explicit opt-in.
$SourceName = if ($FullMode) { "xiaomi_remote_presenter.ahk" } else { "xiaomi_remote_safe.ahk" }
$SourceScript = Join-Path $PSScriptRoot $SourceName
$ControllerPath = Join-Path $InstallDir "xiaomi_remote_presenter.ahk"
$OldProfile = Join-Path $InstallDir "profile.txt"
if (Test-Path $ControllerPath) {
    $BackupDir = Join-Path $InstallDir "backups"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    $TimeTag = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    Copy-Item $ControllerPath (Join-Path $BackupDir "xiaomi_remote_presenter.$TimeTag.ahk") -Force
}
Copy-Item $SourceScript $ControllerPath -Force
@("mode=" + $(if ($FullMode) { "full" } else { "safe" }), "script=$SourceName") |
    Set-Content -Path $OldProfile -Encoding UTF8
Copy-Item (Join-Path $PSScriptRoot "xiaomi_remote_safe.ahk") (Join-Path $InstallDir "xiaomi_remote_safe.ahk") -Force

# Keep the browser companion beside the installed controller so the user
# can import it without looking for the Git checkout.
$BrowserDir = Join-Path $InstallDir "browser"
New-Item -ItemType Directory -Path $BrowserDir -Force | Out-Null
$BrowserUserscript = Join-Path (Split-Path $PSScriptRoot -Parent) "browser\xiaomi-remote-video.user.js"
if (Test-Path $BrowserUserscript) {
    Copy-Item $BrowserUserscript (Join-Path $BrowserDir "xiaomi-remote-video.user.js") -Force
}

if ($InstallDriver) {
    $DriverInstaller = Join-Path $InterceptionExtract "Interception\command line installer\install-interception.exe"
    Write-Host "Installing Interception driver with administrator privileges..."
    Start-Process $DriverInstaller -ArgumentList "/install" -Verb RunAs -Wait
    Write-Warning "Windows must be restarted before the Interception driver becomes active."
}

if (-not $NoStartup) {
    $Startup = [Environment]::GetFolderPath("Startup")
    $ShortcutPath = Join-Path $Startup "Xiaomi Remote Presenter.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $AhkExe
    $Shortcut.Arguments = '"' + (Join-Path $InstallDir "xiaomi_remote_presenter.ahk") + '"'
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Save()
}

Write-Host ""
Write-Host "Installed to: $InstallDir"
Write-Host "AutoHotkey: $AhkExe"
Write-Host ("Active mapping profile: " + $(if ($FullMode) { "FULL (opt-in)" } else { "SAFE (default)" }))
Write-Host "To switch profiles, rerun the installer with or without -FullMode."
Write-Host "Previously installed controller scripts are backed up in $InstallDir\backups"
Write-Host ""
if (-not $InstallDriver) {
    Write-Warning "The Interception driver was not installed by this run."
    Write-Host "Rerun from PowerShell with:"
    Write-Host "  .\install.ps1 -InstallDriver"
    Write-Host "Then reboot Windows once."
} else {
    Write-Host "Reboot Windows once, then the controller will start at login."
}

Write-Host "Browser video OK uses F13 only on recognized video-page titles in SAFE mode."
Write-Host "Titles are heuristic; on unrelated sites Enter is untouched."
Write-Host "Import the userscript into Tampermonkey or Violentmonkey:"
Write-Host ("  " + (Join-Path $InstallDir "browser\xiaomi-remote-video.user.js"))
Write-Host "Global Speed D/A is triggered only on recognized video sites."
