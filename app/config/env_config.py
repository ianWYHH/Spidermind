"""
配置桥 - 严格对齐旧语义的配置管理

保持与旧项目完全一致的行为:
- .env 自动加载 (env_file=".env")
- MySQL DSN 优先级: MYSQL_DSN > config/database.json > 默认DSN
- GitHub tokens 验证与默认值同旧版
- QWEN 配置读取与默认值同旧版
- 严禁打印敏感信息，仅允许脱敏输出

验收自检:
1. MYSQL_DSN 环境变量 -> 直接返回
2. config/database.json 解析 -> 拼装DSN (支持username/user字段)
3. 兜底默认DSN: mysql+pymysql://root:111111@127.0.0.1:3306/Spidermind
4. mask_dsn() 正确脱敏密码段
5. GitHub tokens 缺文件/缺键报错信息与旧版一致
6. QWEN 配置默认值与旧版一致
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse, unquote

# 安全尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    # 计算项目根目录：当前文件向上2级
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"
    load_dotenv(env_path)  # 加载根目录下的 .env 文件
except ImportError:
    # 没有 python-dotenv 也能正常工作
    pass
except Exception:
    # .env 文件不存在或加载失败也不报错
    pass


def _build_dsn_from_json() -> Optional[str]:
    """
    从 config/database.json 构建 DSN (内部函数)
    
    兼容 username/user 字段，默认值与旧版完全一致
    """
    db_config_path = Path("config/database.json")
    if not db_config_path.exists():
        return None
    
    try:
        with open(db_config_path, 'r', encoding='utf-8') as f:
            db_config = json.load(f)
        
        # 与旧版逻辑完全一致: username 优先，然后 user，最后默认值
        username = db_config.get('username', db_config.get('user', 'root'))
        password = db_config.get('password', '111111')
        host = db_config.get('host', '127.0.0.1')
        port = db_config.get('port', 3306)
        database = db_config.get('database', 'Spidermind')
        
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        
    except Exception:
        # 与旧版行为一致：JSON 解析失败时返回 None，不抛异常
        return None


def mysql_dsn() -> str:
    """
    获取 MySQL DSN，优先级与旧版完全一致
    
    ⚠️ 注意：不要在日志中输出明文口令，使用 mask_dsn() 进行脱敏
    
    优先级:
    1. 环境变量 MYSQL_DSN 
    2. config/database.json 拼装
    3. 默认 DSN (与旧版字面量一致)
    
    Returns:
        str: MySQL 连接字符串 "mysql+pymysql://..."
    """
    # 1. 优先检查环境变量 MYSQL_DSN (与旧版行为一致)
    mysql_dsn_env = os.getenv('MYSQL_DSN')
    if mysql_dsn_env:
        return mysql_dsn_env
    
    # 2. 尝试从 config/database.json 读取配置 (与旧版逻辑一致)
    dsn_from_json = _build_dsn_from_json()
    if dsn_from_json:
        return dsn_from_json
    
    # 3. 兜底：默认配置 (与旧版字面量完全一致)
    return "mysql+pymysql://root:111111@127.0.0.1:3306/Spidermind"


def mysql_params() -> Dict[str, Any]:
    """
    返回 MySQL 连接参数字典 {host, port, user, password, database, charset}
    
    ⚠️ 注意：不要在日志中输出明文口令，返回的密码参数包含敏感信息
    
    优先级:
    1. 解析环境变量 MYSQL_DSN
    2. 读取 config/database.json
    3. 返回默认参数
    
    支持对 URL 编码的密码解码（如 %40 -> @）
    
    Returns:
        dict: 包含 host, port, user, password, database, charset 的连接参数
    """
    # 1. 优先尝试解析环境变量 MYSQL_DSN
    mysql_dsn_env = os.getenv('MYSQL_DSN')
    if mysql_dsn_env:
        try:
            parsed = urlparse(mysql_dsn_env)
            
            # 解析主机和端口
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port or 3306
            
            # 解析用户名和密码，支持URL解码
            user = unquote(parsed.username) if parsed.username else 'root'
            password = unquote(parsed.password) if parsed.password else '111111'
            
            # 解析数据库名
            database = parsed.path.lstrip('/') if parsed.path else 'Spidermind'
            
            # 解析charset参数
            charset = 'utf8mb4'
            if parsed.query:
                query_params = dict(param.split('=') for param in parsed.query.split('&') if '=' in param)
                charset = query_params.get('charset', 'utf8mb4')
            
            return {
                'host': host,
                'port': port,
                'user': user,
                'password': password,
                'database': database,
                'charset': charset
            }
            
        except Exception:
            # DSN 解析失败，继续尝试其他方式
            pass
    
    # 2. 尝试从 config/database.json 读取配置
    db_config_path = Path("config/database.json")
    if db_config_path.exists():
        try:
            with open(db_config_path, 'r', encoding='utf-8') as f:
                db_config = json.load(f)
            
            return {
                'host': db_config.get('host', '127.0.0.1'),
                'port': int(db_config.get('port', 3306)),
                'user': db_config.get('username', db_config.get('user', 'root')),
                'password': db_config.get('password', '111111'),
                'database': db_config.get('database', 'Spidermind'),
                'charset': db_config.get('charset', 'utf8mb4')
            }
            
        except Exception:
            # JSON 解析失败，使用默认配置
            pass
    
    # 3. 兜底：默认配置 (与旧版一致)
    return {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'password': '111111',
        'database': 'Spidermind',
        'charset': 'utf8mb4'
    }


def mask_dsn(dsn: str) -> str:
    """
    脱敏 DSN 中的密码，用于安全日志输出
    
    Args:
        dsn: 完整的数据库连接字符串
        
    Returns:
        str: 脱敏后的 DSN，密码部分用 *** 替代
        
    Example:
        mysql+pymysql://user:password@host:port/db -> mysql+pymysql://user:***@host:port/db
    """
    if '://' not in dsn:
        return dsn
    
    try:
        # 分离协议和连接部分
        protocol, connection_part = dsn.split('://', 1)
        
        # 查找 @ 符号位置
        if '@' not in connection_part:
            return dsn
        
        user_pass_part, host_db_part = connection_part.split('@', 1)
        
        # 处理用户名:密码部分
        if ':' in user_pass_part:
            username, _ = user_pass_part.split(':', 1)
            masked_user_pass = f"{username}:***"
        else:
            masked_user_pass = user_pass_part
        
        return f"{protocol}://{masked_user_pass}@{host_db_part}"
        
    except Exception:
        # 解析失败时返回安全的通用标识
        return "mysql://***:***@***:****/***"


def qwen_cfg() -> Dict[str, Any]:
    """
    获取 QWEN 配置，从环境变量读取，默认值与旧版完全一致
    
    Returns:
        dict: QWEN 配置字典，包含所有必需字段
    """
    return {
        "api_key": os.getenv('QWEN_API_KEY', 'sk-151182825b3849ad88a9283b43ee11e4'),
        "base_url": os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'),
        "model": os.getenv('QWEN_MODEL', 'qwen-plus'),
        "max_tokens": int(os.getenv('QWEN_MAX_TOKENS', '1000')),
        "temperature": float(os.getenv('QWEN_TEMPERATURE', '0.1')),
        "provider": os.getenv('QWEN_PROVIDER', 'qwen')
    }


def github_tokens_cfg() -> Dict[str, Any]:
    """
    获取 GitHub tokens 配置，验证规则与错误信息与旧版完全一致
    
    Returns:
        dict: GitHub tokens 配置，包含 tokens 列表和所有默认键
        
    Raises:
        ValueError: 配置文件问题，错误信息风格与旧版一致
    """
    tokens_file = Path("config/tokens.github.json")
    
    # 文件不存在检查 (错误信息与旧版一致)
    if not tokens_file.exists():
        raise ValueError(f"GitHub令牌文件不存在: {tokens_file}")
    
    try:
        with open(tokens_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        # JSON 格式错误 (错误信息与旧版一致)
        raise ValueError(f"GitHub令牌文件JSON格式错误: {e}")
    except Exception as e:
        # 其他读取错误 (错误信息与旧版一致)
        raise ValueError(f"读取GitHub令牌文件失败: {e}")
    
    # 验证 tokens 字段存在 (错误信息与旧版一致)
    if 'tokens' not in config:
        raise ValueError("配置文件中缺少'tokens'字段")
    
    # 验证 tokens 为非空列表 (错误信息与旧版一致)
    if not isinstance(config['tokens'], list) or len(config['tokens']) == 0:
        raise ValueError("'tokens'必须是非空列表")
    
    # 设置默认值 (与旧版完全一致)
    return {
        "tokens": config['tokens'],
        "api_base": config.get('api_base', 'https://api.github.com'),
        "per_request_sleep_seconds": config.get('per_request_sleep_seconds', 0.1),
        "rate_limit_backoff_seconds": config.get('rate_limit_backoff_seconds', 2.0),
        "retry_limit": config.get('retry_limit', 3),
        "retry_delay_seconds": config.get('retry_delay_seconds', 1.0),
        "max_concurrent_requests": config.get('max_concurrent_requests', 10)
    }


def read_env(key: str, default: Any = None) -> Any:
    """
    统一的环境变量读取接口
    
    Args:
        key: 环境变量名
        default: 默认值
        
    Returns:
        Any: 环境变量值或默认值
    """
    return os.getenv(key, default)