$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/yanjj5521/research-cultivation-os.git'
$Branch = 'main'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host '问道科研 v1.2 - GitHub 一键上传' -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '未检测到 Git。' -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host '正在通过 winget 安装 Git for Windows...'
        winget install --id Git.Git -e --source winget
        Write-Host 'Git 安装完成。请关闭本窗口，再次双击上传脚本。' -ForegroundColor Yellow
        Read-Host '按回车退出'
        exit 0
    }
    throw '请先安装 Git for Windows：https://git-scm.com/download/win'
}

Set-Location $Root

# Safety check: never upload runtime/user data.
$Forbidden = @(
    'instance\research_os.db',
    'instance\hub.db',
    'storage\uploads',
    'storage\backups',
    'storage\hub_backups',
    'HUB_ADMIN_CREDENTIALS.txt',
    '.env'
)
foreach ($item in $Forbidden) {
    if (Test-Path (Join-Path $Root $item)) {
        throw "安全检查失败：上传包中出现不应上传的路径 $item"
    }
}

if (-not (Test-Path (Join-Path $Root '.git'))) {
    git init
    git branch -M $Branch
    git remote add origin $RepoUrl
} else {
    git remote set-url origin $RepoUrl
}

# Preserve the existing remote README commit, then overlay the complete source.
git fetch origin $Branch
try {
    git reset --soft "origin/$Branch"
} catch {
    Write-Host '远端分支为空，将创建首次提交。'
}

git add --all
if (-not (git config user.name)) { git config user.name 'yanjj5521' }
if (-not (git config user.email)) { git config user.email '957270512@qq.com' }

$changes = git status --porcelain
if (-not $changes) {
    Write-Host '没有需要上传的新改动。' -ForegroundColor Green
} else {
    git commit -m 'Publish Research Cultivation OS v1.2 source'
}

Write-Host '即将推送到 GitHub。首次操作可能弹出浏览器登录窗口。' -ForegroundColor Yellow
git push -u origin $Branch
Write-Host '上传完成：https://github.com/yanjj5521/research-cultivation-os' -ForegroundColor Green
Read-Host '按回车退出'
