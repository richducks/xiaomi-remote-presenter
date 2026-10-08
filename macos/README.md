# macOS：小米遥控器 2 Pro 浏览器及演示控制

完整文档：[中文使用手册](../docs/中文使用手册.md)。

macOS 使用 [Karabiner-Elements](https://karabiner-elements.pqrs.org/)
按小米遥控器设备 VID=10007、PID=12984，以及前台应用做映射。
Mac 浏览器原生快捷键采用 Command，而不是 Windows 的 Ctrl。

| 遥控器 | 浏览器前台 | WPS / PowerPoint / Keynote |
|---|---|---|
| 小房子 | ⌘+T，新建标签页 | 原样 |
| TV（grave / HID 0x35） | ⌘+W，关闭标签页 | 原样 |
| 三横杠菜单（Application） | Control+Tab，下一个标签页 | 原样 |
| 返回（AC Back） | ⌘+[，返回上一页 | Esc |
| OK（Enter） | F13（需视频用户脚本） | WPS F5、PowerPoint ⌘⇧Return、Keynote ⌘⌥P |
| 圆盘上/下 | 可选模式：D/A 控制 Global Speed | 原样 |
| 音量 +/− | 不改动 | 不改动 |

其中 ⌘ 为 Command，⇧ 为 Shift，⌥ 为 Option。

## 安装

1. 在系统蓝牙中配对遥控器，安装 Karabiner-Elements，
   授予系统要求的辅助功能、输入监控及驱动权限。
2. 在终端执行：

        cd macos
        ./install.sh

3. 在 Karabiner-Elements → Complex Modifications → Add predefined rule
   启用「Xiaomi Remote 2 Pro · 浏览器 / 演示」规则。
4. 在 Firefox、Chrome、Safari 等浏览器安装 Tampermonkey 或
   Violentmonkey，导入 browser/xiaomi-remote-video.user.js，
   使遥控器 OK/F13 控制页面上的可见 HTML5 视频。
5. 如果需要视频加减速，安装 Global Speed，设置 D 为 +0.1x、
   A 为 -0.1x，然后才手动启用独立的
   「Xiaomi 2 Pro · Global Speed 视频模式（可选，浏览器占用方向键）」规则。
   **这个可选规则会在所有浏览器网页占用上／下方向键，影响滚动，
   不是只在视频播放时才拦截，因此默认不启用。**

## 故障排查

Karabiner-EventViewer → Devices / Frontmost Application / Events
确认遥控器设备和真实事件：TV 通常是 grave_accent_and_tilde，
菜单通常是 application，返回通常是 ac_back，小房子通常是
home 或 ac_home。不同固件存在差异，按 EventViewer 结果调整。

该平台的配置已生成并经过 JSON 与静态规则测试，
但尚未在真正的 Mac 蓝牙硬件上验收。
Firefox Linux 特有的画中画倍速连接桥、BLE 语音麦克风，
尚未直接移植到 macOS。
