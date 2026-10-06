"""认证与账号相关接口。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import ROLE_LABELS
from ..db import get_db
from ..deps import current_employee, get_current_user, require_admin, write_log
from ..models import Department, Employee, User
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["认证"])


# ------------------------------------------------------------------ 入参模型
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ProfileIn(BaseModel):
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    real_name: str = Field(min_length=1, max_length=64)
    role: str = "employee"
    department_id: int | None = None
    phone: str | None = None
    email: str | None = None


class UserUpdateIn(BaseModel):
    real_name: str | None = None
    role: str | None = None
    department_id: int | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


# ------------------------------------------------------------------ 接口
@router.post("/login", summary="登录，返回访问令牌")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username.strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        # 不区分"用户不存在"与"密码错误"，避免账号枚举
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被停用，请联系管理员")

    user.last_login_at = datetime.now()
    db.commit()

    token = create_access_token(user.id, {"role": user.role, "name": user.real_name})
    write_log(db, user=user, action="登录", module="认证", detail=f"{user.real_name} 登录系统",
              request=request)
    return {"token": token, "user": user.to_dict(), "roles": ROLE_LABELS}


@router.get("/me", summary="当前登录用户信息")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = current_employee(db, user)
    data = user.to_dict()
    data["employee"] = emp.to_dict() if emp else None
    return data


@router.put("/me", summary="修改个人资料")
def update_me(payload: ProfileIn, request: Request,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value)
    # 员工档案里同步一份联系方式，避免两处填的信息不一致
    emp = current_employee(db, user)
    if emp:
        if payload.real_name:
            emp.name = payload.real_name
        if payload.phone:
            emp.phone = payload.phone
        if payload.email:
            emp.email = payload.email
    db.commit()
    write_log(db, user=user, action="修改", module="个人中心", detail="更新个人资料", request=request)
    return user.to_dict()


@router.post("/change-password", summary="修改自己的密码")
def change_password(payload: PasswordIn, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "原密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与原密码相同")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    write_log(db, user=user, action="修改", module="个人中心", detail="修改登录密码", request=request)
    return {"ok": True, "message": "密码修改成功，请重新登录"}


# ------------------------------------------------------------------ 账号管理（管理员）
@router.get("/users", summary="账号列表")
def list_users(keyword: str | None = None, role: str | None = None,
               department_id: int | None = None, is_active: bool | None = None,
               page: int = 1, size: int = 20,
               user: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id.desc())
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(User.username.like(kw), User.real_name.like(kw)))
    if role:
        stmt = stmt.where(User.role == role)
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return {"items": [u.to_dict() for u in rows], "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


@router.post("/users", summary="新建登录账号")
def create_user(payload: UserCreateIn, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in ROLE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色不合法")
    if db.scalar(select(User).where(User.username == payload.username.strip())):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"用户名 {payload.username} 已存在")
    if payload.department_id and not db.get(Department, payload.department_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "所选部门不存在")

    new_user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        real_name=payload.real_name.strip(),
        role=payload.role,
        department_id=payload.department_id,
        phone=payload.phone,
        email=payload.email,
    )
    db.add(new_user)
    db.commit()
    write_log(db, user=admin, action="新增", module="账号管理",
              detail=f"新建账号 {new_user.username}（{new_user.real_name}，{ROLE_LABELS[new_user.role]}）",
              target_id=new_user.id, request=request)
    return new_user.to_dict()


@router.put("/users/{user_id}", summary="修改账号")
def update_user(user_id: int, payload: UserUpdateIn, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("role") and data["role"] not in ROLE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色不合法")
    if target.id == admin.id and data.get("is_active") is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用当前登录的管理员账号")

    for field, value in data.items():
        setattr(target, field, value)
    db.commit()
    write_log(db, user=admin, action="修改", module="账号管理",
              detail=f"修改账号 {target.username}：{data}", target_id=target.id, request=request)
    return target.to_dict()


@router.post("/users/{user_id}/reset-password", summary="重置账号密码")
def reset_password(user_id: int, payload: ResetPasswordIn, request: Request,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    target.password_hash = hash_password(payload.new_password)
    db.commit()
    write_log(db, user=admin, action="修改", module="账号管理",
              detail=f"重置账号 {target.username} 的密码", target_id=target.id, request=request)
    return {"ok": True, "message": f"已重置 {target.real_name} 的密码"}


@router.delete("/users/{user_id}", summary="删除账号")
def delete_user(user_id: int, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除自己的账号")

    # 员工档案保留，仅解除绑定，避免删账号把人一起删了
    for emp in db.scalars(select(Employee).where(Employee.user_id == target.id)).all():
        emp.user_id = None
    username = target.username
    db.delete(target)
    db.commit()
    write_log(db, user=admin, action="删除", module="账号管理",
              detail=f"删除账号 {username}", target_id=user_id, request=request)
    return {"ok": True, "message": f"账号 {username} 已删除"}
