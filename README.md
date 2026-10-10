# Xiaomi Remote Presenter

Turn a **Xiaomi Remote 2 Pro / Xiaomi Bluetooth Voice Remote** into a device-specific **browser, video and presentation** remote on **Windows, macOS, and Linux**.

**[中文完整使用手册：按键表、Windows/macOS/Linux 安装、视频兼容与验收](docs/中文使用手册.md)**

**Ubuntu / Firefox 连播恢复（2026-10-10）：** [诊断与恢复步骤](linux/remote-mic/README.md#2026-10-10firefox--夸克网盘连播与浏览器按键恢复记录) 包含 systemd 安全重启、浏览器快捷键检查，以及默认只读的 [Firefox 自动播放配置工具](linux/remote-mic/firefox-autoplay.py)。自动播放权限与网站的“下一集/连续播放”是两个不同的功能；浏览器全站点自动播放必须通过 `--apply` 自愿开启。

The key design rule is: **never globally remap Enter/Back**. The remote reports OK as an Enter-like key, so each operating system uses a device-aware input layer.

**Recommended SAFE profile (2026-10-09):** browser-only Home → new tab, Menu → next tab, TV → close tab, with ordinary Enter unaffected. [Linux](linux/remote-mic/README.md): run `bash install-services.sh --enable-video` (also handles video playback/speed) and optionally `bash pin-linux-safe.sh --backup` to persist a local rollback snapshot. [Windows](windows/README.md): `windows/install.ps1 -InstallDriver` defaults to `xiaomi_remote_safe.ahk`. [macOS](macos/README.md): `macos/install.sh --enable-safe` installs the device-scoped safe Karabiner rules with a configuration backup. The legacy full presentation/back mappings are opt-in. macOS video OK/speed require optional rules and may capture Enter/arrow keys even outside videos.

## Platform matrix

| Platform | Backend | Device-specific | Browser tabs & navigation | Video OK | Global Speed | Validation |
|---|---|---:|---|---|---|---|
| Linux | evdev + uinput | Yes | Yes | MPRIS → YouTube K fallback | D/A on focused video | Tested on Ubuntu/GNOME |
| Windows | AutoHotkey v2 + AutoHotInterception | Yes | Yes | F13 + browser userscript | D/A on recognized video-site titles | Static/CI only; needs Windows hardware validation |
| macOS | Karabiner-Elements | Yes | Yes | F13 + browser userscript | Optional all-browser D/A mode (scroll conflict) | JSON/CI only; needs Mac hardware validation |

## Default browser behavior

| Xiaomi button | Windows/Linux | macOS |
|---|---|---|
| Home (house) | Ctrl+T: new tab | Command+T |
| TV | Ctrl+W: close tab | Command+W |
| Menu (three lines) | Ctrl+Tab: next tab | Control+Tab |
| Back | Unchanged in SAFE (legacy mode adds Alt+Left) | Unchanged in SAFE (legacy mode adds Command+[) |
| OK | Linux: foreground video only; Windows: title-recognized video only | Unchanged in SAFE; optional video rule captures browser Enter |
| Round Up/Down | Linux: video-context D/A; Windows: title-recognized video D/A | Unchanged in SAFE; optional all-browser D/A mode |
| Volume +/- | Unchanged | Unchanged |

For presentation apps: SAFE passes original keys unchanged. Full presenter mode is optional.
Only the Xiaomi remote is remapped; ordinary keyboards remain untouched.

Browser OK on Windows/macOS requires
[browser/xiaomi-remote-video.user.js](browser/xiaomi-remote-video.user.js)
via Tampermonkey or Violentmonkey. Linux's Firefox PiP/video bridge and BLE
microphone are separate platform-specific implementations.

## Platform guides

- [Linux 演示遥控器 / Linux presenter](linux/README.md)
- [Linux 增强版：Global Speed 视频倍速、Firefox 画中画、BLE 麦克风](linux/remote-mic/README.md)
- [Windows](windows/README.md)
- [macOS](macos/README.md)
- [中文使用手册 / Chinese manual](docs/中文使用手册.md)

## Tested hardware ID

```text
VID: 0x2717
PID: 0x32B8
```

## Why the implementations differ

The same behavior needs different OS-native interception mechanisms:

- Linux can grab the exact HID device with `evdev`, suppress selected events, and re-emit the rest through `uinput`.
- Windows needs a per-device filter; AutoHotInterception provides this through the Interception driver.
- macOS Karabiner-Elements provides `device_if` plus `frontmost_application_if`, which lets the mapping target both the Xiaomi remote and the presentation app.

## Licenses

- **MIT**: the original Windows, macOS and Linux presentation-remote implementation (see [LICENSE](LICENSE)).
- **GPL-3.0-only**: the separate [Linux enhanced remote/microphone and Global Speed integration](linux/remote-mic/README.md) (see [linux/remote-mic/LICENSE](linux/remote-mic/LICENSE)).

The Linux Global Speed / Firefox native PiP integration is tested on Ubuntu.
Windows and macOS now also implement device-specific browser keyboard mappings
and a browser video userscript, but they have not been verified on physical
Windows or Mac hosts. Linux's native PiP Global Speed bridge and BLE voice
capture are not cross-platform. macOS speed controls are opt-in because they
take over browser arrow keys. See the Chinese manual for complete limitations.
