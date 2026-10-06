# 企业后台管理系统

一个面向中小企业的内部管理系统，覆盖员工档案、组织架构、项目管理、报告归档、考勤与请假审批。
后端 FastAPI + SQLite，前端 Vue 3（无构建步骤），整套系统可以在本机直接跑起来，不依赖任何外部服务。

## 功能

| 模块 | 说明 |
|---|---|
| 数据看板 | 打卡面板、人员/项目/报告 KPI、项目状态与部门人数分布、近半年报告产出与入职走势、逾期项目提醒 |
| 员工管理 | 多条件筛选与分页、增删改查、工号自动生成、批量改状态/删除、批量开通登录账号、Excel 导入导出（含模板与逐行校验） |
| 部门架构 | 多级部门树、部门主管指定、成员查看；删除前校验子部门与在职员工，防止组织树断链 |
| 项目管理 | 卡片/列表双视图、编号自动生成、进度与剩余天数提醒、项目成员维护、成员可自行更新进度 |
| 报告管理 | 拖拽上传、按项目归档、同名重传自动递增版本、PDF/图片在线预览、下载计数、批量下载 |
| 考勤打卡 | 上下班打卡与状态自动判定（迟到/早退/缺卡）、月历视图、记录查询、月度汇总、主管补录 |
| 请假审批 | 申请提交、时段重叠校验、三级视图（我的/待审批/部门）、审批通过后自动标记考勤 |
| 公告通知 | 发布/编辑/置顶、草稿状态、已读回执与未读角标 |
| 操作审计 | 全量操作日志与统计图表，覆盖新增/修改/删除/登录/上传/下载/审批等动作 |
| 账号与角色 | 四种角色的数据范围隔离、账号管理、密码重置、员工档案绑定 |

## 技术栈

| 层次 | 选型 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 |
| 数据库 | SQLite（单文件，免安装；可通过环境变量切换到 PostgreSQL / MySQL） |
| 认证 | JWT（PyJWT）+ PBKDF2-SHA256 密码哈希 |
| 前端 | Vue 3 + Vue Router（本地文件，无构建步骤） |
| 图表 | ECharts 5 |
| 导入导出 | openpyxl |

## 快速开始

环境要求：Python 3.10 及以上。启动脚本提供 PowerShell 版本（Windows 直接用），其他平台按下面的手动步骤执行。

```powershell
# 初始化：创建虚拟环境、安装依赖、下载前端依赖、建库并写入演示数据
.\scripts\setup.ps1

# 启动
.\scripts\start.ps1
```

启动后访问 <http://127.0.0.1:8000/>，接口文档在 <http://127.0.0.1:8000/docs>。

手动执行（跨平台）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# 下载 Vue、Vue Router、ECharts 三个文件放入 web/static/vendor/
.venv/bin/python -m scripts.seed
.venv/bin/python -m uvicorn app.main:app --reload
```

### 演示账号

密码均为 `123456`，登录页点击账号可自动填充。

| 用户名 | 姓名 | 角色 | 数据范围 |
|---|---|---|---|
| `boss` | 王建国 | 老板（董事长） | 全公司 |
| `admin` | 赵敏 | 系统管理员 | 全公司 |
| `liqiang` | 李强 | 技术部主管 | 技术部及其下级部门 |
| `wangfang` | 王芳 | 市场部主管 | 市场部 |
| `yanglei` | 杨磊 | 普通员工 | 仅本人相关 |

演示数据包含 9 个部门、27 名员工、8 个项目、13 份报告（真实可下载的 PDF）、约 1400 条考勤记录。

## 权限模型

权限由「角色 + 部门树」两层决定，判断逻辑集中在 `app/config.py` 与 `app/deps.py`：

```python
ADMIN_LIKE_ROLES   = ("boss", "admin")              # 全公司数据 + 管理功能
MANAGER_LIKE_ROLES = ("boss", "admin", "manager")   # 本部门及下级部门 + 审批
```

| 角色 | 数据范围 | 说明 |
|---|---|---|
| `boss` | 全公司 | 与系统管理员同权，标签上区分业务负责人视角 |
| `admin` | 全公司 | 全部功能，含账号管理、操作日志、物理删除员工、查看薪资 |
| `manager` | 本部门 + 所有下级部门 | 管理范围内的员工/项目/报告/考勤，可审批请假；不能跨部门；删除员工会降级为"标记离职" |
| `employee` | 本人相关 | 打卡、请假、上传下载自己可见项目的报告、查看本人考勤 |

其他约定：

- 员工档案与登录账号分离，可先建档后开号；删除账号不会删除员工记录
- `salary`（月薪）、`id_card`（身份证号）仅最高权限角色可见，其他角色接口直接返回空值
- 报告的可见范围为「本部门项目 + 本人参与项目」，修改和删除仅限自己上传的文件
- 所有写操作都会记录操作日志（含操作人、详情与来源 IP）
- 最高权限角色不能删除或停用自己的账号，避免把自己锁在系统外

## 项目结构

```
company-admin/
├── app/                        # 后端
│   ├── main.py                 # 应用入口、路由挂载、全局异常处理
│   ├── config.py               # 配置项与业务字典
│   ├── db.py                   # 引擎与会话
│   ├── models.py               # ORM 模型
│   ├── security.py             # 密码哈希与 JWT
│   ├── deps.py                 # 登录校验、角色校验、数据范围、审计
│   ├── serializers.py          # 统一序列化
│   └── api/                    # 各模块接口
├── web/                        # 前端（无构建步骤）
│   ├── index.html
│   └── static/
│       ├── css/app.css
│       ├── js/                 # api / utils / components / charts / app
│       ├── js/pages/           # 12 个页面
│       └── vendor/             # Vue、Vue Router、ECharts 本地文件
├── scripts/                    # 运维与测试脚本
├── data/                       # 运行期数据（数据库、上传文件）
└── requirements.txt
```

## 配置项

通过环境变量覆盖，无需改代码：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CADMIN_DATABASE_URL` | `sqlite:///data/cadmin.db` | 数据库连接串 |
| `CADMIN_SECRET_KEY` | 开发用固定值 | JWT 签名密钥，部署前必须修改 |
| `CADMIN_TOKEN_EXPIRE_MINUTES` | `720` | 登录有效期（分钟） |
| `CADMIN_MAX_UPLOAD_MB` | `50` | 上传文件大小上限 |
| `CADMIN_DATA_DIR` | `./data` | 数据目录 |

考勤规则（上下班时间、迟到/早退判定线）位于 `app/api/attendance.py` 顶部，按实际制度调整即可。

## 测试

需要先启动服务，然后另开一个窗口执行：

```powershell
.\scripts\test.ps1                  # 全部检查
.\scripts\test.ps1 -SkipBrowser     # 跳过浏览器渲染测试
.\scripts\test.ps1 -SkipSmoke       # 只跑前端相关检查
.\scripts\test.ps1 -Port 8001       # 对非默认端口做自测
```

| 脚本 | 覆盖内容 |
|---|---|
| `test_api.py` | 接口全流程：登录与越权拦截、员工增删改查与 Excel 导入导出、项目与成员、报告上传/版本/下载/预览、考勤打卡与补录、请假审批状态机、公告、日志与账号管理 |
| `test_permissions.py` | 普通员工的权限矩阵：管理操作必须被拒、日常操作必须放行、报告的改删归属与可见范围 |
| `test_admin.py` | 系统管理员：全公司数据可见性、跨部门写权限、独占功能与应有的边界 |
| `test_boss.py` | 老板角色：标签与菜单可用性、全公司可见、开除员工（含批量）与关联账号处理 |
| `test_frontend.py` | 静态资源可用性、页面脚本注册、示例文件有效性、文件编码检查 |
| `test_browser.py` | 无头 Chrome/Edge 真实渲染全部页面，抓取 JS 报错，校验未登录跳转与顶栏身份显示 |

测试脚本会自动清理自身产生的数据，可反复执行。修改权限相关代码后建议至少跑一遍前四个。

## 部署提示

当前配置面向本地运行，正式部署前需要处理：

1. 通过环境变量设置随机 `CADMIN_SECRET_KEY`
2. 数据库换为 PostgreSQL 或 MySQL（SQLite 在并发写入下会锁表）
3. 生产环境关闭 `/docs`，收紧 CORS 的允许来源
4. 前置 Nginx 并启用 HTTPS；会话令牌改用 HttpOnly Cookie 存储更安全
5. 上传文件改用对象存储，并加入病毒扫描
6. 对 `data/` 目录做定时备份（数据库与上传文件需一起备份）
7. 批量开通的初始密码应强制首次登录修改，登录接口建议加失败次数限制

## 常见问题

**端口被占用？**
`start.ps1` 会自动从指定端口向后寻找可用端口并打印实际地址，也可用 `-Port` 手动指定。

**忘记密码？**
用具备账号管理权限的账号登录后重置。若该账号密码也遗失，可用命令行重置：

```bash
.venv/bin/python -c "from app.db import SessionLocal; from app.models import User; from app.security import hash_password; from sqlalchemy import select; db=SessionLocal(); u=db.scalar(select(User).where(User.username=='admin')); u.password_hash=hash_password('123456'); db.commit(); print('done')"
```

**想从空库开始？**
删除 `data/cadmin.db` 后启动，系统会自动建表但不会写入演示数据。

**页面打开是空白？**
在浏览器控制台执行 `document.getElementById('error-collector').textContent` 查看采集到的报错，
或运行 `python -m scripts.test_browser`，它会渲染每个页面并输出错误信息。
常见原因是新增的页面脚本没有在 `web/index.html` 中引入。

## 许可

MIT License，见 [LICENSE](LICENSE)。
