<#
.SYNOPSIS
    自测：后端接口冒烟测试 + 角色权限实测 + 前端静态资源检查 + 真实浏览器渲染验证。

.DESCRIPTION
    需要先启动服务（.\scripts\start.ps1，另开一个窗口）。
    冒烟测试与权限测试都会自动清理自己产生的数据，可以反复执行。

.PARAMETER SkipSmoke
    跳过后端接口与权限测试，只跑前端相关检查。

.PARAMETER SkipBrowser
    跳过浏览器渲染测试（本机没装 Chrome/Edge 时用得上）。

.EXAMPLE
    .\scripts\test.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipSmoke,
    [switch]$SkipBrowser,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host '未找到虚拟环境，请先执行 .\scripts\setup.ps1' -ForegroundColor Red
    exit 1
}

# 服务探测
$env:CADMIN_BASE_URL = "http://127.0.0.1:$Port"
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 6
} catch {
    Write-Host "检测到 http://127.0.0.1:$Port 上没有运行的服务。" -ForegroundColor Red
    Write-Host '请先在另一个窗口执行：.\scripts\start.ps1' -ForegroundColor Yellow
    exit 1
}

Push-Location $root
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

    $code = 0
    if (-not $SkipSmoke) {
        & $python -m scripts.test_api
        if ($LASTEXITCODE -ne 0) { $code = 1 }
        & $python -m scripts.test_permissions
        if ($LASTEXITCODE -ne 0) { $code = 1 }
        & $python -m scripts.test_admin
        if ($LASTEXITCODE -ne 0) { $code = 1 }
        & $python -m scripts.test_boss
        if ($LASTEXITCODE -ne 0) { $code = 1 }
    }
    & $python -m scripts.test_frontend
    if ($LASTEXITCODE -ne 0) { $code = 1 }
    if (-not $SkipBrowser) {
        & $python -m scripts.test_browser
        if ($LASTEXITCODE -ne 0) { $code = 1 }
    }

    Write-Host ''
    if ($code -eq 0) {
        Write-Host '自测全部通过 ✅' -ForegroundColor Green
    } else {
        Write-Host '自测存在失败项，请查看上方输出 ❌' -ForegroundColor Red
    }
    exit $code
} finally {
    Pop-Location
}
