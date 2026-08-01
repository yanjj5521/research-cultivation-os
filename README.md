# 问道科研 · 3.0 体验正式版

当前稳定版本：**问道科研 v3.0.1**（3.0 原体验重构版）

这是面向实际使用的公开下载入口。正式源码只在私有开发仓库维护；公开仓库仅保留稳定说明、校验信息和可直接使用的发行文件。

## 下载

- [Windows 单程序](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.0.1/WendaoResearch-v3.0.1-Windows-x64.exe)
- [Windows 便携包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.0.1/WendaoResearch-v3.0.1-Portable.zip)
- [Android 安装包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.0.1/WendaoResearch-Mobile-v3.0.1-Android.apk)
- [SHA-256 校验文件](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.0.1/SHA256SUMS.txt)

Windows 仍然只有一个 `WendaoResearchV3.exe`：双击进入个人端；需要团队中心时，使用便携包内的 `启动团队中心.cmd`，或执行 `WendaoResearchV3.exe --mode team`。

## 这一版的边界

- 完整保留原 3.0 的界面、页面层级、功能入口、URL、表单、文案和操作规则。
- 底层拆分为模块化结构，数据库、领域服务、网页路由、启动器、打包和测试彼此分离。
- 使用全新的 `wendao-v3-clean.db` 与独立 Android 包名；不读取、不迁移、不兼容任何旧数据库。
- 新版动效作为独立层接入，不重排原 3.0 页面。
- 个人研究资料默认只保存在本机；团队模式只承载主动提交的轻量协作状态。

Windows 暂无商业代码签名，首次运行可能出现 SmartScreen；Android 为侧载安装包。此前版本仍保留下载，但当前 Latest 为 `wendao-v3.0.1`。
