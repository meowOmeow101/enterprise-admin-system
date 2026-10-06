"""
普通员工权限实测：用真实账号把每个接口打一遍，输出实际权限矩阵。

    python -m scripts.test_permissions
    # 或直接跑全部自测：.\\scripts\\test.ps1

用途：修改权限相关代码后，跑一遍就能确认三种角色的边界没有被破坏。
比读代码可靠 —— 它验证的是接口的真实行为（HTTP 状态码 + 返回内容）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = os.getenv("CADMIN_BASE_URL", "http://127.0.0.1:8000")
FAILED: list[str] = []


def call(method: str, path: str, token: str | None = None, body=None, form: dict | None = None):
    url = BASE + urllib.parse.quote(path, safe="/?&=%")
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        boundary = "----permtest" + str(abs(hash(path)) % 99999)
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
            return e.code, {"message": payload[:120].decode("utf-8", "replace")}


def login(username: str, password: str = "123456") -> str:
    _, res = call("POST", "/api/login", body={"username": username, "password": password})
    return res.get("token", "")


def expect(name: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILED.append(f"{name}：期望 {want}，实际 {got}")
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:58s} {got}")


def section(title: str) -> None:
    print()
    print("=" * 88)
    print(title)
    print("=" * 88)


def main() -> None:
    emp = login("yanglei")
    admin = login("admin")
    manager = login("liqiang")
    if not (emp and admin):
        print("登录失败，请先启动服务：.\\scripts\\start.ps1")
        sys.exit(1)

    _, me = call("GET", "/api/me", token=emp)
    my_emp_id = (me.get("employee") or {}).get("id")
    my_dept = me.get("department_name")
    print(f"测试身份：{me.get('real_name')} / {me.get('role_label')} / {my_dept} / 档案id={my_emp_id}")

    # ------------------------------------------------------------ 数据范围
    section("【一】普通员工能看到的数据范围")
    _, emps = call("GET", "/api/employees?page=1&size=100", token=emp)
    depts = sorted({e.get("department_name") for e in emps.get("items", [])})
    print(f"  员工列表：{emps.get('total')} 人，部门 {depts}")
    expect("员工列表只含本部门", depts, [my_dept])
    salaries = [e for e in emps.get("items", []) if e.get("salary") is not None]
    expect("薪资字段全部脱敏（可见条数）", len(salaries), 0)
    _, admin_emps = call("GET", "/api/employees?page=1&size=100", token=admin)
    print(f"  对比：管理员可见 {admin_emps.get('total')} 人")

    _, att = call("GET", "/api/attendance/records?page=1&size=100", token=emp)
    att_names = sorted({r.get("employee_name") for r in att.get("items", [])})
    expect("考勤记录只含本人", att_names in ([], [me.get("real_name")]), True)

    _, leaves_mine = call("GET", "/api/leaves?scope=mine", token=emp)
    print(f"  我的请假申请：{leaves_mine.get('total')} 条")

    _, reports = call("GET", "/api/reports?page=1&size=50", token=emp)
    _, admin_reports = call("GET", "/api/reports?page=1&size=50", token=admin)
    print(f"  报告可见 {reports.get('total')} 份（管理员 {admin_reports.get('total')} 份）")
    expect("报告可见数量不超过管理员", reports.get("total", 0) <= admin_reports.get("total", 0), True)

    # ------------------------------------------------------------ 管理类操作应被拒绝
    section("【二】普通员工应被拒绝的管理操作（全部期望 403）")
    other_leave = None
    _, all_leaves = call("GET", "/api/leaves?scope=dept&page=1&size=50", token=admin)
    for lv in all_leaves.get("items", []):
        if lv.get("employee_id") != my_emp_id:
            other_leave = lv["id"]
            break
    if other_leave is None:
        print("  （没有他人的请假记录，跳过越权审批测试）")

    emp_cases = [
        ("新增员工", "POST", "/api/employees", {"name": "越权", "department_id": 2}),
        ("修改员工", "PUT", f"/api/employees/{my_emp_id}", {"name": "越权改名", "department_id": 2}),
        ("删除员工", "DELETE", f"/api/employees/{my_emp_id}", None),
        ("导出员工名册", "GET", "/api/employees/export/excel", None),
        ("批量改员工状态", "POST", "/api/employees/batch-status", {"ids": [1], "status": "离职"}),
        ("新建部门", "POST", "/api/departments", {"name": "越权部门"}),
        ("修改部门", "PUT", "/api/departments/2", {"name": "越权改名"}),
        ("删除部门", "DELETE", "/api/departments/2", None),
        ("新建项目", "POST", "/api/projects", {"name": "越权项目", "department_id": 2}),
        ("修改项目", "PUT", "/api/projects/1", {"name": "越权改名", "department_id": 2}),
        ("删除项目", "DELETE", "/api/projects/1", None),
        ("添加项目成员", "POST", "/api/projects/1/members", {"members": [{"employee_id": 1}]}),
        ("考勤补录/修改", "POST", "/api/attendance/records",
         {"employee_id": 1, "work_date": "2026-01-05", "check_in": "09:00"}),
        ("请假-待审批视图", "GET", "/api/leaves?scope=pending", None),
        ("请假-部门视图", "GET", "/api/leaves?scope=dept", None),
        ("发布公告", "POST", "/api/announcements", {"title": "越权公告", "content": "x"}),
        ("删除公告", "DELETE", "/api/announcements/1", None),
        ("操作日志（全量）", "GET", "/api/logs", None),
        ("日志统计", "GET", "/api/logs/stats", None),
        ("账号列表", "GET", "/api/users", None),
        ("新建账号", "POST", "/api/users",
         {"username": "hack", "password": "123456", "real_name": "越权"}),
        ("重置他人密码", "POST", "/api/users/1/reset-password", {"new_password": "123456"}),
    ]
    if other_leave:
        emp_cases.append(("审批他人请假", "POST", f"/api/leaves/{other_leave}/approve",
                          {"action": "approve", "comment": "越权"}))
        emp_cases.append(("查看他人请假详情", "GET", f"/api/leaves/{other_leave}", None))

    for name, method, path, body in emp_cases:
        status, _ = call(method, path, token=emp, body=body)
        expect(name, status, 403)

    # ------------------------------------------------------------ 允许的操作
    section("【三】普通员工被允许的操作（期望 200）")
    allowed_cases = [
        ("查看自己的信息", "GET", "/api/me", None),
        ("看板总览", "GET", "/api/dashboard/overview", None),
        ("组织架构图", "GET", "/api/dashboard/org-chart", None),
        ("员工列表", "GET", "/api/employees?page=1&size=3", None),
        ("部门列表", "GET", "/api/departments", None),
        ("项目列表", "GET", "/api/projects?page=1&size=5", None),
        ("报告列表", "GET", "/api/reports?page=1&size=5", None),
        ("报告分类字典", "GET", "/api/reports/categories", None),
        ("考勤规则", "GET", "/api/attendance/rules", None),
        ("我今天的考勤", "GET", "/api/attendance/today", None),
        ("我的考勤记录", "GET", "/api/attendance/records?scope=mine", None),
        ("我的请假申请", "GET", "/api/leaves?scope=mine", None),
        ("公告列表", "GET", "/api/announcements", None),
        ("我的操作记录", "GET", "/api/logs/mine", None),
    ]
    for name, method, path, body in allowed_cases:
        status, _ = call(method, path, token=emp, body=body)
        expect(name, status, 200)

    # ------------------------------------------------------------ 报告：只能管自己的
    section("【四】报告：上传/下载/预览可以，但只能改删自己上传的")
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    _, projects = call("GET", "/api/projects?page=1&size=5", token=emp)
    proj_id = projects["items"][0]["id"] if projects.get("items") else None
    status, res = call("POST", "/api/reports/upload", token=emp, form={
        "file": ("权限实测.pdf", pdf), "title": "权限实测临时报告",
        "category": "周报", "project_id": str(proj_id or ""),
        "report_date": "2026-01-05", "summary": "权限测试自动生成，测完即删",
    })
    new_id = (res.get("report") or {}).get("id") if isinstance(res, dict) else None
    expect("上传报告到自己可见的项目", status, 200)
    if new_id:
        expect("下载自己上传的报告", call("GET", f"/api/reports/{new_id}/download", token=emp)[0], 200)
        expect("预览自己上传的报告", call("GET", f"/api/reports/{new_id}/preview", token=emp)[0], 200)
        expect("修改自己上传的报告",
               call("PUT", f"/api/reports/{new_id}", token=emp, body={"summary": "改一下"})[0], 200)
        expect("删除自己上传的报告",
               call("DELETE", f"/api/reports/{new_id}", token=emp)[0], 200)

    # ---- 他人报告：可见范围外的必须 403，范围内的允许下载；改删一律 403
    _, all_reports = call("GET", "/api/reports?page=1&size=200", token=admin)
    visible_ids = {r["id"] for r in reports.get("items", [])}
    mine_ids = {r["id"] for r in reports.get("items", [])
                if r.get("uploader_name") == me.get("real_name")}
    others_visible = [r for r in all_reports.get("items", [])
                      if r["id"] in visible_ids and r["id"] not in mine_ids]
    others_invisible = [r for r in all_reports.get("items", []) if r["id"] not in visible_ids]
    print(f"  可见报告 {len(visible_ids)} 份（其中自己上传 {len(mine_ids)} 份）；"
          f"范围内的他人报告 {len(others_visible)} 份；范围外 {len(others_invisible)} 份")

    if others_visible:
        target = others_visible[0]
        expect("修改他人上传的报告（应拒绝）",
               call("PUT", f"/api/reports/{target['id']}", token=emp, body={"summary": "越权"})[0], 403)
        expect("删除他人上传的报告（应拒绝）",
               call("DELETE", f"/api/reports/{target['id']}", token=emp)[0], 403)
        expect("下载可见范围内的他人报告（允许）",
               call("GET", f"/api/reports/{target['id']}/download", token=emp)[0], 200)
    else:
        print("  （可见范围内没有他人上传的报告，跳过该组用例）")

    if others_invisible:
        out_of_scope = others_invisible[0]
        print(f"  范围外样本：《{out_of_scope['title'][:20]}》（{out_of_scope.get('project_name')}）")
        expect("下载可见范围外的报告（应拒绝）",
               call("GET", f"/api/reports/{out_of_scope['id']}/download", token=emp)[0], 403)
        expect("查看可见范围外的报告详情（应拒绝）",
               call("GET", f"/api/reports/{out_of_scope['id']}", token=emp)[0], 403)
    else:
        print("  （当前数据下该员工能看到全部报告，无法验证范围外拒绝）")

    # ------------------------------------------------------------ 项目进度
    section("【五】项目进度：只有项目成员能更新")
    if proj_id:
        status, _ = call("PATCH", f"/api/projects/{proj_id}/progress", token=emp,
                         body={"progress": 55, "remark": "权限测试更新进度"})
        expect("成员更新自己参与项目的进度", status, 200)

    # ------------------------------------------------------------ 主管对照
    section("【六】对照：主管的 scope 视图应正常（未被误伤）")
    for scope, label in (("mine", "我的申请"), ("pending", "待我审批"), ("dept", "部门记录")):
        status, res = call("GET", f"/api/leaves?scope={scope}", token=manager)
        expect(f"主管 scope={scope}（{label}）", status, 200)

    print()
    print("=" * 88)
    if FAILED:
        print(f"权限实测发现 {len(FAILED)} 处不符合预期：")
        for f in FAILED:
            print("  ✗", f)
        print("=" * 88)
        sys.exit(1)
    print("普通员工权限实测全部符合预期 ✅")
    print("=" * 88)


if __name__ == "__main__":
    main()
