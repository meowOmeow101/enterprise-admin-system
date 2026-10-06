"""
企业后台管理系统 —— 应用入口。

本地启动：
    .\\scripts\\start.ps1            # 推荐，自动做完检查
    uvicorn app.main:app --reload    # 手动方式，在项目根目录执行

访问：
    http://127.0.0.1:8000/          前端界面
    http://127.0.0.1:8000/docs      接口文档（Swagger）
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import (announcements, attendance, auth, dashboard, departments, employees, leaves,
                  logs, projects, reports)
from .config import APP_NAME, AVATAR_DIR, UPLOAD_DIR, WEB_DIR
from .db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cadmin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s 已就绪，数据目录与数据库连接正常", APP_NAME)
    yield
    logger.info("%s 已停止", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    description="员工管理、项目与报告管理、考勤请假、公告与操作审计的一体化后台。",
    version="1.0.0",
    lifespan=lifespan,
)

# 本地前后端同源部署其实用不到 CORS，但留着方便你用别的端口做前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================================== 统一错误格式
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """把 HTTPException 统一成 {code, message}，前端只管读 message 弹提示。"""
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": message, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """表单校验错误也翻译成人话。"""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", [])[1:]) or "参数"
        problems.append(f"{loc}: {err.get('msg', '不合法')}")
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "参数校验失败 —— " + "；".join(problems[:5]), "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"code": 500, "message": f"服务器内部错误：{exc}", "data": None})


# ==================================================================== 请求日志
@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    cost = (time.perf_counter() - started) * 1000
    # 静态资源刷屏没意义，只记录接口调用和慢请求
    if request.url.path.startswith("/api") or cost > 800:
        logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path,
                    response.status_code, cost)
    return response


# ==================================================================== 路由
for module in (auth, departments, employees, projects, reports, dashboard,
               attendance, leaves, announcements, logs):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["系统"], summary="健康检查")
def health():
    return {"status": "ok", "app": APP_NAME}


# ==================================================================== 静态资源
# 上传的文件（报告、头像）按原样对外提供；需要鉴权的下载走 /api/reports/{id}/download
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
# 兜底：前端单页应用，html=True 让根路径直接返回 index.html
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
