"""
老板（boss）角色权限实测：确认"全部权限 + 能直接开除员工"确实落地。

    python -m scripts.test_boss

与 test_admin.py 的区别：这里专门盯新角色容易漏的地方 ——
新增角色必须同时改"后端权限集合""前端菜单可见性""角色标签"三处，
任何一处漏了都会表现为"某个页面看不到"或"某个按钮点了报 403"。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 允许通过环境变量指向非默认端口（与其他测试脚本保持一致）
BASE = os.getenv("CADMIN_BASE_URL", "http://127.0.0.1:8000")
FAILED: list[str] = []


def call(method: str, path: str, token: str | None = None, body=None, form: dict | None = None):
    url = BASE + urllib.parse.quote(path, safe="/?&=%")
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        boundary = "----bosstest" + str(abs(hash(path)) % 99999)
        parts = []
        for k, v in form.items():
            if isinstance(v, tuple):
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                             f"filename=\"{v[0]}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                             .encode() + v[1] + b"\r\n")
            else:
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
                             .encode())
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            try:
                return resp.status, json.loads(payload.decode("utf-8"))
            except Exception:
                return resp.status, f"<{len(payload)} 字节二进制>"
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload.decode("utf-8"))
        except Exception:
            return e.code, {"message": payload[:150].decode("utf-8", "replace")}


def expect(name: str, got, want, detail=None) -> None:
    ok = got == want
    if not ok:
        extra = ""
        if isinstance(detail, dict) and detail.get("message"):
            extra = f" —— {detail['message']}"
        FAILED.append(f"{name}：期望 {want}，实际 {got}{extra}")
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:56s} {got}"
          + (f"   {detail.get('message')}" if not ok and isinstance(detail, dict)
             and detail.get("message") else ""))


def section(title: str) -> None:
    print()
    print("=" * 88)
    print(title)
    print("=" * 88)


def main() -> None:
    print("=" * 88)
    print("老板（boss）角色权限实测")
    print("=" * 88)

    try:
        from scripts.test_cleanup import cleanup
        removed = cleanup(verbose=False)
        if removed:
            print(f"（已清理上一轮残留：{removed}）")
    except Exception as exc:
        print(f"（跳过前置清理：{exc}）")

    TAG = time.strftime("%H%M%S")

    # ------------------------------------------------------------ 登录与身份
    section("【一】老板账号能登录，身份标签正确")
    status, res = call("POST", "/api/login", body={"username": "boss", "password": "123456"})
    expect("老板账号登录", status, 200, res)
    boss = res.get("token", "")
    if not boss:
        print("老板登录失败，后续测试无法进行")
        sys.exit(1)
    _, me = call("GET", "/api/me", token=boss)
    print(f"  身份：{me.get('real_name')} / {me.get('role_label')} / "
          f"{me.get('department_name')} / 角色代码={me.get('role')}")
    expect("角色代码为 boss", me.get("role"), "boss")
    expect("角色标签已识别（不是原始代码）", me.get("role_label"), "老板（董事长/总经理）")

    # ------------------------------------------------------------ 全公司可见
    section("【二】全公司数据可见（与系统管理员同权）")
    _, emps = call("GET", "/api/employees?page=1&size=200", token=boss)
    depts = sorted({e.get("department_name") for e in emps.get("items", [])})
    print(f"  员工 {emps.get('total')} 人，覆盖 {len(depts)} 个部门")
    expect("能看到全部部门", len(depts) >= 9, True)
    with_salary = [e for e in emps.get("items", []) if e.get("salary") is not None]
    expect("薪资全部可见", len(with_salary), emps.get("total"))
    _, reports = call("GET", "/api/reports?page=1&size=50", token=boss)
    print(f"  报告 {reports.get('total')} 份")
    att = call("GET", "/api/attendance/records?page=1&size=200", token=boss)[1]
    att_names = sorted({r.get("employee_name") for r in att.get("items", [])})
    expect("能看到全公司考勤", len(att_names) > 1, True)

    # ------------------------------------------------------------ 管理员专属功能
    section("【三】管理员专属功能（最容易漏配的地方）")
    expect("账号管理：账号列表", call("GET", "/api/users?page=1&size=50", token=boss)[0], 200)
    expect("操作日志：全量查询", call("GET", "/api/logs?page=1&size=10", token=boss)[0], 200)
    expect("操作日志：统计图表", call("GET", "/api/logs/stats?days=7", token=boss)[0], 200)
    expect("员工管理：导出 Excel",
           call("GET", "/api/employees/export/excel", token=boss)[0], 200)
    expect("员工管理：下载导入模板",
           call("GET", "/api/employees/import/template", token=boss)[0], 200)
    expect("公告：可发布",
           call("POST", "/api/announcements", token=boss,
                body={"title": "老板实测公告" + TAG, "content": "测试",
                      "category": "通知", "is_pinned": False, "is_published": True})[0], 200)
    status, u = call("POST", "/api/users", token=boss, body={
        "username": "bosstest_" + TAG, "password": "123456",
        "real_name": "老板实测账号" + TAG, "role": "employee"})
    expect("账号管理：可新建账号", status, 200, u)
    boss_created_user = u.get("id") if isinstance(u, dict) else None
    expect("账号管理：可授予 boss 角色",
           call("PUT", f"/api/users/{boss_created_user}", token=boss,
                body={"role": "boss"})[0] if boss_created_user else 0, 200)

    # ------------------------------------------------------------ 开除员工
    section("【四】核心诉求：能直接开除员工")
    _, dept_list = call("GET", "/api/departments", token=boss)
    target_dept = dept_list["items"][0]["id"] if dept_list.get("items") else None

    status, res = call("POST", "/api/employees", token=boss, body={
        "name": "老板实测待开除员工" + TAG, "department_id": target_dept,
        "position": "临时岗", "hire_date": date.today().isoformat(), "salary": 8000})
    victim_id = res.get("id") if isinstance(res, dict) else None
    expect("先建一个测试员工", status, 200, res)

    if victim_id:
        # 给他开个账号，验证"开除"时账号也被停用
        call("POST", "/api/employees/create-accounts", token=boss,
             body={"ids": [victim_id], "default_password": "123456", "role": "employee"})
        status, res = call("GET", f"/api/employees/{victim_id}", token=boss)
        victim_user = res.get("username") if isinstance(res, dict) else None
        print(f"         └─ 已为其开通账号：{victim_user}")

        status, res = call("DELETE", f"/api/employees/{victim_id}", token=boss)
        expect("★ 开除员工（物理删除）", status, 200, res)
        print(f"         └─ {res.get('message') if isinstance(res, dict) else res}")

        status, res = call("GET", f"/api/employees/{victim_id}", token=boss)
        expect("被开除后档案查不到", status, 404)

        if victim_user:
            _, users = call("GET", f"/api/users?keyword={victim_user}", token=boss)
            if users.get("items"):
                u = users["items"][0]
                expect("被开除员工的原账号已停用", u.get("is_active"), False)
                print(f"         └─ 账号 {u.get('username')} 姓名标记为「{u.get('real_name')}」")
                call("DELETE", f"/api/users/{u['id']}", token=boss)

    # 批量开除
    ids = []
    for i in range(2):
        st, r = call("POST", "/api/employees", token=boss, body={
            "name": f"老板实测批量开除{i}{TAG}", "department_id": target_dept,
            "position": "临时岗", "hire_date": date.today().isoformat()})
        if isinstance(r, dict) and r.get("id"):
            ids.append(r["id"])
    if len(ids) == 2:
        status, res = call("POST", "/api/employees/batch-delete", token=boss, body={"ids": ids})
        expect("★ 批量开除员工", status, 200, res)
        print(f"         └─ {res.get('message') if isinstance(res, dict) else res}")

    # ------------------------------------------------------------ 应有边界
    section("【五】老板也会被拦住的边界（防止把自己锁在系统外）")
    _, me2 = call("GET", "/api/me", token=boss)
    my_uid = me2.get("id")
    status, res = call("DELETE", f"/api/users/{my_uid}", token=boss)
    expect("不能删除自己的账号", status, 400, res)
    status, res = call("PUT", f"/api/users/{my_uid}", token=boss, body={"is_active": False})
    expect("不能停用自己的账号", status, 400, res)

    # ------------------------------------------------------------ 清理
    if boss_created_user:
        call("DELETE", f"/api/users/{boss_created_user}", token=boss)
    if isinstance(res, dict):
        pass

    print()
    print("=" * 88)
    if FAILED:
        print(f"老板权限实测发现 {len(FAILED)} 处不符合预期：")
        for f in FAILED:
            print("  ✗", f)
        print("=" * 88)
        sys.exit(1)
    print("老板角色权限实测全部符合预期 ✅")
    print("=" * 88)


if __name__ == "__main__":
    main()
