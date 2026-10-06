"""
一键初始化：建表 + 灌入一批中文示例数据，方便打开就能看到真实效果。

    .\\scripts\\seed.ps1                 # 等价于 python -m scripts.seed
    python -m scripts.seed --reset      # 清空数据库重新灌一遍

初始账号（密码统一 123456）：
    boss     / 123456    老板（董事长）—— 全部权限，可直接开除员工
    admin    / 123456    系统管理员     —— 全部权限（用于系统维护）
    liqiang  / 123456    技术部主管
    wangfang / 123456    市场部主管
    yanglei  / 123456    普通员工
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# 允许用 `python scripts/seed.py` 直接执行（此时项目根目录不在 sys.path 里）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.config import UPLOAD_DIR
from app.db import Base, SessionLocal, engine, init_db
from app.models import (Announcement, AnnouncementRead, Attendance, Department, Employee,
                        LeaveRequest, OperationLog, Project, ProjectMember, Report, User)
from app.security import hash_password

DEFAULT_PASSWORD = "123456"
random.seed(20240501)   # 固定随机种子，保证每次生成的数据一致

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
GIVEN = ["伟", "芳", "娜", "敏", "静", "强", "磊", "洋", "艳", "勇", "军", "杰", "娟", "涛",
         "明", "超", "秀英", "霞", "平", "刚", "桂英", "文", "浩", "宇", "欣", "悦", "晨", "博",
         "雪", "琳", "鹏", "斌", "倩", "宁", "峰", "梅"]

POSITIONS = ["后端工程师", "前端工程师", "测试工程师", "产品经理", "UI 设计师", "运维工程师",
             "数据分析师", "销售经理", "市场专员", "人事专员", "财务专员", "项目经理",
             "算法工程师", "技术支持"]

EDUCATIONS = ["大专", "本科", "本科", "本科", "硕士", "硕士", "博士"]
SCHOOLS = ["清华大学", "北京大学", "浙江大学", "南京大学", "武汉大学", "华中科技大学",
           "西安电子科技大学", "北京邮电大学", "四川大学", "山东大学", "郑州大学", "深圳大学"]


# ==================================================================== 部门
DEPARTMENTS = [
    # (名称, 编码, 上级, 说明)
    ("总经办", "GM", None, "公司决策与管理层"),
    ("技术部", "TECH", None, "产品研发与技术支撑"),
    ("市场部", "MKT", None, "市场推广与品牌"),
    ("销售部", "SALES", None, "客户开发与签约"),
    ("人事行政部", "HR", None, "人力资源与行政后勤"),
    ("财务部", "FIN", None, "财务核算与资金管理"),
    ("后端组", "TECH-BE", "技术部", "服务端开发"),
    ("前端组", "TECH-FE", "技术部", "Web 与移动端开发"),
    ("测试组", "TECH-QA", "技术部", "质量保障"),
]


def seed_departments(db) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for name, code, parent, desc in DEPARTMENTS:
        dept = Department(name=name, code=code, description=desc,
                          parent_id=mapping.get(parent) if parent else None,
                          sort_order=len(mapping))
        db.add(dept)
        db.flush()
        mapping[name] = dept.id
    return mapping


# ==================================================================== 员工
def seed_employees(db, depts: dict[str, int]) -> list[Employee]:
    """生成 26 名员工，并给其中一部分开通登录账号。"""
    plan = [
        # (姓名, 部门, 职位, 职级, 角色, 月薪, 入职偏移天数, 状态)
        ("王建国", "总经办", "董事长", "M5", "boss", 120000, 2600, "在职"),
        ("赵敏", "总经办", "总经理", "M4", "admin", 60000, 2400, "在职"),
        ("李强", "技术部", "技术总监", "M3", "manager", 45000, 2100, "在职"),
        ("王芳", "市场部", "市场总监", "M3", "manager", 38000, 1800, "在职"),
        ("张伟", "销售部", "销售总监", "M3", "manager", 36000, 1750, "在职"),
        ("刘洋", "人事行政部", "人事经理", "M2", "manager", 25000, 1500, "在职"),
        ("陈静", "财务部", "财务经理", "M2", "manager", 26000, 1600, "在职"),
        ("杨磊", "后端组", "后端工程师", "P7", "employee", 32000, 1200, "在职"),
        ("周涛", "后端组", "后端工程师", "P6", "employee", 26000, 900, "在职"),
        ("吴敏", "后端组", "算法工程师", "P7", "employee", 35000, 800, "在职"),
        ("郑凯", "后端组", "后端工程师", "P5", "employee", 20000, 400, "在职"),
        ("孙丽", "前端组", "前端工程师", "P7", "employee", 31000, 1100, "在职"),
        ("马超", "前端组", "前端工程师", "P6", "employee", 25000, 700, "在职"),
        ("朱婷", "前端组", "UI 设计师", "P5", "employee", 18000, 350, "在职"),
        ("胡军", "测试组", "测试工程师", "P6", "employee", 22000, 950, "在职"),
        ("林霞", "测试组", "测试工程师", "P5", "employee", 17000, 300, "试用期"),
        ("何文", "技术部", "产品经理", "P7", "employee", 30000, 1300, "在职"),
        ("高鹏", "技术部", "项目经理", "P7", "employee", 29000, 1000, "在职"),
        ("罗琳", "技术部", "运维工程师", "P6", "employee", 24000, 850, "在职"),
        ("梁雪", "市场部", "市场专员", "P5", "employee", 15000, 600, "在职"),
        ("宋斌", "市场部", "市场专员", "P4", "employee", 12000, 200, "在职"),
        ("谢宁", "销售部", "销售经理", "P6", "employee", 21000, 780, "在职"),
        ("唐倩", "销售部", "销售专员", "P4", "employee", 11000, 150, "试用期"),
        ("冯浩", "人事行政部", "人事专员", "P5", "employee", 14000, 520, "在职"),
        ("曹雨", "人事行政部", "行政专员", "P4", "employee", 10000, 260, "在职"),
        ("邓梅", "财务部", "财务专员", "P5", "employee", 15000, 640, "在职"),
        ("许峰", "财务部", "会计", "P5", "employee", 16000, 480, "在职"),
    ]

    employees: list[Employee] = []
    used_names: set[str] = set()
    for idx, (name, dept, position, level, role, salary, days_ago, status) in enumerate(plan, start=1):
        used_names.add(name)
        hire = date.today() - timedelta(days=days_ago)
        emp = Employee(
            emp_no=f"EMP{idx:04d}",
            name=name,
            gender="女" if name[-1] in "芳静敏丽婷霞雪倩梅雨" else "男",
            birth_date=date(1985 + idx % 14, (idx * 3) % 12 + 1, (idx * 7) % 27 + 1),
            phone=f"138{idx:04d}{idx * 7 % 10000:04d}"[:11],
            email=f"{name}@demo-company.com",
            id_card=f"1101{idx:02d}{1985 + idx % 14}{(idx * 3) % 12 + 1:02d}{(idx * 7) % 27 + 1:02d}{idx:04d}",
            department_id=depts[dept],
            position=position,
            job_level=level,
            status=status,
            hire_date=hire,
            salary=float(salary),
            education=random.choice(EDUCATIONS),
            school=random.choice(SCHOOLS),
            address=random.choice(["北京市朝阳区建国路 88 号", "北京市海淀区中关村大街 27 号",
                                   "上海市浦东新区世纪大道 100 号", "深圳市南山区科技园南区",
                                   "杭州市西湖区文三路 90 号"]),
            emergency_contact=random.choice(SURNAMES) + random.choice(GIVEN),
            emergency_phone=f"139{idx:04d}{idx * 3 % 10000:04d}"[:11],
            remark="示例数据，可自由修改或删除",
        )
        db.add(emp)
        db.flush()

        # 前 14 人开通登录账号，覆盖四种角色（老板 / 管理员 / 主管 / 员工）
        if idx <= 14:
            username = {"boss": "boss", "admin": "admin"}.get(role) or _pinyin_like(name, idx)
            account = User(
                username=username,
                password_hash=hash_password(DEFAULT_PASSWORD),
                real_name=name,
                role=role,
                department_id=depts[dept],
                phone=emp.phone,
                email=emp.email,
                is_active=True,
            )
            db.add(account)
            db.flush()
            emp.user_id = account.id
        employees.append(emp)
    db.flush()
    return employees


def _pinyin_like(name: str, idx: int) -> str:
    """给示例账号起个像拼音的用户名（真实拼音转换不必要，加序号保证唯一）。"""
    table = {
        "李强": "liqiang", "王芳": "wangfang", "张伟": "zhangwei", "刘洋": "liuyang",
        "陈静": "chenjing", "杨磊": "yanglei", "周涛": "zhoutao", "吴敏": "wumin",
        "郑凯": "zhengkai", "孙丽": "sunli", "马超": "machao", "朱婷": "zhuting",
    }
    return table.get(name, f"user{idx:03d}")


# ==================================================================== 项目
PROJECTS = [
    # (名称, 客户, 状态, 优先级, 进度, 部门, 负责人姓名, 开始偏移, 结束偏移, 预算)
    ("企业级协同办公平台", "中远集团", "进行中", "高", 68, "技术部", "高鹏", -120, 45, 2800000),
    ("智能客服知识库系统", "华信银行", "进行中", "紧急", 45, "技术部", "何文", -80, 20, 1600000),
    ("手机银行 App 3.0 改版", "华信银行", "进行中", "高", 82, "技术部", "孙丽", -150, -5, 2200000),
    ("官网品牌视觉升级", "自营", "已完成", "中", 100, "市场部", "梁雪", -200, -30, 350000),
    ("华东区渠道拓展计划", "自营", "进行中", "中", 55, "销售部", "谢宁", -90, 60, 800000),
    ("数据中台一期建设", "中远集团", "筹备中", "高", 8, "技术部", "杨磊", 10, 180, 3500000),
    ("年度校园招聘项目", "自营", "进行中", "中", 70, "人事行政部", "冯浩", -45, 25, 200000),
    ("2024 财务系统合规改造", "自营", "已暂停", "低", 30, "财务部", "邓梅", -260, -60, 150000),
]

MEMBERS_BY_DEPT = {
    "技术部": ["杨磊", "周涛", "吴敏", "郑凯", "孙丽", "马超", "朱婷", "胡军", "林霞", "罗琳"],
    "市场部": ["梁雪", "宋斌", "朱婷"],
    "销售部": ["谢宁", "唐倩"],
    "人事行政部": ["冯浩", "曹雨"],
    "财务部": ["邓梅", "许峰"],
}


def seed_projects(db, depts: dict[str, int], employees: list[Employee]) -> list[Project]:
    by_name = {e.name: e for e in employees}
    year = date.today().year
    projects: list[Project] = []
    for idx, (name, customer, status, priority, progress, dept, owner,
              start_off, end_off, budget) in enumerate(PROJECTS, start=1):
        proj = Project(
            code=f"PRJ-{year}-{idx:03d}",
            name=name,
            description=f"{name}（示例项目），负责方：{dept}。目标客户：{customer}。",
            customer=customer,
            status=status,
            priority=priority,
            progress=progress,
            department_id=depts[dept],
            owner_id=by_name[owner].id if owner in by_name else None,
            start_date=date.today() + timedelta(days=start_off),
            end_date=date.today() + timedelta(days=end_off),
            budget=float(budget),
        )
        db.add(proj)
        db.flush()

        member_names = {owner}
        pool = MEMBERS_BY_DEPT.get(dept, [])
        member_names.update(random.sample(pool, k=min(len(pool), random.randint(2, 5))))
        for mn in member_names:
            emp = by_name.get(mn)
            if not emp:
                continue
            db.add(ProjectMember(
                project_id=proj.id, employee_id=emp.id,
                role="项目负责人" if mn == owner else random.choice(
                    ["开发", "开发", "测试", "设计", "需求", "实施"]),
            ))
        projects.append(proj)
    db.flush()
    return projects


# ==================================================================== 报告（真实可下载的文件）
REPORT_PLAN = [
    ("企业级协同办公平台", "协同办公平台需求规格说明书", "需求文档", 10, ["需求", "评审通过"],
     "包含功能清单、角色权限矩阵与验收标准，已通过客户评审。"),
    ("企业级协同办公平台", "第 12 周项目周报", "周报", 6, ["周报", "迭代"],
     "本周完成审批流引擎联调，进度 68%，无阻塞风险。"),
    ("企业级协同办公平台", "系统性能测试报告", "测试报告", 3, ["性能", "压测"],
     "500 并发下平均响应 320ms，满足 SLA 要求。"),
    ("智能客服知识库系统", "知识库检索算法调研报告", "其他", 20, ["算法", "调研"],
     "对比 BM25、向量检索与混合检索三种方案，推荐混合检索。"),
    ("智能客服知识库系统", "第 6 周项目周报", "周报", 5, ["周报"],
     "数据标注完成 60%，接口联调按计划推进。"),
    ("手机银行 App 3.0 改版", "App 3.0 项目结项报告", "项目结项报告", 12, ["结项", "验收"],
     "项目已交付并通过验收，累计提测 14 轮，遗留缺陷 0。"),
    ("手机银行 App 3.0 改版", "UI 走查问题清单", "测试报告", 30, ["UI", "走查"],
     "共记录 63 项视觉走查问题，已全部修复关闭。"),
    ("华东区渠道拓展计划", "华东区渠道拓展月度报告", "月报", 8, ["月报", "销售"],
     "新增签约渠道 12 家，季度目标完成率 78%。"),
    ("华东区渠道拓展计划", "竞品价格策略分析", "其他", 15, ["竞品", "分析"],
     "梳理主要竞品定价与返点规则，给出三条应对建议。"),
    ("官网品牌视觉升级", "品牌视觉升级结项报告", "项目结项报告", 25, ["结项", "品牌"],
     "新官网已上线，首月访问量环比增长 42%。"),
    ("数据中台一期建设", "数据中台技术方案初稿", "需求文档", 7, ["方案", "初稿"],
     "含数据分层、血缘治理与调度体系设计，待评审。"),
    ("年度校园招聘项目", "2024 校招阶段性总结", "月报", 9, ["校招", "总结"],
     "收到简历 3260 份，已完成两轮面试，发放 offer 38 个。"),
    ("2024 财务系统合规改造", "财务系统合规风险说明", "其他", 40, ["合规", "风险"],
     "识别 7 项合规风险，其中 2 项为高优先级，需在整改期内闭环。"),
]


def _write_demo_pdf(title: str, lines: list[str], path) -> int:
    """
    手写一个最小可用的 PDF 文件（不引第三方库）。
    目的是让示例报告真的能下载、能在浏览器里预览，而不是空壳文件。
    """
    def esc(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # 中文在标准 14 号字体（Helvetica）里显示不出来，这里统一用英文占位说明 + 拼音式标题
    content_lines = ["Demo Report File", ""]
    content_lines += lines
    parts = ["BT", "/F1 11 Tf", "14 TL", "60 780 Td"]
    for i, line in enumerate(content_lines):
        if i:
            parts.append("T*")
        parts.append(f"({esc(line)}) Tj")
    parts.append("ET")
    stream = "\n".join(parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n"
            "%%EOF\n").encode()
    path.write_bytes(bytes(out))
    return len(out)


def seed_reports(db, projects: list[Project], accounts: list[User]) -> int:
    by_project = {p.name: p for p in projects}
    uploaders = [a for a in accounts if a.role in ("admin", "manager")] or accounts
    created = 0
    folder = UPLOAD_DIR / "demo"
    folder.mkdir(parents=True, exist_ok=True)

    for idx, (proj_name, title, category, days_ago, tags, summary) in enumerate(REPORT_PLAN, start=1):
        proj = by_project.get(proj_name)
        if not proj:
            continue
        safe = f"demo_{idx:02d}_{abs(hash(title)) % 10000:04d}.pdf"
        content = [
            f"Project : {proj.code}",
            f"Category: {category}",
            f"Version : 1",
            f"Date    : {(date.today() - timedelta(days=days_ago)).isoformat()}",
            "",
            "This file is generated automatically as demo data",
            "for the local company admin system.",
            "",
            "Summary:",
        ] + [f"  - {line}" for line in summary.split("。") if line]
        size = _write_demo_pdf(title, content, folder / safe)

        uploader = random.choice(uploaders)
        report = Report(
            project_id=proj.id,
            title=title,
            category=category,
            version=1,
            report_date=date.today() - timedelta(days=days_ago),
            tags=",".join(tags),
            summary=summary,
            file_name=f"{title}.pdf",
            stored_path=f"demo/{safe}",
            file_size=size,
            file_ext=".pdf",
            uploader_id=uploader.id,
            download_count=random.randint(0, 18),
            created_at=datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 8)),
        )
        db.add(report)
        created += 1

    # 给两份报告补一个历史版本，演示版本追溯
    for proj_name, title, category in [
        ("企业级协同办公平台", "第 12 周项目周报", "周报"),
        ("智能客服知识库系统", "知识库检索算法调研报告", "其他"),
    ]:
        proj = by_project.get(proj_name)
        if not proj:
            continue
        base = db.scalar(select(Report).where(Report.title == title, Report.project_id == proj.id))
        if not base:
            continue

        # 把现有记录推到 v2，再插入一份 v1，形成可追溯的版本链
        old_date = base.report_date or date.today()
        old_summary, old_tags = base.summary, base.tags
        old_uploader, old_created = base.uploader_id, base.created_at
        safe = f"demo_v1_{abs(hash(title)) % 10000:04d}.pdf"
        content = [f"Project : {proj.code}", "Version : 1 (history)", "",
                   "This is the previous version kept for version tracking."]
        size = _write_demo_pdf(title, content, folder / safe)
        base.version = 2
        db.add(Report(
            project_id=proj.id, title=title, category=category, version=1,
            report_date=old_date - timedelta(days=7), tags=old_tags,
            summary="（历史版本）" + (old_summary or ""),
            file_name=f"{title}_v1.pdf", stored_path=f"demo/{safe}", file_size=size,
            file_ext=".pdf", uploader_id=old_uploader, download_count=random.randint(0, 5),
            created_at=(old_created or datetime.now()) - timedelta(days=7),
        ))
        created += 1

    db.flush()
    return created


# ==================================================================== 考勤与请假
def seed_attendance(db, employees: list[Employee], days: int = 75) -> int:
    """生成最近 N 天的考勤，工作日打卡，随机产生迟到/早退/缺卡/请假。"""
    created = 0
    today = date.today()
    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:      # 跳过周末
            continue
        for emp in employees:
            if emp.hire_date and emp.hire_date > day or emp.status == "离职":
                continue
            roll = random.random()
            if roll < 0.03:                      # 请假
                rec = Attendance(employee_id=emp.id, work_date=day, status="请假",
                                 remark="事假（示例数据）", work_hours=0)
                db.add(rec)
                created += 1
                continue
            if roll < 0.05 and offset > 2:       # 缺卡
                db.add(Attendance(employee_id=emp.id, work_date=day, status="缺卡",
                                  remark="忘记打卡（示例数据）", work_hours=0))
                created += 1
                continue

            late = random.random() < 0.08
            in_h, in_m = (9, random.randint(16, 55)) if late else (8, random.randint(35, 59))
            out_h, out_m = (18, random.randint(5, 50))
            if random.random() < 0.06:
                out_h, out_m = (17, random.randint(10, 44))    # 早退
            check_in = datetime.combine(day, time(in_h, in_m, random.randint(0, 59)))
            check_out = datetime.combine(day, time(out_h, out_m, random.randint(0, 59)))
            hours = round((check_out - check_in).total_seconds() / 3600, 2)
            status = "迟到" if late else ("早退" if out_h < 18 else "正常")
            db.add(Attendance(employee_id=emp.id, work_date=day, check_in=check_in,
                              check_out=check_out, status=status, work_hours=hours))
            created += 1
    db.flush()
    return created


def seed_leaves(db, employees: list[Employee], accounts: list[User]) -> int:
    approvers = [a for a in accounts if a.role in ("admin", "manager")]
    if not approvers:
        return 0
    plan = [
        (-25, 2, "事假", "家中有事，需要请假两天", "已通过"),
        (-18, 1, "病假", "感冒发烧，去医院就诊", "已通过"),
        (-12, 3, "年假", "计划外出旅行，提前申请", "已通过"),
        (-6, 1, "调休", "上周末加班，申请调休一天", "已通过"),
        (-3, 2, "事假", "办理房屋过户手续", "待审批"),
        (-1, 1, "事假", "个人事务", "已驳回"),
        (3, 5, "年假", "国庆前后连休，已与同事交接", "待审批"),
    ]
    created = 0
    for idx, (start_off, days, ltype, reason, status_value) in enumerate(plan):
        emp = employees[(idx * 3 + 2) % len(employees)]
        start = date.today() + timedelta(days=start_off)
        end = start + timedelta(days=days - 1)
        approver = approvers[idx % len(approvers)]
        leave = LeaveRequest(
            employee_id=emp.id, leave_type=ltype, start_date=start, end_date=end,
            days=float(days), reason=reason, status=status_value,
            approver_id=approver.id if status_value != "待审批" else None,
            approved_at=datetime.now() - timedelta(days=max(days, 1))
            if status_value != "待审批" else None,
            approve_comment={"已通过": "同意，注意交接工作", "已驳回": "当前项目处于关键期，建议改期"}
            .get(status_value),
        )
        db.add(leave)
        created += 1
    db.flush()
    return created


# ==================================================================== 公告与日志
ANNOUNCEMENTS = [
    ("关于 2025 年度绩效考核安排的通知", "通知", True,
     "各部门：\n\n2025 年度绩效考核工作将于下月启动，请各位同事在 15 日前完成自评，"
     "并由部门主管完成复评。考核结果将作为调薪与晋升的重要依据。\n\n特此通知。\n人事行政部"),
    ("办公区网络升级维护公告", "通知", False,
     "为提升办公网络稳定性，本周六 22:00 至次日 02:00 将对机房核心交换机进行升级。"
     "维护期间内网与 VPN 会短时中断，请提前保存工作内容。\n\n技术支持：罗琳"),
    ("员工考勤与请假制度更新说明", "制度", True,
     "自本月起，考勤规则调整如下：\n1. 上班打卡时间晚于 09:15 记为迟到；\n"
     "2. 下班打卡早于 17:45 记为早退；\n3. 请假需提前一个工作日在系统提交申请，"
     "由部门主管审批。\n请各位同事知悉并遵照执行。"),
    ("三季度团建活动报名开始", "活动", False,
     "三季度团建定于本月最后一个周五，地点为郊区度假村，含拓展活动与烧烤晚宴。"
     "请各部门在本周五前把参与人数报给行政专员曹雨。"),
    ("新同事入职欢迎", "人事", False,
     "欢迎唐倩、林霞两位新同事加入公司！两位分别就职于销售部与测试组，"
     "请大家在工作中多多协助，帮助新同事尽快融入团队。"),
    ("技术分享会：从单体到微服务的踩坑实录", "技术分享", False,
     "本周四 16:00 在 3 号会议室，由杨磊分享服务拆分过程中的实际问题与解决方案，"
     "欢迎研发同学参加，也欢迎其他部门同事旁听。"),
]


def seed_announcements(db, accounts: list[User]) -> int:
    publishers = [a for a in accounts if a.role in ("admin", "manager")] or accounts
    created = 0
    for idx, (title, category, pinned, content) in enumerate(ANNOUNCEMENTS):
        ann = Announcement(
            title=title, content=content, category=category, is_pinned=pinned,
            is_published=True, publisher_id=publishers[idx % len(publishers)].id,
            created_at=datetime.now() - timedelta(days=idx * 3 + 1),
        )
        db.add(ann)
        db.flush()
        # 前两条让部分人已读，演示已读回执
        if idx < 2:
            for account in accounts[: max(2, len(accounts) // 3)]:
                db.add(AnnouncementRead(announcement_id=ann.id, user_id=account.id))
        created += 1
    db.flush()
    return created


def seed_logs(db, accounts: list[User], projects: list[Project]) -> int:
    """补一批历史操作日志，让审计页面不是空的。"""
    samples = [
        ("登录", "认证", "登录系统"),
        ("新增", "员工管理", "新增员工 {}"),
        ("修改", "项目管理", "修改项目 {} 的进度"),
        ("上传", "报告管理", "上传报告《{}》v1"),
        ("下载", "报告管理", "下载报告《{}》"),
        ("审批", "请假审批", "通过 {} 的请假申请"),
        ("修改", "考勤管理", "补录 {} 的考勤记录"),
        ("新增", "公告通知", "发布公告《{}》"),
        ("导出", "员工管理", "导出员工名册"),
        ("修改", "部门管理", "调整部门负责人"),
    ]
    created = 0
    for idx in range(60):
        action, module, template = samples[idx % len(samples)]
        account = accounts[(idx * 5) % len(accounts)]
        target = random.choice(projects).name if projects else "示例对象"
        detail = template.format(target) if "{}" in template else template
        db.add(OperationLog(
            user_id=account.id, username=account.username, action=action, module=module,
            detail=detail, ip="127.0.0.1",
            created_at=datetime.now() - timedelta(days=random.randint(0, 20),
                                                  hours=random.randint(0, 23),
                                                  minutes=random.randint(0, 59)),
        ))
        created += 1
    db.flush()
    return created


# ==================================================================== 主流程
def main(reset: bool = False) -> None:
    if reset:
        print("[1/3] 清空既有数据 ...")
        Base.metadata.drop_all(bind=engine)
    init_db()

    with SessionLocal() as db:
        if db.scalar(select(Employee.id).limit(1)):
            print("数据库已有数据，跳过初始化。")
            print("如需重新生成示例数据，请执行：python -m scripts.seed --reset")
            return

        print("[2/3] 正在生成示例数据 ...")
        depts = seed_departments(db)
        employees = seed_employees(db, depts)
        accounts = db.scalars(select(User)).all()
        projects = seed_projects(db, depts, employees)
        reports = seed_reports(db, projects, accounts)
        attendance = seed_attendance(db, employees)
        leaves = seed_leaves(db, employees, accounts)
        announcements = seed_announcements(db, accounts)
        logs = seed_logs(db, accounts, projects)
        db.commit()

    print("[3/3] 完成！")
    print(f"  部门 {len(depts)} 个 | 员工 {len(employees)} 名 | 登录账号 {len(accounts)} 个")
    print(f"  项目 {len(projects)} 个 | 报告 {reports} 份 | 考勤 {attendance} 条")
    print(f"  请假 {leaves} 条 | 公告 {announcements} 条 | 操作日志 {logs} 条")
    print()
    print("  可用账号（密码均为 123456）：")
    print("    boss     老板（董事长）—— 全部权限，可直接开除员工")
    print("    admin    系统管理员     —— 全部权限（用于系统维护）")
    print("    liqiang  技术部主管     —— 本部门及下级部门数据")
    print("    wangfang 市场部主管     —— 本部门数据")
    print("    yanglei  普通员工       —— 仅本人相关数据")
    print()
    print("  下一步：.\\scripts\\start.ps1  然后访问 http://127.0.0.1:8000/")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
