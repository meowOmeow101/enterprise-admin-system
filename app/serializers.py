"""轻量序列化工具：把 ORM 对象转成前端能直接吃的 dict。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable


def _val(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


class Serializable:
    """
    混入类：子类声明 `__fields__` 与可选的 `__computed__`。

    computed 用函数声明，参数是自身，便于拼部门名、负责人姓名这类关联字段。
    好处：一处声明，列表/详情/导出全都一致，不会出现"列表有、详情没有"的坑。
    """

    __fields__: tuple[str, ...] = ()
    __computed__: dict[str, Any] = {}

    def to_dict(self, include: Iterable[str] | None = None, exclude: Iterable[str] = ()) -> dict:
        fields = tuple(include) if include is not None else self.__fields__
        skip = set(exclude)
        data: dict[str, Any] = {}
        for f in fields:
            if f in skip:
                continue
            if f in self.__computed__:
                data[f] = self.__computed__[f](self)
            else:
                data[f] = _val(getattr(self, f, None))
        return data


def to_dicts(items: Iterable[Any]) -> list[dict]:
    return [i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in items]


def page_payload(items: list[dict], total: int, page: int, size: int) -> dict:
    """统一的分页返回结构。"""
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size else 0,
    }
