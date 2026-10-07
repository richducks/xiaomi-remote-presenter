param(
    [switch]$InstallDriver,
    [switch]$NoStartup
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

$SourceScript = Join-Path $PSScriptRoot "xiaomi_remote_presenter.ahk"
Copy-Item $SourceScript (Join-Path $InstallDir "xiaomi_remote_presenter.ahk") -Force

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
Write-Host ""
if (-not $InstallDriver) {
    Write-Warning "The Interception driver was not installed by this run."
    Write-Host "Rerun from PowerShell with:"
    Write-Host "  .\install.ps1 -InstallDriver"
    Write-Host "Then reboot Windows once."
} else {
    Write-Host "Reboot Windows once, then the controller will start at login."
}
