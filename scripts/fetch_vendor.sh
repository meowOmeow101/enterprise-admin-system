#!/usr/bin/env bash
# 下载前端依赖（Vue / Vue Router / ECharts）到 web/static/vendor。
# 这些文件本地化后，整个系统断网也能正常打开。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/web/static/vendor"
mkdir -p "$VENDOR"

fetch() {
  local name="$1" min_kb="$2"; shift 2
  local out="$VENDOR/$name"
  if [ -f "$out" ] && [ "$(du -k "$out" | cut -f1)" -ge "$min_kb" ]; then
    echo "  [跳过] $name 已存在"
    return 0
  fi
  for url in "$@"; do
    if curl -fsSL --max-time 90 "$url" -o "$out"; then
      local kb; kb=$(du -k "$out" | cut -f1)
      if [ "$kb" -ge "$min_kb" ]; then
        echo "  [完成] $name  ${kb} KB"
        return 0
      fi
      echo "  [重试] $name 文件不完整（${kb} KB）"
    else
      echo "  [重试] $name 下载失败：$url"
    fi
  done
  echo "  [失败] $name 所有来源均不可用" >&2
  return 1
}

echo "下载前端依赖 ..."
fetch vue.global.prod.js 100 \
  https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.global.prod.js \
  https://unpkg.com/vue@3.5.13/dist/vue.global.prod.js \
  https://registry.npmmirror.com/vue/3.5.13/files/dist/vue.global.prod.js
fetch vue-router.global.prod.js 15 \
  https://cdn.jsdelivr.net/npm/vue-router@4.5.0/dist/vue-router.global.prod.js \
  https://unpkg.com/vue-router@4.5.0/dist/vue-router.global.prod.js \
  https://registry.npmmirror.com/vue-router/4.5.0/files/dist/vue-router.global.prod.js
fetch echarts.min.js 600 \
  https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js \
  https://unpkg.com/echarts@5.5.1/dist/echarts.min.js \
  https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js

echo "前端依赖已就绪"