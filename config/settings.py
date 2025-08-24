"""
应用配置管理

Author: Spidermind
"""
import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用设置"""
    
    # ================================
    # 基础应用配置
    # ================================
    DEBUG: bool = True
    SECRET_KEY: str = "spidermind-secret-key-change-in-production"
    
    # ================================
    # 数据库配置 - 开发环境 (DATABASE_CONFIG)
    # ================================
    DB_USER: str = "root"
    DB_PASSWORD: str = "111111"
    DB_HOST: str = "127.0.0.1"
    DB_DATABASE: str = "pcjc_db"
    DB_PORT: int = 3306
    DB_CHARSET: str = "utf8mb4"
    
    # ================================
    # 数据库配置 - 生产环境1 (PRODUCTION_DATABASE_CONFIG)
    # ================================
    PROD_DB_USER: str = "root"
    PROD_DB_PASSWORD: str = "111111"
    PROD_DB_HOST: str = "127.0.0.1"
    PROD_DB_DATABASE: str = "headhunter_django_db"
    PROD_DB_PORT: int = 3306
    PROD_DB_CHARSET: str = "utf8mb4"
    
    # ================================
    # 数据库配置 - 生产环境2 (PRODUCTION_DATABASE_CONFIG_111)
    # ================================
    PROD_DB_111_USER: str = "root"
    PROD_DB_111_PASSWORD: str = "Wy99581428"
    PROD_DB_111_HOST: str = "rm-bp1024v1uj11h6ysq7o.mysql.rds.aliyuncs.com"
    PROD_DB_111_DATABASE: str = "headhunter_django_db"
    PROD_DB_111_PORT: int = 3306
    PROD_DB_111_CHARSET: str = "utf8mb4"
    
    # ================================
    # QWEN API 配置
    # ================================
    QWEN_API_KEY: str = "sk-151182825b3849ad88a9283b43ee11e4"
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    QWEN_MODEL: str = "qwen-plus"
    QWEN_MAX_TOKENS: int = 1000
    QWEN_TEMPERATURE: float = 0.1
    QWEN_PROVIDER: str = "qwen"
    
    # ================================
    # 兼容性配置 - 保持原有配置
    # ================================
    MYSQL_DSN: str = "mysql+pymysql://root:111111@127.0.0.1:3306/pcjc_db"
    
    # GitHub API配置
    GITHUB_TOKENS_FILE: str = "config/tokens.github.json"
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_RATE_LIMIT: int = 5000  # 每小时请求数
    
    # OpenReview配置
    OPENREVIEW_API_BASE: str = "https://api.openreview.net"
    OPENREVIEW_RATE_LIMIT: int = 100  # 每分钟请求数
    
    # 解析配置
    USE_LLM_PARSE: bool = False  # 是否启用LLM解析
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-3.5-turbo"
    
    # 爬虫配置
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    PLAYWRIGHT_TIMEOUT: int = 60000  # 毫秒
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/spidermind.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def get_database_url(self, config_name: str) -> str:
        """
        动态拼接 MySQL DSN 用于 dev/prod 切换
        
        Args:
            config_name: 配置名称，支持：
                        - "DATABASE_CONFIG" (开发环境)
                        - "PRODUCTION_DATABASE_CONFIG" (生产环境1)
                        - "PRODUCTION_DATABASE_CONFIG_111" (生产环境2)
        
        Returns:
            str: 完整的 MySQL DSN 连接字符串
        
        Raises:
            ValueError: 当配置名称不支持时
        """
        config_mapping = {
            "DATABASE_CONFIG": {
                "user": self.DB_USER,
                "password": self.DB_PASSWORD,
                "host": self.DB_HOST,
                "database": self.DB_DATABASE,
                "port": self.DB_PORT,
                "charset": self.DB_CHARSET
            },
            "PRODUCTION_DATABASE_CONFIG": {
                "user": self.PROD_DB_USER,
                "password": self.PROD_DB_PASSWORD,
                "host": self.PROD_DB_HOST,
                "database": self.PROD_DB_DATABASE,
                "port": self.PROD_DB_PORT,
                "charset": self.PROD_DB_CHARSET
            },
            "PRODUCTION_DATABASE_CONFIG_111": {
                "user": self.PROD_DB_111_USER,
                "password": self.PROD_DB_111_PASSWORD,
                "host": self.PROD_DB_111_HOST,
                "database": self.PROD_DB_111_DATABASE,
                "port": self.PROD_DB_111_PORT,
                "charset": self.PROD_DB_111_CHARSET
            }
        }
        
        if config_name not in config_mapping:
            raise ValueError(f"不支持的配置名称: {config_name}. 支持的配置: {list(config_mapping.keys())}")
        
        config = config_mapping[config_name]
        
        # 拼接 MySQL DSN
        dsn = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}?charset={config['charset']}"
        
        return dsn
    
    def get_qwen_config(self) -> Dict[str, Any]:
        """
        返回完整的 QWEN_API_CONFIG 字典
        
        Returns:
            Dict[str, Any]: QWEN API 配置字典
        """
        return {
            "api_key": self.QWEN_API_KEY,
            "base_url": self.QWEN_BASE_URL,
            "model": self.QWEN_MODEL,
            "max_tokens": self.QWEN_MAX_TOKENS,
            "temperature": self.QWEN_TEMPERATURE,
            "provider": self.QWEN_PROVIDER
        }
    
    def get_database_config(self, config_name: str) -> Dict[str, Any]:
        """
        获取指定的数据库配置字典
        
        Args:
            config_name: 配置名称
        
        Returns:
            Dict[str, Any]: 数据库配置字典
        """
        config_mapping = {
            "DATABASE_CONFIG": {
                "user": self.DB_USER,
                "password": self.DB_PASSWORD,
                "host": self.DB_HOST,
                "database": self.DB_DATABASE,
                "port": self.DB_PORT,
                "charset": self.DB_CHARSET
            },
            "PRODUCTION_DATABASE_CONFIG": {
                "user": self.PROD_DB_USER,
                "password": self.PROD_DB_PASSWORD,
                "host": self.PROD_DB_HOST,
                "database": self.PROD_DB_DATABASE,
                "port": self.PROD_DB_PORT,
                "charset": self.PROD_DB_CHARSET
            },
            "PRODUCTION_DATABASE_CONFIG_111": {
                "user": self.PROD_DB_111_USER,
                "password": self.PROD_DB_111_PASSWORD,
                "host": self.PROD_DB_111_HOST,
                "database": self.PROD_DB_111_DATABASE,
                "port": self.PROD_DB_111_PORT,
                "charset": self.PROD_DB_111_CHARSET
            }
        }
        
        if config_name not in config_mapping:
            raise ValueError(f"不支持的配置名称: {config_name}. 支持的配置: {list(config_mapping.keys())}")
        
        return config_mapping[config_name]


# 全局设置实例
settings = Settings()