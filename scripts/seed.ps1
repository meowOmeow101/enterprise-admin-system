<#
.SYNOPSIS
    重置示例数据 / 重新灌库。

.DESCRIPTION
    -Reset 会清空所有业务数据并重新生成一套演示数据（适合演示前恢复干净状态）。
    不加 -Reset 时只在数据库为空时初始化。

.EXAMPLE
    .\scripts\seed.ps1 -Reset
#>
[CmdletBinding()]
param(
    [switch]$Reset
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host '未找到虚拟环境，请先执行 .\scripts\setup.ps1' -ForegroundColor Red
    exit 1
}

if ($Reset) {
    Write-Host '注意：-Reset 会清空数据库中的所有业务数据（员工、项目、报告、考勤等）' -ForegroundColor Yellow
    $answer = Read-Host '确认继续？输入 y 回车执行'
    if ($answer -ne 'y' -and $answer -ne 'Y') {
        Write-Host '已取消' -ForegroundColor DarkGray
        exit 0
    }
}

Push-Location $root
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'
    if ($Reset) {
        & $python -m scripts.seed --reset
    } else {
        & $python -m scripts.seed
    }
} finally {
    Pop-Location
}
