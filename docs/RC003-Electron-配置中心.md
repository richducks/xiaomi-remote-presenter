# 小米遥控器 2 Pro · Electron 配置客户端

适用设备：小米 RC003，VID 2717 / PID 32B8。当前版本是 Linux x64 v1.1.0。Windows/macOS 的原生按键后端见仓库对应目录；Linux deb 不可用于 Windows/macOS。

## 小白操作

软件左侧包含：设备概览、浏览器、ChatGPT、WPS 演示、微信语音、系统按键、方案与备份、诊断维护，共八个页面。
在浏览器/WPS/ChatGPT 页面添加或编辑按钮；选择应用、遥控器按键、动作与防重复时间；点击右上角保存。所有映射须经过 Python 规则引擎校验，且保存前自动备份。
微信支持按住听写、松开查看、手动 OK 提交；不会再次粘贴语音或者自动发送。
全局音量键不可被网页应用接管。

## 安装 Linux 版

在 Ubuntu GNOME 系统上从本目录运行 bash install.sh 部署 Python BLE 后端，运行 bash install-services.sh --enable-video 配置服务。
当 BlueZ 连接遥控器但没有对应 HID 设备时，运行 bash install-gatt-fallback.sh。兼容桥会检测原生 HID 并让位。
从 GitHub Releases 获取版本匹配的 xiaomi-remote-control_1.1.0_amd64.deb，确认来源后通过 Ubuntu 包管理器安装，随后运行 bash electron/install-linux-desktop.sh 设置本地后台目录。
开发者可直接使用 bash electron/build-deb.sh 构建本机发行包；已配置操作系统授权的开发机可运行 bash electron/build-and-upgrade.sh 来打包、校验、安装。
本程序依赖 Python/systemd 后端；单装 Electron 不能代替蓝牙和音频驱动。

## 安全与数据

配置、聊天和语音都在本机处理。请勿公开个人音频、聊天、系统日志、MAC 地址、机密令牌或配置备份。
软件禁用 Node 渲染层权限，启用 Electron sandbox 和 contextIsolation；所有危险操作严格使用 IPC 白名单与 Linux 操作系统权限机制。
公开发行版不自动 root 执行未知下载程序。
