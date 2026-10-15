# 小米遥控器 2 Pro Electron 控制中心

该应用直接管理原有 Linux Python 蓝牙语音/evdev/systemd 用户服务和 remote_rules.json，而非第二套按键驱动。

功能：区分蓝牙连接与真正的物理 HID、查看三项服务与日志、仅对可信 RC003 做受限蓝牙重连、查看并校验保存 11 条现有映射。所有变更备份到后端 backups 目录。

Ubuntu 构建：运行 ./electron/build-deb.sh；Debian 安装包在 electron/dist/xiaomi-remote-control_1.0.1_amd64.deb。可以在应用菜单中启动。构建需本机缓存的 Electron 40.10.2 Linux x64 ZIP，Node.js、unzip 和 dpkg-deb。

其他电脑上须先部署原后端及用户服务。原项目根目录不同请设置 XIAOMI_REMOTE_HOME 指向配置目录。

Electron 窗口开启 sandbox / contextIsolation 且禁用 nodeIntegration。不会运行第二个 HID 监听，不访问网站，不自动提交聊天文字。
\nV1.0.1 显示原生 HID / BLE GATT 桥接模式，并将兼容桥纳入服务管理。\n

## 图形化配置（v1.1.1）
应用包含：设备概览、浏览器、ChatGPT、WPS 演示、微信语音、系统音量、方案与备份、诊断。
对应用可增加/修改/删除按键映射，界面输入校验后还会由原 Python RuleBook 校验；
微信语音设置同样校验并备份。导入方案先预览后保存。
系统音量键为全局保留键，不允许重映射。
Linux 需要 RC003 蓝牙驱动和 systemd 用户服务；Windows/macOS 需要各自原生后端。
按 Ctrl+Alt 的微信实时听写只在 GNOME 确认前台是微信且聊天输入框可编辑时触发。
