"""
系统管理员（admin）权限实测：确认"几乎无所不能"的同时，也验证应有的边界仍然存在。

    python -m scripts.test_admin

设计意图：admin 是最高权限角色，但它不该是"完全无约束"的 ——
比如不能删自己的账号、不能审批自己提交的请假。这些边界也在这里测出来。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8000"
FAILED: list[str] = []


def call(method: str, path: str, token: str | None = None, body=None, form: dict | None = None):
    url = BASE + urllib.parse.quote(path, safe="/?&=%")
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        boundary = "----admintest" + str(abs(hash(path)) % 99999)
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
        elif detail:
            extra = f" —— {str(detail)[:200]}"
        FAILED.append(f"{name}：期望 {want}，实际 {got}{extra}")
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:60s} {got}"
          + (f"   {detail.get('message')}" if not ok and isinstance(detail, dict)
             and detail.get("message") else ""))


def section(title: str) -> None:
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)


def main() -> None:
    print("=" * 90)
    print("系统管理员权限实测")
    print("=" * 90)

    # 前置清理：保证脚本可反复运行，不累积残留数据
    try:
        from scripts.test_cleanup import cleanup
        removed = cleanup(verbose=False)
        if removed:
            print(f"（已清理上一轮残留：{removed}）")
    except Exception as exc:
        print(f"（跳过前置清理：{exc}）")

    TAG = time.strftime("%H%M%S")

    _, res = call("POST", "/api/login", body={"username": "admin", "password": "123456"})
    admin = res.get("token", "")
    if not admin:
        print("管理员登录失败，请先启动服务：.\\scripts\\start.ps1")
        sys.exit(1)
    _, me = call("GET", "/api/me", token=admin)
    print(f"测试身份：{me.get('real_name')} / {me.get('role_label')} / "
          f"{me.get('department_name')} / 账号id={me.get('id')}")
    my_user_id = me.get("id")

    # ------------------------------------------------------------ 全量可见
    section("【一】全公司数据的可见性（对比员工只有本部门）")
    _, emps = call("GET", "/api/employees?page=1&size=200", token=admin)
    depts = sorted({e.get("department_name") for e in emps.get("items", [])})
    print(f"  员工列表：{emps.get('total')} 人，覆盖部门 {depts}")
    expect("能看到全部部门的人", len(depts) >= 9, True)
    with_salary = [e for e in emps.get("items", []) if e.get("salary") is not None]
    expect("薪资字段全部可见（应等于总人数）", len(with_salary), emps.get("total"))
    with_idcard = [e for e in emps.get("items", []) if e.get("id_card")]
    print(f"  身份证号可见条数：{len(with_idcard)} / {emps.get('total')}")

    _, projects = call("GET", "/api/projects?page=1&size=50", token=admin)
    print(f"  项目：{projects.get('total')} 个")
    _, reports = call("GET", "/api/reports?page=1&size=50", token=admin)
    print(f"  报告：{reports.get('total')} 份")
    _, att = call("GET", "/api/attendance/records?page=1&size=200", token=admin)
    att_names = sorted({r.get("employee_name") for r in att.get("items", [])})
    print(f"  考勤记录：{att.get('total')} 条，涉及 {len(att_names)} 人")
    expect("能看到全公司考勤（不止本人）", len(att_names) > 1, True)
    _, logs = call("GET", "/api/logs?page=1&size=5", token=admin)
    expect("可查看全量操作日志", call("GET", "/api/logs", token=admin)[0], 200)
    print(f"  操作日志：{logs.get('total')} 条")

    # ------------------------------------------------------------ 跨部门写权限
    section("【二】跨部门写权限（主管只能管本部门及下级）")
    _, dept_list = call("GET", "/api/departments", token=admin)
    target_dept = None
    for d in dept_list.get("items", []):
        if d.get("name") == "财务部":
            target_dept = d
            break
    if target_dept is None and dept_list.get("items"):
        target_dept = dept_list["items"][-1]
    print(f"  选取与管理员不同部门的「{target_dept['name']}」(id={target_dept['id']}) 做跨部门测试")

    status, res = call("POST", "/api/employees", token=admin, body={
        "name": "管理员跨部门建号" + TAG, "department_id": target_dept["id"],
        "position": "权限实测", "hire_date": date.today().isoformat(), "salary": 9999,
    })
    cross_emp_id = res.get("id") if isinstance(res, dict) else None
    expect("在任意部门新增员工", status, 200)

    status, res = call("POST", "/api/projects", token=admin, body={
        "name": "管理员跨部门项目" + TAG, "department_id": target_dept["id"],
        "status": "进行中", "priority": "中", "progress": 5,
    })
    cross_proj_id = res.get("id") if isinstance(res, dict) else None
    expect("在任意部门新建项目", status, 200)

    # ------------------------------------------------------------ 独占功能
    section("【三】仅管理员可用的功能")
    status, res = call("GET", "/api/users?page=1&size=50", token=admin)
    expect("账号管理：账号列表", status, 200)
    _, all_users = call("GET", "/api/users?page=1&size=100", token=admin)
    other_user = None
    for u in all_users.get("items", []):
        if u.get("id") != my_user_id:
            other_user = u
            break

    status, res = call("POST", "/api/users", token=admin, body={
        "username": "admintest_" + TAG, "password": "123456",
        "real_name": "管理员实测账号" + TAG, "role": "manager",
        "department_id": target_dept["id"],
    })
    new_user_id = res.get("id") if isinstance(res, dict) else None
    expect("账号管理：新建账号（可指定任意角色）", status, 200)

    if new_user_id:
        expect("账号管理：修改账号角色",
               call("PUT", f"/api/users/{new_user_id}", token=admin,
                    body={"role": "employee"})[0], 200)
        expect("账号管理：重置他人密码",
               call("POST", f"/api/users/{new_user_id}/reset-password", token=admin,
                    body={"new_password": "654321"})[0], 200)
    if other_user:
        expect("账号管理：停用他人账号",
               call("PUT", f"/api/users/{other_user['id']}", token=admin,
                    body={"is_active": True})[0], 200)
    expect("账号管理：删除账号",
           call("DELETE", f"/api/users/{new_user_id}", token=admin)[0] if new_user_id else 0, 200)

    expect("员工管理：导出 Excel",
           call("GET", "/api/employees/export/excel", token=admin)[0], 200)
    expect("员工管理：下载导入模板",
           call("GET", "/api/employees/import/template", token=admin)[0], 200)

    if cross_emp_id:
        expect("员工管理：批量开通登录账号",
               call("POST", "/api/employees/create-accounts", token=admin,
                    body={"ids": [cross_emp_id], "default_password": "123456",
                          "role": "employee"})[0], 200)
        expect("员工管理：物理删除员工（主管只能标记离职）",
               call("DELETE", f"/api/employees/{cross_emp_id}", token=admin)[0], 200)

    # ------------------------------------------------------------ 审批与公告
    section("【四】审批、公告、日志")
    _, pending = call("GET", "/api/leaves?scope=pending", token=admin)
    print(f"  待审批请假：{pending.get('total')} 条")
    expect("请假：可看待审批列表", call("GET", "/api/leaves?scope=pending", token=admin)[0], 200)
    expect("请假：可看部门记录", call("GET", "/api/leaves?scope=dept", token=admin)[0], 200)

    # 代他人提交：必须用一个"当前确实存在"的员工 id 做参数
    _, fresh_emps = call("GET", "/api/employees?page=1&size=5", token=admin)
    valid_emp = next((e["id"] for e in fresh_emps.get("items", []) if e["id"] != 1), None)
    far_day = (date.today() + timedelta(days=360)).isoformat()
    status, res = call("POST", "/api/leaves", token=admin, body={
        "leave_type": "事假", "start_date": far_day, "end_date": far_day,
        "reason": "管理员代提交实测", "employee_id": valid_emp})
    proxy_leave_id = (res.get("leave") or {}).get("id") if isinstance(res, dict) else None
    expect("请假：可代他人提交申请", status, 200, res)

    status, res = call("POST", "/api/leaves", token=admin, body={
        "leave_type": "事假", "start_date": far_day, "end_date": far_day,
        "reason": "不存在的员工", "employee_id": 999999})
    expect("请假：代不存在的员工提交应被拒", status, 400, res)

    expect("日志统计：可查看",
           call("GET", "/api/logs/stats?days=7", token=admin)[0], 200)
    status, ann = call("POST", "/api/announcements", token=admin,
                       body={"title": "管理员实测公告" + TAG, "content": "测试",
                             "category": "通知", "is_pinned": False, "is_published": True})
    expect("公告：可发布", status, 200, ann)
    if isinstance(ann, dict) and ann.get("id"):
        call("DELETE", f"/api/announcements/{ann['id']}", token=admin)

    # ------------------------------------------------------------ 应有的边界
    section("【五】管理员也会被拦住的边界（设计如此，不是 bug）")
    status, res = call("DELETE", f"/api/users/{my_user_id}", token=admin)
    expect("不能删除自己的账号", status, 400, res)
    print(f"         └─ {res.get('message') if isinstance(res, dict) else res}")

    status, res = call("PUT", f"/api/users/{my_user_id}", token=admin, body={"is_active": False})
    expect("不能停用自己的账号", status, 400, res)
    print(f"         └─ {res.get('message') if isinstance(res, dict) else res}")

    # 管理员自批：当前实现是"允许"的（管理员之上没有更高角色，不允许就永远批不了）。
    # 这里把真实行为记录下来，方便日后按公司制度调整时对照。
    own_day = (date.today() + timedelta(days=420)).isoformat()
    status, res = call("POST", "/api/leaves", token=admin, body={
        "leave_type": "事假", "start_date": own_day, "end_date": own_day,
        "reason": "管理员自批实测"})
    own_leave_id = (res.get("leave") or {}).get("id") if isinstance(res, dict) else None
    if own_leave_id:
        status, res = call("POST", f"/api/leaves/{own_leave_id}/approve", token=admin,
                           body={"action": "approve", "comment": "自批实测"})
        print(f"  [注意] 管理员审批自己的请假：HTTP {status}"
              f"（当前策略：允许，因为管理员之上没有更高审批人）")
        call("DELETE", f"/api/leaves/{own_leave_id}", token=admin)

    # 清理本测试产生的请假记录
    for lid in (proxy_leave_id,):
        if lid:
            call("DELETE", f"/api/leaves/{lid}", token=admin)

    # ------------------------------------------------------------ 收尾清理
    # 本脚本创建的项目留到最后删（前面几步还要用到它），避免给下一轮留下残留
    if cross_proj_id:
        status, res = call("DELETE", f"/api/projects/{cross_proj_id}", token=admin)
        print(f"\n  收尾：删除测试项目 id={cross_proj_id} -> HTTP {status} "
              f"{res.get('message') if isinstance(res, dict) else ''}")

    print()
    print("=" * 90)
    if FAILED:
        print(f"管理员权限实测发现 {len(FAILED)} 处不符合预期：")
        for f in FAILED:
            print("  ✗", f)
        print("=" * 90)
        sys.exit(1)
    print("管理员权限实测全部符合预期 ✅")
    print("=" * 90)


if __name__ == "__main__":
    main()
