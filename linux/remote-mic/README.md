# 小米遥控器 2 Pro · Linux 增强版

[English guide](#english-guide) · [项目首页](../../README.md)

小米蓝牙语音遥控器 2 Pro（VID 0x2717，PID 0x32B8）功能：

- **WPS 幻灯片**：OK → F5，返回 → Esc。
- **浏览器关闭当前标签页**：遥控器**小房子/Home** 键 → **Ctrl+W**，只在支持的网页浏览器窗口处于前台时触发（Firefox、Chrome、Chromium、Edge、Brave、Opera、Vivaldi、LibreWolf、Tor、Zen、GNOME Web 等）；普通网页也能用，无需正在播放视频。长按只关闭一个标签页。其他应用的 Home 键保持原始功能。
- **浏览器切换标签页**：遥控器**三横杠菜单键（≡ / KEY_COMPOSE）** → **Ctrl+Tab**，切换到下一个标签页；Firefox、Chrome、Chromium、Edge、Brave、Opera、Vivaldi 等浏览器前台均适用；非浏览器保持原生菜单键。长按只切换一次，不会卡住 Ctrl。
- **普通 Firefox / Chromium 视频**：圆盘上 → Global Speed 的 D（+0.1x），圆盘下 → A（-0.1x）。
- **Firefox 原生画中画（PiP）**：原视频页面接收 D/A，由已经安装的 Global Speed 负责改速；画中画不会因为切换焦点而关闭。
- **耳机、外置播放器和独立音量键**：保持原有音量行为。
- **浏览器 OK**：MPRIS 播放/暂停。
- **可选 BLE 语音输入**：ATVV → 虚拟麦克风，以及可选 ChatGPT 网页用户脚本。

这是现有 Xiaomi Remote Presenter 仓库的 **Linux 增强模式**。本目录的 HID 服务与旧版 linux/install.sh 部署的 xiaomi-remote-wps-linux 服务会竞争同一个遥控器设备，**两者不能同时运行**。Windows/macOS 仍支持 PPT 操作，但尚不支持这里的 Linux 专用画中画功能。

## 实机验证（2026-10-08）

在 Ubuntu 26 / GNOME Wayland / Firefox 157 / Global Speed 3.4.124 / 小米遥控器 2 Pro 实体设备上确认：

| 项目 | 结果 |
| --- | --- |
| 普通 Firefox 网页 | D/A 调用 Global Speed 加减速，已验证 |
| Firefox B 站原生画中画 | MPRIS 1.2→1.3→1.2x，画中画保持前台，已验证 |
| 真实遥控器圆盘输入 | 日志记录按键，PiP 页面速率随之变化 |
| WPS 演示键 | 保留既有已用逻辑 |
| 独立音量键 | 未重映射，仍需对各音频设备单独测试 |
| 自动化 | Python + JavaScript 覆盖 PiP、普通模式和失败降级 |

其他视频网站（例如夸克网盘）、Linux 桌面和外设需进一步验证。

## 1. 安装

先用系统蓝牙设置配对遥控器。在 Ubuntu/Debian 安装依赖：

    sudo apt update
    sudo apt install python3 python3-venv python3-pip python3-gi \
      gir1.2-atspi-2.0 python3-evdev bluez pulseaudio-utils x11-utils libxtst6

克隆仓库并安装项目内 Python 虚拟环境：

    git clone https://github.com/richducks/xiaomi-remote-presenter.git
    cd xiaomi-remote-presenter/linux/remote-mic
    bash install.sh
    .venv/bin/xiaomi-remote-mic doctor

install.sh 不调用 sudo、不删除现有环境。如果 /dev/input/eventX 或 /dev/uinput 权限不足，需先让管理员审查 [udev 示例](udev/71-xiaomi-remote.rules.example) 并配置设备访问权。不要向所有用户开放全部 /dev/input 权限。

如已安装旧版 PPT 专用过滤器，先主动停止，以免抢占设备：

    systemctl --user disable --now xiaomi-remote-wps-linux.service

## 2. 安装并配置 Global Speed（必需）

1. 在 Firefox 启用 **Global Speed – 视频速度控制器**。
2. 在插件「页面快捷键」里把 **D 设为在当前速度上 +0.1x**，**A 设为在当前速度上 -0.1x**。不能设置成固定 1.5x、1.2x，否则会发生速率循环。
3. Global Speed 的「选项 → 页面快捷键 → URL 条件」默认是白名单，包含 B 站但不包含抖音和夸克。需要另外新增 https://www.douyin.com 和 https://pan.quark.cn 两条「以…开始」规则，并保留原有条件。最后用电脑实体键盘 D/A 确认普通网页倍速有效。
4. 普通视频不需要本项目的 Tampermonkey 辅助脚本。Firefox **原生画中画**需要下一节的 v0.5 浏览器辅助脚本。

Global Speed 是**唯一的倍速修改引擎**。用户脚本只合成快捷键并读取播放速率，不直接修改 playbackRate。旧版的 Firefox 原生 PiP < >、切窗映射和直接改速均未发布。

## 3. 启用后台服务

    bash install-services.sh
    bash install-services.sh --enable
    systemctl --user status xiaomi-remote-hid-filter.service
    systemctl --user status xiaomi-chatgpt-web-bridge.service

首次运行不自动启用服务；只有明确指定 --enable 才启动 HID 与网页事件桥。它们仅监听本机 127.0.0.1:18766，不对局域网开放。

在 **本机 Firefox**访问：

**http://127.0.0.1:18766/video/setup**

点击页面内的「更新 Global Speed 画中画辅助脚本」，并在 Tampermonkey 中确认安装/更新 **v0.5.0**；之后刷新视频网站。Firefox 画中画窗口前台时圆盘上/下即调用原网页中的 Global Speed。

诊断：

    curl http://127.0.0.1:18766/video/debug
    journalctl --user -fu xiaomi-remote-hid-filter.service -o cat

实机验收：client_versions.firefox 包含 5，pip_ready 为 true，画中画按键后 last_results 中 engine=global-speed、pip=true、ok=true，且 before 与 speed 确实不同。**仅收到指令不代表视频倍速已经生效**。

安全边界：助手不运行、视频暂停、来源不明、多个 Firefox 视频同时播放时，可以拒绝 PiP 加速，以免误操作其他网页或破坏普通模式。

## 4. 可选 BLE 虚拟麦克风

    .venv/bin/xiaomi-remote-mic scan
    .venv/bin/xiaomi-remote-mic run --gain-db 6

开机启动语音桥（需先停止手动运行）：

    bash install-services.sh --enable-mic

网页 ChatGPT 语音脚本在 chatgpt-web/xiaomi-chatgpt.user.js，安装必须通过用户自己的浏览器/扩展授权。语音功能与 Global Speed 相互独立。

## 5. 测试、停止及恢复

    .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
    node tests/test_video_userscript.cjs
    node tests/test_video_userscript_pip.cjs

注意：自动测试无法取代具体 Firefox 网站上的实机验证。

停止：

    systemctl --user disable --now xiaomi-remote-hid-filter.service
    systemctl --user disable --now xiaomi-chatgpt-web-bridge.service
    systemctl --user disable --now xiaomi-remote-mic.service

这些指令不删除蓝牙配对、浏览器扩展或用户数据。可以手动重新启用旧版 PPT 专用服务。

## 逻辑说明

    小米遥控器 (Bluetooth HID)
      └── evdev → uinput
           ├── WPS OK/F5 + 返回/Esc
           ├── 独立音量键 → 原系统音量事件
           ├── 普通视频圆盘上下 → 实体 D/A → Global Speed
           └── Firefox 原生画中画圆盘上下
                → 本地专用事件 localhost:18766
                → Tampermonkey v0.5（原视频网页）
                → 合成 D/A 键盘事件
                → Global Speed 改速
                → 只读 video.playbackRate 验证

## 授权与来源

**linux/remote-mic 目录独立以 GNU GPL-3.0-only 授权**，详见 [LICENSE](LICENSE)。BLE/ATVV 实现学习参考 [ZSTDJan/windows-remote-mic-app](https://github.com/ZSTDJan/windows-remote-mic-app) 与 [nijez/open-voice-bridge](https://github.com/nijez/open-voice-bridge)，请尊重上游许可。仓库已有 Windows/macOS/Linux PPT 演示文件仍沿用仓库根目录的 MIT License。

本公开源码**不包括**个人蓝牙配对地址、设备密钥、API Token、浏览器用户数据、扩展签名私钥和本地日志。

## English guide

This optional Linux-enhanced profile supports Xiaomi Bluetooth Remote 2 Pro (0x2717:0x32B8), WPS, BLE virtual microphone and Firefox native PiP video speed **through Global Speed only**. Install dependencies, run "bash install.sh" then "bash install-services.sh --enable", configure the Global Speed page shortcuts **D (+0.1x)** and **A (-0.1x)**, and approve the v0.5 helper from **http://127.0.0.1:18766/video/setup** in Firefox Tampermonkey. Do not run the legacy xiaomi-remote-wps-linux service simultaneously. This video feature is Linux-specific; the Windows/macOS files continue to support presentation mode. Licensing: GPL-3.0-only for this subfolder, MIT for existing presenter files.
