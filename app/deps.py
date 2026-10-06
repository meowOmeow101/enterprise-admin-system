"""
FastAPI 公共依赖：登录校验、角色校验、数据范围（部门级隔离）、操作日志。
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ADMIN_LIKE_ROLES, MANAGER_LIKE_ROLES, ROLE_LABELS
from .db import get_db
from .models import Employee, OperationLog, User
from .security import decode_access_token


# ==================================================================== 认证
def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析当前登录用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期，请重新登录")

    payload = decode_access_token(authorization.split(" ", 1)[1].strip())
    if not payload or not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录凭证无效，请重新登录")

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被停用，请联系管理员")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    """生成一个"只允许指定角色访问"的依赖。"""
    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            names = "、".join(ROLE_LABELS.get(r, r) for r in roles)
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"权限不足，该操作仅限：{names}")
        return user

    return _dep


def is_admin_like(user: User | None) -> bool:
    """
    是否为最高权限角色（老板 / 系统管理员）。

    权限判断统一走这里：新角色只要加进 config.ADMIN_LIKE_ROLES 就自动生效，
    不用再去各个接口里改 `user.role == "admin"`。
    """
    return bool(user) and user.role in ADMIN_LIKE_ROLES


def is_manager_like(user: User | None) -> bool:
    """是否为管理级角色（老板 / 系统管理员 / 部门主管）。"""
    return bool(user) and user.role in MANAGER_LIKE_ROLES


require_admin = require_roles(*ADMIN_LIKE_ROLES)
require_manager = require_roles(*MANAGER_LIKE_ROLES)
require_any = get_current_user


# ==================================================================== 数据范围
def current_employee(db: Session, user: User) -> Employee | None:
    """取当前登录用户名下的员工档案（可能没有）。"""
    return db.scalar(select(Employee).where(Employee.user_id == user.id))


def scoped_department_ids(db: Session, user: User) -> list[int] | None:
    """
    返回当前用户可见的部门 id 列表：
      - 老板 / 管理员：None 表示不限制（全公司）
      - manager：本部门 + 所有子部门
      - employee：仅本部门
    """
    if is_admin_like(user):
        return None
    if user.department_id is None:
        return []

    from .models import Department

    if user.role == "employee":
        return [user.department_id]

    # manager：递归收集子部门
    all_depts = db.execute(select(Department.id, Department.parent_id)).all()
    children: dict[int | None, list[int]] = {}
    for did, pid in all_depts:
        children.setdefault(pid, []).append(did)

    result: list[int] = []
    stack = [user.department_id]
    while stack:
        cur = stack.pop()
        result.append(cur)
        stack.extend(children.get(cur, []))
    return result


def assert_department_in_scope(db: Session, user: User, department_id: int | None) -> None:
    """
    校验目标部门是否在当前用户的可管理范围内，不在则 403。
    老板/管理员不受限；主管只能管自己部门及其子部门；员工一律拒绝。
    """
    if is_admin_like(user):
        return
    if user.role == "employee":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，普通员工不能修改部门数据")
    if department_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先为记录指定所属部门")
    allowed = scoped_department_ids(db, user) or []
    if department_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能管理本部门及下级部门的数据")


def assert_self_or_manager(db: Session, user: User, employee: Employee | None) -> None:
    """考勤/请假等个人数据的访问校验：本人、本部门主管、最高权限角色三者之一。"""
    if is_admin_like(user):
        return
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未找到对应员工档案")
    if employee.user_id == user.id:
        return
    allowed = scoped_department_ids(db, user) or []
    if employee.department_id in allowed:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能查看本人或本部门的数据")


# ==================================================================== 审计
def write_log(
    db: Session,
    *,
    user: User | None,
    action: str,
    module: str,
    detail: str | None = None,
    target_id: int | None = None,
    request: Request | None = None,
    commit: bool = True,
) -> None:
    """写一条操作日志。默认顺带提交，避免调用方忘记。"""
    ip = None
    if request is not None:
        ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    db.add(
        OperationLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            module=module,
            detail=detail,
            target_id=target_id,
            ip=ip,
        )
    )
    if commit:
        db.commit()
