# 问道科研 · 正式版

当前稳定版本：**问道科研 · 正式版 1.0**（技术版本 `1.0.0`）

这是面向实际使用的公开下载入口。正式源码只在私有开发仓库维护；公开仓库仅保留稳定说明、校验信息和可直接使用的发行文件。

## 下载

- [Windows 单程序](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-formal-v1.0.0/WendaoResearch-Formal-v1.0.0-Windows-x64.exe)
- [Windows 便携包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-formal-v1.0.0/WendaoResearch-Formal-v1.0.0-Portable.zip)
- [Android 安装包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-formal-v1.0.0/WendaoResearch-Mobile-Formal-v1.0.0-Android.apk)
- [SHA-256 校验文件](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-formal-v1.0.0/SHA256SUMS.txt)

Windows 仍然只有一个 `WendaoResearch.exe`：双击进入个人端；需要团队中心时，使用便携包内唯一的 `启动团队中心.cmd`，或执行 `WendaoResearch.exe --mode team`。

## 这一版的边界

- 界面、动效与完整功能回归“问道科研”：山门总览、课题推进、近期计划、知识库、AI 协作、复盘、科研工具、成长系统、个人主页和轻量团队中心都已恢复。
- 底层沿用正式版的模块化结构，数据库、领域服务、网页路由、团队中心、桌面打包和 Android 工程彼此分离。
- 使用全新的 `wendao-research.db` 与独立 Android 包名；不读取、不迁移、不兼容之前任何测试版或精简候选数据库。
- 个人研究资料默认只保存在本机；团队模式只承载主动提交的轻量协作状态。

`formal-v1.0.0` 与 `formal-v1.0.1` 保留作“精简重构候选 / 已撤回”；`v2.1.0` 至 `v3.0.0` 仍为测试版。Windows 暂无商业代码签名，首次运行可能出现 SmartScreen；Android 为侧载安装包。
