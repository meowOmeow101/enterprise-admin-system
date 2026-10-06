"""项目报告接口：上传、版本管理、下载、预览、统计。"""
from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile,
                     status)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import ALLOWED_UPLOAD_EXT, MAX_UPLOAD_MB, REPORT_CATEGORIES, UPLOAD_DIR
from ..db import get_db
from ..deps import current_employee, get_current_user, is_admin_like, scoped_department_ids, write_log
from ..models import Employee, Project, ProjectMember, Report, User
from .common import attachment_header

router = APIRouter(prefix="/reports", tags=["报告管理"])

PREVIEW_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
}


class ReportMetaIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    category: str | None = None
    report_date: str | None = None
    tags: str | None = None
    summary: str | None = None
    project_id: int | None = None


# ==================================================================== 内部工具
def _safe_name(raw: str) -> str:
    """清掉路径分隔符和非法字符，只保留文件名本身。"""
    name = Path(raw or "file").name
    for ch in '<>:"/\\|?*\x00':
        name = name.replace(ch, "_")
    return name.strip()[:180] or "file"


def _content_disposition(filename: str, inline: bool = False) -> str:
    """兼容旧调用：返回单个头部值。"""
    return attachment_header(filename, inline)["Content-Disposition"]


def _resolve(stored_path: str) -> Path:
    """把数据库里的相对路径解析成绝对路径，并确保没有越出上传目录。"""
    root = UPLOAD_DIR.resolve()
    target = (root / stored_path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在或已被清理")
    return target


def _can_access_report(db: Session, user: User, report: Report) -> bool:
    """报告可见性：管理员全可见；其余人看本部门项目 / 本人参与项目 / 自己上传的。"""
    if is_admin_like(user):
        return True
    if report.uploader_id == user.id:
        return True
    project = report.project
    if project is None:
        return True   # 未挂项目的公共报告，登录即可见
    allowed = scoped_department_ids(db, user)
    if allowed is not None and project.department_id in allowed:
        return True
    emp = current_employee(db, user)
    if emp:
        is_member = db.scalar(
            select(ProjectMember.id).where(ProjectMember.project_id == project.id,
                                           ProjectMember.employee_id == emp.id)
        )
        if is_member:
            return True
    return False


def _get_report(db: Session, user: User, report_id: int) -> Report:
    report = db.scalar(
        select(Report).options(selectinload(Report.project), selectinload(Report.uploader))
        .where(Report.id == report_id)
    )
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报告不存在")
    if not _can_access_report(db, user, report):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，无法访问该报告")
    return report


def _next_version(db: Session, project_id: int | None, title: str, category: str) -> int:
    """同项目 + 同标题 + 同分类视为一个版本序列，版本号递增。"""
    max_v = db.scalar(
        select(func.max(Report.version)).where(
            Report.project_id == project_id, Report.title == title, Report.category == category
        )
    )
    return (max_v or 0) + 1


# ==================================================================== 查询
@router.get("", summary="报告列表（分页 + 筛选）")
def list_reports(
    keyword: str | None = Query(None, description="标题/文件名/标签 模糊搜索"),
    project_id: int | None = None,
    category: str | None = None,
    uploader_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Report).options(selectinload(Report.project), selectinload(Report.uploader))

    # 数据范围：先算出可见的项目 id 集合，再拼条件
    if not is_admin_like(user):
        allowed = scoped_department_ids(db, user) or []
        emp = current_employee(db, user)
        member_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == (emp.id if emp else -1))
        ).all()]
        project_ids = {pid for (pid,) in db.execute(
            select(Project.id).where(Project.department_id.in_(allowed or [-1]))
        ).all()} | set(member_ids)
        cond = Report.project_id.in_(project_ids or [-1])
        cond = or_(cond, Report.project_id.is_(None), Report.uploader_id == user.id)
        stmt = stmt.where(cond)

    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Report.title.like(kw), Report.file_name.like(kw),
                              Report.tags.like(kw), Report.summary.like(kw)))
    if project_id:
        stmt = stmt.where(Report.project_id == project_id)
    if category:
        stmt = stmt.where(Report.category == category)
    if uploader_id:
        stmt = stmt.where(Report.uploader_id == uploader_id)
    if date_from:
        stmt = stmt.where(Report.report_date >= date.fromisoformat(date_from[:10]))
    if date_to:
        stmt = stmt.where(Report.report_date <= date.fromisoformat(date_to[:10]))

    stmt = stmt.order_by(Report.report_date.desc().nullslast(), Report.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()

    # 标注每份报告是否是该标题下的最新版本，前端可以据此显示"历史版本"入口
    items = []
    for r in rows:
        d = r.to_dict()
        latest = db.scalar(
            select(func.max(Report.version)).where(
                Report.project_id == r.project_id, Report.title == r.title,
                Report.category == r.category,
            )
        )
        d["is_latest"] = (latest or 1) == r.version
        items.append(d)
    return {"items": items, "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


@router.get("/categories", summary="报告分类字典")
def report_categories():
    return {"items": REPORT_CATEGORIES}


@router.get("/stats", summary="报告统计（看板用）")
def report_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Report).options(selectinload(Report.project))
    if not is_admin_like(user):
        allowed = scoped_department_ids(db, user) or []
        emp = current_employee(db, user)
        member_ids = [pid for (pid,) in db.execute(
            select(ProjectMember.project_id).where(ProjectMember.employee_id == (emp.id if emp else -1))
        ).all()]
        project_ids = {pid for (pid,) in db.execute(
            select(Project.id).where(Project.department_id.in_(allowed or [-1]))
        ).all()} | set(member_ids)
        stmt = stmt.where(or_(Report.project_id.in_(project_ids or [-1]),
                              Report.project_id.is_(None), Report.uploader_id == user.id))

    rows = db.scalars(stmt).unique().all()
    by_category: dict[str, int] = {}
    by_month: dict[str, int] = {}
    for r in rows:
        by_category[r.category] = by_category.get(r.category, 0) + 1
        key = (r.report_date or r.created_at.date()).strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + 1

    return {
        "total": len(rows),
        "total_size": sum(r.file_size or 0 for r in rows),
        "total_downloads": sum(r.download_count or 0 for r in rows),
        "by_category": by_category,
        # 只保留最近 12 个月的走势，避免图表挤成一团
        "by_month": dict(sorted(by_month.items())[-12:]),
    }


@router.get("/{report_id}", summary="报告详情")
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    data = report.to_dict()
    siblings = db.scalars(
        select(Report).where(Report.project_id == report.project_id,
                             Report.title == report.title,
                             Report.category == report.category)
        .order_by(Report.version.desc())
    ).all()
    data["versions"] = [s.to_dict() for s in siblings]
    return data


@router.get("/{report_id}/versions", summary="同一报告的历史版本")
def report_versions(report_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    rows = db.scalars(
        select(Report).options(selectinload(Report.uploader))
        .where(Report.project_id == report.project_id, Report.title == report.title,
               Report.category == report.category)
        .order_by(Report.version.desc())
    ).all()
    return {"items": [r.to_dict() for r in rows], "total": len(rows)}


# ==================================================================== 上传
@router.post("/upload", summary="上传报告（自动递增版本号）")
def upload_report(
    request: Request,
    file: UploadFile = File(..., description="报告文件"),
    title: str | None = Form(None),
    category: str = Form("其他"),
    project_id: int | None = Form(None),
    report_date: str | None = Form(None),
    tags: str | None = Form(None),
    summary: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = _safe_name(file.filename or "")
    if not original_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要上传的文件")
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"不支持的文件类型 {ext or '(无扩展名)'}。"
                            f"允许：{'、'.join(sorted(ALLOWED_UPLOAD_EXT))}")

    # 先落盘到临时位置，拿到真实大小后再校验，避免大文件把内存撑爆
    today_dir = UPLOAD_DIR / datetime.now().strftime("%Y-%m")
    today_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    target = today_dir / stored_name

    size = 0
    try:
        with target.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"文件超过 {MAX_UPLOAD_MB} MB 限制")
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "文件保存失败，请重试")

    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件内容为空")

    # 项目校验 + 上传权限：必须是本部门项目或本人参与的项目
    project = None
    if project_id:
        project = db.scalar(select(Project).options(selectinload(Project.members))
                            .where(Project.id == project_id))
        if not project:
            target.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "所选项目不存在")
        if not is_admin_like(user):
            allowed = scoped_department_ids(db, user) or []
            emp = current_employee(db, user)
            is_member = emp is not None and any(m.employee_id == emp.id for m in project.members)
            if project.department_id not in allowed and not is_member:
                target.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    "权限不足，只能往本部门或本人参与的项目上传报告")

    final_title = (title or "").strip() or Path(original_name).stem
    if category not in REPORT_CATEGORIES:
        category = "其他"
    report_day = None
    if report_date:
        try:
            report_day = date.fromisoformat(report_date.strip()[:10])
        except ValueError:
            report_day = None

    version = _next_version(db, project_id, final_title, category)
    report = Report(
        project_id=project_id,
        title=final_title,
        category=category,
        version=version,
        report_date=report_day or date.today(),
        tags=(tags or "").strip() or None,
        summary=(summary or "").strip() or None,
        file_name=original_name,
        stored_path=str(target.relative_to(UPLOAD_DIR)).replace("\\", "/"),
        file_size=size,
        file_ext=ext,
        uploader_id=user.id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    write_log(db, user=user, action="上传", module="报告管理",
              detail=f"上传报告《{final_title}》v{version}（{original_name}，"
                     f"{size / 1024:.0f} KB）到项目「{project.name if project else '未指定'}」",
              target_id=report.id, request=request)
    return {"ok": True, "report": report.to_dict(),
            "message": f"上传成功：《{final_title}》v{version}"}


# ==================================================================== 修改 / 删除
@router.put("/{report_id}", summary="修改报告信息")
def update_report(report_id: int, payload: ReportMetaIn, request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    if user.role == "employee" and report.uploader_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能修改自己上传的报告")

    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"]:
        report.title = data["title"].strip()
    if "category" in data and data["category"] in REPORT_CATEGORIES:
        report.category = data["category"]
    if "tags" in data:
        report.tags = (data["tags"] or "").strip() or None
    if "summary" in data:
        report.summary = (data["summary"] or "").strip() or None
    if "report_date" in data and data["report_date"]:
        try:
            report.report_date = date.fromisoformat(data["report_date"].strip()[:10])
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "报告日期格式应为 YYYY-MM-DD")
    if "project_id" in data:
        if data["project_id"]:
            if not db.get(Project, data["project_id"]):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "所选项目不存在")
        report.project_id = data["project_id"]

    db.commit()
    write_log(db, user=user, action="修改", module="报告管理",
              detail=f"修改报告《{report.title}》v{report.version} 的信息",
              target_id=report.id, request=request)
    return report.to_dict()


@router.delete("/{report_id}", summary="删除报告（含磁盘文件）")
def delete_report(report_id: int, request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    if user.role == "employee" and report.uploader_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能删除自己上传的报告")

    title, version = report.title, report.version
    try:
        (UPLOAD_DIR / report.stored_path).unlink(missing_ok=True)
    except OSError:
        pass  # 文件已被手工删除不影响记录清理
    db.delete(report)
    db.commit()
    write_log(db, user=user, action="删除", module="报告管理",
              detail=f"删除报告《{title}》v{version}", target_id=report_id, request=request)
    return {"ok": True, "message": f"报告《{title}》v{version} 已删除"}


# ==================================================================== 下载 / 预览
@router.get("/{report_id}/download", summary="下载报告")
def download_report(report_id: int, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    path = _resolve(report.stored_path)

    report.download_count = (report.download_count or 0) + 1
    db.commit()
    write_log(db, user=user, action="下载", module="报告管理",
              detail=f"下载报告《{report.title}》v{report.version}（{report.file_name}）",
              target_id=report.id, request=request)

    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(report.file_name)},
    )


@router.get("/{report_id}/preview", summary="在线预览（PDF/图片/文本）")
def preview_report(report_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    report = _get_report(db, user, report_id)
    ext = (report.file_ext or "").lower()
    if ext not in PREVIEW_MIME:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "该文件类型不支持在线预览，请下载后查看")
    path = _resolve(report.stored_path)
    return FileResponse(
        path,
        media_type=PREVIEW_MIME[ext],
        headers={"Content-Disposition": _content_disposition(report.file_name, inline=True)},
    )


# ==================================================================== 批量打包下载（可选）
@router.post("/batch-download", summary="批量下载（返回文件清单，由前端逐个下载）")
def batch_download_info(payload: dict, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先选择要下载的报告")
    items = []
    for rid in ids:
        report = db.scalar(select(Report).where(Report.id == rid))
        if report and _can_access_report(db, user, report):
            items.append({"id": report.id, "title": report.title, "version": report.version,
                          "file_name": report.file_name,
                          "url": f"/api/reports/{report.id}/download"})
    write_log(db, user=user, action="下载", module="报告管理",
              detail=f"批量下载 {len(items)} 份报告")
    return {"items": items, "total": len(items)}
