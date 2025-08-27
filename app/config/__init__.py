"""
配置桥 API 导出

对外统一接口，严格对齐旧语义:
- mysql_dsn(): 获取 MySQL DSN，优先级与旧版一致
- mask_dsn(): 脱敏 DSN 用于安全日志  
- qwen_cfg(): 获取 QWEN 配置，默认值与旧版一致
- github_tokens_cfg(): 获取 GitHub tokens，验证与旧版一致
- read_env(): 统一环境变量读取
"""

from .env_config import (
    mysql_dsn,
    mysql_params,
    mask_dsn, 
    qwen_cfg,
    github_tokens_cfg,
    read_env
)

__all__ = [
    'mysql_dsn',
    'mysql_params',
    'mask_dsn',
    'qwen_cfg', 
    'github_tokens_cfg',
    'read_env'
]