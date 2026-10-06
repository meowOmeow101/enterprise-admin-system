"""公告通知接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user, is_admin_like, is_manager_like, require_manager, write_log
from ..models import Announcement, AnnouncementRead, User

router = APIRouter(prefix="/announcements", tags=["公告通知"])

CATEGORIES = ["通知", "制度", "活动", "人事", "技术分享"]


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    category: str = "通知"
    is_pinned: bool = False
    is_published: bool = True


class AnnouncementPatch(BaseModel):
    is_pinned: bool | None = None
    is_published: bool | None = None


def _with_reads(db: Session):
    return select(Announcement).options(
        selectinload(Announcement.reads), selectinload(Announcement.publisher)
    )


@router.get("", summary="公告列表")
def list_announcements(
    keyword: str | None = None,
    category: str | None = None,
    only_unread: bool = False,
    include_draft: bool = Query(False, description="管理员可查看未发布草稿"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = _with_reads(db)
    if include_draft and is_manager_like(user):
        pass
    else:
        stmt = stmt.where(Announcement.is_published.is_(True))
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Announcement.title.like(kw), Announcement.content.like(kw)))
    if category:
        stmt = stmt.where(Announcement.category == category)

    stmt = stmt.order_by(Announcement.is_pinned.desc(), Announcement.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).unique().all()

    items = []
    for a in rows:
        d = a.to_dict()
        d["is_read"] = any(rd.user_id == user.id for rd in a.reads)
        if only_unread and d["is_read"]:
            continue
        items.append(d)

    unread = db.scalar(
        select(func.count(Announcement.id)).where(
            Announcement.is_published.is_(True),
            ~Announcement.id.in_(
                select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
            ),
        )
    ) or 0
    return {"items": items, "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0, "unread": unread,
            "categories": CATEGORIES}


@router.get("/{ann_id}", summary="公告详情（自动标记已读）")
def get_announcement(ann_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ann = db.scalar(_with_reads(db).where(Announcement.id == ann_id))
    if not ann:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    if not ann.is_published and not is_manager_like(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该公告尚未发布")

    already = db.scalar(select(AnnouncementRead).where(AnnouncementRead.announcement_id == ann_id,
                                                       AnnouncementRead.user_id == user.id))
    if not already:
        db.add(AnnouncementRead(announcement_id=ann_id, user_id=user.id))
        db.commit()
        db.refresh(ann)

    data = ann.to_dict()
    data["is_read"] = True
    data["readers"] = [rd.user.real_name if rd.user else str(rd.user_id) for rd in ann.reads]
    return data


@router.post("", summary="发布公告")
def create_announcement(payload: AnnouncementIn, request: Request,
                        user: User = Depends(require_manager), db: Session = Depends(get_db)):
    if payload.category not in CATEGORIES:
        payload.category = "通知"
    ann = Announcement(
        title=payload.title.strip(), content=payload.content.strip(),
        category=payload.category, is_pinned=payload.is_pinned,
        is_published=payload.is_published, publisher_id=user.id,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    write_log(db, user=user, action="新增", module="公告通知",
              detail=f"发布公告《{ann.title}》" + ("" if ann.is_published else "（草稿）"),
              target_id=ann.id, request=request)
    return ann.to_dict()


@router.put("/{ann_id}", summary="修改公告")
def update_announcement(ann_id: int, payload: AnnouncementIn, request: Request,
                        user: User = Depends(require_manager), db: Session = Depends(get_db)):
    ann = db.get(Announcement, ann_id)
    if not ann:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    if not is_admin_like(user) and ann.publisher_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能修改自己发布的公告")

    ann.title = payload.title.strip()
    ann.content = payload.content.strip()
    ann.category = payload.category if payload.category in CATEGORIES else "通知"
    ann.is_pinned = payload.is_pinned
    ann.is_published = payload.is_published
    db.commit()
    write_log(db, user=user, action="修改", module="公告通知",
              detail=f"修改公告《{ann.title}》", target_id=ann.id, request=request)
    return ann.to_dict()


@router.patch("/{ann_id}", summary="置顶 / 发布状态切换")
def patch_announcement(ann_id: int, payload: AnnouncementPatch, request: Request,
                       user: User = Depends(require_manager), db: Session = Depends(get_db)):
    ann = db.get(Announcement, ann_id)
    if not ann:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ann, field, value)
    db.commit()
    write_log(db, user=user, action="修改", module="公告通知",
              detail=f"更新公告《{ann.title}》状态：{data}", target_id=ann.id, request=request)
    return ann.to_dict()


@router.delete("/{ann_id}", summary="删除公告")
def delete_announcement(ann_id: int, request: Request,
                        user: User = Depends(require_manager), db: Session = Depends(get_db)):
    ann = db.get(Announcement, ann_id)
    if not ann:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    if not is_admin_like(user) and ann.publisher_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能删除自己发布的公告")
    title = ann.title
    db.delete(ann)
    db.commit()
    write_log(db, user=user, action="删除", module="公告通知",
              detail=f"删除公告《{title}》", target_id=ann_id, request=request)
    return {"ok": True, "message": f"公告《{title}》已删除"}
