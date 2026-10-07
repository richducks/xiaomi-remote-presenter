$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "XiaomiRemotePresenter"
$Startup = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $Startup "Xiaomi Remote Presenter.lnk"

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*xiaomi_remote_presenter.ahk*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item $ShortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Xiaomi Remote Presenter user files removed."
Write-Host "The Interception driver is intentionally left installed."
Write-Host "To remove the driver too, use the official Interception installer with /uninstall and reboot."
