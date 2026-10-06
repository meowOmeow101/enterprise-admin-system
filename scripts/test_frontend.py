"""前端静态资源自检：确认所有 html/css/js 都能被正确提供，且没有 404。

顺带检查两件事：
  1. 前端文件必须是合法 UTF-8（乱码会让页面文字变成问号）
  2. ps1 脚本必须带 UTF-8 BOM（Windows PowerShell 5.1 读无 BOM 的 UTF-8 会按 GBK 解析，
     中文注释会把脚本直接搞成语法错误 —— 这个坑我们踩过）
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent

ASSETS = [
    "/",
    "/index.html",
    "/static/css/app.css",
    "/static/vendor/vue.global.prod.js",
    "/static/vendor/vue-router.global.prod.js",
    "/static/vendor/echarts.min.js",
    "/static/js/api.js",
    "/static/js/utils.js",
    "/static/js/components.js",
    "/static/js/charts.js",
    "/static/js/app.js",
    "/static/js/pages/dashboard.js",
    "/static/js/pages/employees.js",
    "/static/js/pages/departments.js",
    "/static/js/pages/projects.js",
    "/static/js/pages/reports.js",
    "/static/js/pages/attendance.js",
    "/static/js/pages/leaves.js",
    "/static/js/pages/announcements.js",
    "/static/js/pages/logs.js",
    "/static/js/pages/profile.js",
    "/static/js/pages/accounts.js",
]

# 页面里声明的全局对象，用来确认每个页面文件都真的注册了对应组件
EXPECTED_GLOBALS = {
    "/static/js/pages/dashboard.js": "PageDashboard",
    "/static/js/pages/employees.js": "PageEmployees",
    "/static/js/pages/departments.js": "PageDepartments",
    "/static/js/pages/projects.js": "PageProjects",
    "/static/js/pages/reports.js": "PageReports",
    "/static/js/pages/attendance.js": "PageAttendance",
    "/static/js/pages/leaves.js": "PageLeaves",
    "/static/js/pages/announcements.js": "PageAnnouncements",
    "/static/js/pages/logs.js": "PageLogs",
    "/static/js/pages/profile.js": "PageProfile",
    "/static/js/pages/accounts.js": "PageAccounts",
}

problems: list[str] = []

print("=" * 70)
print("前端静态资源自检")
print("=" * 70)

for path in ASSETS:
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            body = r.read()
            size = len(body)
            status = r.status
    except urllib.error.HTTPError as e:
        problems.append(f"{path} -> HTTP {e.code}")
        print(f"  [FAIL] {path:48s} HTTP {e.code}")
        continue
    except Exception as e:
        problems.append(f"{path} -> {e}")
        print(f"  [FAIL] {path:48s} {e}")
        continue

    ok = status == 200 and size > 0
    # 页面脚本必须真的注册自己的全局组件，否则路由会渲染空白
    if path in EXPECTED_GLOBALS:
        name = EXPECTED_GLOBALS[path]
        marker = f"window.{name}"
        if marker.encode() not in body:
            ok = False
            problems.append(f"{path} 未注册 {marker}")
    print(f"  [{'OK' if ok else 'FAIL'}]   {path:48s} {size:>9,} bytes")

# 种子报告文件是否可访问（这些是真实生成的 PDF）
print("\n--- 抽查示例报告文件 ---")
import json

req = urllib.request.Request(BASE + "/api/login",
                             data=json.dumps({"username": "admin", "password": "123456"}).encode(),
                             headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(req, timeout=20).read())["token"]

req = urllib.request.Request(BASE + "/api/reports?page=1&size=3",
                             headers={"Authorization": "Bearer " + token})
reports = json.loads(urllib.request.urlopen(req, timeout=20).read())["items"]
for rep in reports:
    try:
        code, blob = None, None
        req = urllib.request.Request(BASE + f"/api/reports/{rep['id']}/download",
                                     headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=30) as r:
            blob = r.read()
            code = r.status
        is_pdf = blob[:4] == b"%PDF"
        print(f"  [{'OK' if is_pdf else 'FAIL'}]   {rep['title'][:34]:36s} "
              f"{rep['file_name'][:22]:24s} {len(blob):>7,} bytes  PDF={is_pdf}")
        if not is_pdf:
            problems.append(f"报告 {rep['id']} 下载内容不是 PDF")
    except Exception as e:
        problems.append(f"报告 {rep['id']} 下载失败：{e}")
        print(f"  [FAIL] 报告 {rep['id']} 下载失败：{e}")

print()
print("--- 文件编码检查 ---")
encoding_problems: list[str] = []

frontend_files = ([ROOT / "web" / "index.html"]
                  + sorted((ROOT / "web" / "static").rglob("*.js"))
                  + sorted((ROOT / "web" / "static" / "css").glob("*.css")))
bad_utf8 = 0
for path in frontend_files:
    try:
        text = path.read_bytes().decode("utf-8")
        if "\ufffd" in text:
            bad_utf8 += 1
            encoding_problems.append(f"{path.name} 含替换字符 U+FFFD（编码可能被破坏）")
    except UnicodeDecodeError as exc:
        bad_utf8 += 1
        encoding_problems.append(f"{path.name} 不是合法 UTF-8：{exc}")
print(f"  前端文件 {len(frontend_files)} 个，编码异常 {bad_utf8} 个")

ps_files = sorted((ROOT / "scripts").glob("*.ps1"))
missing_bom = []
for path in ps_files:
    if path.read_bytes()[:3] != b"\xef\xbb\xbf":
        missing_bom.append(path.name)
if missing_bom:
    encoding_problems.append(
        "以下 ps1 脚本缺少 UTF-8 BOM，Windows PowerShell 5.1 会按 GBK 解析导致语法错误："
        + "、".join(missing_bom))
print(f"  PowerShell 脚本 {len(ps_files)} 个，缺 BOM {len(missing_bom)} 个")

for p in encoding_problems:
    problems.append(p)

print()
print("=" * 70)
if problems:
    print(f"发现 {len(problems)} 个问题：")
    for p in problems:
        print("  ✗", p)
    sys.exit(1)
print("全部静态资源与示例文件检查通过")
print("=" * 70)
