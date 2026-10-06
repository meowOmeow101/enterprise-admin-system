"""请假 / 调休申请与审批接口。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import LEAVE_TYPES
from ..db import get_db
from ..deps import (assert_self_or_manager, current_employee, get_current_user, is_admin_like,
                    is_manager_like, require_manager, scoped_department_ids, write_log)
from ..models import Attendance, Employee, LeaveRequest, OperationLog, User

router = APIRouter(prefix="/leaves", tags=["请假审批"])


class LeaveIn(BaseModel):
    leave_type: str = "事假"
    start_date: str
    end_date: str
    days: float | None = Field(default=None, gt=0, le=365)
    reason: str | None = None
    employee_id: int | None = Field(default=None, description="仅管理员代他人提交时使用")


class ApproveIn(BaseModel):
    action: str = Field(description="approve 通过 / reject 驳回")
    comment: str | None = None


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field}格式应为 YYYY-MM-DD")


def _workdays(start: date, end: date) -> float:
    """按自然日计算天数（含首尾），周末也计入——公司实际规则不同可改这里。"""
    if end < start:
        return 0
    return float((end - start).days + 1)


def _sync_attendance(db: Session, leave: LeaveRequest, status_value: str) -> None:
    """审批通过后，把请假区间内的考勤记录标记为「请假」。"""
    day = leave.start_date
    while day <= leave.end_date:
        rec = db.scalar(select(Attendance).where(Attendance.employee_id == leave.employee_id,
                                                 Attendance.work_date == day))
        if rec:
            rec.status = status_value
            if status_value == "请假":
                rec.remark = f"{leave.leave_type}（审批通过）"
        elif status_value == "请假":
            db.add(Attendance(employee_id=leave.employee_id, work_date=day, status="请假",
                              remark=f"{leave.leave_type}（审批通过）", work_hours=0))
        day += timedelta(days=1)


def _visible_leave(db: Session, user: User, leave_id: int) -> LeaveRequest:
    leave = db.scalar(
        select(LeaveRequest).options(
            selectinload(LeaveRequest.employee).selectinload(Employee.department),
            selectinload(LeaveRequest.approver),
        ).where(LeaveRequest.id == leave_id)
    )
    if not leave:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "申请记录不存在")
    if is_admin_like(user):
        return leave
    emp = leave.employee
    if emp and emp.user_id == user.id:
        return leave
    allowed = scoped_department_ids(db, user) or []
    if emp and emp.department_id in allowed:
        return leave
    raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能查看本人或本部门的申请")


@router.get("", summary="请假申请列表")
def list_leaves(
    scope: str = Query("mine", description="mine 我的 / pending 待我审批 / dept 本部门 / all 全部"),
    status_: str | None = Query(None, alias="status"),
    leave_type: str | None = None,
    employee_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(LeaveRequest).options(
        selectinload(LeaveRequest.employee).selectinload(Employee.department),
        selectinload(LeaveRequest.approver),
    )
    me = current_employee(db, user)
    my_emp_id = me.id if me else -1

    if scope == "mine":
        stmt = stmt.where(LeaveRequest.employee_id == my_emp_id)
    elif scope == "pending":
        if user.role == "employee":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，普通员工没有审批权限")
        stmt = stmt.where(LeaveRequest.status == "待审批")
        if user.role == "manager":
            allowed = scoped_department_ids(db, user) or []
            stmt = stmt.join(Employee, LeaveRequest.employee_id == Employee.id).where(
                Employee.department_id.in_(allowed or [-1]))
    else:  # dept / all
        if user.role == "employee":
            # 与 scope=pending 保持一致：普通员工没有"部门视图"这个权限，
            # 明确报 403，而不是静默返回空列表让人以为"没有数据"。
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "权限不足，普通员工只能查看自己的申请记录")
        if user.role == "manager":
            allowed = scoped_department_ids(db, user) or []
            stmt = stmt.join(Employee, LeaveRequest.employee_id == Employee.id).where(
                Employee.department_id.in_(allowed or [-1]))

    if status_:
        stmt = stmt.where(LeaveRequest.status == status_)
    if leave_type:
        stmt = stmt.where(LeaveRequest.leave_type == leave_type)
    if employee_id:
        assert_self_or_manager(db, user, db.get(Employee, employee_id))
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(LeaveRequest.start_date >= _parse_date(date_from, "开始日期"))
    if date_to:
        stmt = stmt.where(LeaveRequest.end_date <= _parse_date(date_to, "结束日期"))

    stmt = stmt.order_by(LeaveRequest.status.asc(), LeaveRequest.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()

    items = []
    for lv in rows:
        d = lv.to_dict()
        d["can_approve"] = (lv.status == "待审批" and is_manager_like(user)
                            and lv.employee_id != my_emp_id)
        d["is_mine"] = lv.employee_id == my_emp_id
        items.append(d)
    return {"items": items, "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


@router.get("/stats", summary="请假统计")
def leave_stats(month: str | None = None, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    stmt = select(LeaveRequest).options(selectinload(LeaveRequest.employee))
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.join(Employee, LeaveRequest.employee_id == Employee.id).where(
            Employee.department_id.in_(allowed or [-1]))
    rows = db.scalars(stmt).unique().all()

    if month:
        try:
            y, m = (int(x) for x in month.split("-")[:2])
            rows = [r for r in rows if r.start_date.year == y and r.start_date.month == m]
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "月份格式应为 YYYY-MM")

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_type[r.leave_type] = by_type.get(r.leave_type, 0) + 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "by_type": by_type,
        "total_days": round(sum(r.days or 0 for r in rows if r.status == "已通过"), 1),
    }


@router.get("/types", summary="请假类型字典")
def leave_types():
    return {"items": LEAVE_TYPES}


@router.get("/{leave_id}", summary="申请详情")
def get_leave(leave_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _visible_leave(db, user, leave_id).to_dict()


@router.post("", summary="提交请假申请")
def create_leave(payload: LeaveIn, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    me = current_employee(db, user)
    if payload.employee_id and payload.employee_id != (me.id if me else None):
        if not is_admin_like(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只能为自己提交申请")
        me = db.get(Employee, payload.employee_id)
    if not me:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前账号未绑定员工档案，无法提交申请")

    if payload.leave_type not in LEAVE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"请假类型必须是：{'、'.join(LEAVE_TYPES)}")
    start = _parse_date(payload.start_date, "开始日期")
    end = _parse_date(payload.end_date, "结束日期")
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "结束日期不能早于开始日期")

    overlap = db.scalar(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == me.id,
            LeaveRequest.status.in_(("待审批", "已通过")),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
    )
    if overlap:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"该时间段与已有申请（{overlap.start_date} ~ {overlap.end_date}，"
                            f"{overlap.status}）重叠，请勿重复提交")

    leave = LeaveRequest(
        employee_id=me.id,
        leave_type=payload.leave_type,
        start_date=start,
        end_date=end,
        days=payload.days or _workdays(start, end),
        reason=payload.reason,
        status="待审批",
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    write_log(db, user=user, action="申请", module="请假审批",
              detail=f"{me.name} 提交{leave.leave_type}申请 {start} ~ {end}（{leave.days} 天）",
              target_id=leave.id, request=request)
    return {"ok": True, "leave": leave.to_dict(), "message": "申请已提交，等待审批"}


@router.post("/{leave_id}/approve", summary="审批（通过 / 驳回）")
def approve_leave(leave_id: int, payload: ApproveIn, request: Request,
                  user: User = Depends(require_manager), db: Session = Depends(get_db)):
    leave = _visible_leave(db, user, leave_id)
    if leave.status != "待审批":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"该申请已是「{leave.status}」状态，无法重复审批")

    me = current_employee(db, user)
    if me and leave.employee_id == me.id and not is_admin_like(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "不能审批自己提交的申请")

    if payload.action not in ("approve", "reject"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action 必须是 approve 或 reject")
    if payload.action == "reject" and not (payload.comment or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "驳回时请填写审批意见")

    if payload.action == "approve":
        leave.status = "已通过"
        _sync_attendance(db, leave, "请假")
    else:
        leave.status = "已驳回"
    leave.approver_id = user.id
    leave.approved_at = datetime.now()
    leave.approve_comment = payload.comment
    db.commit()
    db.refresh(leave)

    action_label = "通过" if payload.action == "approve" else "驳回"
    write_log(db, user=user, action="审批", module="请假审批",
              detail=f"{action_label} {leave.employee.name if leave.employee else ''} 的"
                     f"{leave.leave_type}申请（{leave.start_date} ~ {leave.end_date}）"
                     + (f"，意见：{payload.comment}" if payload.comment else ""),
              target_id=leave.id, request=request)
    return {"ok": True, "leave": leave.to_dict(),
            "message": f"已{action_label}该申请"}


@router.post("/{leave_id}/cancel", summary="撤销自己的申请")
def cancel_leave(leave_id: int, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    leave = _visible_leave(db, user, leave_id)
    me = current_employee(db, user)
    if not is_admin_like(user) and (not me or leave.employee_id != me.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能撤销自己提交的申请")
    if leave.status != "待审批":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"「{leave.status}」的申请不能撤销")

    leave.status = "已撤销"
    _sync_attendance(db, leave, "正常")
    db.commit()
    write_log(db, user=user, action="修改", module="请假审批",
              detail=f"撤销 {leave.leave_type}申请（{leave.start_date} ~ {leave.end_date}）",
              target_id=leave.id, request=request)
    return {"ok": True, "message": "申请已撤销"}


@router.delete("/{leave_id}", summary="删除申请记录（管理员）")
def delete_leave(leave_id: int, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    leave = _visible_leave(db, user, leave_id)
    me = current_employee(db, user)
    is_own = me and leave.employee_id == me.id
    if not is_admin_like(user):
        if not (is_own and leave.status in ("已驳回", "已撤销")):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "只能删除自己被驳回或已撤销的申请记录")
    db.delete(leave)
    db.commit()
    write_log(db, user=user, action="删除", module="请假审批",
              detail=f"删除 {leave.employee.name if leave.employee else ''} 的请假记录",
              target_id=leave_id, request=request)
    return {"ok": True, "message": "记录已删除"}
