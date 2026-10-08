# Xiaomi Remote Presenter

Turn a **Xiaomi Remote 2 Pro / Xiaomi Bluetooth Voice Remote** into a device-specific presentation remote on **Windows, macOS, and Linux**.

The key design rule is: **never globally remap Enter/Back**. The remote reports OK as an Enter-like key, so each operating system uses a device-aware input layer.

## Platform matrix

| Platform | Backend | Device-specific | App-specific | State |
|---|---|---:|---:|---|
| Linux | evdev + uinput + XWayland focus recovery | Yes | Yes | Tested on Ubuntu/GNOME/Wayland |
| Windows | AutoHotkey v2 + AutoHotInterception | Yes | Yes | Implemented; requires Interception driver + reboot |
| macOS | Karabiner-Elements | Yes | Yes | Implemented; requires Karabiner permissions |

## Default behavior

| Remote button | WPS Presentation | Microsoft PowerPoint | Keynote |
|---|---|---|---|
| OK | Start slideshow | Start slideshow | Play presentation |
| Back | Esc | Esc | Esc |
| Remote physical F5 | blocked by default | blocked by default | blocked by default |

## Platform guides

- [Linux 演示遥控器 / Linux presenter](linux/README.md)
- [Linux 增强版：Global Speed 视频倍速、Firefox 画中画、BLE 麦克风](linux/remote-mic/README.md)
- [Windows](windows/README.md)
- [macOS](macos/README.md)

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

The Linux Global Speed/Firefox native Picture-in-Picture integration has been tested on Ubuntu/GNOME/Firefox. The Windows/macOS versions currently cover presentation remapping only; these platform-specific features are not yet ported.
