# 问道科研 · v3.6.1 灵知桌宠更新版

当前稳定版本：**问道科研 v3.6.1**

这是面向实际使用的公开下载入口。正式源码只在私有开发仓库维护；公开仓库仅保留稳定说明、校验信息和可直接使用的发行文件。

## 下载

- [Windows 单程序](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.1.0/WendaoResearch-v3.1.0-Windows-x64.exe)
- [Windows 便携包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.1.0/WendaoResearch-v3.1.0-Portable.zip)
- [Android 安装包](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.1.0/WendaoResearch-Mobile-v3.1.0-Android.apk)
- [SHA-256 校验文件](https://github.com/yanjj5521/research-cultivation-os/releases/download/wendao-v3.1.0/SHA256SUMS.txt)
- [完整使用手册](docs/使用手册.md)

Windows 只有一个 `WendaoResearchV3.exe`：双击进入个人端；需要团队中心时，使用便携包内的 `启动团队中心.cmd`，或执行 `WendaoResearchV3.exe --mode team`。

## v3.6.1 重点

- 新增轻量 3D「灵知」桌面宠物：默认 132 px，不遮挡科研工作；支持拖拽、缩放、呼吸动画、随机科研提示与今日任务进度提醒。
- 保留 3.4 中真正实用的桌宠互动，去除复杂而低频的堆叠功能，让科研过程多一点陪伴、少一点打扰。
- 主页持续保持实用优先：学习入口、文献与知识库检索、近期计划、工作台及个人化布局都可直接使用。

## v3.6.0 重点

- 管理员控制台与普通成员同行厅明确分流，服务端继续强制鉴权。
- 五档界面密度；主页组件可显隐、拖动、缩放并一键智能排版。
- 390 px 窄屏自动单列，无横向溢出。
- 五问雷劫、炼丹炉、成就图鉴和彩蛋柜全面扩充。
- 修复冻结程序上传新版 ZIP 的 Internal Server Error。
- Windows、Android、个人端与同行会统一使用水彩金丹图标。
- 继续使用独立的 `wendao-v3-clean.db`，不读取或迁移旧版数据库。

Windows 暂无商业代码签名，首次运行可能出现 SmartScreen；Android 为侧载安装包。当前 Latest 为 `wendao-v3.1.0`。
