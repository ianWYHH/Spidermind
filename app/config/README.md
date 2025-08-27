# 配置桥使用说明

## 概述

本配置桥**严格对齐旧项目语义**，直接使用现有 `.env` 与配置文件，**无需修改任何配置**。优先级、默认值、错误信息完全与旧项目一致。

## 核心原则

- **不修改现有配置文件**：继续使用 `.env`、`config/database.json`、`config/tokens.github.json`
- **保持旧语义**：优先级、默认值、错误信息与旧项目完全一致
- **安全要求**：严禁在日志中打印敏感信息，使用 `mask_dsn()` 脱敏

## 配置优先级

### MySQL DSN 获取
严格按照旧项目优先级：
1. **环境变量 `MYSQL_DSN`** (最高优先级)
2. **`config/database.json`** 文件解析
3. **默认 DSN**: `mysql+pymysql://root:111111@127.0.0.1:3306/Spidermind`

### .env 文件加载
- 如果安装了 `python-dotenv`，自动加载 `.env` 文件 (等价于 `pydantic` 的 `env_file=".env"`)
- 未安装 `python-dotenv` 也能正常工作，只是需要手动设置环境变量

## API 使用

```python
from app.config import mysql_dsn, mask_dsn, qwen_cfg, github_tokens_cfg, read_env

# 1. 获取 MySQL DSN
dsn = mysql_dsn()
print(f"数据库连接: {mask_dsn(dsn)}")  # 安全日志输出

# 2. 获取 QWEN 配置
qwen_config = qwen_cfg()
print(f"QWEN 模型: {qwen_config['model']}")

# 3. 获取 GitHub tokens 配置  
try:
    github_config = github_tokens_cfg()
    print(f"GitHub tokens 数量: {len(github_config['tokens'])}")
except ValueError as e:
    print(f"GitHub 配置错误: {e}")

# 4. 读取环境变量
debug_mode = read_env('DEBUG', 'False')
```

## 配置文件格式

### 1. `.env` 文件 (可选)
```bash
# MySQL 连接 (优先级最高)
MYSQL_DSN=mysql+pymysql://user:pass@host:port/db

# QWEN API 配置
QWEN_API_KEY=sk-your-api-key
QWEN_MODEL=qwen-plus
QWEN_TEMPERATURE=0.1

# 其他配置...
DEBUG=True
```

### 2. `config/database.json` (MySQL DSN 备选)
```json
{
  "username": "root",     // 或使用 "user" 字段
  "password": "111111", 
  "host": "127.0.0.1",
  "port": 3306,
  "database": "Spidermind"
}
```

### 3. `config/tokens.github.json` (必需)
```json
{
  "tokens": [
    {
      "value": "github_pat_xxx",
      "user": "user1", 
      "status": "active"
    }
  ],
  "api_base": "https://api.github.com",
  "per_request_sleep_seconds": 0.1,
  "rate_limit_backoff_seconds": 2.0,
  "retry_limit": 3,
  "retry_delay_seconds": 1.0,
  "max_concurrent_requests": 10
}
```

## 默认值一览

### QWEN 配置默认值 (与旧版一致)
```python
{
    "api_key": "sk-151182825b3849ad88a9283b43ee11e4",
    "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation", 
    "model": "qwen-plus",
    "max_tokens": 1000,
    "temperature": 0.1,
    "provider": "qwen"
}
```

### GitHub Tokens 默认值 (与旧版一致)
```python
{
    "api_base": "https://api.github.com",
    "per_request_sleep_seconds": 0.1,
    "rate_limit_backoff_seconds": 2.0, 
    "retry_limit": 3,
    "retry_delay_seconds": 1.0,
    "max_concurrent_requests": 10
}
```

## 安全使用

### 日志脱敏
**严禁**在日志中打印完整 DSN 或 tokens，必须使用脱敏函数：

```python
from app.config import mysql_dsn, mask_dsn

dsn = mysql_dsn()

# ❌ 错误：暴露敏感信息
print(f"连接数据库: {dsn}")

# ✅ 正确：脱敏输出  
print(f"连接数据库: {mask_dsn(dsn)}")
# 输出: mysql+pymysql://root:***@127.0.0.1:3306/Spidermind
```

### 配置文件安全
- **严禁**将 `.env` 和 `config/*.json` 提交到版本控制
- 生产环境使用环境变量或安全的密钥管理
- 开发环境确保配置文件权限正确

## 验收自检

### 1. MySQL DSN 优先级测试
```bash
# 测试环境变量优先级
export MYSQL_DSN="mysql+pymysql://test:test@localhost/test"
python -c "from app.config import mysql_dsn; print(mysql_dsn())"
# 应输出: mysql+pymysql://test:test@localhost/test

# 清除环境变量，测试 JSON 文件
unset MYSQL_DSN
python -c "from app.config import mysql_dsn, mask_dsn; print(mask_dsn(mysql_dsn()))"
# 应输出脱敏后的 DSN
```

### 2. GitHub Tokens 验证
```python
# 正常情况
from app.config import github_tokens_cfg
config = github_tokens_cfg()
assert 'tokens' in config
assert len(config['tokens']) > 0

# 错误情况测试 (临时重命名文件)
mv config/tokens.github.json config/tokens.github.json.bak
# 应抛出: ValueError: GitHub令牌文件不存在: config/tokens.github.json
```

### 3. 脱敏功能测试
```python
from app.config import mask_dsn

# 测试各种 DSN 格式
test_cases = [
    "mysql+pymysql://root:password@host:3306/db",
    "mysql://user:secret@localhost/test",
    "invalid-dsn"
]

for dsn in test_cases:
    masked = mask_dsn(dsn)
    assert 'password' not in masked
    assert 'secret' not in masked
    print(f"{dsn} -> {masked}")
```

## 错误处理

所有错误信息**完全对齐旧版**，便于迁移排障：

- `GitHub令牌文件不存在: config/tokens.github.json`
- `GitHub令牌文件JSON格式错误: [详细错误]`
- `配置文件中缺少'tokens'字段`
- `'tokens'必须是非空列表`

## 迁移指南

从旧配置迁移到新配置桥：

```python
# 旧用法 (保持兼容)
from config.settings import settings
dsn = settings.get_mysql_dsn()

# 新用法 (推荐)
from app.config import mysql_dsn, mask_dsn
dsn = mysql_dsn()
print(f"连接: {mask_dsn(dsn)}")  # 安全日志
```

配置文件无需任何修改，行为完全一致。