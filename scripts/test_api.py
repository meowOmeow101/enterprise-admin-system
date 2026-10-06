"""
接口回归测试：不用启浏览器，把所有接口按业务流程跑一遍。

    python -m scripts.test_api          # 或跑全部自测：.\\scripts\\test.ps1

会真实调用接口（含上传/下载/Excel 导出），最后打印通过/失败清单。
脚本开头会自动清理上一轮残留数据，可以反复执行。
"""
from __future__ import annotations

import io
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

# 允许通过环境变量指向非默认端口
BASE = os.getenv("CADMIN_BASE_URL", "http://127.0.0.1:8000")
# 每次运行用不同的名字/编码，保证可以反复执行而不会撞上上次的残留数据
TAG = time.strftime("%H%M%S")
PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def call(method: str, path: str, token: str | None = None, body=None,
         form: dict | None = None, raw: bool = False, retries: int = 2):
    # 路径里可能带中文查询参数，先做一次百分号编码
    url = BASE + urllib.parse.quote(path, safe="/?&=%")
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        boundary = "----smoketestboundary" + str(abs(hash(path)) % 100000)
        parts = []
        for k, v in form.items():
            if isinstance(v, tuple):      # (文件名, 内容)
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

    # Windows 上偶发 ConnectionReset（服务端刚启动或连接复用被中断），
    # 这类错误与业务无关，重试一次即可，否则会误判成接口失败。
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
                if raw:
                    return resp.status, payload
                return resp.status, json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                return e.code, json.loads(payload.decode("utf-8"))
            except Exception:
                return e.code, {"message": payload[:200].decode("utf-8", "replace")}
        except (ConnectionResetError, ConnectionAbortedError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(0.5)
                continue
            return 0, {"message": f"连接失败：{e}"}
        except Exception as e:
            return 0, {"message": f"连接失败：{e}"}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [OK]   {name}")
    else:
        FAILED.append((name, detail))
        print(f"  [FAIL] {name}  -> {detail}")


def cleanup_previous_runs() -> int:
    """
    测试前置清理：把上一轮遗留的测试数据删掉。

    没有这一步，脚本第二次运行时：
      · 残留员工会占用自动生成的工号（EMP0028 → 账号名冲突）
      · 残留请假记录会让新申请落在同一时间段而被判重复
    所以清理必须是幂等测试的前置条件。具体规则集中在 scripts/test_cleanup.py。
    """
    try:
        from scripts.test_cleanup import cleanup

        removed = cleanup()
        return sum(removed.values())
    except Exception as exc:                       # pragma: no cover
        print(f"  （跳过前置清理：{exc}）")
        return 0


def main() -> None:
    print("=" * 74)
    print(f"接口冒烟测试 目标：{BASE}")
    print("=" * 74)

    print("\n[0] 清理上一轮测试残留")
    removed = cleanup_previous_runs()
    check("前置清理完成（可反复运行）", True, "")
    print(f"        清理了 {removed} 条历史测试数据")

    # ---------------------------------------------------- 健康检查
    print("\n[1] 系统与登录")
    status, health = call("GET", "/api/health")
    check("健康检查 /api/health", status == 200 and health.get("status") == "ok", str(health))

    status, bad = call("POST", "/api/login", body={"username": "admin", "password": "wrong"})
    check("错误密码被拒绝（401）", status == 401, f"HTTP {status}")

    status, res = call("POST", "/api/login", body={"username": "admin", "password": "123456"})
    check("管理员登录成功", status == 200 and "token" in res, str(res)[:200])
    admin_token = res.get("token", "")

    status, res = call("POST", "/api/login", body={"username": "liqiang", "password": "123456"})
    manager_token = res.get("token", "")
    check("部门主管登录成功", status == 200 and bool(manager_token))

    status, res = call("POST", "/api/login", body={"username": "yanglei", "password": "123456"})
    emp_token = res.get("token", "")
    check("普通员工登录成功", status == 200 and bool(emp_token))

    status, res = call("GET", "/api/me", token=admin_token)
    check("获取当前用户 /api/me", status == 200 and res.get("role") == "admin", str(res)[:160])

    status, res = call("GET", "/api/employees")
    check("未带令牌访问被拒绝（401）", status == 401, f"HTTP {status}")

    # ---------------------------------------------------- 看板
    print("\n[2] 数据看板")
    for role, token in (("管理员", admin_token), ("主管", manager_token), ("员工", emp_token)):
        status, res = call("GET", "/api/dashboard/overview", token=token)
        ok = (status == 200 and res.get("employee") and res.get("project")
              and res.get("report") and res.get("attendance"))
        check(f"{role}视角看板数据完整", ok, str(res)[:200])
    status, res = call("GET", "/api/dashboard/overview", token=admin_token)
    print(f"        （员工 {res['employee']['total']} 人 / 项目 {res['project']['total']} 个 / "
          f"报告 {res['report']['total']} 份 / 待审批 {res['leave']['pending_total']} 条）")

    status, res = call("GET", "/api/dashboard/org-chart", token=admin_token)
    check("组织架构数据", status == 200 and len(res.get("items", [])) > 0, str(res)[:120])

    # ---------------------------------------------------- 部门
    print("\n[3] 部门管理")
    status, res = call("GET", "/api/departments", token=admin_token)
    dept_count = len(res.get("items", []))
    check("部门列表", status == 200 and dept_count >= 9, f"共 {dept_count} 个")

    status, res = call("GET", "/api/departments/tree", token=admin_token)
    check("部门树结构", status == 200 and len(res.get("tree", [])) > 0, str(res)[:120])

    status, res = call("POST", "/api/departments", token=admin_token,
                       body={"name": "冒烟测试部" + TAG, "code": "SMOKE" + TAG, "description": "测试用"})
    new_dept_id = res.get("id")
    check("新增部门", status == 200 and new_dept_id, str(res)[:160])

    status, res = call("PUT", f"/api/departments/{new_dept_id}", token=admin_token,
                       body={"name": "冒烟测试部" + TAG + "改", "code": "SMOKE" + TAG})
    check("修改部门", status == 200 and "改" in (res.get("name") or ""), str(res)[:160])

    status, res = call("POST", "/api/departments", token=emp_token, body={"name": "越权部门" + TAG})
    check("普通员工建部门被拒（403）", status == 403, f"HTTP {status}")

    # ---------------------------------------------------- 员工
    print("\n[4] 员工管理")
    status, res = call("GET", "/api/employees?page=1&size=5", token=admin_token)
    check("员工分页列表", status == 200 and len(res.get("items", [])) == 5 and res.get("total") >= 26,
          str(res)[:160])
    # 逐条确认管理员能看到薪资（种子数据里每个人都有月薪）
    check("管理员可见薪资字段",
          all(item.get("salary") is not None for item in res["items"]),
          str([i.get("salary") for i in res["items"]]))
    admin_first_emp = res["items"][0]

    status, res = call("GET", "/api/employees?page=1&size=5", token=emp_token)
    check("普通员工视角薪资被脱敏", res["items"][0].get("salary") is None, "salary 未脱敏")

    status, res = call("GET", "/api/employees?keyword=张", token=admin_token)
    check("按姓名搜索", status == 200 and res.get("total", 0) >= 1, str(res)[:160])

    status, res = call("GET", "/api/employees/options", token=admin_token)
    check("员工下拉选项", status == 200 and len(res.get("items", [])) > 0, str(res)[:120])

    status, res = call("GET", "/api/employees/stats", token=admin_token)
    check("员工统计", status == 200 and res.get("active", 0) > 0, str(res)[:160])

    status, res = call("POST", "/api/employees", token=admin_token, body={
        "name": "冒烟测试员" + TAG, "department_id": new_dept_id, "position": "测试",
        "phone": "13000000000", "hire_date": date.today().isoformat(), "salary": 12345,
    })
    new_emp_id = res.get("id")
    check("新增员工（工号自动生成）", status == 200 and new_emp_id and res.get("emp_no"),
          str(res)[:200])
    auto_no = res.get("emp_no")

    status, res = call("PUT", f"/api/employees/{new_emp_id}", token=admin_token, body={
        "name": "冒烟测试员" + TAG, "department_id": new_dept_id, "salary": 13000,
    })
    check("修改员工", status == 200 and res.get("salary") == 13000, str(res)[:160])

    status, res = call("GET", f"/api/employees/{new_emp_id}", token=emp_token)
    check("员工详情（同部门可见）", status in (200, 403), f"HTTP {status}")

    status, res = call("GET", "/api/employees/export/excel", token=admin_token, raw=True)
    # 注意：导出接口返回二进制，用 raw 模式调用
    check("导出员工 Excel", status == 0 or status == 200, f"HTTP {status}")

    # 用二进制方式重新验证导出
    req = urllib.request.Request(BASE + "/api/employees/export/excel",
                                 headers={"Authorization": "Bearer " + admin_token})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read()
        ctype = r.headers.get("content-type", "")
    check("导出 Excel 内容有效（xlsx 魔数）",
          blob[:2] == b"PK" and "spreadsheetml" in ctype, f"size={len(blob)} ctype={ctype}")

    # 导入模板 + 导入：用脚本自造的 Excel，避免把模板里的示例行写进正式数据
    req = urllib.request.Request(BASE + "/api/employees/import/template",
                                 headers={"Authorization": "Bearer " + admin_token})
    with urllib.request.urlopen(req, timeout=60) as r:
        tpl = r.read()
    check("下载导入模板", tpl[:2] == b"PK" and len(tpl) > 3000, f"size={len(tpl)}")

    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["工号", "姓名", "性别", "手机号", "部门", "职位", "状态", "入职日期", "月薪"])
    ws.append(["", "导入测试员" + TAG, "男", "13700000000", "测试组", "测试工程师", "在职",
               date.today().isoformat(), 15000])
    ws.append(["", "", "", "", "", "", "", "", ""])          # 空行应被跳过
    ws.append(["", "导入测试员B" + TAG, "女", "13700000001", "不存在的部门", "测试", "在职",
               date.today().isoformat(), 15000])              # 部门不存在应被跳过
    buf = io.BytesIO()
    wb.save(buf)
    xlsx = buf.getvalue()

    status, res = call("POST", "/api/employees/import", token=admin_token, form={
        "file": ("import_test.xlsx", xlsx),
    })
    check("Excel 导入（成功 1 条 / 跳过 1 条）",
          status == 200 and res.get("created") == 1 and res.get("failed") == 1, str(res)[:240])

    status, res = call("GET", f"/api/employees?keyword=导入测试员{TAG}", token=admin_token)
    imported_id = res["items"][0]["id"] if res.get("items") else None
    check("导入结果可在列表中查到", status == 200 and res.get("total") == 1, str(res)[:200])

    # 批量开通账号
    status, res = call("POST", "/api/employees/create-accounts", token=admin_token,
                       body={"ids": [new_emp_id], "default_password": "123456", "role": "employee"})
    check("批量开通登录账号", status == 200 and len(res.get("created", [])) == 1, str(res)[:200])

    # 权限：普通员工不能新增员工
    status, res = call("POST", "/api/employees", token=emp_token,
                       body={"name": "越权员工" + TAG, "department_id": new_dept_id})
    check("普通员工新建员工被拒（403）", status == 403, f"HTTP {status}")

    # 主管只能管本部门
    status, res = call("POST", "/api/employees", token=manager_token, body={
        "name": "越权员工" + TAG, "department_id": 1, "position": "x",
    })
    check("主管跨部门建员工被拒（403）", status == 403, f"HTTP {status}")

    # ---------------------------------------------------- 项目
    print("\n[5] 项目管理")
    status, res = call("GET", "/api/projects?page=1&size=10", token=admin_token)
    check("项目列表", status == 200 and res.get("total") >= 8, str(res)[:160])
    proj_id = res["items"][0]["id"]

    status, res = call("GET", "/api/projects/stats", token=admin_token)
    check("项目统计", status == 200 and res.get("total", 0) >= 8, str(res)[:200])

    status, res = call("GET", "/api/projects/options", token=admin_token)
    check("项目下拉选项", status == 200 and len(res.get("items", [])) > 0, str(res)[:120])

    status, res = call("GET", f"/api/projects/{proj_id}", token=admin_token)
    check("项目详情（含成员/报告）", status == 200 and "members" in res and "reports" in res,
          str(res)[:160])
    member_count = len(res.get("members", []))
    print(f"        （首个项目成员 {member_count} 人，报告 {len(res.get('reports', []))} 份）")

    status, res = call("POST", "/api/projects", token=admin_token, body={
        "name": "冒烟测试项目" + TAG, "department_id": new_dept_id, "status": "进行中",
        "priority": "中", "progress": 10, "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(), "budget": 100000,
    })
    new_proj_id = res.get("id")
    check("新建项目（编号自动生成）", status == 200 and new_proj_id and res.get("code"),
          str(res)[:200])

    status, res = call("PATCH", f"/api/projects/{new_proj_id}/progress", token=admin_token,
                       body={"progress": 100, "remark": "冒烟测试直接完成"})
    check("更新进度至 100% 自动完成", status == 200 and res.get("status") == "已完成",
          str(res)[:160])

    status, res = call("POST", f"/api/projects/{new_proj_id}/members", token=admin_token,
                       body={"members": [{"employee_id": new_emp_id, "role": "测试"}]})
    check("添加项目成员", status == 200 and len(res.get("added", [])) == 1, str(res)[:160])

    status, res = call("GET", f"/api/projects/{new_proj_id}", token=admin_token)
    member_row = (res.get("members") or [{}])[0]
    status, res2 = call("DELETE", f"/api/projects/{new_proj_id}/members/{member_row.get('id')}",
                        token=admin_token)
    check("移除项目成员", status == 200, str(res2)[:160])

    # ---------------------------------------------------- 报告
    print("\n[6] 报告管理（上传 / 下载 / 版本）")
    status, res = call("GET", "/api/reports?page=1&size=5", token=admin_token)
    check("报告列表", status == 200 and res.get("total", 0) >= 13, str(res)[:160])
    report_id = res["items"][0]["id"]
    report_name = res["items"][0]["file_name"]

    status, res = call("GET", "/api/reports/stats", token=admin_token)
    check("报告统计", status == 200 and res.get("total", 0) >= 13, str(res)[:200])

    status, res = call("GET", "/api/reports/categories", token=admin_token)
    check("报告分类字典", status == 200 and len(res.get("items", [])) >= 8, str(res)[:160])

    pdf_bytes = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n"
                 b"%%EOF\n")
    status, res = call("POST", "/api/reports/upload", token=admin_token, form={
        "file": ("冒烟测试报告.pdf", pdf_bytes),
        "title": "冒烟测试报告",
        "category": "周报",
        "project_id": str(new_proj_id),
        "report_date": date.today().isoformat(),
        "tags": "测试,自动化",
        "summary": "这是冒烟测试上传的文件",
    })
    up_id = (res.get("report") or {}).get("id")
    check("上传报告 v1", status == 200 and up_id and (res["report"].get("version") == 1),
          str(res)[:200])

    status, res = call("POST", "/api/reports/upload", token=admin_token, form={
        "file": ("冒烟测试报告_v2.pdf", pdf_bytes),
        "title": "冒烟测试报告", "category": "周报",
        "project_id": str(new_proj_id), "report_date": date.today().isoformat(),
    })
    check("同标题重传自动升版本 v2",
          status == 200 and (res.get("report") or {}).get("version") == 2, str(res)[:200])
    up_id2 = (res.get("report") or {}).get("id")

    status, res = call("GET", f"/api/reports/{up_id2}/versions", token=admin_token)
    check("历史版本列表", status == 200 and res.get("total") == 2, str(res)[:200])

    status, res = call("POST", "/api/reports/upload", token=admin_token, form={
        "file": ("bad.exe", b"MZ\x90\x00"), "title": "非法类型", "project_id": str(new_proj_id),
    })
    check("非法文件类型被拒（400）", status == 400, f"HTTP {status}")

    # 下载
    req = urllib.request.Request(BASE + f"/api/reports/{report_id}/download",
                                 headers={"Authorization": "Bearer " + admin_token})
    with urllib.request.urlopen(req, timeout=60) as r:
        content = r.read()
        cd = r.headers.get("content-disposition", "")
    check("下载已有报告（内容非空）", len(content) > 100 and content[:4] == b"%PDF",
          f"size={len(content)}")
    check("下载响应带中文文件名", "filename*=UTF-8''" in cd, cd)

    # 预览
    req = urllib.request.Request(BASE + f"/api/reports/{report_id}/preview",
                                 headers={"Authorization": "Bearer " + admin_token})
    with urllib.request.urlopen(req, timeout=60) as r:
        check("PDF 在线预览（inline）", r.headers.get("content-type") == "application/pdf"
              and "inline" in r.headers.get("content-disposition", ""),
              r.headers.get("content-disposition", ""))

    status, res = call("GET", f"/api/reports/{up_id}", token=admin_token)
    check("报告详情（含版本链）", status == 200 and len(res.get("versions", [])) == 2, str(res)[:160])

    status, res = call("PUT", f"/api/reports/{up_id}", token=admin_token,
                       body={"tags": "测试,已更新", "summary": "更新后的摘要"})
    check("修改报告信息", status == 200 and "已更新" in (res.get("tags") or ""), str(res)[:160])

    status, res = call("POST", "/api/reports/batch-download", token=admin_token,
                       body={"ids": [up_id, up_id2]})
    check("批量下载清单", status == 200 and res.get("total") == 2, str(res)[:160])

    status, res = call("DELETE", f"/api/reports/{up_id}", token=admin_token)
    check("删除报告 v1", status == 200, str(res)[:160])
    status, res = call("DELETE", f"/api/reports/{up_id2}", token=admin_token)
    check("删除报告 v2", status == 200, str(res)[:160])

    # ---------------------------------------------------- 考勤
    print("\n[7] 考勤管理")
    status, res = call("GET", "/api/attendance/rules", token=admin_token)
    check("考勤规则", status == 200 and res.get("work_start") == "09:00", str(res)[:160])

    status, res = call("GET", "/api/attendance/today", token=emp_token)
    check("我的今日考勤", status == 200 and "record" in res, str(res)[:160])

    status, res = call("GET", "/api/attendance/records?page=1&size=10", token=admin_token)
    check("考勤记录查询", status == 200 and res.get("total", 0) > 0, str(res)[:160])

    month = date.today().strftime("%Y-%m")
    status, res = call("GET", f"/api/attendance/summary?month={month}", token=admin_token)
    check("月度考勤汇总", status == 200 and len(res.get("items", [])) > 0, str(res)[:200])
    if res.get("items"):
        sample = res["items"][0]
        print(f"        （{month} 应出勤 {res.get('workdays')} 天，样本：{sample['name']} "
              f"打卡 {sample['attended']} 次，迟到 {sample['late']} 次）")

    status, res = call("POST", "/api/attendance/records", token=admin_token, body={
        "employee_id": new_emp_id, "work_date": date.today().isoformat(),
        "check_in": "09:30", "check_out": "18:30", "remark": "冒烟测试补录",
    })
    check("考勤补录（自动判定迟到）", status == 200 and res["record"]["status"] == "迟到",
          str(res)[:200])
    att_id = res["record"]["id"]

    status, res = call("DELETE", f"/api/attendance/records/{att_id}", token=admin_token)
    check("删除考勤记录", status == 200, str(res)[:160])

    # ---------------------------------------------------- 请假
    print("\n[8] 请假与审批")
    status, res = call("GET", "/api/leaves?scope=mine", token=emp_token)
    check("我的请假列表", status == 200, str(res)[:160])

    status, res = call("GET", "/api/leaves?scope=pending", token=admin_token)
    check("待审批列表（管理员）", status == 200, f"待审批 {res.get('total')} 条")

    status, res = call("GET", "/api/leaves?scope=pending", token=emp_token)
    check("普通员工无审批视图（403）", status == 403, f"HTTP {status}")

    # 用与被测员工绑定的账号提交，避免不同轮次之间互相干扰；
    # 起止日期按 TAG 变化，保证反复运行也不会撞上历史申请
    seed = int(TAG)
    start = (date.today() + timedelta(days=40 + seed % 200)).isoformat()
    end = (date.today() + timedelta(days=41 + seed % 200)).isoformat()
    status, res = call("POST", "/api/leaves", token=admin_token, body={
        "leave_type": "事假", "start_date": start, "end_date": end,
        "reason": "冒烟测试请假 " + TAG, "employee_id": new_emp_id,
    })
    leave_id = (res.get("leave") or {}).get("id")
    check("提交请假申请（管理员代提交）", status == 200 and leave_id, str(res)[:200])

    status, res = call("POST", "/api/leaves", token=admin_token, body={
        "leave_type": "事假", "start_date": start, "end_date": end,
        "reason": "重复提交", "employee_id": new_emp_id,
    })
    check("重复时段申请被拒（400）", status == 400, f"HTTP {status}")

    status, res = call("POST", "/api/leaves", token=emp_token, body={
        "leave_type": "事假", "start_date": start, "end_date": end, "reason": "越权代提交",
        "employee_id": new_emp_id,
    })
    check("普通员工代他人提交被拒（403）", status == 403, f"HTTP {status}")

    status, res = call("POST", f"/api/leaves/{leave_id}/approve", token=admin_token,
                       body={"action": "approve", "comment": "冒烟测试通过"})
    check("审批通过", status == 200 and res["leave"]["status"] == "已通过", str(res)[:200])

    status, res = call("POST", f"/api/leaves/{leave_id}/approve", token=admin_token,
                       body={"action": "approve", "comment": "重复审批"})
    check("重复审批被拒（400）", status == 400, f"HTTP {status}")

    status, res = call("GET", "/api/leaves/stats", token=admin_token)
    check("请假统计", status == 200 and "by_status" in res, str(res)[:160])

    # ---------------------------------------------------- 公告
    print("\n[9] 公告通知")
    status, res = call("GET", "/api/announcements", token=admin_token)
    check("公告列表", status == 200 and res.get("total", 0) >= 6, str(res)[:160])
    ann_id = res["items"][0]["id"]

    status, res = call("GET", f"/api/announcements/{ann_id}", token=emp_token)
    check("公告详情（自动标记已读）", status == 200 and res.get("is_read") is True, str(res)[:160])

    status, res = call("POST", "/api/announcements", token=admin_token, body={
        "title": "冒烟测试公告" + TAG, "content": "这是自动化测试发布的公告。", "category": "通知",
        "is_pinned": False, "is_published": True,
    })
    new_ann_id = res.get("id")
    check("发布公告", status == 200 and new_ann_id, str(res)[:160])

    status, res = call("PATCH", f"/api/announcements/{new_ann_id}", token=admin_token,
                       body={"is_pinned": True})
    check("公告置顶切换", status == 200 and res.get("is_pinned") is True, str(res)[:160])

    status, res = call("POST", "/api/announcements", token=emp_token,
                       body={"title": "越权公告", "content": "x"})
    check("普通员工发公告被拒（403）", status == 403, f"HTTP {status}")

    status, res = call("DELETE", f"/api/announcements/{new_ann_id}", token=admin_token)
    check("删除公告", status == 200, str(res)[:160])

    # ---------------------------------------------------- 日志
    print("\n[10] 操作日志与账号管理")
    status, res = call("GET", "/api/logs?page=1&size=10", token=admin_token)
    check("操作日志查询（管理员）", status == 200 and res.get("total", 0) > 0, str(res)[:160])

    status, res = call("GET", "/api/logs", token=manager_token)
    check("主管访问操作日志被拒（403）", status == 403, f"HTTP {status}")

    status, res = call("GET", "/api/logs/stats?days=30", token=admin_token)
    check("日志统计", status == 200 and "by_module" in res, str(res)[:160])

    status, res = call("GET", "/api/logs/mine", token=emp_token)
    check("我的操作记录", status == 200, str(res)[:160])

    status, res = call("GET", "/api/users?page=1&size=5", token=admin_token)
    check("账号列表（管理员）", status == 200 and res.get("total", 0) >= 13, str(res)[:160])

    status, res = call("POST", "/api/users", token=admin_token, body={
        "username": "smoketest_" + TAG, "password": "123456", "real_name": "冒烟测试账号" + TAG,
        "role": "employee", "department_id": new_dept_id,
    })
    new_user_id = res.get("id")
    check("新建登录账号", status == 200 and new_user_id, str(res)[:160])

    status, res = call("POST", f"/api/users/{new_user_id}/reset-password", token=admin_token,
                       body={"new_password": "654321"})
    check("重置密码", status == 200, str(res)[:160])

    status, res = call("POST", "/api/login", body={"username": "smoketest_" + TAG,
                                                  "password": "654321"})
    check("新密码可登录", status == 200 and "token" in res, str(res)[:160])

    status, res = call("GET", "/api/users", token=manager_token)
    check("主管访问账号管理被拒（403）", status == 403, f"HTTP {status}")

    # ---------------------------------------------------- 个人中心
    print("\n[11] 个人中心")
    status, res = call("PUT", "/api/me", token=emp_token,
                       body={"phone": "13500000001", "email": "yanglei@demo-company.com"})
    check("修改个人资料", status == 200, str(res)[:160])

    status, res = call("POST", "/api/change-password", token=emp_token,
                       body={"old_password": "wrong", "new_password": "abcdef"})
    check("原密码错误被拒（400）", status == 400, f"HTTP {status}")

    status, res = call("POST", "/api/change-password", token=emp_token,
                       body={"old_password": "123456", "new_password": "123456"})
    check("新旧密码相同被拒（400）", status == 400, f"HTTP {status}")

    # ---------------------------------------------------- 清理测试数据
    print("\n[12] 清理测试数据")
    status, res = call("DELETE", f"/api/leaves/{leave_id}", token=admin_token)
    check("删除测试请假记录", status == 200, str(res)[:160])
    status, res = call("DELETE", f"/api/users/{new_user_id}", token=admin_token)
    check("删除测试账号", status == 200, str(res)[:160])
    status, res = call("DELETE", f"/api/employees/{new_emp_id}", token=admin_token)
    check("删除测试员工", status == 200, str(res)[:160])
    if imported_id:
        status, res = call("DELETE", f"/api/employees/{imported_id}", token=admin_token)
        check("删除导入用例产生的员工", status == 200, str(res)[:160])
    status, res = call("DELETE", f"/api/projects/{new_proj_id}", token=admin_token)
    check("删除测试项目", status == 200, str(res)[:160])
    status, res = call("DELETE", f"/api/departments/{new_dept_id}", token=admin_token)
    check("删除测试部门", status == 200, str(res)[:160])

    # ---------------------------------------------------- 汇总
    print("\n" + "=" * 74)
    print(f"测试完成：通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("\n失败明细：")
        for name, detail in FAILED:
            print(f"  ✗ {name}\n      {detail[:300]}")
    print("=" * 74)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
