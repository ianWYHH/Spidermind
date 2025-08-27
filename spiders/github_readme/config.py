"""
GitHub README爬虫配置模块
"""

# 默认配置
DEFAULT_CONFIG = {
    # 仓库存在性检查
    'validate_repository_existence': True,
    
    # 强制仓库检查超时时间（秒）
    'repository_check_timeout': 5,
    
    # 存在性检查间隔（秒）
    'existence_check_delay': 0.2,
    
    # 缓存过期时间（秒），0表示永不过期
    'cache_expiry_time': 3600,  # 1小时
    
    # 最大普通仓库数量
    'max_normal_repos': 50,
    
    # 是否启用仓库存在性缓存
    'enable_repository_cache': True,
    
    # 重试配置
    'max_retries': 2,
    'retry_delay': 1.0,
    
    # 并发配置
    'max_threads': 2,
    
    # 请求配置
    'request_timeout': 10,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}


def get_config():
    """获取当前配置"""
    return DEFAULT_CONFIG.copy()


def update_config(updates: dict):
    """更新配置"""
    DEFAULT_CONFIG.update(updates)


def get_config_value(key: str, default=None):
    """获取配置值"""
    return DEFAULT_CONFIG.get(key, default)