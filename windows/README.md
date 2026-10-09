# Windows：小米遥控器 2 Pro 浏览器及演示控制

完整文档：[中文使用手册](../docs/中文使用手册.md)。

Windows 使用 AutoHotkey v2 和 AutoHotInterception，通过设备
VID=0x2717、PID=0x32B8 过滤输入事件，仅修改这只小米遥控器。

## 推荐部署：SAFE 浏览器配置（默认）

当前推荐 **`xiaomi_remote_safe.ahk`**。它只为小米遥控器映射
**小房子→Ctrl+T、三横杠菜单→Ctrl+Tab、TV→Ctrl+W**；WPS、
系统键盘、非视频浏览器输入框里的 Enter、返回键均不修改。
在前台窗口标题识别到 YouTube/B 站/抖音/夸克等视频网站时，才将
遥控器 OK 映射为 F13（需视频用户脚本），圆盘上/下映射到
Global Speed 的 D/A。注意：**仅凭标题不能识别真实视频**；
视频网站中即使焦点落在输入框，遥控器 Enter 也可能被映射。
因此 Windows SAFE 是降低干扰风险，尚非与 Linux 一样精确的视频上下文识别。

在 Windows 10/11 配对遥控器并安装 AutoHotkey v2 后，从仓库的
`windows` 目录执行 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -InstallDriver
```

上面的命令默认部署 SAFE，驱动安装时需要管理员授权，完成后重启 Windows。
若驱动已安装，则运行 `.\install.ps1` 更新配置（无需再次加
`-InstallDriver`）。用户登录启动项会指向安装目录中的安全脚本；
更新前的版本保存在 `%LOCALAPPDATA%\XiaomiRemotePresenter\backups`，
当前模式记录在 `profile.txt`。升级已有运行实例后需要退出旧 AHK
实例并重新运行，或者注销后登录。

**仅当确实需要 PPT/WPS 放映、浏览器后退等旧版功能时**
才使用 `.\install.ps1 -FullMode`，明确承担更广泛的映射风险。
同一时间仅运行一套 AHK 映射实例，切勿双开。
Linux 独有的原生 Firefox 画中画辅助桥尚未移植到 Windows。

## 旧版完整映射按键表（需 -FullMode）

| 遥控器 | 浏览器 | WPS / PowerPoint / Impress | 其他应用 |
|---|---|---|---|
| 小房子 | Ctrl+T，新建标签页 | 原样 | 原样 |
| TV（HID 0x35 / SC029） | Ctrl+W，关闭标签页 | 原样 | 原样 |
| 三横杠菜单（AppsKey） | Ctrl+Tab，下一个标签页 | 原样 | 原样 |
| 返回（Browser_Back） | Alt+←，上一页 | Esc | 原样 |
| OK（Enter） | F13 播放／暂停（需用户脚本） | F5 放映 | 原样 |
| 圆盘上/下 | 识别到视频站点时 D/A 调节 Global Speed | 原样 | 原样 |
| 音量 +/− | 不改动 | 不改动 | 不改动 |

Windows 浏览器视频站点识别基于窗口标题，已列入 YouTube、Bilibili、
抖音、夸克、Netflix 等；不是检测正在播放的真实视频。
不符合标题规则的网页保持原始方向键，不保证所有网站变速。

## 依赖与视频扩展配置（SAFE 与完整模式通用）

1. Windows 10/11 蓝牙配对小米遥控器 2 Pro。
2. 安装 [AutoHotkey v2](https://www.autohotkey.com/)。
3. 在 windows 目录打开 PowerShell，运行（第二条命令需要管理员确认）：

        Set-ExecutionPolicy -Scope Process Bypass
        .\install.ps1 -InstallDriver

4. **重启 Windows** 使 Interception 驱动生效。
5. 安装 Tampermonkey 或 Violentmonkey，导入
   本项目 browser/xiaomi-remote-video.user.js，或者本机安装目录
   %LOCALAPPDATA%\XiaomiRemotePresenter\browser\xiaomi-remote-video.user.js。
   此脚本把遥控器专属的 F13 转换为前台 HTML5 视频的播放／暂停，
   不会修改视频倍速。**不安装脚本时浏览器 OK 不会播放／暂停。**
6. 安装浏览器的 Global Speed 扩展，在「页面快捷键」中配置
   D 为 +0.1x、A 为 -0.1x，并把视频网站加入其 URL 白名单。

**注意：底层 Interception 驱动可能影响系统输入。请保留备用键盘，
不要在只能远程连接、无法重启恢复的电脑上直接安装。**

更新：重新运行安装脚本后，登录自启将使用最新版映射。
卸载：执行 windows/uninstall.ps1；用户文件和登录启动项会删除，
但驱动不会自动卸载，需使用官方 Interception 卸载工具并重启。

## 实际键值诊断

使用 AutoHotInterception 附带的 Monitor.ahk 查看设备与键值；
固件可能把 TV、Menu 或 Back 报告为其他 Windows 键值，
以实测输入为准修改 AHK 绑定。正常键盘应不受本配置影响。

本项目未连接到 Windows 设备进行实机操作；
PowerShell 解析与映射契约交由 GitHub Actions 验证。
