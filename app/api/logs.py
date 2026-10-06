"""操作日志（审计）接口。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..models import OperationLog, User

router = APIRouter(prefix="/logs", tags=["操作日志"])

MODULES = ["认证", "员工管理", "部门管理", "项目管理", "报告管理", "考勤管理",
           "请假审批", "公告通知", "账号管理", "个人中心", "导出", "导入"]
ACTIONS = ["新增", "修改", "删除", "登录", "上传", "下载", "审批", "申请", "打卡", "导出", "导入"]


@router.get("", summary="操作日志查询（管理员）")
def list_logs(
    keyword: str | None = Query(None, description="按操作人或详情模糊搜索"),
    module: str | None = None,
    action: str | None = None,
    username: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(OperationLog)
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(OperationLog.detail.like(kw), OperationLog.username.like(kw)))
    if module:
        stmt = stmt.where(OperationLog.module == module)
    if action:
        stmt = stmt.where(OperationLog.action == action)
    if username:
        stmt = stmt.where(OperationLog.username == username)
    if date_from:
        stmt = stmt.where(OperationLog.created_at >= datetime.fromisoformat(date_from[:10]))
    if date_to:
        end = date.fromisoformat(date_to[:10]) + timedelta(days=1)
        stmt = stmt.where(OperationLog.created_at < datetime.combine(end, datetime.min.time()))

    stmt = stmt.order_by(OperationLog.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return {"items": [r.to_dict() for r in rows], "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0,
            "modules": MODULES, "actions": ACTIONS}


@router.get("/stats", summary="日志统计")
def log_stats(days: int = Query(7, ge=1, le=90), _: User = Depends(require_admin),
              db: Session = Depends(get_db)):
    since = datetime.now() - timedelta(days=days)
    rows = db.scalars(select(OperationLog).where(OperationLog.created_at >= since)).all()

    by_module: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_user: dict[str, int] = {}
    by_day: dict[str, int] = {}
    for r in rows:
        by_module[r.module] = by_module.get(r.module, 0) + 1
        by_action[r.action] = by_action.get(r.action, 0) + 1
        key_user = r.username or "未知"
        by_user[key_user] = by_user.get(key_user, 0) + 1
        key_day = r.created_at.strftime("%Y-%m-%d")
        by_day[key_day] = by_day.get(key_day, 0) + 1

    return {"days": days, "total": len(rows), "by_module": by_module, "by_action": by_action,
            "by_user": dict(sorted(by_user.items(), key=lambda kv: -kv[1])[:10]),
            "by_day": dict(sorted(by_day.items()))}


@router.get("/mine", summary="我的操作记录")
def my_logs(page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=200),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(OperationLog).where(OperationLog.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(OperationLog.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    return {"items": [r.to_dict() for r in rows], "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}
