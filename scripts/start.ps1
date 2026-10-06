<#
.SYNOPSIS
    启动企业后台管理系统（本地开发模式）。

.DESCRIPTION
    启动前会自动做三项检查：虚拟环境、Python 依赖、前端依赖；
    缺什么会直接提示你跑 setup.ps1，不会带着半残的环境启动。
    默认开启热重载（改代码即时生效），并用默认浏览器打开首页。

.PARAMETER Port
    监听端口，默认 8000。被占用时换一个即可。

.PARAMETER NoReload
    关闭热重载（更省资源，适合只是演示给别人看）。

.PARAMETER NoBrowser
    启动后不自动打开浏览器。

.EXAMPLE
    .\scripts\start.ps1
    .\scripts\start.ps1 -Port 8080
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$url = "http://127.0.0.1:$Port/"

Write-Host ''
Write-Host '企业后台管理系统 —— 本地启动' -ForegroundColor White

# ------------------------------------------------------------------ 环境检查
if (-not (Test-Path $python)) {
    Write-Host '未找到虚拟环境，请先执行初始化：' -ForegroundColor Red
    Write-Host '    .\scripts\setup.ps1' -ForegroundColor Yellow
    exit 1
}

& $python -c "import fastapi, uvicorn, sqlalchemy, jwt, openpyxl, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Python 依赖不完整，请先执行：' -ForegroundColor Red
    Write-Host '    .\scripts\setup.ps1' -ForegroundColor Yellow
    exit 1
}

$vendorMissing = @()
foreach ($f in @('vue.global.prod.js', 'vue-router.global.prod.js', 'echarts.min.js')) {
    if (-not (Test-Path (Join-Path $root "web\static\vendor\$f"))) { $vendorMissing += $f }
}
if ($vendorMissing.Count -gt 0) {
    Write-Host "缺少前端依赖：$($vendorMissing -join '、')" -ForegroundColor Red
    Write-Host '正在自动补齐 ...' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'fetch_vendor.ps1')
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

if (-not (Test-Path (Join-Path $root 'data\cadmin.db'))) {
    Write-Host '检测到数据库尚未初始化，正在创建并灌入示例数据 ...' -ForegroundColor Yellow
    Push-Location $root
    try {
        $env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONUTF8 = '1'
        & $python -m scripts.seed
    } finally { Pop-Location }
}

# ------------------------------------------------------------------ 端口检查
# 端口被占用时自动往后找一个可用端口。这样即使上一个服务没退干净
# （Windows 上偶尔会留下已终止进程的 LISTENING 表项），也不用手工换端口。
function Test-PortFree([int]$p) {
    # 先用 TCP 连接探测：比 Get-NetTCPConnection 更可靠 ——
    # 已终止进程残留的 LISTENING 表项会让端口无法绑定，但连接测试也会失败
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', $p)
        $client.Close()
        return $false        # 连得上 → 真的有人在监听
    } catch {
        return $true         # 连不上 → 可以拿来绑定
    } finally {
        if ($client) { $client.Dispose() }
    }
}

$requested = $Port
if (-not (Test-PortFree $Port)) {
    Write-Host "端口 $Port 已被占用，尝试自动寻找可用端口 ..." -ForegroundColor Yellow
    $found = $false
    for ($p = $Port + 1; $p -le $Port + 20; $p++) {
        if (Test-PortFree $p) {
            $Port = $p
            $url = "http://127.0.0.1:$Port/"
            $found = $true
            break
        }
    }
    if (-not $found) {
        Write-Host "从 $requested 起的 20 个端口都被占用了，请手动指定：-" -ForegroundColor Red
        Write-Host "    .\scripts\start.ps1 -Port 9000" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "已改用端口 $Port" -ForegroundColor Green
}

# ------------------------------------------------------------------ 启动
Write-Host ''
Write-Host '  访问地址：' -NoNewline; Write-Host $url -ForegroundColor Green
Write-Host '  接口文档：' -NoNewline; Write-Host "${url}docs" -ForegroundColor Green
Write-Host '  演示账号：' -NoNewline
Write-Host 'boss / admin / liqiang / yanglei    密码均为 123456' -ForegroundColor Yellow
Write-Host '            （boss = 老板，全部权限，可直接开除员工）' -ForegroundColor DarkGray
Write-Host ''
Write-Host '  按 Ctrl + C 停止服务' -ForegroundColor DarkGray
Write-Host ('  ' + ('-' * 62)) -ForegroundColor DarkGray
Write-Host ''

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($u)
        Start-Sleep -Seconds 3
        Start-Process $u
    } -ArgumentList $url | Out-Null
}

Push-Location $root
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'
    $args = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    if (-not $NoReload) { $args += '--reload' }
    & $python @args
} finally {
    Pop-Location
}
