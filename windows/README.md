# Windows

Windows uses **AutoHotkey v2 + AutoHotInterception** so the mapping is tied to the Xiaomi remote itself, not to every keyboard.

Supported presentation apps by default:

- Microsoft PowerPoint (`POWERPNT.EXE`)
- WPS Presentation (`wpp.exe`)
- LibreOffice Impress (`soffice.exe` / `soffice.bin`)

Mappings:

- Xiaomi OK (`Enter`) → `F5`
- Xiaomi Back (`Browser_Back`) → `Esc`
- Xiaomi physical `F5` → blocked, preventing accidental browser refresh
- Laptop/desktop keyboard Enter and Back are not remapped

## Install

1. Install AutoHotkey v2.
2. Pair/connect the Xiaomi remote.
3. Open PowerShell in this folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -InstallDriver
```

4. Approve the administrator prompt.
5. Reboot Windows once.

The script then starts automatically at login.

The configured Xiaomi IDs are:

```text
VID 0x2717
PID 0x32B8
```

If Windows exposes your hardware differently, run `Monitor.ahk` from the AutoHotInterception package and update the two constants in `xiaomi_remote_presenter.ahk`.

## Uninstall

```powershell
.\uninstall.ps1
```
