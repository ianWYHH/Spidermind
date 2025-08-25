"""
应用配置管理 - 统一配置入口
.env 优先，config/database.json 兜底

Author: Spidermind
"""
import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path

# 尝试加载 python-dotenv，不存在则用标准库
try:
    from dotenv import load_dotenv
    load_dotenv()
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

try:
    from pydantic_settings import BaseSettings
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


def get_mysql_dsn() -> str:
    """
    统一的MySQL DSN获取方法
    优先级：环境变量 MYSQL_DSN > config/database.json
    
    Returns:
        str: MySQL连接字符串
    """
    # 1. 优先检查环境变量 MYSQL_DSN
    mysql_dsn = os.getenv('MYSQL_DSN')
    if mysql_dsn:
        return mysql_dsn
    
    # 2. 尝试从 config/database.json 读取配置
    db_config_path = Path("config/database.json")
    if db_config_path.exists():
        try:
            with open(db_config_path, 'r', encoding='utf-8') as f:
                db_config = json.load(f)
            
            # 构建DSN
            username = db_config.get('username', db_config.get('user', 'root'))
            password = db_config.get('password', '111111')
            host = db_config.get('host', '127.0.0.1')
            port = db_config.get('port', 3306)
            database = db_config.get('database', 'Spidermind')
            
            dsn = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
            return dsn
            
        except Exception as e:
            print(f"⚠️  读取 config/database.json 失败: {e}")
    
    # 3. 兜底：默认配置
    return "mysql+pymysql://root:111111@127.0.0.1:3306/Spidermind"


# 保持向后兼容的Settings类（如果有pydantic_settings）
if HAS_PYDANTIC:
    class Settings(BaseSettings):
        """应用设置"""
        
        # 基础应用配置
        DEBUG: bool = True
        SECRET_KEY: str = "spidermind-secret-key-change-in-production"
        ENV: str = "dev"
        
        # 数据库配置 - 开发环境
        DB_USER: str = "root"
        DB_PASSWORD: str = "111111"
        DB_HOST: str = "127.0.0.1"
        DB_DATABASE: str = "Spidermind"
        DB_PORT: int = 3306
        DB_CHARSET: str = "utf8mb4"
        
        # 数据库配置 - 生产环境1
        PROD_DB_USER: str = "root"
        PROD_DB_PASSWORD: str = "111111"
        PROD_DB_HOST: str = "127.0.0.1"
        PROD_DB_DATABASE: str = "headhunter_django_db"
        PROD_DB_PORT: int = 3306
        PROD_DB_CHARSET: str = "utf8mb4"
        
        # 数据库配置 - 生产环境2
        PROD_DB_111_USER: str = "root"
        PROD_DB_111_PASSWORD: str = "Wy99581428"
        PROD_DB_111_HOST: str = "rm-bp1024v1uj11h6ysq7o.mysql.rds.aliyuncs.com"
        PROD_DB_111_DATABASE: str = "headhunter_django_db"
        PROD_DB_111_PORT: int = 3306
        PROD_DB_111_CHARSET: str = "utf8mb4"
        
        # QWEN API配置
        QWEN_API_KEY: str = "sk-151182825b3849ad88a9283b43ee11e4"
        QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        QWEN_MODEL: str = "qwen-plus"
        QWEN_MAX_TOKENS: int = 1000
        QWEN_TEMPERATURE: float = 0.1
        QWEN_PROVIDER: str = "qwen"
        
        # 统一数据库连接配置
        MYSQL_DSN: Optional[str] = None
        
        # GitHub Token配置
        GITHUB_TOKENS_JSON: Optional[str] = None
        GITHUB_TOKENS: Optional[str] = None
        GITHUB_PER_REQUEST_SLEEP_SECONDS: float = 0.8
        GITHUB_RATE_LIMIT_BACKOFF_SECONDS: int = 60
        GITHUB_API_BASE: str = "https://api.github.com"
        GITHUB_TOKENS_FILE: str = "config/tokens.github.json"
        GITHUB_RATE_LIMIT: int = 5000
        
        # OpenReview配置
        OPENREVIEW_API_BASE: str = "https://api.openreview.net"
        OPENREVIEW_RATE_LIMIT: int = 100
        
        # 解析配置
        USE_LLM_PARSE: bool = False
        LLM_API_KEY: Optional[str] = None
        LLM_MODEL: str = "gpt-3.5-turbo"
        
        # 爬虫配置
        REQUEST_TIMEOUT: int = 30
        MAX_CONCURRENT_REQUESTS: int = 10
        RETRY_ATTEMPTS: int = 3
        RETRY_DELAY: float = 1.0
        
        # 文件上传配置
        UPLOAD_PATH: str = "uploads/"
        MAX_FILE_SIZE: int = 50 * 1024 * 1024
        
        # 额外配置字段
        MAX_RETRIES: int = 3
        PLAYWRIGHT_TIMEOUT: int = 60000
        LOG_LEVEL: str = "INFO"
        LOG_FILE: str = "logs/spidermind.log"
        
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"
        
        def get_mysql_dsn(self) -> str:
            """统一的MySQL DSN获取方法（兼容方法）"""
            return get_mysql_dsn()
        
        def get_qwen_config(self) -> Dict[str, Any]:
            """获取QWEN API配置字典"""
            return {
                "api_key": self.QWEN_API_KEY,
                "base_url": self.QWEN_BASE_URL,
                "model": self.QWEN_MODEL,
                "max_tokens": self.QWEN_MAX_TOKENS,
                "temperature": self.QWEN_TEMPERATURE,
                "provider": self.QWEN_PROVIDER
            }

    # 全局设置实例
    settings = Settings()

else:
    # 简化的兼容类（无pydantic）
    class SimpleSettings:
        def __init__(self):
            self.DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
            self.ENV = os.getenv('ENV', 'dev')
            self.SECRET_KEY = os.getenv('SECRET_KEY', 'spidermind-secret-key-change-in-production')
        
        def get_mysql_dsn(self) -> str:
            return get_mysql_dsn()
        
        def get_qwen_config(self) -> Dict[str, Any]:
            return {
                "api_key": os.getenv('QWEN_API_KEY', 'sk-151182825b3849ad88a9283b43ee11e4'),
                "base_url": os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'),
                "model": os.getenv('QWEN_MODEL', 'qwen-plus'),
                "max_tokens": int(os.getenv('QWEN_MAX_TOKENS', '1000')),
                "temperature": float(os.getenv('QWEN_TEMPERATURE', '0.1')),
                "provider": os.getenv('QWEN_PROVIDER', 'qwen')
            }
    
    settings = SimpleSettings()