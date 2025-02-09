from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}  # 仅用于SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 数据库依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 创建所有表
def init_db():
    from app.core.models import Base
    Base.metadata.create_all(bind=engine) 