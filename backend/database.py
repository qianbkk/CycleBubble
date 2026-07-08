"""数据库连接"""
from sqlmodel import SQLModel, Session, create_engine
from config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False}  # SQLite 需要
)


def init_db():
    """创建所有表"""
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
