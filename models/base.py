"""
SQLAlchemy 基础配置和数据库会话管理

Author: Spidermind
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Dict, Any

from config.settings import settings

# 创建数据库引擎
engine = create_engine(
    settings.MYSQL_DSN,
    echo=settings.DEBUG,  # 开发环境下输出SQL
    pool_pre_ping=True,   # 连接池健康检查
    pool_recycle=3600,    # 1小时回收连接
    pool_size=10,         # 连接池大小
    max_overflow=20       # 最大溢出连接数
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话依赖注入
    
    Yields:
        Session: SQLAlchemy 数据库会话
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def create_all_tables():
    """创建所有数据表"""
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """删除所有数据表（谨慎使用）"""
    Base.metadata.drop_all(bind=engine)


def get_table_counts() -> Dict[str, Any]:
    """
    获取所有表的记录数量
    
    Returns:
        Dict[str, Any]: 表名和记录数的映射
    """
    counts = {}
    
    # 获取所有表名
    table_names = [
        'candidates', 'candidate_emails', 'candidate_institutions', 
        'candidate_homepages', 'candidate_files', 'candidate_repos', 
        'candidate_papers', 'raw_texts', 'crawl_tasks', 'crawl_logs', 
        'crawl_log_candidates', 'github_users', 'openreview_users'
    ]
    
    try:
        with engine.connect() as connection:
            for table_name in table_names:
                try:
                    result = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    counts[table_name] = result.scalar()
                except Exception as e:
                    counts[table_name] = f"Error: {str(e)}"
    except Exception as e:
        return {"error": f"Database connection failed: {str(e)}"}
    
    return counts


def test_database_connection() -> Dict[str, str]:
    """
    测试数据库连接
    
    Returns:
        Dict[str, str]: 连接状态信息
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            if result.scalar() == 1:
                return {"status": "connected", "message": "Database connection successful"}
            else:
                return {"status": "error", "message": "Unexpected result from test query"}
    except Exception as e:
        return {"status": "error", "message": f"Database connection failed: {str(e)}"}