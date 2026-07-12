from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import settings
from .database import init_db, demo_engine
from sqlmodel import Session, select
from .models import User, Memory
from .auth import hash_password
from .services.admin_settings import init_settings_from_env

DEMO_EMAIL = "demo@cyclebubble.local"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时同时初始化真实库和演示库"""
    from . import models  # 确保模型被注册
    init_db(target="both")
    # 把环境变量默认值写入 AdminSetting
    init_settings_from_env()
    # 确保演示账号存在
    _ensure_demo_user()
    yield


def _ensure_demo_user():
    """在演示库创建 demo 账号（如果已存在则跳过）。"""
    with Session(demo_engine) as session:
        existing = session.exec(select(User).where(User.email == DEMO_EMAIL)).first()
        if existing:
            return
        u = User(
            email=DEMO_EMAIL,
            nickname="演示用户",
            password_hash=hash_password("demo"),
        )
        session.add(u)
        session.commit()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    # 公网关闭 Swagger UI / Redoc / OpenAPI schema，避免 API 拓扑 + admin 端点
    # 完全暴露给攻击者（"Try it out" 让探测变得非常容易）。
    # 开发时可设 CB_API_DOCS_ENABLED=true 临时开启。
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

# CORS 配置：白名单模式 + 不带 credentials
# 浏览器通过 Bearer Token 认证，不依赖 Cookie/credentials
# allow_origins=["*"] + allow_credentials=True 在浏览器规范中是非法且危险的
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Demo-Mode"],
)

# 路由挂载（其他 agent 正在创建这些文件，确保导入正确）
from .routers import auth, cycle, memory, resonance, growth, reports, profile, admin
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(cycle.router, prefix="/api/cycle", tags=["cycle"])
app.include_router(memory.router, prefix="/api/memories", tags=["memories"])
app.include_router(resonance.router, prefix="/api/resonance", tags=["resonance"])
app.include_router(growth.router, prefix="/api/growth", tags=["growth"])
app.include_router(reports.router)  # reports.router 自带 prefix="/api/reports"
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(admin.router)  # admin.router 自带 prefix="/admin"

@app.get("/")
def root():
    return {"status": "ok", "app": settings.app_name}

@app.get("/api/health")
def health():
    """轻量健康检查（不查数据库，给 LB / 外层探活用）"""
    return {"status": "ok"}

@app.get("/api/healthz")
def healthz():
    """深度健康检查（查数据库 + 关键表是否存在）

    用来判断"代码迁移是否成功"——例如新增字段后 create_all 漏掉，
    这里会返回 "db":"missing_table" 而不是 fake-ok。
    部署脚本（cyclebubble-update.sh）通过本接口判断回滚。
    """
    from .models import User, Memory, Cycle
    try:
        with Session(real_engine) as session:
            session.exec(select(User)).first()
            session.exec(select(Memory)).first()
            session.exec(select(Cycle)).first()
        return {"db": "ok", "tables": ["user", "memory", "cycle"], "app": settings.app_name}
    except Exception as e:
        # 数据库迁移漏表/字段时这里会失败
        return {"db": "error", "error": str(e)[:200]}