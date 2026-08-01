# 科研系统 · 正式版

当前稳定版本：**正式版 1.0**（技术版本 `1.0.1`）

这是面向实际使用的公开下载入口。正式版源码只在私有开发仓库维护；公开仓库仅保留稳定版本说明、校验信息和可直接使用的发行文件。

## 下载

- [Windows 单程序](https://github.com/yanjj5521/research-cultivation-os/releases/download/formal-v1.0.1/ResearchSystem-Formal-v1.0.1-Windows-x64.exe)
- [Windows 便携包](https://github.com/yanjj5521/research-cultivation-os/releases/download/formal-v1.0.1/ResearchSystem-Formal-v1.0.1-Portable.zip)
- [Android 安装包](https://github.com/yanjj5521/research-cultivation-os/releases/download/formal-v1.0.1/ResearchSystem-Mobile-Formal-v1.0.1-Android.apk)
- [SHA-256 校验文件](https://github.com/yanjj5521/research-cultivation-os/releases/download/formal-v1.0.1/SHA256SUMS.txt)

Windows 只提供一个 `ResearchSystem.exe`：双击进入个人科研系统；需要团队中心时，用便携包内唯一的 `启动团队中心.cmd`，或执行 `ResearchSystem.exe --mode team`。

## 版本边界

- `formal-v1.0.0` 是正式产品线起点；`formal-v1.0.1` 修复无控制台启动并更新极简蓝色图标。
- `v2.1.0` 至 `v3.0.0` 统一视为测试版，相关分支和发布记录继续保留。
- 正式版不读取、不迁移测试版数据库。首次启动会建立独立数据目录，避免测试数据和正式资料互相污染。
- 个人科研资料默认仅保存在本机；团队模式只承载主动提交的轻量协作状态。

Windows 暂无商业代码签名，首次启动可能出现 SmartScreen；Android 为侧载安装包。
