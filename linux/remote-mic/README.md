# 小米遥控器 2 Pro · Linux 增强版

[English guide](#english-guide) · [项目首页](../../README.md)

## 2026-10-14：RC003 方向、确定及系统音量安全映射

基于 [open-voice-bridge](https://github.com/nijez/open-voice-bridge) 的 RC003 实体键定义与 [xremap](https://github.com/xremap/xremap)、[evremap](https://github.com/wez/evremap) 的设备级 evdev/uinput 隔离方案，**沿用当前唯一 HID 服务**，不再安装第二套全局键盘映射器。当前实体遥控器 VID:PID 为 `2717:32b8`，原生 OK 发送 `KEY_ENTER`（而非 `KEY_OK`）。

| RC003 物理键 | 无视频普通应用/网页 | 确认前台视频时 |
| --- | --- | --- |
| 上、下 | 原生 ↑/↓，保留长按重复与释放 | 上 D：Global Speed +0.1x；下 A：Global Speed -0.1x；PiP 优先现有助手，失败后退回原方向键 |
| 左、右 | 原生 ←/→，保留按住连续导航 | 原生 ←/→，由网站播放器决定是否快退/快进（不承诺各站一致） |
| OK | 原生 Enter（WPS 演示前台：单次 F5） | 前台媒体 MPRIS 播放／暂停；YouTube 可回退为 K，其他网页保留 Enter |
| 实体音量 + / - | **始终转发原生系统音量键**，保留连发/松开；由 GNOME/PipeWire 处理 | 同左，不会误触视频倍速或 ChatGPT 听写 |

安全约束：`remote_rules.json` 的应用级规则禁止重绑定音量键，实际事件在进入应用规则前直通系统；不改变系统静音状态、不设置固定音量、不改变个人键盘及 Solaar。只在确认前台视频时重映射上/下；左右保持真实方向键。设备声明具备 `KEY_MUTE` 事件能力，但公开 RC003 资料显示实体遥控器未必有独立静音按键，故不假设存在。修改后运行 `python -m unittest discover -s linux/remote-mic/tests -p 'test_*.py'` 并做实体按键验收。

## 2026-10-12：Firefox 多标签卡死、扩展内存泄漏与保护

本机诊断：30 GiB 内存、Firefox `WebExtensions` 单进程常驻约 12.5–13 GiB、交换分区使用约 5.8 GiB。2026-10-11 23:09 内核 OOM 曾杀死一个占用约 12 GiB 匿名内存的 WebExtensions 进程。2026-10-12 抓取 Firefox 原生匿名 `about:memory` 报告，发现扩展宿主包含大量 JS 对象与已提交堆内存，内置 GC/CC 未明显释放。确切是哪一个浏览器扩展导致增长尚未锁定，不能推定是 Global Speed、Tampermonkey 或其他具体插件。

在保持 Firefox 主进程和已打开标签页不退出的情况下，只对经进程名/父进程核验的过量 `WebExtensions` 子进程发送一次 SIGTERM。用户现场：约 24 GiB 已使用内存降低到 13 GiB、可用内存从约 5.8 GiB 增至 17 GiB，扩展子进程重新启动后约为 440–500 MiB；遥控器服务和 Firefox 视频桥接正常。扩展后台任务在进程重建时可能短暂中断。此操作是症状恢复而不是找到了根本泄漏插件。

为防止无人值守的长期多标签会话再次触发 OOM，安装一个仅针对 Firefox Snap `WebExtensions` 子进程的本机低频保护。程序只读 `/proc`，每 3 分钟由 systemd 用户级定时器运行一次，必须确认**同一个进程**连续超过 7 GiB、且间隔至少 3 分钟，才会向这个子进程发送 SIGTERM；不杀 Firefox 主进程、不关闭标签页、不重启系统或小米遥控器服务，不卸载扩展。无法明确识别进程身份时拒绝动作。正常占用下只记录一次检查日志。

安装与检查：

```bash
cd linux/remote-mic
bash install-firefox-memory-guard.sh
systemctl --user status xiaomi-firefox-extension-memory-guard.timer
journalctl --user -u xiaomi-firefox-extension-memory-guard.service -n 30 --no-pager
```

可随时停用：`systemctl --user disable --now xiaomi-firefox-extension-memory-guard.timer`。这个保护可缓解内存暴涨，但扩展具体泄漏源仍需 Firefox `about:memory` 和 `about:debugging` 的逐插件验证；不要以保护已启用作为插件完全修好的证明。

## 2026-10-12：修复映射已发送但浏览器可能漏掉快速组合键

现场：GNOME 焦点桥接仍返回 Firefox，实体 HID 按键和 Ctrl+Tab/Ctrl+W 映射日志均存在，映射服务没有重启；使用独立虚拟键盘保持约 60ms 的 Ctrl+Tab，可以观察到 Firefox 标签页标题切换。原 `modified_tap` 在相邻 SYN 帧之间立即释放组合键，没有按键驻留时间。

将合成 Ctrl/Alt 组合键保持 60ms，合成单键保持 35ms；仍在同次操作中完整释放修饰键。仅影响遥控器合成的浏览器/WPS 操作，不修改物理 Enter 原样透传、音量、Firefox 视频自动连播设置或浏览器配置。新增按键时长及释放平衡的回归测试。上述现场结果支持修复可能的丢键风险，但不能单凭日志认定每个实体按键在每个网站都执行成功。

## 2026-10-11 16:50：根治 GNOME Wayland 假 ACTIVE 的焦点桥接

再次失效时的现场证据：2026-10-11 16:44:25 的 `KEY_COMPOSE` 确实到达遥控器 HID 服务，但被记录为 `pass-through: browser not confirmed`。系统同时显示微信和 Firefox ACTIVE，而二者 AT-SPI 树都没有可信 FOCUSED 后代；继续依靠 AT-SPI 无法稳定识别。

**修复**：GNOME Shell 50 的本地只读扩展通过 D-Bus 暴露 Mutter 的 `global.display.focus_window` 应用 ID、窗口类、标题（不传网络）；HID 服务优先从 GNOME 真正的前台读取。桥接不可用时才保守降级到原来的 AT-SPI 判断。已确认真实前台是 `firefox_firefox.desktop`（夸克网盘），而之前 AT-SPI 判断为假；新的检测为真。桌面补丁并不修改 Firefox 连播设置和任何物理键盘映射。

现有 Ubuntu/GNOME 50 机器安装焦点扩展：

```bash
cd linux/remote-mic
bash install-gnome-focus.sh
systemctl --user restart xiaomi-remote-video-only.service
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/gnome/Shell/Extensions/XiaomiRemoteFocus \
  --method org.xiaomi.RemoteFocus.GetFocus
```

此扩展在 `xiaomi-wps-ok@local` 这个历史**已停用**的小米 WPS 扩展 UUID 下运行（为了在当前 GNOME 会话中直接启用，而不用强制退出桌面）；新实现只提供前台读取功能，不捕获键盘。旧 WPS OK/F5 功能已经由唯一的 HID 服务提供。安装脚本会拒绝覆盖仍启用的旧扩展，并备份旧文件。新机器首次安装时 GNOME 可能需要重新登录一次才能加载新扩展；不要强行重启 GNOME Shell Wayland 会话。

## 2026-10-11：修复多应用假 ACTIVE 导致快捷键间歇失效

GNOME Wayland / AT-SPI 实测会同时把 Firefox 和微信、或 Firefox 和 Chrome 标记为 ACTIVE。这不是可靠的真实焦点信息。旧版在找到浏览器 ACTIVE 时会误认浏览器为前台；如果 WPS 同时 ACTIVE，则会拒绝 WPS 的 OK/F5、返回/Esc，表现为间歇失效。

新版只在唯一 ACTIVE 窗口时直接识别；多个 ACTIVE 窗口时，在可访问性树中寻找唯一 FOCUSED 后代。仍无法消歧时保留实体按键，不发送危险的 Ctrl+W/F5。前台媒体会话也统一使用该焦点选择器，减少背景媒体错误接管 OK 键。新增假 ACTIVE 的回归测试；不改 Firefox 自动播放配置。

日志中 browser tab 表示 HID 按键已映射；remote navigation ... pass-through: browser not confirmed 表示实体事件已到达服务，但前台识别没有确认浏览器。如果按键后两类日志均未出现，应进一步核查蓝牙/HID 事件链。systemd 服务显示 active 与单元测试通过，均不代表跨应用实体按键验收已完成。

## 2026-10-10：统一安全服务（浏览器 + WPS）

保留当前 Firefox/夸克连播设置，不启动旧 HID 过滤器。`xiaomi-remote-video-only.service` 现在是**唯一遥控器事件入口**，在原有视频按键和标签页快捷键上增加：前台可明确识别 WPS 演示时 **OK→单次 F5**、**返回→单次 Esc**；前台浏览器时 **返回→Alt+左方向键**。遥控器物理 F5（可能来自话筒按键）会被过滤以防意外刷新网页。普通应用 Enter 保留原始按下/重复/释放事件，音量键不变。所有合成组合键都会立即完整释放修饰键。

GNOME Wayland 上 AT-SPI 有时会同时报告不同程序的活动窗口；如同时报告浏览器和 WPS，本方案**宁可不触发这两类高风险快捷键**，不向不确定的前台窗口发送 Ctrl+W/F5。现场焦点可靠性仍须用实体遥控器分别验收；不应声称已对所有应用实现绝对兼容。

## 2026-10-09：视频安全模式（推荐）

为避免遥控器 OK 被全局映射成 Enter 后影响 ChatGPT 消息发送、WPS 和钉钉，本项目新增**安全的视频及浏览器标签页专用 HID 服务** `video_only_hid.py`。它只接管 VID `2717` / PID `32B8` 的小米遥控器，**从不打开实体电脑键盘设备**。普通应用中的 Enter、Home、TV、菜单、返回、音量等仍原样传递；**不会**向普通应用发送 Ctrl+W、F5 或合成 Enter。浏览器前台的 Home、TV 和菜单键有独立快捷键（见下表），旧版完整映射逻辑保留但无需启用。

| 视频安全模式按键 | 前提和行为 |
| --- | --- |
| OK | 前台浏览器视频优先通过 MPRIS 播放／暂停；YouTube 视频标签页可退回单次 K。非视频环境原样透传 Enter。 |
| 圆盘上 | 前台普通视频通过 Global Speed D 加速一个步进；Firefox 原生画中画通过现有本地助手触发。 |
| 圆盘下 | 同理通过 Global Speed A 减速一个步进。 |
| 小房子（KEY_HOME／KEY_WWW） | **仅前台浏览器** Ctrl+T 新建标签页；兼容同次按下 HOME+WWW 双事件去重。 |
| 三横杠菜单（KEY_COMPOSE） | **仅前台浏览器** Ctrl+Tab 切换下一标签页。 |
| TV（KEY_GRAVE） | **仅前台浏览器** Ctrl+W 关闭当前标签页。 |
| 返回 | 浏览器前台 Alt+← 返回上一页；WPS 演示明确前台时 Esc；其他应用原样传递。 |
| WPS 演示 OK | 明确识别到 WPS 演示前台时触发一次 F5；WPS 文字/表格和其他程序不触发。 |
| 遥控器原始 F5 | 拦截（部分 RC003 固件的话筒键会发 F5，避免误刷新浏览器）。 |
| 音量和其他键 | 保留设备原始 HID 行为；不在钉钉或其他普通应用里做全局快捷键映射。 |

首次安装（先按下方“1. 安装”和“2. 配置 Global Speed”准备依赖和扩展）：

```bash
cd xiaomi-remote-presenter/linux/remote-mic
bash install.sh
systemctl --user disable --now xiaomi-remote-hid-filter.service 2>/dev/null || true
systemctl --user disable --now xiaomi-remote-wps-linux.service 2>/dev/null || true
bash install-services.sh --enable-video
systemctl --user status xiaomi-remote-video-only.service
```

`install-services.sh` 使用当前仓库目录生成用户级 systemd 服务，**不包含开发者本机绝对路径**；`--enable-video` 同时启用原有 `xiaomi-chatgpt-web-bridge.service`（供 Firefox 原生画中画助手调用）。如检测到竞争的旧 HID 服务正在运行，安装程序会拒绝切换，避免两个服务同时抓取遥控器。

诊断：

```bash
journalctl --user -fu xiaomi-remote-video-only.service -o cat
curl http://127.0.0.1:18766/video/debug
```

### 2026-10-10：Firefox / 夸克网盘连播与浏览器按键恢复记录

Ubuntu 26 / GNOME Wayland / Firefox 157 的本机排查记录：`video_only_hid.py` 与仓库文件 SHA-256 一致，安全模式服务已启用；旧 `xiaomi-remote-hid-filter.service` 和 `xiaomi-remote-wps-linux.service` 处于 inactive，`xiaomi-chatgpt-web-bridge.service` 正常运行。浏览器按键失灵时，记录过 AT-SPI 无障碍总线套接字连接错误；**重启 HID 服务后重新抓取遥控器**。按键测试验证虚拟设备的 Ctrl+T、Ctrl+Tab、Ctrl+W 能送到 Firefox，但这**不等于所有实体按键在所有网站通过了实机验收**。用户随后反馈当前使用已恢复。

出现浏览器小房子、三横杠、TV 按键失效时，先看服务和日志，不要启用竞争的旧完整映射，也不要全局重新绑定 Enter：

```bash
systemctl --user is-active xiaomi-remote-video-only.service
systemctl --user is-active xiaomi-chatgpt-web-bridge.service
systemctl --user is-active xiaomi-remote-hid-filter.service   # 应为 inactive
systemctl --user is-active xiaomi-remote-wps-linux.service    # 应为 inactive
journalctl --user -u xiaomi-remote-video-only.service -n 50 --no-pager
# 蓝牙在线但按键服务失去正常上下文、或日志有 AT-SPI 连接异常时：
systemctl --user restart xiaomi-remote-video-only.service
systemctl --user status xiaomi-remote-video-only.service
```

只有出现 `safe video/browser filter grabbed ...` 才能说明 HID 被重新抓取；服务 `active` **本身不证明按键已生效**。重新测试浏览器里的小房子→新建、三横杠→切换、TV→关闭（注意先保存标签页内容）。验证 Enter、钉钉/WPS 普通输入和视频播放/倍速未受到影响。若按键在任意应用都失效，再检查蓝牙配对和 `/dev/input` 设备；**不可同时运行两个抓取同一物理遥控器的服务**。

Firefox 当前机器上观察到 `media.autoplay.default=0`（允许视频自动播放）和 `media.block-autoplay-until-in-foreground=false`（不要求先把标签页切到前台）。为了让新机器**选择性复现**这两个设置，提供不修改 `prefs.js`、不读取 cookies 的配置脚本：

```bash
# 只查看 Firefox 当前 profile、prefs.js 和 user.js 设置（默认不写入）
python3 linux/remote-mic/firefox-autoplay.py
# 在仓库根目录运行；明确接受所有站点均允许自动播放后才执行：
python3 linux/remote-mic/firefox-autoplay.py --apply
# 更改 user.js 后完全退出、重开 Firefox 才能生效
```

支持 Firefox Snap / 非 Snap `profiles.ini` 中唯一默认 profile；有多个无法判定的配置时用 `--profile /path/to/your/firefox-profile` 显式指定。`--apply` 备份原 `user.js` 到**本机 profile**，保留其他配置，重复应用不会重复写入；绝不上传浏览器 profile。**代价是所有网站都可以尝试自动播放（包括带声音视频）**；不接受这种行为时不要运行 `--apply`，改为在 Firefox 地址栏左侧的网站权限中对指定网站单独允许自动播放。

**重要边界：Firefox 允许自动播放 ≠ 夸克网盘会自动选择下一集。** 夸克的顺序播放/连续播放属于网站播放器或播放列表控制；本项目的 Global Speed、画中画和 HID 映射**不提供**“下一集”功能，也不应盲目向网站注入自动点击。若当前视频播完后未跳下一集，优先看网站列表和连播开关；若已跳转但停在暂停状态，再检查 Firefox 的自动播放权限。用户报告已恢复，但无法由静态配置检查证明特定站点的完整连续剧跨集播放。

2026-10-10 起 SAFE 模式已包含 WPS 的前台 OK→F5、返回→Esc 和浏览器返回→Alt+←；无需切换旧完整映射，也绝不能让两个服务同时抓取实体遥控器。

回滚视频模式（**不会修改系统键盘，也不会自动恢复旧全功能映射**）：

```bash
systemctl --user disable --now xiaomi-remote-video-only.service
```

2026-10-09：Ubuntu 26 / GNOME Wayland 已确认服务抓取小米遥控器并正常运行；加入浏览器三个标签页快捷键后，91 项 Python 自动测试通过（其中 19 项验证新服务的键位隔离）。**本模式在 YouTube、抖音、夸克和 Firefox 画中画中的最新实机播放效果尚待逐站验收**；此前 2026-10-08 的视频验证针对旧完整版，并非新模式的最终验收。

### 旧完整版与视频模式不能同时运行

下列完整按键列表与第 3 节中的 `--enable` 命令属于**旧完整版**（包含 WPS/返回网页等其他映射）；新增标签页、切换标签页、关闭标签页和视频播放已经包含在推荐的 `--enable-video` 中，无需启用旧服务。为保持 ChatGPT、钉钉和实体键盘正常，建议只启用安全模式。若明确需要旧版 WPS/返回键功能，必须先停用当前模式并独立验收输入行为。

小米蓝牙语音遥控器 2 Pro（VID 0x2717，PID 0x32B8）功能：

- **WPS 幻灯片**：OK → F5，返回 → Esc。
- **浏览器新建标签页（小房子键）**：遥控器**小房子/Home** → **Ctrl+T**，只在浏览器前台新建一个标签页（Firefox、Chrome、Chromium、Edge、Brave、Opera、Vivaldi、LibreWolf、Tor、Zen、GNOME Web 等）；长按不重复创建，其他应用保持原来的 Home 键行为。
- **浏览器切换标签页**：遥控器**三横杠菜单键（≡ / KEY_COMPOSE）** → **Ctrl+Tab**，切换到下一个标签页；Firefox、Chrome、Chromium、Edge、Brave、Opera、Vivaldi 等浏览器前台均适用；非浏览器保持原生菜单键。长按只切换一次，不会卡住 Ctrl。
- **浏览器返回上一页**：遥控器**返回键（KEY_BACK）** → **Alt+←**，在 Firefox、Chrome、Chromium、Edge、Brave、Opera、Vivaldi 等浏览器中返回上一页；长按只执行一次，WPS 中仍为 Esc，其他非浏览器应用保持原返回键。
- **TV 键关闭网页**：遥控器 **TV 键（Linux KEY_GRAVE，RC003 HID 0x35）** → **Ctrl+W**，仅在浏览器前台关闭当前标签页；和小房子键的新建标签页功能明确区分。长按只关闭一个，其他软件保持 TV 键原有功能。
- **普通 Firefox / Chromium 视频**：圆盘上 → Global Speed 的 D（+0.1x），圆盘下 → A（-0.1x）。
- **Firefox 原生画中画（PiP）**：原视频页面接收 D/A，由已经安装的 Global Speed 负责改速；画中画不会因为切换焦点而关闭。
- **耳机、外置播放器和独立音量键**：保持原有音量行为。
- **浏览器 OK**：优先使用 MPRIS 播放/暂停。YouTube 视频页如果存在简繁翻译使 MPRIS 标题与窗口标题不匹配，则自动发送 YouTube 原生 K 播放/暂停（仅前台选中的 YouTube 视频标签页，且不会在搜索框/输入框输入 K），无需额外插件。
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

## 3. 启用旧完整版后台服务（仅需要 WPS/浏览器额外快捷键时）

**推荐使用上方的 `bash install-services.sh --enable-video`。** 下列指令会切换为旧完整版，在恢复其他快捷键前应明确测试普通应用 Enter：

    systemctl --user disable --now xiaomi-remote-video-only.service
    bash install-services.sh
    bash install-services.sh --enable
    systemctl --user status xiaomi-remote-hid-filter.service
    systemctl --user status xiaomi-chatgpt-web-bridge.service

首次运行不自动启用服务。只有指定 `--enable-video` 或 `--enable` 才启动对应 HID 方案；两种方案互斥。网页事件桥仅监听本机 127.0.0.1:18766，不对局域网开放。

在 **本机 Firefox**访问：

**http://127.0.0.1:18766/video/setup**

点击页面内的「更新 Global Speed 画中画辅助脚本」，并在 Tampermonkey 中确认安装/更新 **v0.5.0**；之后刷新视频网站。Firefox 画中画窗口前台时圆盘上/下即调用原网页中的 Global Speed。

诊断：

    curl http://127.0.0.1:18766/video/debug
    journalctl --user -fu xiaomi-remote-video-only.service -o cat
    # 如明确改用旧完整版，请查询 xiaomi-remote-hid-filter.service

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

    systemctl --user disable --now xiaomi-remote-video-only.service
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

This optional Linux-enhanced profile supports Xiaomi Bluetooth Remote 2 Pro (0x2717:0x32B8), WPS, BLE virtual microphone and Firefox native PiP video speed **through Global Speed only**. For the recommended **video-only mode that preserves Enter and all non-video keys**, install dependencies, run `bash install.sh` then `bash install-services.sh --enable-video`. Configure Global Speed shortcuts **D (+0.1x)** and **A (-0.1x)** and, for Firefox native PiP, approve helper v0.5 from **http://127.0.0.1:18766/video/setup**. The optional legacy full remapper is `--enable`; never run both profiles or the older WPS-only HID service together. Video-only mode has automated test coverage but site-level hardware validation is still pending. This Linux-native feature is separate from Windows/macOS support. Licensing: GPL-3.0-only for this subfolder, MIT for existing presenter files.


## 2026-10-14：低内存、可热更新的应用规则引擎（Linux）

`video_only_hid.py` 仍然是唯一的 **Xiaomi HID 设备抓取者**。没有新增常驻 Python 进程或全局键盘监听器。WPS 演示和浏览器快捷键改由相同目录中的 `remote_rules.json` 驱动，`remote_rules.py` 负责白名单校验与热更新（按键事件到来时最多每秒检查一次文件）。

规则结构（在 `remote_rules.json` 的 `rules` 数组里添加或修改）：

```json
{"id":"browser-menu","scope":"browser","input":"KEY_COMPOSE",
 "shortcut":["KEY_LEFTCTRL","KEY_TAB"],"cooldown_ms":450}
```

`scope` 只能选择 `browser`（已确认的前台浏览器）或 `wps`（已确认的 WPS 演示）。每条规则必须具有唯一 `id`、输入键 `input`，以及 **二选一** `tap` 或 `shortcut`。输出键、修饰键、输入键受允许名单限制；重复输入、未知应用、危险的全局规则、浏览器 `Enter/OK` 映射均被拒绝。配置文件无效时保留最后一次有效配置；前台应用不确定时执行原始按键而不是猜测。

**安全边界：** 视频 OK（MPRIS/YouTube）、画中画及视频倍速仍由同一现有进程的原视频逻辑处理。物理麦克风 `F5` 仍被阻断。普通键盘不抓取；小米设备非目标场景的物理 Enter 原样透传。为避免误关闭多个标签页，默认仍对 TV（Ctrl+W）设置 800ms 防抖。浏览器 `Ctrl+W` 是有损操作，修改前确认不会误触。

验证配置：

```bash
cd ~/Documents/CodexProjects/xiaomi-remote-mic-linux
.venv/bin/python remote_rules.py --check remote_rules.json
```

修改 JSON 后无需重启服务；下一次遥控器按键输入会检查是否变化（最多约 1 秒缓存）。`{"version":1,"rules":[]}` 会关闭 WPS/浏览器快捷键，但不会关闭视频模块。若文件不存在，使用内置的安全默认规则。更换设备、桌面/浏览器或新增动作前先做离线测试。

查看日志及内存：`journalctl --user -u xiaomi-remote-video-only.service -n 40 --no-pager`；`systemctl --user status xiaomi-remote-video-only.service`。回滚时恢复部署前的 `video_only_hid.py` 并重启该服务；不要同时启用 `xiaomi-remote-hid-filter.service`。


## 2026-10-14：ChatGPT 网页专用遥控规则

ChatGPT 网页（`https://chatgpt.com/` 下任意页面）与普通 Firefox 网页使用不同动作；**必须先安装或更新浏览器 Tampermonkey 用户脚本**，否则保留原浏览器快捷键。新版用户脚本位于 `chatgpt-web/xiaomi-chatgpt.user.js`，可从已运行的本地桥接地址 `http://127.0.0.1:18766/xiaomi-chatgpt.user.js` 打开并在 Tampermonkey 中安装/更新。安装完成并切到 ChatGPT 前台后，按键作用：

| 遥控器按键 | ChatGPT 动作 | 其他 Firefox 网页 |
| --- | --- | --- |
| Home / Homepage / WWW | 新建聊天，若当前有未发送草稿则拒绝 | 新标签 Ctrl+T |
| Menu | 切换标签 Ctrl+Tab（不触发听写） | 切换标签 Ctrl+Tab |
| TV | 只有已产生文字且未在录音时才触发发送 | 关闭标签 Ctrl+W |
| 小米物理麦克风 | 按住录音，松开完成听写并显示草稿，**不会自动提交**（需要网页麦克风权限） | 物理 F5 仍被抑制，绝不刷新 |
| OK / Enter | **有待审阅草稿且停止听写后**，按一次才提交；无草稿时仍保留原生 Enter / 视频操作 | 原有安全处理；WPS 前台保持 F5 |
| 返回 | 原有浏览器返回 | 原有浏览器返回 |

键位可在 `remote_rules.json` 修改 `scope="chatgpt"` 和允许的 `action`（仅 `new_chat`、`voice_toggle`、`send`）；键位热更新，无需重启 HID 服务。所有新动作经当前已有 `chatgpt_web_bridge.py` 转给当前活动的 ChatGPT 标签，**并不启动第二个 HID 进程**。网页每 2 秒轻量心跳确认焦点，桥接 6 秒超时自动失效；多标签焦点有歧义时拒绝操作。网页脚本仍须在页面内确认输入框及目标按钮，找到不可靠时不自动模拟 Enter；旧版本脚本不会收到新增指令。此机制针对 Firefox 当前网页，不支持 ChatGPT 桌面原生应用。

录音需要额外的 `xiaomi-remote-mic.service`（ATVV → PipeWire 虚拟音频）；这**不是**主 HID 按键过滤器。服务停用时 Home/TV 中的普通 DOM 点击仍可工作，但真实遥控器语音不能采集。ChatGPT 语音听写在松开遥控器语音键后转为可审阅、可修改的草稿，**绝不自动发送**。用户核对后按遥控器 OK 提交（TV 原发送快捷键仍可使用）；仅当 ChatGPT 用户脚本 V0.6.0 的草稿就绪状态获得确认时，OK 才会接管实体 Enter。其他软件的 OK、WPS F5、视频播放及系统音量映射均不变。若页面未提供听写入口，语音按钮不执行。仅能在已授权该浏览器麦克风访问、已安装用户脚本、设备 BLE 麦克风正常时进行实机语音验收。

状态检查：

```bash
curl -fsS http://127.0.0.1:18766/chatgpt/active
systemctl --user status xiaomi-remote-video-only.service xiaomi-chatgpt-web-bridge.service xiaomi-remote-mic.service
journalctl --user -u xiaomi-remote-video-only.service -n 30 --no-pager
```

`/chatgpt/active` 的 `active:true` 表示浏览器用户脚本报告当前 ChatGPT 网页焦点；不表示麦克风权限或语音转文字已经验证。若为 `false`，先更新/启用 Tampermonkey 脚本并打开 ChatGPT 网页检查。


### Linux 微信语音输入：低延迟实时听写（小米 RC003）

在**原生 Linux 微信聊天会话前台**，按住遥控器语音键将自动聚焦聊天编辑框，并模拟
`Ctrl+Alt` 两键按下，触发电脑原有实时语音听写提示和边说边显示的文字；
松开后释放 `Ctrl+Alt`，仅等待实时听写最后一段文字完成，**不重复识别、不粘贴第二次**。
审阅或手动改字后，45 秒内按遥控器 OK 才发送。

用户体验修复（2026-10-14）：
- 双输入回归原因：第一次版本 `Ctrl+Alt` 触发实时输入，同时后台又执行 Whisper，造成两遍文字。
- 后续无响应原因：去重版本强制读取微信 Qt 草稿，AT-SPI `get_text` 偶发不可用，直接拒绝发起快捷键。
- 后续迟缓无图标原因：绕开快捷键、仅用 Whisper 的版本只能松开后识别，常见延时数秒。
- 现版**只用 Ctrl+Alt 原生实时输入**，开始前验证聊天框可自动聚焦，但**不再依赖读取草稿内容**。
  微信编辑框优先采用可校验的无障碍快捷路径（约 10–90ms），失败时才走完整搜索；保留安全焦点判断。

不在后台启动本地 Whisper 子进程，也不会调用剪贴板 Ctrl+V 或自动按 Enter。
微信设置应允许 Enter 发送。浏览器/ChatGPT/WPS/系统音量原先的配置不变。
离线 `wechat_transcribe.py` 和 `install-wechat-dictation.sh` 保留为非默认备用组件。

验证：`python -m unittest discover -s tests -p test_wechat_dictation.py -v`。


#### 微信实时语音启动延迟优化（2026-10-14）

当按住遥控器语音键出现偶发 1–2 秒延迟或未唤起输入图标时，主要瓶颈来自微信 Qt/AT-SPI 对聊天编辑框的深层全树查找。现已改为：优先在原生微信聊天窗口中验证快速编辑框路径，路径变化时只搜索附近的聊天编辑区并设置约 0.5 秒的搜索预算；启动服务时预注册虚拟键盘以消除首次按键设备初始化等待；日志新增 `editor_lookup_ms` 便于监测。保留 Ctrl+Alt 单一实时输入源，不启动离线 Whisper、不松开后重复粘贴、不自动发送。启动前仍需确认前台是微信且确实能聚焦聊天输入框，以免误输入搜索框或其他应用。
