<#
.SYNOPSIS
    下载前端依赖（Vue 3 / Vue Router / ECharts）到本地 static/vendor 目录。

.DESCRIPTION
    系统刻意不引 CDN —— 这三个文件放到本地后，整个后台断网也能正常打开。
    优先用国内 CDN，失败时自动切换备用源。

.EXAMPLE
    .\scripts\fetch_vendor.ps1
    .\scripts\fetch_vendor.ps1 -Force     # 强制重新下载
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$vendorDir = Join-Path $root 'web\static\vendor'
if (-not (Test-Path $vendorDir)) { New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null }

# 每个文件给出多个来源，按顺序尝试
$targets = @(
    @{
        Name = 'vue.global.prod.js'
        Urls = @(
            'https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.global.prod.js',
            'https://unpkg.com/vue@3.5.13/dist/vue.global.prod.js',
            'https://registry.npmmirror.com/vue/3.5.13/files/dist/vue.global.prod.js'
        )
        MinKB = 100
    },
    @{
        Name = 'vue-router.global.prod.js'
        Urls = @(
            'https://cdn.jsdelivr.net/npm/vue-router@4.5.0/dist/vue-router.global.prod.js',
            'https://unpkg.com/vue-router@4.5.0/dist/vue-router.global.prod.js',
            'https://registry.npmmirror.com/vue-router/4.5.0/files/dist/vue-router.global.prod.js'
        )
        MinKB = 15
    },
    @{
        Name = 'echarts.min.js'
        Urls = @(
            'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js',
            'https://unpkg.com/echarts@5.5.1/dist/echarts.min.js',
            'https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js'
        )
        MinKB = 600
    }
)

$failed = @()

foreach ($t in $targets) {
    $out = Join-Path $vendorDir $t.Name

    if ((Test-Path $out) -and -not $Force) {
        $kb = [math]::Round((Get-Item $out).Length / 1KB, 1)
        if ($kb -ge $t.MinKB) {
            Write-Host ("  [跳过] {0} 已存在（{1} KB）" -f $t.Name, $kb) -ForegroundColor DarkGray
            continue
        }
    }

    $done = $false
    foreach ($url in $t.Urls) {
        try {
            Invoke-WebRequest -Uri $url -OutFile $out -TimeoutSec 90 -UseBasicParsing
            $kb = [math]::Round((Get-Item $out).Length / 1KB, 1)
            if ($kb -lt $t.MinKB) { throw "文件过小（$kb KB），可能下载不完整" }
            Write-Host ("  [完成] {0}  {1} KB" -f $t.Name, $kb) -ForegroundColor Green
            $done = $true
            break
        } catch {
            Write-Host ("  [重试] {0} 源失败：{1}" -f $t.Name, $_.Exception.Message) -ForegroundColor DarkYellow
        }
    }
    if (-not $done) { $failed += $t.Name }
}

Write-Host ''
if ($failed.Count -gt 0) {
    Write-Host "以下前端依赖下载失败：$($failed -join '、')" -ForegroundColor Red
    Write-Host '请检查网络后重新执行本脚本；也可以手动下载同名文件放入：' -ForegroundColor Yellow
    Write-Host "  $vendorDir" -ForegroundColor Yellow
    exit 1
}
Write-Host '前端依赖已就绪（本地文件，无需联网即可运行）' -ForegroundColor Green
