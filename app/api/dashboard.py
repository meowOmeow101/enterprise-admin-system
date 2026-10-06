"""数据看板接口：把各模块统计汇总成一个首页。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import current_employee, get_current_user, is_admin_like, scoped_department_ids
from ..models import (Announcement, Attendance, Department, Employee, LeaveRequest, OperationLog,
                      Project, ProjectMember, Report, User)

router = APIRouter(prefix="/dashboard", tags=["数据看板"])


@router.get("/overview", summary="首页总览（KPI + 图表数据）")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = scoped_department_ids(db, user)
    today = date.today()
    emp = current_employee(db, user)

    # ------------------------------------------------ 员工
    emp_stmt = select(Employee).options(selectinload(Employee.department))
    if allowed is not None:
        emp_stmt = emp_stmt.where(Employee.department_id.in_(allowed or [-1]))
    employees = db.scalars(emp_stmt).all()
    active_employees = [e for e in employees if e.status != "离职"]
    emp_by_dept: dict[str, int] = {}
    emp_by_status: dict[str, int] = {}
    for e in employees:
        emp_by_status[e.status] = emp_by_status.get(e.status, 0) + 1
        if e.status != "离职":
            key = e.department.name if e.department else "未分配"
            emp_by_dept[key] = emp_by_dept.get(key, 0) + 1

    # 近 6 个月入职人数走势
    hire_trend: dict[str, int] = {}
    for i in range(5, -1, -1):
        m = (today.replace(day=1) - timedelta(days=i * 30)).strftime("%Y-%m")
        hire_trend[m] = 0
    for e in employees:
        if e.hire_date:
            key = e.hire_date.strftime("%Y-%m")
            if key in hire_trend:
                hire_trend[key] += 1

    # ------------------------------------------------ 项目
    proj_stmt = select(Project).options(selectinload(Project.members), selectinload(Project.reports))
    if allowed is not None:
        proj_stmt = proj_stmt.where(Project.department_id.in_(allowed or [-1]))
    projects = db.scalars(proj_stmt).unique().all()
    proj_by_status: dict[str, int] = {}
    proj_by_dept: dict[str, int] = {}
    active_projects, overdue_projects = [], []
    for p in projects:
        proj_by_status[p.status] = proj_by_status.get(p.status, 0) + 1
        key = p.department.name if p.department else "未分配"
        proj_by_dept[key] = proj_by_dept.get(key, 0) + 1
        if p.status not in ("已完成", "已归档"):
            active_projects.append(p)
            if p.end_date and p.end_date < today:
                overdue_projects.append(p)

    # 进行中项目按进度排序，首页取前 6 个
    focus = sorted(active_projects, key=lambda p: (p.end_date or date.max))[:6]

    # ------------------------------------------------ 报告
    rep_stmt = select(Report).options(selectinload(Report.project))
    if allowed is not None:
        member_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == (emp.id if emp else -1))
        ).all()]
        project_ids = {p.id for p in projects} | set(member_ids)
        rep_stmt = rep_stmt.where(or_(Report.project_id.in_(project_ids or [-1]),
                                      Report.project_id.is_(None), Report.uploader_id == user.id))
    reports = db.scalars(rep_stmt).unique().all()
    rep_by_category: dict[str, int] = {}
    rep_by_month: dict[str, int] = {}
    for r in reports:
        rep_by_category[r.category] = rep_by_category.get(r.category, 0) + 1
        key = (r.report_date or r.created_at.date()).strftime("%Y-%m")
        rep_by_month[key] = rep_by_month.get(key, 0) + 1
    rep_by_month = dict(sorted(rep_by_month.items())[-6:])

    # ------------------------------------------------ 考勤 / 请假
    att_stmt = select(Attendance).where(Attendance.work_date == today)
    if allowed is not None:
        att_stmt = att_stmt.join(Employee, Attendance.employee_id == Employee.id).where(
            Employee.department_id.in_(allowed or [-1]))
    today_att = db.scalars(att_stmt).all()
    att_summary = {
        "checked_in": len([a for a in today_att if a.check_in]),
        "late": len([a for a in today_att if a.status == "迟到"]),
        "leave": len([a for a in today_att if a.status == "请假"]),
        "not_checked": max(len(active_employees) - len([a for a in today_att if a.check_in]), 0),
    }

    leave_stmt = select(LeaveRequest).options(selectinload(LeaveRequest.employee))
    if not is_admin_like(user):
        if allowed is not None:
            leave_stmt = leave_stmt.join(Employee, LeaveRequest.employee_id == Employee.id).where(
                Employee.department_id.in_(allowed or [-1]))
    pending_leaves = db.scalars(leave_stmt.where(LeaveRequest.status == "待审批")).all()

    # ------------------------------------------------ 最近动态
    log_stmt = select(OperationLog).order_by(OperationLog.id.desc()).limit(8)
    if not is_admin_like(user):
        log_stmt = log_stmt.where(OperationLog.user_id == user.id)
    recent_logs = [l.to_dict() for l in db.scalars(log_stmt).all()]

    recent_reports = []
    for r in sorted(reports, key=lambda x: x.id, reverse=True)[:5]:
        d = r.to_dict()
        recent_reports.append(d)

    # ------------------------------------------------ 公告
    ann_stmt = (select(Announcement)
                .options(selectinload(Announcement.reads), selectinload(Announcement.publisher))
                .where(Announcement.is_published.is_(True))
                .order_by(Announcement.is_pinned.desc(), Announcement.id.desc()).limit(5))
    announcements = []
    for a in db.scalars(ann_stmt).all():
        d = a.to_dict()
        d["is_read"] = any(rd.user_id == user.id for rd in a.reads)
        announcements.append(d)

    # ------------------------------------------------ 我的待办
    my_emp = emp
    my_pending = db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == (my_emp.id if my_emp else -1),
            LeaveRequest.status == "待审批")
    ) or 0
    my_projects = []
    if my_emp:
        my_project_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == my_emp.id)).all()]
        my_projects = [p.to_dict() for p in projects
                       if p.id in my_project_ids or p.owner_id == my_emp.id][:5]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {"role": user.role, "department": user.department.name if user.department else None},
        "employee": {
            "total": len(employees),
            "active": len(active_employees),
            "probation": len([e for e in employees if e.status == "试用期"]),
            "resigned": len([e for e in employees if e.status == "离职"]),
            "by_department": emp_by_dept,
            "by_status": emp_by_status,
            "hire_trend": hire_trend,
        },
        "project": {
            "total": len(projects),
            "active": len(active_projects),
            "overdue": len(overdue_projects),
            "done": len([p for p in projects if p.status in ("已完成", "已归档")]),
            "avg_progress": round(sum(p.progress for p in active_projects) / len(active_projects))
            if active_projects else 0,
            "by_status": proj_by_status,
            "by_department": proj_by_dept,
            "focus": [p.to_dict() for p in focus],
            "overdue_list": [{"id": p.id, "name": p.name, "end_date": p.end_date.isoformat(),
                              "progress": p.progress} for p in overdue_projects[:5]],
        },
        "report": {
            "total": len(reports),
            "total_size": sum(r.file_size or 0 for r in reports),
            "downloads": sum(r.download_count or 0 for r in reports),
            "by_category": rep_by_category,
            "by_month": rep_by_month,
            "recent": recent_reports,
        },
        "attendance": att_summary,
        "leave": {
            "pending_total": len(pending_leaves),
            "my_pending": my_pending,
        },
        "recent_logs": recent_logs,
        "announcements": announcements,
        "my_projects": my_projects,
    }


@router.get("/org-chart", summary="组织架构图数据")
def org_chart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = scoped_department_ids(db, user)
    depts = db.scalars(
        select(Department).options(selectinload(Department.employees))
        .order_by(Department.sort_order, Department.id)
    ).all()
    if allowed is not None:
        depts = [d for d in depts if d.id in allowed]

    items = []
    for d in depts:
        members = [e for e in d.employees if e.status != "离职"]
        items.append({
            "id": d.id, "name": d.name, "parent_id": d.parent_id,
            "manager_name": d.manager.name if d.manager else None,
            "member_count": len(members),
            "members": [{"id": e.id, "name": e.name, "position": e.position, "status": e.status}
                        for e in sorted(members, key=lambda x: x.name)],
        })
    return {"items": items}
