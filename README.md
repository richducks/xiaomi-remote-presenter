# Xiaomi Remote 2 Pro → WPS Presentation on Linux

Use a **Xiaomi Bluetooth Voice Remote / Xiaomi Remote 2 Pro** as a presentation remote for **WPS Presentation on Linux**.

The remote reports OK as `KEY_ENTER`, while WPS needs `F5` to start slideshow mode. On GNOME Wayland, WPS can also leave keyboard focus on a tiny XWayland helper window after exiting slideshow mode, so a simple global key remap is not reliable.

## What it does

Only while WPS Presentation is the active context:

| Remote button | Linux input | WPS action |
|---|---|---|
| OK | `KEY_ENTER` | `F5` — start slideshow |
| Back | `KEY_BACK` | `Esc` — exit slideshow |

It also:

- forwards all other remote buttons unchanged;
- blocks the remote's physical `KEY_F5` by default, preventing accidental browser refreshes;
- restores WPS editor focus after `Esc`, then allows the next OK press to start slideshow again;
- uses a narrow udev ACL rule for Xiaomi Remote 2 Pro (`VID 2717`, `PID 32b8`);
- runs as a normal **systemd user service**, not as root.

## Tested environment

- Ubuntu / GNOME
- Wayland desktop session
- WPS Office for Linux running through XWayland
- Xiaomi Bluetooth Voice Remote:
  - VID: `2717`
  - PID: `32b8`

The focus workaround relies on X11/XWayland utilities and libraries (`xprop`, `xwininfo`, `libX11`, `libXtst`).

## Install

Pair the Xiaomi remote in Ubuntu first, then:

```bash
git clone https://github.com/richducks/xiaomi-remote-wps-linux.git
cd xiaomi-remote-wps-linux
./install.sh
```

The installer requests `sudo` only for dependency installation and narrow device ACL setup. The service itself runs as your desktop user.

## Use

Open a `.ppt`, `.pptx`, or `.dps` document in **WPS Presentation**.

- **OK** → starts slideshow (`F5`)
- **Back** → exits slideshow (`Esc`)
- **OK again** → restores WPS focus when necessary, then starts slideshow again

Outside WPS Presentation, OK and Back are forwarded unchanged.

## Logs and diagnostics

Follow logs:

```bash
journalctl --user -fu xiaomi-remote-wps-linux.service
```

Run:

```bash
./diagnose.sh
```

Successful mappings look like:

```text
mapped KEY_ENTER down -> KEY_F5
mapped KEY_BACK down -> KEY_ESC
```

## Configuration

`remote_hid_filter.py` supports:

| Variable | Default | Meaning |
|---|---:|---|
| `XIAOMI_REMOTE_VID` | `0x2717` | HID vendor ID |
| `XIAOMI_REMOTE_PID` | `0x32B8` | HID product ID |
| `XIAOMI_BLOCK_PHYSICAL_F5` | `1` | Block the remote's original F5-like event |
| `XIAOMI_WPS_RESUME_WINDOW_SECONDS` | `15` | Focus recovery window after exiting slideshow |

Add `Environment=` lines to the generated user service if you need to override them.

## Why not a global key remapper?

A global `KEY_ENTER -> F5` mapping breaks normal remote behavior in browsers and other applications.

This project instead:

1. grabs only the Xiaomi remote;
2. checks the current WPS/XWayland context;
3. translates OK/Back only for WPS Presentation;
4. forwards every other event unchanged.

After `Esc`, WPS on XWayland can leave `_NET_ACTIVE_WINDOW` pointing at an invisible 1×1 helper window. During the short resume window, the next OK press briefly simulates a click on the WPS title bar, restores the pointer, and then sends F5.

## Uninstall

```bash
./uninstall.sh
```

## Security note

Access to `/dev/input` and `/dev/uinput` is security-sensitive. The installer does **not** grant access to all input devices. It creates a device-specific rule for the Xiaomi remote and grants the installing desktop user access to `uinput`.

Review `install.sh` before installing on shared or multi-user systems.

## License

MIT
