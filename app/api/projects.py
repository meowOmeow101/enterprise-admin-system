"""项目管理接口：CRUD、项目成员、统计。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import PROJECT_PRIORITY, PROJECT_STATUS
from ..db import get_db
from ..deps import (assert_department_in_scope, current_employee, get_current_user,
                    is_admin_like, require_manager, scoped_department_ids, write_log)
from ..models import Department, Employee, Project, ProjectMember, Report, User

router = APIRouter(prefix="/projects", tags=["项目管理"])


class ProjectIn(BaseModel):
    code: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    customer: str | None = None
    status: str = "进行中"
    priority: str = "中"
    progress: int = Field(default=0, ge=0, le=100)
    department_id: int | None = None
    owner_id: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    budget: float | None = None


class MemberIn(BaseModel):
    employee_id: int
    role: str | None = Field(default=None, max_length=32)


class MembersIn(BaseModel):
    members: list[MemberIn] = Field(min_length=1)


class ProgressIn(BaseModel):
    progress: int = Field(ge=0, le=100)
    remark: str | None = None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"日期格式应为 YYYY-MM-DD，收到：{value}")


def _load(db: Session, project_id: int) -> Project:
    p = db.scalar(
        select(Project)
        .options(selectinload(Project.department), selectinload(Project.owner),
                 selectinload(Project.members).selectinload(ProjectMember.employee),
                 selectinload(Project.reports))
        .where(Project.id == project_id)
    )
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    return p


def _visible_project(db: Session, user: User, project_id: int) -> Project:
    p = _load(db, project_id)
    allowed = scoped_department_ids(db, user)
    if allowed is None:
        return p
    # 本部门项目、或本人参与的项目，都可以看
    emp = current_employee(db, user)
    is_member = emp is not None and any(m.employee_id == emp.id for m in p.members)
    if p.department_id in allowed or is_member:
        return p
    raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能查看本部门或本人参与的项目")


def _next_code(db: Session) -> str:
    year = date.today().year
    prefix = f"PRJ-{year}-"
    count = db.scalar(select(func.count(Project.id)).where(Project.code.like(f"{prefix}%"))) or 0
    while True:
        count += 1
        candidate = f"{prefix}{count:03d}"
        if not db.scalar(select(Project.id).where(Project.code == candidate)):
            return candidate


def _assert_project_write(db: Session, user: User, project: Project | None,
                          department_id: int | None) -> None:
    """
    项目写权限：
      - admin：全部
      - manager：本部门及下级部门的项目
      - employee：只能改自己参与项目（仅限进度，接口层单独判断）
    """
    if is_admin_like(user):
        return
    if user.role == "manager":
        allowed = scoped_department_ids(db, user) or []
        target_dept = project.department_id if project else department_id
        if target_dept in allowed:
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能管理本部门及下级部门的项目")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，普通员工不能创建或删除项目")


# ==================================================================== 查询
@router.get("", summary="项目列表（分页 + 筛选）")
def list_projects(
    keyword: str | None = Query(None, description="项目名/编号/客户 模糊搜索"),
    status_: str | None = Query(None, alias="status"),
    priority: str | None = None,
    department_id: int | None = None,
    owner_id: int | None = None,
    mine: bool = Query(False, description="只看我参与的项目"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Project).options(
        selectinload(Project.department), selectinload(Project.owner),
        selectinload(Project.members), selectinload(Project.reports),
    )
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        emp = current_employee(db, user)
        member_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == (emp.id if emp else -1))
        ).all()]
        cond = Project.department_id.in_(allowed or [-1])
        if member_ids:
            cond = or_(cond, Project.id.in_(member_ids))
        stmt = stmt.where(cond)

    if mine:
        emp = current_employee(db, user)
        if not emp:
            return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}
        my_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == emp.id)).all()]
        stmt = stmt.where(or_(Project.id.in_(my_ids or [-1]), Project.owner_id == emp.id))

    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Project.name.like(kw), Project.code.like(kw), Project.customer.like(kw)))
    if status_:
        stmt = stmt.where(Project.status == status_)
    if priority:
        stmt = stmt.where(Project.priority == priority)
    if department_id:
        stmt = stmt.where(Project.department_id == department_id)
    if owner_id:
        stmt = stmt.where(Project.owner_id == owner_id)

    stmt = stmt.order_by(Project.updated_at.desc(), Project.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()

    # 数据库排序拿不到"剩余天数"，这里按状态+截止日期再排一次，让紧急的排前面
    items = [p.to_dict() for p in rows]
    items.sort(key=lambda p: (p["status"] in ("已完成", "已归档"),
                              p["end_date"] or "9999-12-31"))
    return {"items": items, "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


@router.get("/options", summary="项目下拉选项")
def project_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Project)
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Project.department_id.in_(allowed or [-1]))
    rows = db.scalars(stmt.order_by(Project.name)).all()
    return {"items": [{"id": p.id, "name": p.name, "code": p.code, "status": p.status}
                      for p in rows]}


@router.get("/stats", summary="项目统计（看板用）")
def project_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Project).options(selectinload(Project.members), selectinload(Project.reports))
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Project.department_id.in_(allowed or [-1]))
    rows = db.scalars(stmt).unique().all()

    by_status = {s: 0 for s in PROJECT_STATUS}
    by_priority = {p: 0 for p in PROJECT_PRIORITY}
    by_dept: dict[str, int] = {}
    overdue = 0
    today = date.today()
    for p in rows:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        by_priority[p.priority] = by_priority.get(p.priority, 0) + 1
        key = p.department.name if p.department else "未分配"
        by_dept[key] = by_dept.get(key, 0) + 1
        if p.end_date and p.end_date < today and p.status not in ("已完成", "已归档"):
            overdue += 1

    active = [p for p in rows if p.status not in ("已完成", "已归档")]
    avg_progress = round(sum(p.progress for p in active) / len(active)) if active else 0
    return {
        "total": len(rows),
        "active": len(active),
        "overdue": overdue,
        "avg_progress": avg_progress,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_department": by_dept,
        "report_total": sum(len(p.reports or []) for p in rows),
    }


@router.get("/{project_id}", summary="项目详情")
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _visible_project(db, user, project_id)
    data = p.to_dict()
    data["members"] = [
        {"id": m.id, "employee_id": m.employee_id,
         "name": m.employee.name if m.employee else None,
         "emp_no": m.employee.emp_no if m.employee else None,
         "position": m.employee.position if m.employee else None,
         "department_name": (m.employee.department.name
                             if m.employee and m.employee.department else None),
         "role": m.role, "joined_at": m.joined_at.isoformat() if m.joined_at else None}
        for m in p.members
    ]
    data["reports"] = [r.to_dict() for r in
                       sorted(p.reports, key=lambda r: (r.report_date or date.min, r.id), reverse=True)]
    return data


# ==================================================================== 写操作
@router.post("", summary="新建项目")
def create_project(payload: ProjectIn, request: Request,
                   user: User = Depends(require_manager), db: Session = Depends(get_db)):
    _assert_project_write(db, user, None, payload.department_id)
    if payload.status not in PROJECT_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"状态必须是：{'、'.join(PROJECT_STATUS)}")
    if payload.priority not in PROJECT_PRIORITY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"优先级必须是：{'、'.join(PROJECT_PRIORITY)}")

    code = (payload.code or "").strip() or _next_code(db)
    if db.scalar(select(Project).where(Project.code == code)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"项目编号 {code} 已存在")
    if payload.owner_id and not db.get(Employee, payload.owner_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "项目负责人不存在")

    project = Project(
        code=code, name=payload.name.strip(), description=payload.description,
        customer=payload.customer, status=payload.status, priority=payload.priority,
        progress=payload.progress, department_id=payload.department_id,
        owner_id=payload.owner_id, budget=payload.budget,
        start_date=_parse_date(payload.start_date), end_date=_parse_date(payload.end_date),
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    # 负责人自动进成员列表，省得再手动加一次
    if payload.owner_id:
        db.add(ProjectMember(project_id=project.id, employee_id=payload.owner_id, role="项目负责人"))
    db.commit()
    write_log(db, user=user, action="新增", module="项目管理",
              detail=f"新建项目 {project.name}（{project.code}）", target_id=project.id, request=request)
    return _load(db, project.id).to_dict()


@router.put("/{project_id}", summary="修改项目")
def update_project(project_id: int, payload: ProjectIn, request: Request,
                   user: User = Depends(require_manager), db: Session = Depends(get_db)):
    project = _load(db, project_id)
    _assert_project_write(db, user, project, payload.department_id or project.department_id)

    if payload.code and payload.code.strip() != project.code:
        if db.scalar(select(Project).where(Project.code == payload.code.strip(),
                                           Project.id != project_id)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"项目编号 {payload.code} 已存在")
        project.code = payload.code.strip()
    if payload.status not in PROJECT_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"状态必须是：{'、'.join(PROJECT_STATUS)}")

    if not is_admin_like(user):
        # 主管不能把项目改到自己管不着的部门
        assert_department_in_scope(db, user, payload.department_id or project.department_id)

    project.name = payload.name.strip()
    project.description = payload.description
    project.customer = payload.customer
    project.status = payload.status
    project.priority = payload.priority
    project.progress = payload.progress
    project.department_id = payload.department_id
    project.owner_id = payload.owner_id
    project.budget = payload.budget
    project.start_date = _parse_date(payload.start_date)
    project.end_date = _parse_date(payload.end_date)
    if project.progress == 100 and project.status not in ("已完成", "已归档"):
        project.status = "已完成"
    db.commit()
    write_log(db, user=user, action="修改", module="项目管理",
              detail=f"修改项目 {project.name}（进度 {project.progress}%，状态 {project.status}）",
              target_id=project.id, request=request)
    return _load(db, project.id).to_dict()


@router.patch("/{project_id}/progress", summary="更新项目进度（项目成员也可操作）")
def update_progress(project_id: int, payload: ProgressIn, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _visible_project(db, user, project_id)
    if user.role == "employee":
        emp = current_employee(db, user)
        if not emp or not any(m.employee_id == emp.id for m in project.members):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有项目成员可以更新进度")
    project.progress = payload.progress
    if payload.progress == 100 and project.status not in ("已完成", "已归档"):
        project.status = "已完成"
    db.commit()
    detail = f"{project.name} 进度更新为 {payload.progress}%"
    if payload.remark:
        detail += f"（{payload.remark}）"
    write_log(db, user=user, action="修改", module="项目管理", detail=detail,
              target_id=project.id, request=request)
    return {"ok": True, "progress": project.progress, "status": project.status,
            "message": f"进度已更新为 {project.progress}%"}


@router.delete("/{project_id}", summary="删除项目")
def delete_project(project_id: int, request: Request,
                   user: User = Depends(require_manager), db: Session = Depends(get_db)):
    project = _load(db, project_id)
    _assert_project_write(db, user, project, project.department_id)
    if project.reports:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"该项目下还有 {len(project.reports)} 份报告，请先删除报告或改为「已归档」")
    name, code = project.name, project.code
    db.delete(project)
    db.commit()
    write_log(db, user=user, action="删除", module="项目管理",
              detail=f"删除项目 {name}（{code}）", target_id=project_id, request=request)
    return {"ok": True, "message": f"项目「{name}」已删除"}


# ==================================================================== 项目成员
@router.post("/{project_id}/members", summary="添加项目成员（支持批量）")
def add_members(project_id: int, payload: MembersIn, request: Request,
                user: User = Depends(require_manager), db: Session = Depends(get_db)):
    project = _load(db, project_id)
    _assert_project_write(db, user, project, project.department_id)

    existing = {m.employee_id for m in project.members}
    added = []
    for item in payload.members:
        if item.employee_id in existing:
            continue
        emp = db.get(Employee, item.employee_id)
        if not emp:
            continue
        db.add(ProjectMember(project_id=project_id, employee_id=item.employee_id, role=item.role))
        existing.add(item.employee_id)
        added.append(emp.name)
    db.commit()
    write_log(db, user=user, action="新增", module="项目管理",
              detail=f"为项目 {project.name} 添加成员：{'、'.join(added) if added else '无新增'}",
              target_id=project_id, request=request)
    return {"ok": True, "added": added,
            "message": f"已添加 {len(added)} 名成员" if added else "所选员工都已在项目中"}


@router.delete("/{project_id}/members/{member_id}", summary="移除项目成员")
def remove_member(project_id: int, member_id: int, request: Request,
                  user: User = Depends(require_manager), db: Session = Depends(get_db)):
    project = _load(db, project_id)
    _assert_project_write(db, user, project, project.department_id)
    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员记录不存在")
    if project.owner_id == member.employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能移除项目负责人，请先更换负责人")

    name = member.employee.name if member.employee else str(member.employee_id)
    db.delete(member)
    db.commit()
    write_log(db, user=user, action="删除", module="项目管理",
              detail=f"将 {name} 移出项目 {project.name}", target_id=project_id, request=request)
    return {"ok": True, "message": f"已将 {name} 移出项目"}
