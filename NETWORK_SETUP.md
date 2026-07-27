# 问道科研 v1.5 联机说明

## 先看清边界

v1.5 默认选择“未启用”，不会建立同步队列，也不会上传或拉取任何状态。新增的规模化云端 v2 只是接口、事件信封和 OpenAPI 草案，服务器、统一登录与多租户数据库尚未实现。

下面的局域网、隧道和 VPS 方案只用于兼容现有“轻量同行会”，适合小范围自托管，不是成百上千用户的生产架构。要使用它，先在个人节点的“联机扩展”中主动选择“轻量同行会（兼容）”。

## 首选建议

### 只在实验室或宿舍使用

使用局域网，零额外费用。

### 需要公网访问，主机电脑可一直开着

有自己的域名时，使用 Cloudflare Named Tunnel。它不要求家庭宽带具有公网 IP，也不需要在路由器开放入站端口。

没有域名、只想先试用时，可以使用 Tailscale Funnel；它会公开一个 HTTPS 地址，因此仍需应用内邀请码和强密码。Tailscale 免费 Personal 计划的成员数有限，10 人团队不宜把“所有成员加入同一个免费 Tailnet”作为长期架构。

### 希望稳定、无需依赖自己的电脑

租用低配 VPS，只部署轻量同行会。科研原文件仍不上传。它适合小团队，不应因部署到 VPS 就被当作规模化云服务。

## 方案 A：局域网

1. 主机双击 `启动联机中心.cmd`；
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
