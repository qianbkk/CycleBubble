from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import settings
from .database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    from . import models  # 确保模型被注册
    init_db()
    yield

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由挂载（其他 agent 正在创建这些文件，确保导入正确）
from .routers import auth, cycle, memory, resonance, growth
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(cycle.router, prefix="/api/cycle", tags=["cycle"])
app.include_router(memory.router, prefix="/api/memories", tags=["memories"])
app.include_router(resonance.router, prefix="/api/resonance", tags=["resonance"])
app.include_router(growth.router, prefix="/api/growth", tags=["growth"])

@app.get("/")
def root():
    return {"status": "ok", "app": settings.app_name}

@app.get("/api/health")
def health():
    return {"status": "ok"}