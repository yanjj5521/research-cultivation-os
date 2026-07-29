问道科研 · Windows 公开发行版
================================

一、先选你要点哪个

普通成员、只管理自己科研资料：
  双击 ResearchOS.exe

负责让大家联机的中心主机：
  双击 ResearchHub.exe

同一台电脑既做中心、又是个人用户：
  双击“启动完整联机套件.cmd”

两个程序都不需要 Python、pip 或管理员权限。首次启动 ResearchHub 时，
Windows 可能询问是否允许“专用网络”访问；需要局域网联机时请选择允许。

二、两个 EXE 分别做什么

ResearchOS.exe（个人节点）
  保存个人计划、课题推进、论文、实验、MD/ML/COMSOL、笔记和附件。
  这些内容默认只在本机。

ResearchHub.exe（轻量联机中心）
  保存成员账号、邀请码、公开主页、灵石/资材、公共资料卡、版本通知和
  同步事件。它不读取成员电脑上的论文、实验原始数据或交付文件。

ResearchOS-Mobile-*-Android.apk（在 GitHub Release 单独下载）
  连接已经运行的 ResearchHub，提供手机上的账号、同行、资料卡和轻量
  状态入口。它不复制个人端数据库或科研原文件。

普通模式数据目录：
  个人节点  %LOCALAPPDATA%\ResearchCultivationOS
  联机中心  %LOCALAPPDATA%\ResearchCultivationOSHub

更新 EXE 不会覆盖这两个数据目录。

三、最简单的联机方法（同一局域网）

1. 选一台会保持开机的电脑，运行 ResearchHub.exe。
2. 窗口会显示中心主机地址，例如 http://192.168.1.20:5050。
3. 管理员打开窗口中显示的一次性凭据文件，登录中心后立即修改密码。
4. 管理员在中心网页生成邀请码；成员用邀请码注册。
5. 每位成员打开自己的 ResearchOS.exe，在“联机扩展”中填写中心地址和
   自己的 API Token，然后点击“保存并联机”。
6. Android 用户可填写窗口显示的地址，或在手机浏览器打开 Hub 后点击
   页面底部“一键打开”链接。

如果不启用联机，ResearchOS.exe 的全部本地功能仍可正常使用。

四、便携 ZIP 中的辅助入口

- 启动问道科研.cmd：启动个人节点；
- 启动联机中心.cmd：启动联机中心；
- 启动完整联机套件.cmd：同机启动个人节点和中心；
- 便携模式启动.cmd：个人数据写入当前文件夹 user_data；
- 联机中心便携模式.cmd：中心数据写入当前文件夹 hub_data；
- 打开数据目录.cmd / 打开联机中心数据.cmd：打开对应数据目录；
- 迁移旧版数据.cmd：导入 v2.0 个人节点数据库与附件。

便携模式移动前必须先关闭程序，并连同整个文件夹复制。

五、更新与安全

- 正式 Release 同时提供个人端 EXE、中心端 EXE、完整 ZIP 和 SHA-256；
- Android APK 与 Windows 产品位于同一 Release，并写入同一 SHA-256 文件；
- 只做个人使用的人不需要下载或运行 ResearchHub；
- 公网联机必须使用 HTTPS Tunnel 或 VPS，不能直接暴露 5050；
- 不要把 research_os.db、hub.db、管理员凭据或 API Token 放进网盘共享；
- 定期在个人网页“设置与备份”和中心管理页分别制作备份。
