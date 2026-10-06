"""员工管理接口：CRUD、批量操作、开通账号、Excel 导入导出。"""
from __future__ import annotations

import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import EMPLOYEE_STATUS, ROLE_LABELS
from ..db import get_db
from ..deps import (assert_department_in_scope, get_current_user, is_admin_like, require_admin,
                    require_manager, scoped_department_ids, write_log)
from ..models import Department, Employee, User
from ..security import hash_password
from .common import attachment_header

router = APIRouter(prefix="/employees", tags=["员工管理"])

# 只有系统管理员能看/改的敏感字段
SENSITIVE_FIELDS = ("salary", "id_card")

# 导入时允许的列名 -> 模型字段
IMPORT_COLUMNS = {
    "工号": "emp_no", "姓名": "name", "性别": "gender", "手机号": "phone", "邮箱": "email",
    "部门": "department_name", "职位": "position", "职级": "job_level", "状态": "status",
    "入职日期": "hire_date", "学历": "education", "毕业院校": "school", "身份证号": "id_card",
    "月薪": "salary", "住址": "address", "紧急联系人": "emergency_contact",
    "紧急联系电话": "emergency_phone", "备注": "remark",
}


class EmployeeIn(BaseModel):
    emp_no: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    gender: str | None = "保密"
    birth_date: str | None = None
    phone: str | None = None
    email: str | None = None
    id_card: str | None = None
    department_id: int | None = None
    position: str | None = None
    job_level: str | None = None
    status: str = "在职"
    hire_date: str | None = None
    leave_date: str | None = None
    salary: float | None = None
    education: str | None = None
    school: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    remark: str | None = None
    user_id: int | None = None


class BatchIdsIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class BatchStatusIn(BatchIdsIn):
    status: str


class CreateAccountsIn(BatchIdsIn):
    default_password: str = Field(default="123456", min_length=6)
    role: str = "employee"


class LinkAccountIn(BaseModel):
    user_id: int | None = None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"日期格式应为 YYYY-MM-DD，收到：{value}")


def _next_emp_no(db: Session) -> str:
    """自动生成工号：EMP + 4 位序号。"""
    count = db.scalar(select(func.count(Employee.id))) or 0
    while True:
        count += 1
        candidate = f"EMP{count:04d}"
        if not db.scalar(select(Employee.id).where(Employee.emp_no == candidate)):
            return candidate


def _mask(emp_dict: dict, viewer: User) -> dict:
    """非管理员看不到薪资、身份证号等敏感信息。"""
    if not is_admin_like(viewer):
        for f in SENSITIVE_FIELDS:
            emp_dict[f] = None
    return emp_dict


def _visible_employee(db: Session, user: User, emp_id: int) -> Employee:
    emp = db.scalar(
        select(Employee).options(selectinload(Employee.department), selectinload(Employee.user))
        .where(Employee.id == emp_id)
    )
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "员工不存在")
    allowed = scoped_department_ids(db, user)
    if allowed is not None and emp.department_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，只能查看本部门及下级部门的员工")
    return emp


# ==================================================================== 查询
@router.get("", summary="员工列表（分页 + 多条件筛选）")
def list_employees(
    keyword: str | None = Query(None, description="按工号/姓名/手机号/职位模糊搜索"),
    department_id: int | None = None,
    include_sub_dept: bool = True,
    status_: str | None = Query(None, alias="status"),
    gender: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    sort: str = Query("id_desc", description="id_desc / hire_date_desc / name_asc"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Employee).options(
        selectinload(Employee.department), selectinload(Employee.user)
    )
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Employee.department_id.in_(allowed or [-1]))

    if department_id:
        if include_sub_dept:
            from ..models import Department as D

            all_rows = db.execute(select(D.id, D.parent_id)).all()
            children: dict[int | None, list[int]] = {}
            for did, pid in all_rows:
                children.setdefault(pid, []).append(did)
            ids, stack = [], [department_id]
            while stack:
                cur = stack.pop()
                ids.append(cur)
                stack.extend(children.get(cur, []))
            stmt = stmt.where(Employee.department_id.in_(ids))
        else:
            stmt = stmt.where(Employee.department_id == department_id)

    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Employee.name.like(kw), Employee.emp_no.like(kw),
                              Employee.phone.like(kw), Employee.position.like(kw),
                              Employee.email.like(kw)))
    if status_:
        stmt = stmt.where(Employee.status == status_)
    if gender:
        stmt = stmt.where(Employee.gender == gender)

    order = {
        "id_desc": Employee.id.desc(),
        "id_asc": Employee.id.asc(),
        "hire_date_desc": Employee.hire_date.desc().nullslast(),
        "name_asc": Employee.name.asc(),
    }.get(sort, Employee.id.desc())
    stmt = stmt.order_by(order)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()
    return {
        "items": [_mask(e.to_dict(), user) for e in rows],
        "total": total, "page": page, "size": size,
        "pages": (total + size - 1) // size if size else 0,
    }


@router.get("/options", summary="员工下拉选项（表单用）")
def employee_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Employee).options(selectinload(Employee.department)).where(Employee.status != "离职")
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Employee.department_id.in_(allowed or [-1]))
    rows = db.scalars(stmt.order_by(Employee.name)).all()
    return {
        "items": [
            {"id": e.id, "name": e.name, "emp_no": e.emp_no, "position": e.position,
             "department_id": e.department_id,
             "department_name": e.department.name if e.department else None,
             "user_id": e.user_id}
            for e in rows
        ]
    }


@router.get("/stats", summary="员工统计（看板用）")
def employee_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = scoped_department_ids(db, user)
    base = select(Employee)
    if allowed is not None:
        base = base.where(Employee.department_id.in_(allowed or [-1]))
    rows = db.scalars(base).all()

    by_status: dict[str, int] = {}
    by_dept: dict[str, int] = {}
    by_gender: dict[str, int] = {}
    for e in rows:
        by_status[e.status] = by_status.get(e.status, 0) + 1
        if e.status != "离职":
            key = e.department.name if e.department else "未分配"
            by_dept[key] = by_dept.get(key, 0) + 1
            by_gender[e.gender or "保密"] = by_gender.get(e.gender or "保密", 0) + 1

    return {
        "total": len(rows),
        "active": len([e for e in rows if e.status != "离职"]),
        "by_status": by_status,
        "by_department": by_dept,
        "by_gender": by_gender,
    }


@router.get("/{emp_id}", summary="员工详情")
def get_employee(emp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _mask(_visible_employee(db, user, emp_id).to_dict(), user)


# ==================================================================== 写操作
@router.post("", summary="新增员工")
def create_employee(payload: EmployeeIn, request: Request,
                    user: User = Depends(require_manager), db: Session = Depends(get_db)):
    assert_department_in_scope(db, user, payload.department_id)
    emp_no = (payload.emp_no or "").strip() or _next_emp_no(db)
    if db.scalar(select(Employee).where(Employee.emp_no == emp_no)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"工号 {emp_no} 已存在")
    if payload.status not in EMPLOYEE_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"状态必须是：{'、'.join(EMPLOYEE_STATUS)}")

    data = payload.model_dump()
    if not is_admin_like(user):
        # 主管建号时不允许顺手设置敏感字段
        for f in SENSITIVE_FIELDS:
            data.pop(f, None)

    emp = Employee(
        **{k: v for k, v in data.items()
           if k not in ("emp_no", "birth_date", "hire_date", "leave_date")},
        emp_no=emp_no,          # 用上面校验过的工号，避免与 payload 里的重复传参
        birth_date=_parse_date(payload.birth_date),
        hire_date=_parse_date(payload.hire_date),
        leave_date=_parse_date(payload.leave_date),
    )
    db.add(emp)
    db.commit()
    write_log(db, user=user, action="新增", module="员工管理",
              detail=f"新增员工 {emp.name}（{emp.emp_no}）", target_id=emp.id, request=request)
    return _mask(_visible_employee(db, user, emp.id).to_dict(), user)


@router.put("/{emp_id}", summary="修改员工")
def update_employee(emp_id: int, payload: EmployeeIn, request: Request,
                    user: User = Depends(require_manager), db: Session = Depends(get_db)):
    emp = _visible_employee(db, user, emp_id)
    if payload.emp_no and payload.emp_no.strip() != emp.emp_no:
        if db.scalar(select(Employee).where(Employee.emp_no == payload.emp_no.strip(),
                                            Employee.id != emp_id)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"工号 {payload.emp_no} 已存在")
        emp.emp_no = payload.emp_no.strip()
    if payload.department_id != emp.department_id:
        assert_department_in_scope(db, user, payload.department_id)

    data = payload.model_dump(exclude={"emp_no", "birth_date", "hire_date", "leave_date"})
    if not is_admin_like(user):
        for f in SENSITIVE_FIELDS:
            data.pop(f, None)
    for field, value in data.items():
        setattr(emp, field, value)
    emp.birth_date = _parse_date(payload.birth_date)
    emp.hire_date = _parse_date(payload.hire_date)
    emp.leave_date = _parse_date(payload.leave_date)
    db.commit()
    write_log(db, user=user, action="修改", module="员工管理",
              detail=f"修改员工 {emp.name}（{emp.emp_no}）", target_id=emp.id, request=request)
    return _mask(_visible_employee(db, user, emp.id).to_dict(), user)


@router.delete("/{emp_id}", summary="删除员工（主管执行则为离职处理）")
def delete_employee(emp_id: int, request: Request,
                   user: User = Depends(require_manager), db: Session = Depends(get_db)):
    emp = _visible_employee(db, user, emp_id)

    if not is_admin_like(user):
        # 主管不能物理删除，只能标记离职，保留历史考勤与报告归属
        emp.status = "离职"
        emp.leave_date = emp.leave_date or date.today()
        if emp.user_id:
            u = db.get(User, emp.user_id)
            if u:
                u.is_active = False
        db.commit()
        write_log(db, user=user, action="修改", module="员工管理",
                  detail=f"将员工 {emp.name}（{emp.emp_no}）标记为离职",
                  target_id=emp.id, request=request)
        return {"ok": True, "message": f"已将 {emp.name} 标记为离职（如需彻底删除请由管理员操作）"}

    name, emp_no = emp.name, emp.emp_no
    if emp.user_id:
        u = db.get(User, emp.user_id)
        if u:
            # 停用账号并打上标记，避免留下"孤儿账号"：
            # 账号能登录却没有对应员工档案，会导致打卡、请假等功能直接不可用，
            # 而且用户名（工号小写）被永久占用，无法给新员工复用。
            u.is_active = False
            if "（员工已删除）" not in (u.real_name or ""):
                u.real_name = f"{u.real_name}（员工已删除）"
    db.delete(emp)
    db.commit()
    write_log(db, user=user, action="删除", module="员工管理",
              detail=f"删除员工 {name}（{emp_no}）"
                     + ("，其登录账号已停用" if emp.user_id else ""),
              target_id=emp_id, request=request)
    return {"ok": True, "message": f"员工 {name} 已删除"
                                   + ("（关联账号已停用，用户名保留以便追溯）" if emp.user_id else "")}


# ==================================================================== 批量
@router.post("/batch-status", summary="批量修改员工状态")
def batch_status(payload: BatchStatusIn, request: Request,
                 user: User = Depends(require_manager), db: Session = Depends(get_db)):
    if payload.status not in EMPLOYEE_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"状态必须是：{'、'.join(EMPLOYEE_STATUS)}")
    done = 0
    for emp_id in payload.ids:
        emp = _visible_employee(db, user, emp_id)
        emp.status = payload.status
        if payload.status == "离职":
            emp.leave_date = emp.leave_date or date.today()
        done += 1
    db.commit()
    write_log(db, user=user, action="修改", module="员工管理",
              detail=f"批量将 {done} 名员工状态改为「{payload.status}」", request=request)
    return {"ok": True, "message": f"已更新 {done} 名员工的状态为「{payload.status}」"}


@router.post("/batch-delete", summary="批量删除员工")
def batch_delete(payload: BatchIdsIn, request: Request,
                 user: User = Depends(require_admin), db: Session = Depends(get_db)):
    done = 0
    for emp_id in payload.ids:
        emp = db.get(Employee, emp_id)
        if not emp:
            continue
        if emp.user_id:
            u = db.get(User, emp.user_id)
            if u:
                u.is_active = False
        db.delete(emp)
        done += 1
    db.commit()
    write_log(db, user=user, action="删除", module="员工管理",
              detail=f"批量删除 {done} 名员工", request=request)
    return {"ok": True, "message": f"已删除 {done} 名员工"}


@router.post("/create-accounts", summary="批量为员工开通登录账号")
def create_accounts(payload: CreateAccountsIn, request: Request,
                    user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in ROLE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色不合法")

    created, skipped = [], []
    for emp_id in payload.ids:
        emp = db.get(Employee, emp_id)
        if not emp:
            continue
        if emp.user_id:
            skipped.append(f"{emp.name}(已有账号)")
            continue
        username = emp.emp_no.lower()
        if db.scalar(select(User).where(User.username == username)):
            skipped.append(f"{emp.name}(用户名 {username} 被占用)")
            continue
        account = User(
            username=username,
            password_hash=hash_password(payload.default_password),
            real_name=emp.name,
            role=payload.role,
            department_id=emp.department_id,
            phone=emp.phone,
            email=emp.email,
        )
        db.add(account)
        db.flush()
        emp.user_id = account.id
        created.append(f"{emp.name}({username})")

    db.commit()
    write_log(db, user=user, action="新增", module="员工管理",
              detail=f"批量开通账号：成功 {len(created)}，跳过 {len(skipped)}", request=request)
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "default_password": payload.default_password,
        "message": f"成功开通 {len(created)} 个账号，初始密码 {payload.default_password}"
                   + (f"；跳过 {len(skipped)} 个" if skipped else ""),
    }


@router.post("/{emp_id}/link-account", summary="绑定/解绑登录账号")
def link_account(emp_id: int, payload: LinkAccountIn, request: Request,
                 user: User = Depends(require_admin), db: Session = Depends(get_db)):
    emp = db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "员工不存在")

    if payload.user_id is None:
        emp.user_id = None
        db.commit()
        write_log(db, user=user, action="修改", module="员工管理",
                  detail=f"解除 {emp.name} 的账号绑定", target_id=emp.id, request=request)
        return {"ok": True, "message": "已解除账号绑定"}

    account = db.get(User, payload.user_id)
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    other = db.scalar(select(Employee).where(Employee.user_id == payload.user_id,
                                             Employee.id != emp_id))
    if other:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"该账号已绑定员工 {other.name}，请先解绑")
    emp.user_id = account.id
    if not account.department_id:
        account.department_id = emp.department_id
    db.commit()
    write_log(db, user=user, action="修改", module="员工管理",
              detail=f"将 {emp.name} 绑定到账号 {account.username}", target_id=emp.id, request=request)
    return {"ok": True, "message": f"已绑定账号 {account.username}"}


# ==================================================================== 导入导出
@router.get("/export/excel", summary="导出员工名册为 Excel")
def export_employees(user: User = Depends(require_manager), db: Session = Depends(get_db)):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    stmt = select(Employee).options(selectinload(Employee.department))
    allowed = scoped_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Employee.department_id.in_(allowed or [-1]))
    rows = db.scalars(stmt.order_by(Employee.emp_no)).all()

    headers = ["工号", "姓名", "性别", "手机号", "邮箱", "部门", "职位", "职级", "状态",
               "入职日期", "学历", "毕业院校", "月薪", "住址", "紧急联系人", "紧急联系电话", "备注"]
    if not is_admin_like(user):
        headers = [h for h in headers if h not in ("月薪",)]

    wb = Workbook()
    ws = wb.active
    ws.title = "员工名册"
    ws.append(headers)
    head_fill = PatternFill("solid", fgColor="1F4E79")
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"

    for e in rows:
        row = {
            "工号": e.emp_no, "姓名": e.name, "性别": e.gender, "手机号": e.phone, "邮箱": e.email,
            "部门": e.department.name if e.department else "", "职位": e.position,
            "职级": e.job_level, "状态": e.status,
            "入职日期": e.hire_date.isoformat() if e.hire_date else "",
            "学历": e.education, "毕业院校": e.school, "月薪": e.salary,
            "住址": e.address, "紧急联系人": e.emergency_contact,
            "紧急联系电话": e.emergency_phone, "备注": e.remark,
        }
        ws.append([row.get(h) for h in headers])

    widths = {"工号": 12, "姓名": 10, "性别": 6, "手机号": 14, "邮箱": 24, "部门": 14,
              "职位": 14, "职级": 8, "状态": 8, "入职日期": 12, "学历": 10, "毕业院校": 20,
              "月薪": 10, "住址": 30, "紧急联系人": 12, "紧急联系电话": 14, "备注": 24}
    for idx, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = widths.get(h, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    write_log(db, user=user, action="导出", module="员工管理",
              detail=f"导出员工名册（{len(rows)} 条）")
    filename = f"员工名册_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=attachment_header(filename),
    )


@router.get("/import/template", summary="下载员工导入模板")
def import_template(user: User = Depends(require_manager)):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "员工导入"
    headers = list(IMPORT_COLUMNS.keys())
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2E7D32")
    ws.append(["EMP1001", "张三", "男", "13800000000", "zhangsan@demo.com", "技术部", "后端工程师",
               "P6", "在职", "2024-03-01", "本科", "某某大学", "", "", "本科", "北京市朝阳区",
               "李四", "13900000000", "示例数据，可删除"])
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 10
    for letter, width in zip("CDEFGHIJKLMNOPQR",
                             [6, 15, 24, 14, 16, 8, 8, 12, 10, 20, 18, 30, 12, 15, 24]):
        ws.column_dimensions[letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=attachment_header("employee_import_template.xlsx"),
    )


@router.post("/import", summary="从 Excel 批量导入员工")
def import_employees(file: UploadFile = File(...), request: Request = None,
                     user: User = Depends(require_manager), db: Session = Depends(get_db)):
    from openpyxl import load_workbook

    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请上传 .xlsx 文件（可先下载导入模板）")

    try:
        wb = load_workbook(io.BytesIO(file.file.read()), data_only=True)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件无法解析，请确认是有效的 Excel 文件")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件内容为空")
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    unknown = [h for h in header if h and h not in IMPORT_COLUMNS]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"存在无法识别的列：{'、'.join(unknown)}。请使用下载的导入模板")

    dept_map = {d.name: d.id for d in db.scalars(select(Department)).all()}
    existing_nos = {n for (n,) in db.execute(select(Employee.emp_no)).all()}
    created, errors = 0, []

    for line_no, raw in enumerate(rows[1:], start=2):
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        record = {IMPORT_COLUMNS[h]: v for h, v in zip(header, raw) if h in IMPORT_COLUMNS}
        name = str(record.get("name") or "").strip()
        if not name:
            errors.append(f"第 {line_no} 行：缺少姓名，已跳过")
            continue

        dept_name = str(record.get("department_name") or "").strip()
        dept_id = dept_map.get(dept_name)
        if dept_name and not dept_id:
            errors.append(f"第 {line_no} 行：部门「{dept_name}」不存在，已跳过")
            continue
        if dept_id is None and dept_name == "":
            dept_id = None
        if not is_admin_like(user) and dept_id is None:
            errors.append(f"第 {line_no} 行：部门主管导入时必须填写部门，已跳过")
            continue
        if not is_admin_like(user):
            allowed = scoped_department_ids(db, user) or []
            if dept_id not in allowed:
                errors.append(f"第 {line_no} 行：无权往部门「{dept_name}」导入，已跳过")
                continue

        emp_no = str(record.get("emp_no") or "").strip() or _next_emp_no(db)
        if emp_no in existing_nos:
            errors.append(f"第 {line_no} 行：工号 {emp_no} 已存在，已跳过")
            continue

        status_val = str(record.get("status") or "在职").strip() or "在职"
        if status_val not in EMPLOYEE_STATUS:
            status_val = "在职"

        data = dict(
            emp_no=emp_no,
            name=name,
            gender=str(record.get("gender") or "保密").strip() or "保密",
            phone=str(record.get("phone") or "").strip() or None,
            email=str(record.get("email") or "").strip() or None,
            department_id=dept_id,
            position=str(record.get("position") or "").strip() or None,
            job_level=str(record.get("job_level") or "").strip() or None,
            status=status_val,
            education=str(record.get("education") or "").strip() or None,
            school=str(record.get("school") or "").strip() or None,
            address=str(record.get("address") or "").strip() or None,
            emergency_contact=str(record.get("emergency_contact") or "").strip() or None,
            emergency_phone=str(record.get("emergency_phone") or "").strip() or None,
            remark=str(record.get("remark") or "").strip() or None,
            birth_date=_parse_date(record.get("birth_date")),
            hire_date=_parse_date(record.get("hire_date")) or date.today(),
            leave_date=_parse_date(record.get("leave_date")),
        )
        if is_admin_like(user):
            data["id_card"] = str(record.get("id_card") or "").strip() or None
            try:
                data["salary"] = float(record["salary"]) if record.get("salary") not in (None, "") else None
            except (TypeError, ValueError):
                data["salary"] = None

        db.add(Employee(**data))
        existing_nos.add(emp_no)
        created += 1
        if created % 50 == 0:
            db.flush()

    db.commit()
    write_log(db, user=user, action="导入", module="员工管理",
              detail=f"Excel 导入员工：成功 {created} 条，失败 {len(errors)} 条", request=request)
    return {"ok": True, "created": created, "failed": len(errors), "errors": errors[:50],
            "message": f"导入完成：成功 {created} 条，跳过 {len(errors)} 条"}
