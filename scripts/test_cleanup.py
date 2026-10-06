"""
测试数据清理：清掉自测脚本自己产生的数据，保证测试可反复运行、且不污染正式数据。

    python -m scripts.test_cleanup

被 test_api.py / test_admin.py 在开始时自动调用。
之所以要独立成模块：脚本一旦某一步失败，后面不会执行，残留数据会累积，
下一次运行就会莫名其妙失败（比如"用户名被占用"）。前置清理是幂等测试的前提。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (Announcement, Attendance, Department, Employee, LeaveRequest, OperationLog,
                        Project, Report, User)

# 测试数据的识别特征（脚本创建的对象都带这些关键字）
PATTERNS = (
    "冒烟测试", "SMOKE", "smoketest", "越权", "导入测试员",
    "管理员跨部门", "管理员实测", "管理员代提交", "管理员自批", "admintest",
    "权限实测", "定位用",
)


def looks_test(*values) -> bool:
    return any(v and any(p in str(v) for p in PATTERNS) for v in values)


def cleanup(verbose: bool = True) -> dict[str, int]:
    """删除所有测试残留，返回清理统计。"""
    removed = {"部门": 0, "员工": 0, "账号": 0, "项目": 0, "报告": 0,
               "请假": 0, "考勤": 0, "公告": 0}

    with SessionLocal() as db:
        # ---- 报告（必须最先删，否则项目因关联报告删不掉）
        for r in db.scalars(select(Report)).all():
            if looks_test(r.title, r.summary, r.tags, r.file_name):
                db.delete(r)
                removed["报告"] += 1
        db.commit()

        # ---- 请假（连同审批时自动生成的考勤记录）
        for lv in db.scalars(select(LeaveRequest)).all():
            if not looks_test(lv.reason):
                continue
            day = lv.start_date
            while day <= lv.end_date:
                rec = db.scalar(select(Attendance).where(Attendance.employee_id == lv.employee_id,
                                                         Attendance.work_date == day))
                # 只删"因该请假生成"的记录（没有实际打卡时间的）
                if rec and not rec.check_in and not rec.check_out:
                    db.delete(rec)
                    removed["考勤"] += 1
                day += timedelta(days=1)
            db.delete(lv)
            removed["请假"] += 1
        db.commit()

        # ---- 员工（连同其账号与考勤）
        for e in db.scalars(select(Employee)).all():
            if not looks_test(e.name, e.emp_no, e.remark):
                continue
            if e.user_id:
                u = db.get(User, e.user_id)
                if u:
                    db.delete(u)
                    removed["账号"] += 1
            for rec in db.scalars(select(Attendance).where(Attendance.employee_id == e.id)).all():
                db.delete(rec)
                removed["考勤"] += 1
            db.delete(e)
            removed["员工"] += 1
        db.commit()

        # ---- 项目
        for p in db.scalars(select(Project)).all():
            if looks_test(p.name, p.code, p.description):
                db.delete(p)
                removed["项目"] += 1
        db.commit()

        # ---- 账号：测试名 + 孤儿账号（已不绑定任何员工，且姓名带"已删除"标记）
        for u in db.scalars(select(User)).all():
            if looks_test(u.username, u.real_name):
                db.delete(u)
                removed["账号"] += 1
        db.commit()

        bound = {e.user_id for e in db.scalars(select(Employee)).all() if e.user_id}
        for u in db.scalars(select(User)).all():
            if u.id not in bound and "员工已删除" in (u.real_name or ""):
                if verbose:
                    print(f"    清理孤儿账号：{u.username}（{u.real_name}）")
                db.delete(u)
                removed["账号"] += 1
        db.commit()

        # ---- 公告
        for a in db.scalars(select(Announcement)).all():
            if looks_test(a.title, a.content[:40] if a.content else ""):
                db.delete(a)
                removed["公告"] += 1
        db.commit()

        # ---- 部门（放最后，先解开主管引用避免外键阻塞）
        for d in db.scalars(select(Department)).all():
            if looks_test(d.name, d.code):
                d.manager_id = None
        db.commit()
        for d in db.scalars(select(Department)).all():
            if looks_test(d.name, d.code):
                db.delete(d)
                removed["部门"] += 1
        db.commit()

    return {k: v for k, v in removed.items() if v}


def main() -> None:
    print("清理自测脚本产生的残留数据 ...")
    removed = cleanup()
    if removed:
        print(f"  已清理：{removed}")
    else:
        print("  没有发现残留数据")

    with SessionLocal() as db:
        print(f"  当前：部门 {len(db.scalars(select(Department)).all())} 个 / "
              f"员工 {len(db.scalars(select(Employee)).all())} 名 / "
              f"账号 {len(db.scalars(select(User)).all())} 个 / "
              f"项目 {len(db.scalars(select(Project)).all())} 个 / "
              f"报告 {len(db.scalars(select(Report)).all())} 份")


if __name__ == "__main__":
    main()
