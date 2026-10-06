"""
全局配置。

刻意做成"读环境变量 + 合理默认值"的形式：
以后真要上线，只要改环境变量即可，不用动代码。
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- 路径
BASE_DIR = Path(__file__).resolve().parent.parent   # 项目根目录
DATA_DIR = Path(os.getenv("CADMIN_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"      # 报告等附件
AVATAR_DIR = DATA_DIR / "avatars"      # 用户头像
EXPORT_DIR = DATA_DIR / "exports"      # 临时导出的 Excel
WEB_DIR = BASE_DIR / "web"             # 前端静态文件

for _d in (DATA_DIR, UPLOAD_DIR, AVATAR_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 数据库
# 本地默认 SQLite（单文件、免安装）。想换 PostgreSQL/MySQL 只需改这个变量。
DATABASE_URL = os.getenv("CADMIN_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'cadmin.db').as_posix()}")

# ---------------------------------------------------------------- 安全
# 生产环境请务必通过环境变量覆盖，否则 JWT 可被伪造。
SECRET_KEY = os.getenv("CADMIN_SECRET_KEY", "local-dev-only-change-me-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("CADMIN_TOKEN_EXPIRE_MINUTES", "720"))  # 12 小时

# ---------------------------------------------------------------- 上传限制
ALLOWED_UPLOAD_EXT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".md", ".csv", ".zip", ".rar", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
}
MAX_UPLOAD_MB = int(os.getenv("CADMIN_MAX_UPLOAD_MB", "50"))

# ---------------------------------------------------------------- 业务字典
# 角色 -> 中文名
ROLE_LABELS = {
    "boss": "老板（董事长/总经理）",
    "admin": "系统管理员",
    "manager": "部门主管",
    "employee": "普通员工",
}

# 拥有"最高权限"的角色：能看全公司数据、能开除员工、能管账号与日志。
# 老板与系统管理员的权限完全相同，区别只在身份标签与使用场景：
#   · 老板：给公司最高管理者用的业务视角账号
#   · 系统管理员：给 IT/运维用的系统维护账号
# 想给两者做区分（比如老板只能看不能改），改这里的集合即可，
# 全项目所有权限判断都读它，不需要再逐处修改。
ADMIN_LIKE_ROLES = ("boss", "admin")

# 拥有"管理级"权限的角色（可管本部门及下级部门数据、可审批）
MANAGER_LIKE_ROLES = ("boss", "admin", "manager")

# 角色权限高低，用于审批链判断
ROLE_RANK = {"employee": 1, "manager": 2, "admin": 3, "boss": 4}

PROJECT_STATUS = ["筹备中", "进行中", "已暂停", "已完成", "已归档"]
PROJECT_PRIORITY = ["低", "中", "高", "紧急"]
EMPLOYEE_STATUS = ["在职", "试用期", "休假", "离职"]
LEAVE_TYPES = ["事假", "病假", "年假", "调休", "婚假", "产假", "陪产假", "其他"]
REPORT_CATEGORIES = ["周报", "月报", "季报", "年报", "项目结项报告", "需求文档", "测试报告", "其他"]

# 自动登出（前端使用）
APP_NAME = "企业后台管理系统"
