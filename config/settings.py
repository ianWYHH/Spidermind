"""
应用配置管理 - 统一配置入口
.env 优先，config/database.json 兜底

Author: Spidermind
"""
import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载 .env 文件
load_dotenv()


class Settings(BaseSettings):
    """应用设置"""
    
    # ================================
    # 基础应用配置
    # ================================
    DEBUG: bool = True
    SECRET_KEY: str = "spidermind-secret-key-change-in-production"
    ENV: str = "dev"  # 环境标识: dev, test, prod
    
    # ================================
    # 数据库配置 - 开发环境 (DATABASE_CONFIG)
    # ================================
    DB_USER: str = "root"
    DB_PASSWORD: str = "111111"
    DB_HOST: str = "127.0.0.1"
    DB_DATABASE: str = "Spidermind"  # 使用正确的数据库名
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
    # QWEN API配置 (QWEN_API_CONFIG)
    # ================================
    QWEN_API_KEY: str = "sk-151182825b3849ad88a9283b43ee11e4"
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    QWEN_MODEL: str = "qwen-plus"
    QWEN_MAX_TOKENS: int = 1000
    QWEN_TEMPERATURE: float = 0.1
    QWEN_PROVIDER: str = "qwen"
    
    # ================================
    # 统一数据库连接配置
    # ================================
    # 可以通过 .env 文件直接指定 MYSQL_DSN
    MYSQL_DSN: Optional[str] = None
    
    # ================================
    # GitHub Token配置 - 支持多种来源
    # ================================
    # 优先级1：JSON格式配置（完整配置）
    GITHUB_TOKENS_JSON: Optional[str] = None
    
    # 优先级2：单独的环境变量
    GITHUB_TOKENS: Optional[str] = None  # 逗号分隔的多个token
    GITHUB_PER_REQUEST_SLEEP_SECONDS: float = 0.8
    GITHUB_RATE_LIMIT_BACKOFF_SECONDS: int = 60
    GITHUB_API_BASE: str = "https://api.github.com"
    
    # 兜底：配置文件路径
    GITHUB_TOKENS_FILE: str = "config/tokens.github.json"
    GITHUB_RATE_LIMIT: int = 5000  # 每小时请求数（向后兼容）
    
    # OpenReview配置
    OPENREVIEW_API_BASE: str = "https://api.openreview.net"
    OPENREVIEW_RATE_LIMIT: int = 100  # 每分钟请求数
    
    # 解析配置
    USE_LLM_PARSE: bool = False  # 是否启用LLM解析
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-3.5-turbo"
    
    # 爬虫配置
    REQUEST_TIMEOUT: int = 30
    MAX_CONCURRENT_REQUESTS: int = 10
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: float = 1.0
    
    # 文件上传配置
    UPLOAD_PATH: str = "uploads/"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # 额外配置字段（可能来自.env文件）
    MAX_RETRIES: int = 3
    PLAYWRIGHT_TIMEOUT: int = 60000
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/spidermind.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略额外字段，避免验证错误
    
    def get_mysql_dsn(self) -> str:
        """
        统一的MySQL DSN获取方法
        优先级：.env中的MYSQL_DSN > config/database.json > 默认配置
        
        Returns:
            str: MySQL连接字符串
        """
        # 1. 优先检查 .env 中的 MYSQL_DSN
        if self.MYSQL_DSN:
            return self.MYSQL_DSN
        
        # 2. 尝试从 config/database.json 读取配置
        db_config_path = Path("config/database.json")
        if db_config_path.exists():
            try:
                with open(db_config_path, 'r', encoding='utf-8') as f:
                    db_config = json.load(f)
                
                # 构建DSN
                user = db_config.get('username', db_config.get('user', 'root'))
                password = db_config.get('password', '111111')
                host = db_config.get('host', '127.0.0.1')
                port = db_config.get('port', 3306)
                database = db_config.get('database', 'Spidermind')
                charset = db_config.get('charset', 'utf8mb4')
                
                dsn = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"
                return dsn
                
            except Exception as e:
                print(f"⚠️  读取 config/database.json 失败: {e}")
        
        # 3. 兜底：使用默认配置构建DSN
        dsn = f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_DATABASE}?charset={self.DB_CHARSET}"
        return dsn
    
    def get_database_url(self, config_name: str) -> str:
        """
        获取指定配置的数据库URL（保持向后兼容）
        
        Args:
            config_name: 配置名称
        
        Returns:
            str: MySQL连接字符串
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
        return f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}?charset={config['charset']}"
    
    def get_qwen_config(self) -> Dict[str, Any]:
        """
        获取QWEN API配置字典
        
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
    
    def get_github_tokens_config(self) -> Dict[str, Any]:
        """
        统一的GitHub Token配置获取方法
        优先级：.env中的GITHUB_TOKENS_JSON > .env中的单独变量 > config/tokens.github.json
        
        Returns:
            Dict[str, Any]: 标准化的GitHub配置
            
        Raises:
            ValueError: 如果没有找到任何有效的GitHub Token
        """
        # 默认配置
        default_config = {
            "api_base": self.GITHUB_API_BASE,
            "tokens": [],
            "per_request_sleep_seconds": self.GITHUB_PER_REQUEST_SLEEP_SECONDS,
            "rate_limit_backoff_seconds": self.GITHUB_RATE_LIMIT_BACKOFF_SECONDS
        }
        
        # 优先级1：检查 GITHUB_TOKENS_JSON 环境变量
        if self.GITHUB_TOKENS_JSON:
            try:
                json_config = json.loads(self.GITHUB_TOKENS_JSON)
                return self._parse_github_json_config(json_config, default_config)
            except json.JSONDecodeError as e:
                print(f"⚠️  解析 GITHUB_TOKENS_JSON 失败: {e}")
        
        # 优先级2：检查单独的环境变量
        if self.GITHUB_TOKENS:
            tokens = [token.strip() for token in self.GITHUB_TOKENS.split(',') if token.strip()]
            if tokens:
                config = default_config.copy()
                config["tokens"] = [
                    {
                        "value": token,
                        "status": "active",
                        "last_used_at": None,
                        "remaining": 5000,
                        "reset_time": None,
                        "cooldown_until": None
                    }
                    for token in tokens
                ]
                return config
        
        # 优先级3：兜底读取配置文件
        config_file_path = Path(self.GITHUB_TOKENS_FILE)
        if config_file_path.exists():
            try:
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                return self._parse_github_file_config(file_config, default_config)
            except Exception as e:
                print(f"⚠️  读取 {self.GITHUB_TOKENS_FILE} 失败: {e}")
        
        # 没有找到任何token配置
        raise ValueError(
            "❌ 未找到GitHub Token配置！请设置以下任一配置:\n"
            "1. 环境变量 GITHUB_TOKENS_JSON（JSON格式）\n"
            "2. 环境变量 GITHUB_TOKENS（逗号分隔）\n"
            "3. 配置文件 config/tokens.github.json\n\n"
            "示例:\n"
            "  GITHUB_TOKENS=ghp_token1,ghp_token2\n"
            "  或\n"
            "  GITHUB_TOKENS_JSON='{\"tokens\":[{\"value\":\"ghp_token1\"}]}'"
        )
    
    def _parse_github_json_config(self, json_config: Dict[str, Any], default_config: Dict[str, Any]) -> Dict[str, Any]:
        """解析JSON格式的GitHub配置"""
        config = default_config.copy()
        
        # 更新API base
        if "api_base" in json_config:
            config["api_base"] = json_config["api_base"]
        
        # 更新sleep配置
        if "per_request_sleep_seconds" in json_config:
            config["per_request_sleep_seconds"] = float(json_config["per_request_sleep_seconds"])
        
        # 更新backoff配置
        if "rate_limit_backoff_seconds" in json_config:
            config["rate_limit_backoff_seconds"] = int(json_config["rate_limit_backoff_seconds"])
        
        # 解析tokens
        if "tokens" in json_config:
            tokens = json_config["tokens"]
            if isinstance(tokens, list):
                config["tokens"] = [
                    self._normalize_token(token) for token in tokens
                ]
        
        return config
    
    def _parse_github_file_config(self, file_config: Any, default_config: Dict[str, Any]) -> Dict[str, Any]:
        """解析文件格式的GitHub配置（支持旧格式和新格式）"""
        config = default_config.copy()
        
        # 旧格式：简单数组 ["ghp_xxx1", "ghp_xxx2"]
        if isinstance(file_config, list):
            config["tokens"] = [
                {
                    "value": token,
                    "status": "active",
                    "last_used_at": None,
                    "remaining": 5000,
                    "reset_time": None,
                    "cooldown_until": None
                }
                for token in file_config if isinstance(token, str)
            ]
            return config
        
        # 新格式：对象格式
        if isinstance(file_config, dict):
            # 更新配置参数
            if "per_request_sleep_seconds" in file_config:
                config["per_request_sleep_seconds"] = float(file_config["per_request_sleep_seconds"])
            
            if "rate_limit_backoff_seconds" in file_config:
                config["rate_limit_backoff_seconds"] = int(file_config["rate_limit_backoff_seconds"])
            
            # 兼容旧字段名
            if "sleep_between_requests" in file_config:
                config["per_request_sleep_seconds"] = float(file_config["sleep_between_requests"])
            
            # 解析tokens
            if "tokens" in file_config:
                tokens = file_config["tokens"]
                if isinstance(tokens, list):
                    config["tokens"] = [
                        self._normalize_token(token) for token in tokens
                    ]
        
        return config
    
    def _normalize_token(self, token: Any) -> Dict[str, Any]:
        """标准化token对象格式"""
        # 如果是字符串，转换为标准对象
        if isinstance(token, str):
            return {
                "value": token,
                "status": "active",
                "last_used_at": None,
                "remaining": 5000,
                "reset_time": None,
                "cooldown_until": None
            }
        
        # 如果是对象，补全缺失字段
        if isinstance(token, dict):
            normalized = {
                "value": token.get("value", token.get("token", "")),
                "status": token.get("status", "active"),
                "last_used_at": token.get("last_used_at"),
                "remaining": token.get("remaining", 5000),
                "reset_time": token.get("reset_time"),
                "cooldown_until": token.get("cooldown_until")
            }
            # 兼容旧字段名
            if "active" in token:
                normalized["status"] = "active" if token["active"] else "inactive"
            
            return normalized
        
        # 无效格式，返回默认
        return {
            "value": str(token),
            "status": "active",
            "last_used_at": None,
            "remaining": 5000,
            "reset_time": None,
            "cooldown_until": None
        }


# 全局设置实例
settings = Settings()