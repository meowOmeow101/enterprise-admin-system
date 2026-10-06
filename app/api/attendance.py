"""考勤接口：打卡、考勤记录查询、月度汇总、补录。"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import assert_self_or_manager, current_employee, get_current_user, is_admin_like, require_manager, write_log
from ..models import Attendance, Employee, User

router = APIRouter(prefix="/attendance", tags=["考勤管理"])

# 考勤规则（如需调整，改这里即可，前端会通过 /rules 接口同步展示）
WORK_START = time(9, 0)
LATE_AFTER = time(9, 15)     # 9:15 之后算迟到
WORK_END = time(18, 0)
EARLY_BEFORE = time(17, 45)  # 17:45 之前走算早退


class AttendanceIn(BaseModel):
    employee_id: int
    work_date: str
    check_in: str | None = None
    check_out: str | None = None
    status: str | None = None
    remark: str | None = None


class CheckInIn(BaseModel):
    remark: str | None = None


def _parse_time_only(value: str | None) -> time | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _calc_status(rec: Attendance) -> str:
    """按打卡时间推断考勤状态。"""
    if rec.status in ("请假", "出差", "旷工"):
        return rec.status          # 人工标注的状态优先
    if not rec.check_in:
        return "缺卡"
    if rec.check_in.time() > LATE_AFTER:
        return "迟到"
    if rec.check_out and rec.check_out.time() < EARLY_BEFORE:
        return "早退"
    return "正常"


@router.get("/rules", summary="考勤规则说明")
def attendance_rules():
    return {
        "work_start": WORK_START.strftime("%H:%M"),
        "work_end": WORK_END.strftime("%H:%M"),
        "late_after": LATE_AFTER.strftime("%H:%M"),
        "early_before": EARLY_BEFORE.strftime("%H:%M"),
        "standard_hours": round((datetime.combine(date.today(), WORK_END)
                                 - datetime.combine(date.today(), WORK_START)).seconds / 3600, 1),
        "note": "上班晚于最晚打卡时间记为迟到，下班早于最早签退时间记为早退。",
    }


@router.get("/today", summary="我今天的考勤状态")
def my_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = current_employee(db, user)
    if not emp:
        return {"has_employee": False, "message": "当前账号未绑定员工档案，无法打卡"}
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id,
                                             Attendance.work_date == date.today()))
    return {
        "has_employee": True,
        "record": rec.to_dict() if rec else None,
        "can_check_in": rec is None or rec.check_in is None,
        "can_check_out": rec is not None and rec.check_out is None,
        "now": datetime.now().strftime("%H:%M:%S"),
    }


@router.post("/check-in", summary="上班打卡")
def check_in(payload: CheckInIn | None = None, request: Request = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = current_employee(db, user)
    if not emp:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前账号未绑定员工档案，请联系管理员")
    today = date.today()
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id,
                                             Attendance.work_date == today))
    now = datetime.now()
    if rec and rec.check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"今天已于 {rec.check_in:%H:%M:%S} 打过上班卡，无需重复打卡")

    if not rec:
        rec = Attendance(employee_id=emp.id, work_date=today, check_in=now,
                         remark=(payload.remark if payload else None))
        db.add(rec)
    else:
        rec.check_in = now
    rec.status = _calc_status(rec)
    db.commit()
    db.refresh(rec)
    write_log(db, user=user, action="打卡", module="考勤管理",
              detail=f"{emp.name} 上班打卡 {now:%H:%M:%S}（{rec.status}）",
              target_id=rec.id, request=request)
    return {"ok": True, "record": rec.to_dict(),
            "message": f"打卡成功 {now:%H:%M:%S}" + ("，已迟到" if rec.status == "迟到" else "")}


@router.post("/check-out", summary="下班打卡")
def check_out(payload: CheckInIn | None = None, request: Request = None,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = current_employee(db, user)
    if not emp:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前账号未绑定员工档案，请联系管理员")
    today = date.today()
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id,
                                             Attendance.work_date == today))
    now = datetime.now()
    if not rec or not rec.check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "还没打上班卡，请先打上班卡")
    if rec.check_out:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"今天已于 {rec.check_out:%H:%M:%S} 打过下班卡")

    rec.check_out = now
    rec.work_hours = round((now - rec.check_in).total_seconds() / 3600, 2)
    rec.status = _calc_status(rec)
    if payload and payload.remark:
        rec.remark = payload.remark
    db.commit()
    db.refresh(rec)
    write_log(db, user=user, action="打卡", module="考勤管理",
              detail=f"{emp.name} 下班打卡 {now:%H:%M:%S}（工时 {rec.work_hours} 小时）",
              target_id=rec.id, request=request)
    return {"ok": True, "record": rec.to_dict(),
            "message": f"签退成功 {now:%H:%M:%S}，今日工时 {rec.work_hours} 小时"}


@router.get("/records", summary="考勤记录查询")
def list_records(
    employee_id: int | None = None,
    department_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_: str | None = Query(None, alias="status"),
    scope: str = Query("scope", description="scope=部门范围 / mine=只看自己"),
    page: int = Query(1, ge=1),
    size: int = Query(31, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Attendance).options(
        selectinload(Attendance.employee).selectinload(Employee.department)
    )

    if scope == "mine":
        emp = current_employee(db, user)
        if not emp:
            return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}
        stmt = stmt.where(Attendance.employee_id == emp.id)
    elif not is_admin_like(user):
        # 非管理员只能看自己部门及下级部门
        from ..deps import scoped_department_ids

        allowed = scoped_department_ids(db, user) or []
        stmt = stmt.join(Employee, Attendance.employee_id == Employee.id).where(
            Employee.department_id.in_(allowed or [-1]))
        if user.role == "employee":
            emp = current_employee(db, user)
            stmt = stmt.where(Attendance.employee_id == (emp.id if emp else -1))

    if employee_id:
        emp_target = db.get(Employee, employee_id)
        assert_self_or_manager(db, user, emp_target)
        stmt = stmt.where(Attendance.employee_id == employee_id)
    if department_id:
        stmt = stmt.join(Employee, Attendance.employee_id == Employee.id, isouter=True).where(
            Employee.department_id == department_id)
    if date_from:
        stmt = stmt.where(Attendance.work_date >= date.fromisoformat(date_from[:10]))
    if date_to:
        stmt = stmt.where(Attendance.work_date <= date.fromisoformat(date_to[:10]))
    if status_:
        stmt = stmt.where(Attendance.status == status_)

    stmt = stmt.order_by(Attendance.work_date.desc(), Attendance.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()
    return {"items": [r.to_dict() for r in rows], "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


@router.get("/summary", summary="月度考勤汇总（按人统计）")
def monthly_summary(
    month: str = Query(..., description="格式 YYYY-MM"),
    department_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        year, mon = (int(x) for x in month.split("-")[:2])
        first = date(year, mon, 1)
        last = date(year, mon, calendar.monthrange(year, mon)[1])
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "月份格式应为 YYYY-MM")

    emp_stmt = select(Employee).options(selectinload(Employee.department)).where(
        Employee.status != "离职")
    from ..deps import scoped_department_ids

    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        emp_stmt = emp_stmt.where(Employee.department_id.in_(allowed or [-1]))
    if department_id:
        emp_stmt = emp_stmt.where(Employee.department_id == department_id)
    employees = db.scalars(emp_stmt).all()

    att_stmt = select(Attendance).where(Attendance.work_date.between(first, last))
    records = db.scalars(att_stmt).all()
    by_emp: dict[int, list[Attendance]] = {}
    for r in records:
        by_emp.setdefault(r.employee_id, []).append(r)

    workdays = sum(1 for d in range(1, last.day + 1)
                   if date(year, mon, d).weekday() < 5)   # 简单按周一到周五估算应出勤
    items = []
    for e in employees:
        recs = by_emp.get(e.id, [])
        items.append({
            "employee_id": e.id, "name": e.name, "emp_no": e.emp_no,
            "department_name": e.department.name if e.department else None,
            "workdays": workdays,
            "attended": len([r for r in recs if r.check_in]),
            "late": len([r for r in recs if r.status == "迟到"]),
            "early": len([r for r in recs if r.status == "早退"]),
            "absent": len([r for r in recs if r.status == "旷工"]),
            "leave": len([r for r in recs if r.status == "请假"]),
            "missing": len([r for r in recs if r.status == "缺卡"]),
            "total_hours": round(sum(r.work_hours or 0 for r in recs), 1),
        })
    items.sort(key=lambda x: (-x["late"], -x["missing"], x["name"]))
    return {"month": month, "workdays": workdays, "items": items, "total": len(items)}


@router.post("/records", summary="考勤补录 / 修正（管理员）")
def upsert_record(payload: AttendanceIn, request: Request,
                  user: User = Depends(require_manager), db: Session = Depends(get_db)):
    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "员工不存在")
    assert_self_or_manager(db, user, emp)
    try:
        work_day = date.fromisoformat(payload.work_date.strip()[:10])
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "日期格式应为 YYYY-MM-DD")

    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id,
                                             Attendance.work_date == work_day))
    if not rec:
        rec = Attendance(employee_id=emp.id, work_date=work_day)
        db.add(rec)

    if payload.check_in is not None:
        t = _parse_time_only(payload.check_in)
        rec.check_in = datetime.combine(work_day, t) if t else None
    if payload.check_out is not None:
        t = _parse_time_only(payload.check_out)
        rec.check_out = datetime.combine(work_day, t) if t else None
    if rec.check_in and rec.check_out:
        rec.work_hours = round((rec.check_out - rec.check_in).total_seconds() / 3600, 2)
    if payload.remark is not None:
        rec.remark = payload.remark

    rec.status = payload.status or _calc_status(rec)
    db.commit()
    db.refresh(rec)
    write_log(db, user=user, action="修改", module="考勤管理",
              detail=f"补录 {emp.name} {work_day} 的考勤（{rec.status}）",
              target_id=rec.id, request=request)
    return {"ok": True, "record": rec.to_dict(), "message": "考勤记录已保存"}


@router.delete("/records/{record_id}", summary="删除考勤记录（管理员）")
def delete_record(record_id: int, request: Request,
                  user: User = Depends(require_manager), db: Session = Depends(get_db)):
    rec = db.get(Attendance, record_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "记录不存在")
    assert_self_or_manager(db, user, rec.employee)
    detail = f"删除 {rec.employee.name if rec.employee else rec.employee_id} {rec.work_date} 的考勤记录"
    db.delete(rec)
    db.commit()
    write_log(db, user=user, action="删除", module="考勤管理", detail=detail,
              target_id=record_id, request=request)
    return {"ok": True, "message": "记录已删除"}
