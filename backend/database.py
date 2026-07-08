"""数据库连接"""
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, create_engine
from config import settings


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False}  # SQLite 需要
)


if _is_sqlite_url(settings.database_url):
    @event.listens_for(Engine, "connect")
    def _sqlite_enable_fk(dbapi_connection, connection_record):  # noqa: ANN001
        """SQLite 默认不强制外键——必须在每个新连接打开 PRAGMA。

        不开的话，schema 里的 FOREIGN KEY 约束会被静默忽略，Phase 1 修复
        (Response.memory_id 外键) 在生产路径完全失效。
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db():
    """创建所有表"""
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
