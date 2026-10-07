# macOS

macOS uses **Karabiner-Elements** with both device-specific and app-specific conditions.

Target device:

```text
VID 0x2717 = 10007
PID 0x32B8 = 12984
```

Supported apps:

| App | Xiaomi OK | Xiaomi Back |
|---|---|---|
| WPS Presentation | F5 | Esc |
| Microsoft PowerPoint | Command+Shift+Return | Esc |
| Apple Keynote | Command+Option+P | Esc |

## Install

1. Install Karabiner-Elements.
2. Pair/connect the Xiaomi remote.
3. Run:

```bash
./install.sh
```

4. Open Karabiner-Elements → **Complex Modifications** → **Add predefined rule** and enable the Xiaomi rules.
5. Grant the Accessibility/Input Monitoring permissions requested by macOS.

## If Back does not work

The remote normally exposes Back as HID `AC Back`, which Karabiner represents as:

```json
{"consumer_key_code":"ac_back"}
```

Open **Karabiner-EventViewer → Capture Raw Input Events**, select the Xiaomi remote, press Back, and update the rule if your firmware reports another event.
