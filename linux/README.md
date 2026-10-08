# Linux 支持 / Linux support

**有两个互斥的 Linux HID 服务，不能同时启用**：它们都独占同一小米遥控器的蓝牙输入设备。

- [基础演示遥控器](install.sh)：WPS OK/F5、Back/Esc；使用本仓库 MIT 授权。
- [Linux 增强版](remote-mic/README.md)：WPS、Global Speed 视频倍速、Firefox 原生画中画、可选 BLE 虚拟麦克风；GPL-3.0-only 授权。

基础版安装：在仓库根目录运行 bash linux/install.sh。增强版安装：先阅读 linux/remote-mic/README.md，再进入该目录运行 bash install.sh 和 bash install-services.sh --enable。旧版服务 xiaomi-remote-wps-linux 应当先由用户自行停止，避免和增强版 xiaomi-remote-hid-filter 争用设备。

Windows/macOS 目录仍为幻灯片演示遥控器，不包含此 Linux 专用画中画功能。
