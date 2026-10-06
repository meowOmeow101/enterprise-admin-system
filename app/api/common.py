"""接口层公共小工具：分页参数解析、日期区间解析、文件下载响应头。"""
from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from fastapi import Query
from sqlalchemy import Select
from sqlalchemy.orm import Session


def attachment_header(filename: str, inline: bool = False) -> dict[str, str]:
    """
    生成 Content-Disposition 响应头。

    HTTP 头只能放 latin-1 字符，中文文件名必须走 RFC 5987 的 filename* 形式，
    同时保留一个 ASCII 回退名给老浏览器。
    """
    ascii_fallback = filename.encode("ascii", "ignore").decode().strip() or "download"
    disposition = "inline" if inline else "attachment"
    return {
        "Content-Disposition": (
            f"{disposition}; filename=\"{ascii_fallback}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        )
    }


class PageParams:
    """统一的 page/size 依赖，带上下限保护。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        size: int = Query(20, ge=1, le=200, description="每页条数"),
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    def apply(self, stmt: Select, db: Session) -> tuple[list, int]:
        """执行查询并返回 (当页数据, 总数)。"""
        from sqlalchemy import func, select

        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.offset(self.offset).limit(self.size)).unique().all()
        return list(rows), total


def parse_date(value: str | None, field: str = "date") -> date | None:
    """解析 YYYY-MM-DD，非法则抛 400。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise ValueError(f"{field} 格式应为 YYYY-MM-DD，收到：{value}") from exc


def parse_datetime(value: str | None) -> datetime | None:
    """解析 ISO 时间串（兼容前端 datetime-local 输出）。"""
    if not value:
        return None
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt.replace('%', '')) + 8], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def auto_code(prefix: str, seq: int, width: int = 3) -> str:
    """生成编码，如 auto_code('PRJ-2025-', 7) -> PRJ-2025-007。"""
    return f"{prefix}{seq:0{width}d}"
