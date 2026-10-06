<#
.SYNOPSIS
    一键初始化：安装 Python 依赖、下载前端依赖、建库并灌入示例数据。

.DESCRIPTION
    第一次使用（或换电脑）时执行一次即可。重复执行是安全的：
      · 已有虚拟环境则复用
      · 依赖已装则跳过
      · 数据库已有数据则不会覆盖，需要重灌请加 -ResetData

.PARAMETER Mirror
    pip 镜像源地址，默认清华 TUNA。国内网络建议保持默认。

.PARAMETER ResetData
    清空数据库并重新生成一套示例数据（会删掉你录入的数据，请谨慎）。

.EXAMPLE
    .\scripts\setup.ps1
    .\scripts\setup.ps1 -ResetData
#>
[CmdletBinding()]
param(
    [string]$Mirror = 'https://pypi.tuna.tsinghua.edu.cn/simple',
    [switch]$ResetData
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

function Write-Step([string]$text) {
    Write-Host ''
    Write-Host "==> $text" -ForegroundColor Cyan
}

Write-Host ''
Write-Host '企业后台管理系统 —— 环境初始化' -ForegroundColor White
Write-Host "项目目录：$root" -ForegroundColor DarkGray

# ------------------------------------------------------------------ 1. Python
Write-Step '1/4 检查 Python 环境'
$pyCmd = $null
foreach ($candidate in @('python', 'py')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $pyCmd = $cmd.Source; break }
}
if (-not $pyCmd) {
    Write-Host '未找到 Python，请先安装 Python 3.10+（https://www.python.org/downloads/）' -ForegroundColor Red
    exit 1
}
$version = & $pyCmd --version 2>&1
Write-Host "  使用解释器：$pyCmd（$version）" -ForegroundColor DarkGray

# ------------------------------------------------------------------ 2. venv
Write-Step '2/4 准备虚拟环境 .venv'
if (Test-Path $python) {
    Write-Host '  虚拟环境已存在，直接复用' -ForegroundColor DarkGray
} else {
    & $pyCmd -m venv $venv
    if (-not (Test-Path $python)) { Write-Host '虚拟环境创建失败' -ForegroundColor Red; exit 1 }
    Write-Host '  虚拟环境创建完成' -ForegroundColor Green
}

# ------------------------------------------------------------------ 3. 依赖
Write-Step "3/4 安装 Python 依赖（镜像：$Mirror）"
& $python -m pip config set global.index-url $Mirror | Out-Null
& $python -m pip config set global.trusted-host ([Uri]$Mirror).Host | Out-Null

& $python -m pip install --upgrade pip --quiet --disable-pip-version-check
& $python -m pip install -r (Join-Path $root 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Host '依赖安装失败，请检查网络或更换镜像源：.\scripts\setup.ps1 -Mirror https://mirrors.aliyun.com/pypi/simple/' -ForegroundColor Red
    exit 1
}

& (Join-Path $PSScriptRoot 'fetch_vendor.ps1')
if ($LASTEXITCODE -ne 0) { exit 1 }

# ------------------------------------------------------------------ 4. 数据库
Write-Step '4/4 初始化数据库与示例数据'
Push-Location $root
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'
    if ($ResetData) {
        & $python -m scripts.seed --reset
    } else {
        & $python -m scripts.seed
    }
    if ($LASTEXITCODE -ne 0) { Write-Host '数据库初始化失败' -ForegroundColor Red; exit 1 }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '初始化完成！' -ForegroundColor Green
Write-Host ''
Write-Host '启动系统：' -ForegroundColor White
Write-Host '    .\scripts\start.ps1' -ForegroundColor Yellow
Write-Host ''
