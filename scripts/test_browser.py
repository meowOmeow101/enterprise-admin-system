"""
用真实浏览器（Edge / Chrome 无头模式）跑一遍前端，确认没有渲染错误或控制台报错。

    python -m scripts.test_browser            # 或跑全部自测：.\\scripts\\test.ps1
    python -m scripts.test_browser --keep     # 保留截图便于人工查看

为什么需要它：静态资源检查只能证明文件能下载，证明不了 Vue 能挂载成功、页面不报错。
它做三件事：
  1. 真实渲染 12 个页面，确认 Vue 挂载成功且没有 JS 报错
  2. 用全新浏览器环境验证"首次访问必须显示登录页"
  3. 在浏览器里真实请求 10 个核心接口，确认登录后数据能取到
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("CADMIN_BASE_URL", "http://127.0.0.1:8000")
SHOT_DIR = ROOT / "data" / "screenshots"

# 要访问的页面（hash 路由）
PAGES = [
    ("/", "登录页"),
    ("/#/dashboard", "数据看板"),
    ("/#/projects", "项目管理"),
    ("/#/reports", "报告管理"),
    ("/#/employees", "员工管理"),
    ("/#/departments", "部门架构"),
    ("/#/attendance", "考勤打卡"),
    ("/#/leaves", "请假审批"),
    ("/#/announcements", "公告通知"),
    ("/#/profile", "个人中心"),
    ("/#/accounts", "账号管理"),
    ("/#/logs", "操作日志"),
]


def find_browser() -> str | None:
    """找本机可用的 Chromium 内核浏览器。"""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def dump_dom(browser: str, url: str, wait_ms: int = 3500, tmpdir: str | None = None) -> tuple[str, str]:
    """
    用无头浏览器渲染页面并导出 DOM。

    注意：Windows 上 Chrome/Edge 的 --dump-dom 结果走的是 **stderr** 而不是 stdout，
    所以这里把两个流都收下来合并，否则会读到空字符串而误判成"页面没渲染"。

    tmpdir 复用同一个浏览器 profile，这样 localStorage 里的登录令牌能带到下一个页面。
    """
    with tempfile.TemporaryDirectory(prefix="cadmin_browser_") as own_tmp:
        profile = tmpdir or own_tmp
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-sync",
            "--hide-scrollbars",
            "--window-size=1600,1000",
            "--virtual-time-budget=" + str(wait_ms),
            f"--user-data-dir={profile}",
            "--dump-dom",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        stdout = proc.stdout.decode("utf-8", "replace")
        stderr = proc.stderr.decode("utf-8", "replace")
        if "<html" in stdout.lower():
            html = stdout
        elif "<html" in stderr.lower():
            html = stderr
        else:
            html = stdout + "\n" + stderr
        return html, stderr


def seed_login_state(browser: str, token: str, profile: str) -> bool:
    """
    把访问令牌写进浏览器的 localStorage，使后续页面访问带登录态。

    无头浏览器每次调用都是独立进程，localStorage 不会自动共享，
    所以要先用一个同源页面把令牌塞进去。这里在 web/static 下临时建一个页面，
    用完立刻删除 —— 既保证同源（能写 localStorage），又不往项目里留测试附件。
    """
    seed_path = ROOT / "web" / "static" / "_tmp_seed.html"
    seed_path.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
        "<pre id='seed'>PENDING</pre><script>"
        "try{"
        f"localStorage.setItem('cadmin.token', {json.dumps(token)});"
        "localStorage.removeItem('cadmin.user');"
        "document.getElementById('seed').textContent='SEED_OK';"
        "}catch(e){document.getElementById('seed').textContent='SEED_FAIL '+e.message;}"
        "</script></body></html>",
        encoding="utf-8",
    )
    try:
        html, _ = dump_dom(browser, BASE + "/static/_tmp_seed.html",
                           wait_ms=1500, tmpdir=profile)
        ok = "SEED_OK" in html
        if not ok:
            print(f"  [警告] 登录态注入失败：{html[:150]}")
        else:
            print("  已注入登录态（localStorage 中的访问令牌）")
        return ok
    finally:
        seed_path.unlink(missing_ok=True)


def check_topbar_user(browser: str, token: str, profile: str) -> bool:
    """
    专门验证顶栏显示的是真实登录用户，而不是"未登录"。

    这是一个真实踩过的 bug：登录成功后顶栏仍显示"未登录 / 普通员工 · 未分配部门"，
    原因是根组件用 data() 按值拷贝了用户对象，登录时的重新赋值没有传导过去。
    所以这里不看"页面能不能打开"，而是直接断言顶栏里出现了账号姓名与角色。
    """
    req = urllib.request.Request(BASE + "/api/me",
                                 headers={"Authorization": "Bearer " + token})
    me = json.loads(urllib.request.urlopen(req, timeout=20).read())
    name, role_label = me.get("real_name", ""), me.get("role_label", "")

    ok = True
    for path in ("/#/dashboard", "/#/accounts"):
        html, _ = dump_dom(browser, BASE + path, tmpdir=profile)
        has_name = name in html
        has_role = role_label in html or me.get("role") == "boss" and "👑 老板" in html
        not_guest = "未登录" not in html
        passed = has_name and has_role and not_guest
        ok = ok and passed
        print(f"  [{'OK  ' if passed else 'FAIL'}] 顶栏身份 {path:16s} "
              f"姓名「{name}」{'✓' if has_name else '✗'} "
              f"角色「{role_label}」{'✓' if has_role else '✗'} "
              f"无未登录字样 {'✓' if not_guest else '✗'}")
        if not passed:
            problems_hint = (f"{path} 顶栏身份显示不正确：姓名={has_name} "
                             f"角色={has_role} 无未登录={not_guest}")
            print(f"         └─ {problems_hint}")
    return ok


def main() -> None:
    keep = "--keep" in sys.argv

    print("=" * 74)
    print("前端浏览器渲染自测")
    print("=" * 74)

    browser = find_browser()
    if not browser:
        print("未找到 Edge / Chrome，跳过浏览器测试")
        print("（本机没有 Chromium 内核浏览器时，可忽略这一步）")
        return
    print(f"浏览器：{browser}")

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []

    # 先登录并把令牌注入浏览器，否则每个业务页面都会被路由守卫重定向到登录页，
    # 看起来像"渲染失败"，实际是没登录。
    token = login()
    if not token:
        problems.append("登录接口不可用，无法验证登录后的页面")
        print("  [FAIL] 登录失败，跳过登录态页面验证\n")
    else:
        profile = tempfile.mkdtemp(prefix="cadmin_profile_")
        try:
            authenticated = seed_login_state(browser, token, profile)
            if not authenticated:
                problems.append("登录态注入失败，业务页面会被重定向到登录页")
        except Exception as exc:
            authenticated = False
            profile = None
            problems.append(f"登录态注入异常：{exc}")
    print()

    try:
        for path, name in PAGES:
            url = BASE + path
            try:
                html, stderr = dump_dom(browser, url, tmpdir=profile if token else None)
            except subprocess.TimeoutExpired:
                problems.append(f"{name}（{path}）渲染超时")
                print(f"  [FAIL] {name:12s} 渲染超时")
                continue

            size = len(html)
            # 页面内置的错误采集器会把 JS 报错写进 #error-collector，这里读出来
            render_errors = ""
            if 'id="error-collector"' in html:
                tail = html.split('id="error-collector"', 1)[1]
                render_errors = tail.split(">", 1)[1].split("</pre>", 1)[0].strip() \
                    if ">" in tail else ""

            checks = {
                "有 DOM 内容": size > 2500,
                "Vue 已挂载": "boot-screen" not in html and "BOOT_OK" in html,
                "无 JS 报错": "RENDER_ERRORS=" not in render_errors,
            }
            ok = all(checks.values())
            if not ok:
                detail = ", ".join(k for k, v in checks.items() if not v)
                problems.append(f"{name}（{path}）: {detail}"
                                + (f" | {render_errors[:200]}" if render_errors else ""))

            # 页面级关键字，确认渲染的确实是对应页面而不是被踢回登录页
            expect = {
                "/": "企业后台管理系统",
                "/#/dashboard": "数据看板",
                "/#/projects": "项目",
                "/#/reports": "报告",
                "/#/employees": "员工",
                "/#/departments": "组织架构",
                "/#/attendance": "考勤",
                "/#/leaves": "请假",
                "/#/announcements": "公告",
                "/#/profile": "个人中心",
                "/#/accounts": "账号",
                "/#/logs": "日志",
            }[path]
            has_keyword = expect in html
            if not has_keyword:
                problems.append(f"{name}（{path}）: 页面未出现关键字「{expect}」")
                ok = False

            flag = "OK  " if ok else "FAIL"
            print(f"  [{flag}] {name:12s} {path:16s} DOM {size:>7,} 字节 "
                  f"关键字「{expect}」{'✓' if has_keyword else '✗'}")
    finally:
        if token and profile:
            shutil.rmtree(profile, ignore_errors=True)



    # ------------------------------------------------------------ 未登录场景
    # 重要：首次访问系统必须是登录页。这里用全新 profile（无令牌）单独验证一次，
    # 否则"登录页空白"这种致命问题会被登录态测试掩盖过去。
    print("\n--- 未登录场景（全新浏览器环境）---")
    fresh = tempfile.mkdtemp(prefix="cadmin_fresh_")
    try:
        html, _ = dump_dom(browser, BASE + "/", tmpdir=fresh)
        has_login = ("请输入用户名" in html and "演示账号" in html)
        mounted = "boot-screen" not in html and "BOOT_OK" in html
        render_errors = ""
        if 'id="error-collector"' in html:
            tail = html.split('id="error-collector"', 1)[1]
            render_errors = tail.split(">", 1)[1].split("</pre>", 1)[0].strip() if ">" in tail else ""
        no_error = "RENDER_ERRORS=" not in render_errors
        ok = has_login and mounted and no_error
        if not ok:
            problems.append("未登录访问首页未正确显示登录页："
                            f"登录表单={has_login} 已挂载={mounted} 无报错={no_error}"
                            + (f" | {render_errors[:200]}" if render_errors else ""))
        print(f"  [{'OK  ' if ok else 'FAIL'}] 首次访问显示登录页 "
              f"（表单 {'✓' if has_login else '✗'} / 挂载 {'✓' if mounted else '✗'} / "
              f"无报错 {'✓' if no_error else '✗'}）")
    finally:
        shutil.rmtree(fresh, ignore_errors=True)

    # ------------------------------------------------------------ 顶栏身份显示
    # 回归验证：登录后顶栏必须显示真实姓名与角色（曾经错显为"未登录"）
    if token and profile:
        print("\n--- 顶栏身份显示（登录后不得显示「未登录」）---")
        if not check_topbar_user(browser, token, profile):
            problems.append("顶栏未正确显示登录用户信息（可能又退回到按值拷贝用户状态）")

        # 顺手验证老板角色的顶栏徽标：老板能进"系统管理"菜单这一条最容易漏配
        boss_token = login("boss")
        if boss_token:
            boss_profile = tempfile.mkdtemp(prefix="cadmin_boss_")
            try:
                if seed_login_state(browser, boss_token, boss_profile):
                    print("  （以下为老板账号 boss 的顶栏与系统管理页验证）")
                    if not check_topbar_user(browser, boss_token, boss_profile):
                        problems.append("老板账号顶栏显示不正确")
                    html, _ = dump_dom(browser, BASE + "/#/accounts", tmpdir=boss_profile)
                    has_menu = "账号管理" in html and "操作日志" in html
                    has_page = "登录用户名" in html or "新建账号" in html
                    if not (has_menu and has_page):
                        problems.append(f"老板看不到系统管理功能：菜单={has_menu} 页面={has_page}")
                    print(f"  [{'OK  ' if has_menu and has_page else 'FAIL'}] "
                          f"老板可进入账号管理页（菜单 {'✓' if has_menu else '✗'} / "
                          f"页面内容 {'✓' if has_page else '✗'}）")
            finally:
                shutil.rmtree(boss_profile, ignore_errors=True)
        else:
            print("  （未取到老板账号令牌，跳过老板顶栏验证）")

    # ------------------------------------------------------------ 用真实登录态再跑一遍
    # 这一步验证"登录之后各接口在浏览器里确实能拿到数据"，
    # 与前面的渲染测试互补：渲染只证明页面能画出来，这里证明数据能取到。
    print("\n--- 使用真实登录态验证核心接口（浏览器内真实请求）---")
    token = login()
    if not token:
        problems.append("无法登录，跳过登录态接口验证")
        print("  [FAIL] 登录接口不可用")
    else:
        probe = ROOT / "web" / "static" / "_probe_api.html"
        # 用 Python 写入（保证 UTF-8 无 BOM），令牌通过 URL hash 传入，不落到服务端日志
        probe.write_text(PROBE_HTML, encoding="utf-8")
        try:
            url = f"{BASE}/static/_probe_api.html#{token}"
            html, _ = dump_dom(browser, url, wait_ms=8000)
            results = {}
            marker = "PROBE_RESULT="
            if marker in html:
                raw = (html.split(marker, 1)[1].split("</pre>", 1)[0]
                       .replace("&quot;", '"').replace("&amp;", "&")
                       .replace("&lt;", "<").replace("&gt;", ">"))
                try:
                    results = json.loads(raw)
                except Exception as exc:
                    problems.append(f"登录态探测结果无法解析：{exc} —— 原始内容 {raw[:200]}")

            if not results:
                problems.append("登录态探测没有返回结果（页面脚本可能被浏览器拦截）")
                print("  [FAIL] 未取到探测结果")
            else:
                for api_name, info in results.items():
                    ok = info.get("status") == 200
                    if not ok:
                        problems.append(f"{api_name} 在浏览器中请求失败：{info}")
                    print(f"  [{'OK  ' if ok else 'FAIL'}] {api_name:22s} "
                          f"HTTP {info.get('status')}  {str(info.get('summary'))[:60]}")
        finally:
            probe.unlink(missing_ok=True)

    if not keep:
        shutil.rmtree(SHOT_DIR, ignore_errors=True)

    print()
    print("=" * 74)
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for p in problems:
            print("  ✗", p)
        print("=" * 74)
        sys.exit(1)
    print("浏览器渲染自测全部通过 ✅")
    print("=" * 74)


def login(username: str = "admin", password: str = "123456") -> str:
    try:
        req = urllib.request.Request(
            BASE + "/api/login",
            data=json.dumps({"username": username, "password": password}).encode(),
            headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())["token"]
    except Exception:
        return ""


# 一个独立探针页面：带着令牌去请求几个核心接口，把结果写进 DOM 供脚本读取。
# 由本脚本在运行时写入 web/static/ 下，跑完即删 —— 这样它是同源的，
# 不会遇到 file:// 页面请求 http 接口被浏览器拦截的问题。
PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>api probe</title></head>
<body>
<pre id="out">PROBE_RESULT={}</pre>
<script>
// 令牌通过 URL hash 传入，不经过服务端，也不落日志
const TOKEN = decodeURIComponent(location.hash.replace(/^#/, ""));
const tasks = {
  "看板总览": "/dashboard/overview",
  "员工列表": "/employees?page=1&size=5",
  "项目列表": "/projects?page=1&size=5",
  "报告列表": "/reports?page=1&size=5",
  "部门树": "/departments/tree",
  "我的考勤": "/attendance/today",
  "请假待审批": "/leaves?scope=pending",
  "公告列表": "/announcements",
  "操作日志": "/logs?page=1&size=5",
  "账号列表": "/users?page=1&size=5"
};
(async () => {
  const out = {};
  for (const [name, path] of Object.entries(tasks)) {
    try {
      const res = await fetch("/api" + path, { headers: { Authorization: "Bearer " + TOKEN } });
      const body = await res.json().catch(() => null);
      let summary = "";
      if (body) {
        if (body.total !== undefined) summary = "total=" + body.total;
        else if (body.items !== undefined) summary = "items=" + body.items.length;
        else if (body.employee) summary = "员工=" + body.employee.total + " 项目=" + body.project.total;
        else if (body.status) summary = "status=" + body.status;
        else summary = JSON.stringify(body).slice(0, 60);
      }
      out[name] = { status: res.status, summary };
    } catch (e) {
      out[name] = { status: 0, summary: String(e) };
    }
  }
  document.getElementById("out").textContent = "PROBE_RESULT=" + JSON.stringify(out);
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
