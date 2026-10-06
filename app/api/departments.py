"""部门 / 组织架构接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import (assert_department_in_scope, get_current_user, is_admin_like,
                    require_manager, scoped_department_ids, write_log)
from ..models import Department, Employee, User

router = APIRouter(prefix="/departments", tags=["部门管理"])


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str | None = Field(default=None, max_length=32)
    parent_id: int | None = None
    manager_id: int | None = None
    description: str | None = None
    sort_order: int = 0


def _load(db: Session, dept_id: int) -> Department | None:
    return db.scalar(
        select(Department).options(selectinload(Department.employees))
        .where(Department.id == dept_id)
    )


def _assert_no_cycle(db: Session, dept_id: int, new_parent_id: int | None) -> None:
    """防止把部门挂到自己的子孙节点下，形成环。"""
    cur = new_parent_id
    guard = 0
    while cur and guard < 100:
        if cur == dept_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能把部门移动到它自己的下级部门里")
        parent = db.get(Department, cur)
        cur = parent.parent_id if parent else None
        guard += 1


@router.get("/tree", summary="部门树（含人数统计）")
def department_tree(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = scoped_department_ids(db, user)
    rows = db.scalars(
        select(Department).options(selectinload(Department.employees))
        .order_by(Department.sort_order, Department.id)
    ).all()
    if allowed is not None:
        rows = [d for d in rows if d.id in allowed]

    items = [d.to_dict() for d in rows]
    id_map = {d["id"]: d for d in items}
    for d in items:
        d["children"] = []
    roots: list[dict] = []
    for d in items:
        parent = id_map.get(d["parent_id"]) if d["parent_id"] else None
        # 父部门不在可见范围时，该部门按根节点展示，避免整枝消失
        (parent["children"] if parent else roots).append(d)
    return {"items": items, "tree": roots, "total": len(items)}


@router.get("", summary="部门列表（平铺）")
def list_departments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = scoped_department_ids(db, user)
    rows = db.scalars(
        select(Department).options(selectinload(Department.employees))
        .order_by(Department.sort_order, Department.id)
    ).all()
    if allowed is not None:
        rows = [d for d in rows if d.id in allowed]
    return {"items": [d.to_dict() for d in rows], "total": len(rows)}


@router.post("", summary="新建部门")
def create_department(payload: DepartmentIn, request: Request,
                      user: User = Depends(require_manager), db: Session = Depends(get_db)):
    if db.scalar(select(Department).where(Department.name == payload.name.strip())):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"部门「{payload.name}」已存在")
    if payload.code and db.scalar(select(Department).where(Department.code == payload.code.strip())):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"部门编码「{payload.code}」已被占用")
    if payload.parent_id:
        assert_department_in_scope(db, user, payload.parent_id)
        if not db.get(Department, payload.parent_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "上级部门不存在")
    elif not is_admin_like(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有系统管理员可以创建顶级部门")

    dept = Department(
        name=payload.name.strip(),
        code=payload.code.strip() if payload.code else None,
        parent_id=payload.parent_id,
        manager_id=payload.manager_id,
        description=payload.description,
        sort_order=payload.sort_order,
    )
    db.add(dept)
    db.commit()
    write_log(db, user=user, action="新增", module="部门管理",
              detail=f"新建部门 {dept.name}", target_id=dept.id, request=request)
    return _load(db, dept.id).to_dict()


@router.put("/{dept_id}", summary="修改部门")
def update_department(dept_id: int, payload: DepartmentIn, request: Request,
                      user: User = Depends(require_manager), db: Session = Depends(get_db)):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部门不存在")
    assert_department_in_scope(db, user, dept.id)

    if payload.parent_id is not None:
        _assert_no_cycle(db, dept_id, payload.parent_id)
        if payload.parent_id:
            assert_department_in_scope(db, user, payload.parent_id)
    dup = db.scalar(select(Department).where(Department.name == payload.name.strip(),
                                            Department.id != dept_id))
    if dup:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"部门「{payload.name}」已存在")

    dept.name = payload.name.strip()
    dept.code = payload.code.strip() if payload.code else None
    dept.parent_id = payload.parent_id
    dept.manager_id = payload.manager_id
    dept.description = payload.description
    dept.sort_order = payload.sort_order
    db.commit()
    write_log(db, user=user, action="修改", module="部门管理",
              detail=f"修改部门 {dept.name}", target_id=dept.id, request=request)
    return _load(db, dept.id).to_dict()


@router.delete("/{dept_id}", summary="删除部门")
def delete_department(dept_id: int, request: Request,
                      user: User = Depends(require_manager), db: Session = Depends(get_db)):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部门不存在")
    assert_department_in_scope(db, user, dept.id)

    child_count = len(db.scalars(select(Department.id).where(Department.parent_id == dept_id)).all())
    if child_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该部门下还有子部门，请先处理子部门")
    emp_count = len([e for e in db.scalars(select(Employee).where(Employee.department_id == dept_id)).all()
                     if e.status != "离职"])
    if emp_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"该部门下还有 {emp_count} 名在职员工，请先调整其归属部门")

    name = dept.name
    db.delete(dept)
    db.commit()
    write_log(db, user=user, action="删除", module="部门管理",
              detail=f"删除部门 {name}", target_id=dept_id, request=request)
    return {"ok": True, "message": f"部门「{name}」已删除"}
