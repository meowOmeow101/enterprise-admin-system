"""
ORM 数据模型。

命名约定：金额用分存整数（本系统暂未涉及），时间统一用本地时间 datetime.now。
每张表都带 created_at，方便看板按时间做统计。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import ROLE_LABELS
from .db import Base
from .serializers import Serializable


def _now() -> datetime:
    return datetime.now()


def _human_size(size: int | None) -> str:
    """把字节数转成人类可读的大小，如 1.2 MB。"""
    n = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ==================================================================== 组织
class Department(Base, Serializable):
    """部门（自关联，支持多级组织架构）。"""

    __tablename__ = "departments"

    __fields__ = ("id", "name", "code", "parent_id", "parent_name", "manager_id",
                  "manager_name", "description", "sort_order", "created_at", "member_count")
    __computed__ = {
        "parent_name": lambda s: s.parent.name if s.parent else None,
        "manager_name": lambda s: s.manager.name if s.manager else None,
        # 由接口层预取后塞入 Employee 列表；未预取时返回 0，不会报错
        "member_count": lambda s: len([e for e in (getattr(s, "employees", None) or [])
                                       if e.status != "离职"]),
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)     # 部门编码，如 TECH
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    # 部门主管（员工）。与 Employee.department_id 互为外键，用 use_alter 打破建表顺序依赖
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL", use_alter=True, name="fk_dept_manager")
    )
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    parent: Mapped["Department | None"] = relationship(
        remote_side="Department.id", backref="children", foreign_keys=[parent_id]
    )
    manager: Mapped["Employee | None"] = relationship(
        foreign_keys=[manager_id], post_update=True
    )
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="department", foreign_keys="Employee.department_id"
    )


# ==================================================================== 账号
class User(Base, Serializable):
    """登录账号。role: admin 系统管理员 / manager 部门主管 / employee 普通员工。"""

    __tablename__ = "users"

    __fields__ = ("id", "username", "real_name", "role", "role_label", "department_id",
                  "department_name", "phone", "email", "avatar", "is_active",
                  "last_login_at", "created_at", "employee_id")
    __computed__ = {
        "role_label": lambda s: ROLE_LABELS.get(s.role, s.role),
        "department_name": lambda s: s.department.name if s.department else None,
        "employee_id": lambda s: s.employee.id if getattr(s, "employee", None) else None,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default="employee", index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    avatar: Mapped[str | None] = mapped_column(String(255))        # 相对 /uploads/avatars/xxx 的路径
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    department: Mapped["Department | None"] = relationship()
    employee: Mapped["Employee | None"] = relationship(
        back_populates="user", foreign_keys="Employee.user_id", uselist=False
    )


# ==================================================================== 员工
class Employee(Base, Serializable):
    """员工档案。与登录账号分开：可以先建档、后开号。"""

    __tablename__ = "employees"

    __fields__ = ("id", "emp_no", "name", "gender", "birth_date", "age", "phone", "email",
                  "id_card", "department_id", "department_name", "position", "job_level",
                  "status", "hire_date", "leave_date", "salary", "education", "school",
                  "address", "emergency_contact", "emergency_phone", "remark", "user_id",
                  "username", "created_at", "updated_at")
    __computed__ = {
        "department_name": lambda s: s.department.name if s.department else None,
        "username": lambda s: s.user.username if s.user else None,
        "age": lambda s: (date.today() - s.birth_date).days // 365 if s.birth_date else None,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)   # 工号
    name: Mapped[str] = mapped_column(String(64), index=True)
    gender: Mapped[str | None] = mapped_column(String(8))                      # 男 / 女 / 保密
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    id_card: Mapped[str | None] = mapped_column(String(32))                    # 身份证号（敏感，仅管理员可见）
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    position: Mapped[str | None] = mapped_column(String(64))                   # 职位
    job_level: Mapped[str | None] = mapped_column(String(32))                  # 职级，如 P6
    status: Mapped[str] = mapped_column(String(16), default="在职", index=True)
    hire_date: Mapped[date | None] = mapped_column(Date)
    leave_date: Mapped[date | None] = mapped_column(Date)
    salary: Mapped[float | None] = mapped_column(Float)                        # 月薪（仅管理员可见）
    education: Mapped[str | None] = mapped_column(String(32))
    school: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255))
    emergency_contact: Mapped[str | None] = mapped_column(String(64))
    emergency_phone: Mapped[str | None] = mapped_column(String(32))
    remark: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # 显式指定外键列：因为 departments 与 employees 之间有两条外键路径（部门主管 / 所属部门）
    department: Mapped["Department | None"] = relationship(
        back_populates="employees", foreign_keys=[department_id]
    )
    user: Mapped["User | None"] = relationship(back_populates="employee", foreign_keys=[user_id])
    attendances: Mapped[list["Attendance"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    leaves: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


# ==================================================================== 项目
class Project(Base, Serializable):
    """项目主表。"""

    __tablename__ = "projects"

    __fields__ = ("id", "code", "name", "description", "customer", "status", "priority",
                  "progress", "department_id", "department_name", "owner_id", "owner_name",
                  "start_date", "end_date", "budget", "member_count", "report_count",
                  "days_left", "created_at", "updated_at")
    __computed__ = {
        "department_name": lambda s: s.department.name if s.department else None,
        "owner_name": lambda s: s.owner.name if s.owner else None,
        "member_count": lambda s: len(s.members or []),
        "report_count": lambda s: len(s.reports or []),
        # 剩余天数：负数代表已逾期，前端据此标红
        "days_left": lambda s: (s.end_date - date.today()).days
        if s.end_date and s.status not in ("已完成", "已归档") else None,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)     # 项目编号，如 PRJ-2025-001
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    customer: Mapped[str | None] = mapped_column(String(128))                  # 客户/甲方
    status: Mapped[str] = mapped_column(String(16), default="进行中", index=True)
    priority: Mapped[str] = mapped_column(String(8), default="中")
    progress: Mapped[int] = mapped_column(Integer, default=0)                  # 0-100
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))  # 项目负责人
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[float | None] = mapped_column(Float)                        # 预算（元）
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    department: Mapped["Department | None"] = relationship()
    owner: Mapped["Employee | None"] = relationship()
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    """项目成员（一个员工可参与多个项目）。"""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "employee_id", name="uq_project_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    role: Mapped[str | None] = mapped_column(String(32))       # 项目内角色：开发/测试/PM...
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship()


# ==================================================================== 报告
class Report(Base, Serializable):
    """项目报告（附件）。同一项目 + 同名文件构成一个版本序列。"""

    __tablename__ = "reports"

    __fields__ = ("id", "project_id", "project_name", "title", "category", "version",
                  "report_date", "tags", "summary", "file_name", "file_size", "file_size_text",
                  "file_ext", "uploader_id", "uploader_name", "download_count",
                  "is_previewable", "created_at")
    __computed__ = {
        "project_name": lambda s: s.project.name if s.project else None,
        "uploader_name": lambda s: s.uploader.real_name if s.uploader else None,
        "file_size_text": lambda s: _human_size(s.file_size),
        "is_previewable": lambda s: (s.file_ext or "").lower() in {".pdf", ".png", ".jpg", ".jpeg",
                                                                  ".gif", ".webp", ".txt", ".md"},
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(32), default="其他", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    report_date: Mapped[date | None] = mapped_column(Date, index=True)
    tags: Mapped[str | None] = mapped_column(String(255))       # 逗号分隔标签
    summary: Mapped[str | None] = mapped_column(Text)           # 报告摘要/说明
    file_name: Mapped[str] = mapped_column(String(255))         # 原始文件名（下载时用）
    stored_path: Mapped[str] = mapped_column(String(500))       # 磁盘相对路径
    file_size: Mapped[int] = mapped_column(Integer, default=0)  # 字节
    file_ext: Mapped[str | None] = mapped_column(String(16))
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project | None"] = relationship(back_populates="reports")
    uploader: Mapped["User | None"] = relationship()


# ==================================================================== 考勤
class Attendance(Base, Serializable):
    """考勤打卡记录：每人每天一条，含上下班时间。"""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_day"),)

    __fields__ = ("id", "employee_id", "employee_name", "emp_no", "department_name", "work_date",
                  "check_in", "check_out", "status", "work_hours", "remark", "created_at")
    __computed__ = {
        "employee_name": lambda s: s.employee.name if s.employee else None,
        "emp_no": lambda s: s.employee.emp_no if s.employee else None,
        "department_name": lambda s: (s.employee.department.name
                                      if s.employee and s.employee.department else None),
        # 只给前端时分秒，避免它自己解析时区
        "check_in": lambda s: s.check_in.strftime("%H:%M:%S") if s.check_in else None,
        "check_out": lambda s: s.check_out.strftime("%H:%M:%S") if s.check_out else None,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    check_in: Mapped[datetime | None] = mapped_column(DateTime)
    check_out: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="正常")   # 正常/迟到/早退/缺卡/旷工/请假/出差
    work_hours: Mapped[float] = mapped_column(Float, default=0.0)
    remark: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    employee: Mapped["Employee"] = relationship(back_populates="attendances")


class LeaveRequest(Base, Serializable):
    """请假/调休申请。状态机：待审批 -> 已通过 / 已驳回；申请人可撤销。"""

    __tablename__ = "leave_requests"

    __fields__ = ("id", "employee_id", "employee_name", "emp_no", "department_name",
                  "leave_type", "start_date", "end_date", "days", "reason", "status",
                  "approver_id", "approver_name", "approved_at", "approve_comment", "created_at")
    __computed__ = {
        "employee_name": lambda s: s.employee.name if s.employee else None,
        "emp_no": lambda s: s.employee.emp_no if s.employee else None,
        "department_name": lambda s: (s.employee.department.name
                                      if s.employee and s.employee.department else None),
        "approver_name": lambda s: s.approver.real_name if s.approver else None,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    leave_type: Mapped[str] = mapped_column(String(16), default="事假")
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    days: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="待审批", index=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approve_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    employee: Mapped["Employee"] = relationship(back_populates="leaves")
    approver: Mapped["User | None"] = relationship()


# ==================================================================== 公告
class Announcement(Base, Serializable):
    """公司公告。"""

    __tablename__ = "announcements"

    __fields__ = ("id", "title", "content", "category", "is_pinned", "is_published",
                  "publisher_id", "publisher_name", "read_count", "is_read", "created_at", "updated_at")
    __computed__ = {
        "publisher_name": lambda s: s.publisher.real_name if s.publisher else None,
        "read_count": lambda s: len(s.reads or []),
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="通知")   # 通知/制度/活动/人事
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)     # 置顶
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)   # 是否发布（草稿）
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    publisher: Mapped["User | None"] = relationship()
    reads: Mapped[list["AnnouncementRead"]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )


class AnnouncementRead(Base):
    """公告已读回执。"""

    __tablename__ = "announcement_reads"
    __table_args__ = (UniqueConstraint("announcement_id", "user_id", name="uq_announcement_read"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    announcement: Mapped["Announcement"] = relationship(back_populates="reads")
    user: Mapped["User"] = relationship()


# ==================================================================== 审计
class OperationLog(Base, Serializable):
    """操作日志（审计）。所有写操作都记一笔，谁改了什么一目了然。"""

    __tablename__ = "operation_logs"

    __fields__ = ("id", "user_id", "username", "action", "module", "detail",
                  "target_id", "ip", "created_at")

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str | None] = mapped_column(String(64))    # 冗余一份，避免用户被删后查不到
    action: Mapped[str] = mapped_column(String(32), index=True)  # 新增/修改/删除/登录/上传/下载/审批...
    module: Mapped[str] = mapped_column(String(32), index=True)  # 员工管理/项目管理...
    detail: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
