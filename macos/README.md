# macOS：小米遥控器 2 Pro 浏览器及演示控制

完整文档：[中文使用手册](../docs/中文使用手册.md)。

macOS 使用 [Karabiner-Elements](https://karabiner-elements.pqrs.org/)
按小米遥控器设备 VID=10007、PID=12984，以及前台应用做映射。
Mac 浏览器原生快捷键采用 Command，而不是 Windows 的 Ctrl。

## 推荐部署：SAFE 浏览器规则（默认）

默认安全配置 `xiaomi-remote-safe.json` 只处理蓝牙遥控器的
**小房子→⌘T、TV→⌘W、三横杠菜单→Control+Tab**。
**不会重映射 Enter、返回键、WPS、PowerPoint、Keynote、普通键盘**。

先在 Mac 蓝牙设置中配对小米遥控器并安装 Karabiner-Elements，
允许所需的输入监控、辅助功能与驱动权限。在本仓库执行：

```bash
cd macos
./install.sh
```

上面只安装规则供检查，默认**不会启用任何按键规则**。在
Karabiner-Elements → Complex Modifications → Add predefined rule 中
启用名称带 **Xiaomi Remote 2 Pro SAFE** 的三条规则即可。

如已确认设备身份并希望**自动启用安全规则**，可使用：

```bash
./install.sh --enable-safe
```

脚本需要 `python3`，会对所选 Karabiner 用户配置执行增量修改：
**先备份原 `~/.config/karabiner/karabiner.json`** 到同目录时间戳备份，
仅替换之前的 Xiaomi 项目规则，保留其他规则与用户 Profile，重复运行
不会重复加入。建议先退出 Karabiner 配置界面，再运行并重启 Karabiner
应用以加载规则。若想还原，退出 Karabiner 后将备份复制回配置文件。

**视频 OK 和倍速的边界**：
macOS Karabiner 无法可靠判断网页内是否正在播放视频。为了确保
浏览器 ChatGPT 的 Enter 不被劫持，SAFE 默认**不占用遥控器 OK**。
如接受“浏览器所有页面的遥控器 Enter 改为 F13”这一取舍，
可选启用 `xiaomi-remote-video-ok.json` 并安装
`browser/xiaomi-remote-video.user.js`；请勿在需要普通遥控器 Enter
的浏览器场景开启。视频 D/A 规则仍是
`xiaomi-remote-video-speed.json`（可选，在所有浏览器页面占用上/下，
影响滚动）。旧版完整 PPT/WPS 映射可单独选择，但不建议与 SAFE 混用。

### 下表为旧版完整映射（不属于 SAFE 默认行为）

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

3. 如确实需要旧版完整演示功能，再在 Karabiner-Elements
   → Complex Modifications → Add predefined rule 启用
   「Xiaomi Remote 2 Pro · 浏览器 / 演示」规则；
   **默认请采用上方 SAFE 方案**。
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
