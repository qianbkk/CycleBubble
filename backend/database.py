from sqlmodel import SQLModel, Session, create_engine
from .config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

def init_db():
    """创建所有表"""
    # 注意：models.py 的导入需要在这里发生，但这里不能直接导入避免循环
    # 我们将在 main.py 的 startup 事件中调用此函数并先 import models
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI 依赖：每次请求一个 Session"""
    with Session(engine) as session:
        yield session