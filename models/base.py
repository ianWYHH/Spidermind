"""
SQLAlchemy 基础配置和数据库会话管理 - 统一配置入口

Author: Spidermind
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Dict, Any

from config.settings import settings

# 创建数据库引擎 - 使用统一配置入口
engine = create_engine(
    settings.get_mysql_dsn(),  # 使用新的统一配置方法
    echo=settings.DEBUG,       # 开发环境下输出SQL
    pool_pre_ping=True,        # 连接池健康检查
    pool_recycle=1800,         # 30分钟回收连接
    pool_size=10,              # 连接池大小
    max_overflow=20            # 最大溢出连接数
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的依赖注入函数
    用于FastAPI的Depends
    
    Yields:
        Session: SQLAlchemy数据库会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables():
    """创建所有数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 数据库表创建/更新完成")
    except Exception as e:
        print(f"❌ 创建数据库表失败: {str(e)}")
        raise


def drop_all_tables():
    """删除所有数据库表（谨慎使用）"""
    Base.metadata.drop_all(bind=engine)
    print("⚠️  所有数据库表已删除")


def get_table_counts() -> Dict[str, Any]:
    """
    获取所有表的记录数量
    
    Returns:
        Dict[str, Any]: 表名和记录数量的字典
    """
    with SessionLocal() as db:
        try:
            counts = {}
            # 主表
            counts['candidates'] = db.execute(text("SELECT COUNT(*) FROM candidates")).scalar()
            
            # 子表
            counts['candidate_emails'] = db.execute(text("SELECT COUNT(*) FROM candidate_emails")).scalar()
            counts['candidate_institutions'] = db.execute(text("SELECT COUNT(*) FROM candidate_institutions")).scalar()
            counts['candidate_homepages'] = db.execute(text("SELECT COUNT(*) FROM candidate_homepages")).scalar()
            counts['candidate_files'] = db.execute(text("SELECT COUNT(*) FROM candidate_files")).scalar()
            counts['candidate_repos'] = db.execute(text("SELECT COUNT(*) FROM candidate_repos")).scalar()
            counts['candidate_papers'] = db.execute(text("SELECT COUNT(*) FROM candidate_papers")).scalar()
            counts['raw_texts'] = db.execute(text("SELECT COUNT(*) FROM raw_texts")).scalar()
            
            # 爬虫相关表
            counts['crawl_tasks'] = db.execute(text("SELECT COUNT(*) FROM crawl_tasks")).scalar()
            counts['crawl_logs'] = db.execute(text("SELECT COUNT(*) FROM crawl_logs")).scalar()
            counts['crawl_log_candidates'] = db.execute(text("SELECT COUNT(*) FROM crawl_log_candidates")).scalar()
            
            # 映射表
            counts['github_users'] = db.execute(text("SELECT COUNT(*) FROM github_users")).scalar()
            counts['openreview_users'] = db.execute(text("SELECT COUNT(*) FROM openreview_users")).scalar()
            
            return counts
        except Exception as e:
            print(f"❌ 获取表数量失败: {str(e)}")
            return {"error": str(e)}


def test_database_connection() -> Dict[str, str]:
    """
    测试数据库连接
    
    Returns:
        Dict[str, str]: 连接状态信息
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
        
        return {
            "status": "connected",
            "message": f"数据库连接成功: {settings.get_mysql_dsn()}",
            "dsn": settings.get_mysql_dsn()
        }
    except Exception as e:
        return {
            "status": "failed", 
            "message": f"Database connection failed: {str(e)}",
            "dsn": settings.get_mysql_dsn()
        }