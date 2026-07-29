# 问道科研 v2.3.0 联机说明

## 先看清边界

v2.3.0 的个人节点默认选择“未启用”，不会建立同步队列，也不会上传或拉取任何状态。用户选择 ResearchHub 后可点击“保存并联机”，一次完成地址校验、首次轻量状态合并和自动同步开启。规模化云端 v2 仍只是接口、事件信封和 OpenAPI 草案，服务器、统一登录与多租户数据库尚未实现。

下面的局域网、隧道和 VPS 方案只用于兼容现有“轻量同行会”，适合小范围自托管，不是成百上千用户的生产架构。要使用它，先在个人节点的“联机扩展”中主动选择“轻量同行会（兼容）”。

## 两个 EXE 分别给谁

- 每位 Windows 使用者下载并双击 `ResearchOS-v2.3.0-Windows-x64.exe`，用于本人的计划、课题、生涯、论文、工作区和附件；
- 只有负责小团队联机服务的人才下载并双击 `ResearchHub-v2.3.0-Windows-x64.exe`；
- Android 使用者安装 `ResearchOS-Mobile-v2.3.0-Android.apk`，连接已经运行的 ResearchHub；
- 同一台电脑可以同时运行两个程序：个人节点默认端口 `5000`，联机中心默认端口 `5050`；
- 个人数据默认位于 `%LOCALAPPDATA%\ResearchCultivationOS`，中心数据默认位于 `%LOCALAPPDATA%\ResearchCultivationOSHub`，二者互不覆盖；
- 不需要团队联机时，只下载 `ResearchOS`，无需运行 `ResearchHub`。

## Android 连接

1. 管理员在一台会保持开机的电脑运行 `ResearchHub.exe`；
2. 窗口会显示 `Android client address` 和 `Android one-tap pairing link`；
3. 手机与主机在同一私有网络时，可在 APK 中填写 `192.168.x.x:5050`；
4. 也可先用手机浏览器打开 Hub，点击页面底部“在 Android App 中打开当前中心”；
5. 公网中心必须使用有效的 `https://` 地址，不能把 5050 直接暴露在互联网上。

APK 只提供 ResearchHub 的账号、公开主页、轻量进度、资产、资料卡和版本入口。它不复制个人电脑上的 `research_os.db`、论文、实验原始数据或交付附件；不启用 JavaScript 原生桥，也不申请相机、麦克风或存储权限。

## 管理员首次设置

1. 第一次启动轻量联机中心时，系统检查数据库中是否已有管理员；
2. 只有在不存在管理员时，系统才创建用户名 `admin` 的唯一初始管理员；
3. 随机密码与 API Token 只写在中心数据目录的 `instance/HUB_ADMIN_CREDENTIALS.txt`；
4. 使用这份密码登录后，进入“我的联机主页”立即修改密码；
5. 修改成功后，一次性凭据文件会自动销毁；Token 仍可在个人页查看或重新生成；
6. 管理员在管理页生成邀请码，其他人通过邀请码注册，注册角色固定为 `member`。

管理员可以管理邀请码、成员启停、版本包、中心备份和同步审计。管理员不能通过中心读取成员电脑上的论文、实验、数据集或附件，也不应手工修改数据库来分配角色。

## 客户端故障隔离

- 所有科研操作先写本地数据库，网络失败不回滚本地结果；
- 自动同步超时为 1.5 秒，临时错误按指数退避并带抖动，同时遵守中心 `Retry-After`；
- 连续 3 次失败后自动暂停至少 5 分钟，避免网络波动形成重试风暴；
- 每个同步事件使用唯一 UUID，中心重复收到同一事件时不会重复记账；
- 单个事件累计 6 次仍未成功会暂停，认证或参数错误不自动重试；
- 联机页提供“检测连接”和“恢复暂停事件”，并显示队列、熔断和最近检测状态；
- 公网中心必须使用 HTTPS；明文 HTTP 只接受本机、私有局域网或 `.local` 地址；
- 中心 `/health` 会检查数据库并在降级时返回 HTTP 503 与 `Retry-After`。

这些保护用于隔离短时断网、DNS/隧道波动、服务重启、限流、重复请求和错误 Token。它们不能把轻量 SQLite 中心变成生产级多租户云服务。

## 首选建议

### 只在实验室或宿舍使用

使用局域网，零额外费用。

### 需要公网访问，主机电脑可一直开着

有自己的域名时，使用 Cloudflare Named Tunnel。它不要求家庭宽带具有公网 IP，也不需要在路由器开放入站端口。

没有域名、只想先试用时，可以使用 Tailscale Funnel；它会公开一个 HTTPS 地址，因此仍需应用内邀请码和强密码。Tailscale 免费 Personal 计划的成员数有限，10 人团队不宜把“所有成员加入同一个免费 Tailnet”作为长期架构。

### 希望稳定、无需依赖自己的电脑

租用低配 VPS，只部署轻量同行会。科研原文件仍不上传。它适合小团队，不应因部署到 VPS 就被当作规模化云服务。

## 方案 A：局域网

1. 主机直接双击 `ResearchHub-v2.3.0-Windows-x64.exe`；若下载了完整 ZIP，也可双击其中的 `启动联机中心.cmd`；
2. PowerShell 运行 `ipconfig`；
3. 找到 IPv4，例如 `192.168.1.20`；
4. 成员打开 `http://192.168.1.20:5050`；
5. Windows 防火墙只允许专用网络 TCP 5050。

优点：免费、简单、数据不出局域网。

缺点：离开同一网络后无法访问；主机必须开机。

## 方案 B：Cloudflare Named Tunnel

适合有域名并让主机常开的情况。

1. 将域名接入 Cloudflare；
2. 安装 `cloudflared`；
3. 创建命名 Tunnel；
4. 公共主机名指向 `http://localhost:5050`；
5. 可直接双击 `启动HTTPS联机中心.cmd` 并输入公网域名；或手动设置环境变量：

```text
HUB_HTTPS_ONLY=1
HUB_TRUST_PROXY=1
HUB_ALLOWED_HOSTS=hub.example.com
```

6. 保留应用邀请码，也可再使用 Cloudflare Access 限制访问者。

不要长期使用随机 Quick Tunnel 作为正式地址。

## 方案 C：Tailscale Funnel

1. 主机安装并登录 Tailscale；
2. 启动联机中心；
3. 按当前客户端帮助运行 Funnel，例如：

```powershell
tailscale funnel --bg 5050
```

4. 将生成的 HTTPS 地址发给成员；
5. 不使用时关闭 Funnel。

Funnel 是公网入口，而不是只对 Tailnet 私有；不要取消应用内登录。

## 方案 D：VPS

项目提供：

```text
deploy/Dockerfile.hub
deploy/docker-compose.hub.yml
deploy/Caddyfile.example
```

推荐：

- 1 vCPU；
- 1 GB RAM；
- 10–20 GB 本地 SSD；
- Ubuntu LTS；
- Caddy 或 Nginx HTTPS；
- 仅开放 80/443；
- 5050 只绑定 `127.0.0.1`；
- 每日异机备份 `instance/hub.db` 和 `storage/hub_backups/`。

Docker 步骤见 `deploy/README.md`。

## 不推荐

- 路由器直接暴露 5050 到公网；
- 把数据库放进网盘或 NAS 让多人直接打开；
- 用随机 Quick Tunnel 作为长期固定服务；
- 把管理员凭据或 API Token 发在群里；
- 把所有科研原文件上传到这台轻量中心。
