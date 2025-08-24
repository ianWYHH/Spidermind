# Spidermind - 学术人才信息爬虫系统

## 📖 项目概述

Spidermind 是一个专为学术人才信息收集设计的智能爬虫系统，支持从 GitHub、OpenReview、个人主页等多个来源自动抓取和整理学者信息。

### 🎯 核心功能

- **多源爬虫**：GitHub、OpenReview、个人主页三大数据源
- **智能解析**：基于规则+LLM的标签提取和信息解析
- **完整度评分**：多维度评估候选人信息完整性
- **可视化仪表盘**：实时统计、进度监控、覆盖率分析
- **人工补录**：支持手动添加和修正候选人信息

### 🏗️ 系统架构

```
Spidermind/
├── main.py                 # FastAPI应用入口
├── requirements.txt        # 项目依赖
├── config/                 # 配置文件
│   ├── settings.py        # 应用配置
│   └── database.json      # 数据库配置
├── models/                 # 数据模型
│   ├── base.py            # 数据库基础配置
│   ├── candidate.py       # 候选人相关模型
│   └── crawl.py           # 爬虫任务模型
├── services/               # 业务逻辑层
│   ├── github_service.py  # GitHub爬虫服务
│   ├── openreview_service.py  # OpenReview爬虫服务
│   ├── homepage_service.py    # 主页爬虫服务
│   ├── parse_service.py   # 解析服务
│   ├── stats_service.py   # 统计服务
│   └── error_handler.py   # 统一异常处理
├── controllers/            # 控制器层
│   ├── dashboard.py       # 仪表盘控制器
│   ├── candidates.py      # 候选人管理
│   ├── parse_llm.py       # 解析管理
│   └── logs.py            # 日志管理
├── crawlers/              # 爬虫客户端
├── extractors/            # 数据提取器
└── templates/             # 前端模板
    ├── dashboard/         # 仪表盘页面
    ├── candidates/        # 候选人页面
    └── parse/             # 解析页面
```

## 🚀 快速开始

### 环境要求

- **操作系统**：Linux/Windows/macOS
- **Python**：3.9+
- **数据库**：MySQL 8.0+
- **内存**：建议 4GB+
- **磁盘**：建议 10GB+ 可用空间

### 1. 环境准备

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev default-libmysqlclient-dev

# CentOS/RHEL
sudo yum install -y python3-pip python3-devel mysql-devel

# Windows
# 请安装 Python 3.9+ 和 Visual Studio Build Tools
```

### 2. 项目部署

```bash
# 1. 克隆项目
git clone <repository-url>
cd Spidermind

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装Playwright（仅在需要JavaScript渲染时）
pip install playwright
python -m playwright install --with-deps
```

### 3. 数据库配置

```bash
# 1. 创建MySQL数据库
mysql -u root -p
CREATE DATABASE Spidermind CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'spidermind'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON Spidermind.* TO 'spidermind'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 4. 应用配置

创建 `config/database.json`：

```json
{
  "databases": {
    "default": {
      "host": "localhost",
      "port": 3306,
      "username": "spidermind",
      "password": "your_password",
      "database": "Spidermind"
    }
  },
  "qwen_api": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "your_qwen_api_key",
    "model": "qwen-turbo"
  }
}
```

创建 `config/tokens.github.json`（可选）：

```json
{
  "tokens": [
    "ghp_your_github_token_1",
    "ghp_your_github_token_2"
  ]
}
```

### 5. 启动应用

```bash
# 开发模式
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000

# 后台运行
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
```

### 6. 访问系统

打开浏览器访问：`http://localhost:8000`

## 🎮 使用指南

### 仪表盘功能

1. **访问首页**：`http://localhost:8000`
2. **查看统计**：候选人数量、解析进度、字段覆盖率
3. **启动爬虫**：点击对应按钮启动GitHub/OpenReview/Homepage爬虫
4. **监控进度**：实时查看爬虫运行状态和日志

### 爬虫操作流程

#### 手动插入示例任务

```sql
-- 插入GitHub用户任务
INSERT INTO crawl_tasks (source, type, github_login, status) VALUES 
('github', 'profile', 'torvalds', 'pending'),
('github', 'profile', 'gvanrossum', 'pending');

-- 插入OpenReview论文任务
INSERT INTO crawl_tasks (source, type, url, status) VALUES 
('openreview', 'forum', 'https://openreview.net/forum?id=example', 'pending');

-- 插入主页任务
INSERT INTO crawl_tasks (source, type, url, status) VALUES 
('homepage', 'homepage', 'https://scholar.example.com', 'pending');
```

#### 运行爬虫流程

1. **启动GitHub爬虫**
   ```bash
   curl -X POST "http://localhost:8000/crawl/github/start" \
        -H "Content-Type: application/json" \
        -d '{"recent_n": 5, "star_n": 5, "follow_depth": 1}'
   ```

2. **启动OpenReview爬虫**
   ```bash
   curl -X POST "http://localhost:8000/crawl/openreview/start" \
        -H "Content-Type: application/json" \
        -d '{"batch_size": 10}'
   ```

3. **启动主页爬虫**
   ```bash
   curl -X POST "http://localhost:8000/crawl/homepage/start" \
        -H "Content-Type: application/json" \
        -d '{"batch_size": 5}'
   ```

### 数据流程示例

1. **GitHub爬取** → 获取用户信息、仓库列表 → 从README提取邮箱/主页
2. **主页发现** → 自动创建homepage任务 → 通用爬虫处理
3. **内容解析** → 规则提取+LLM增强 → 更新标签字段
4. **人工补录** → 候选人详情页 → 手动添加遗漏信息

### API端点列表

#### 爬虫管理
- `POST /crawl/github/start` - 启动GitHub爬虫
- `POST /crawl/openreview/start` - 启动OpenReview爬虫  
- `POST /crawl/homepage/start` - 启动主页爬虫
- `GET /crawl/{source}/status` - 查看爬虫状态

#### 解析管理
- `POST /parse/start` - 启动智能解析
- `GET /parse/review` - 解析结果审查
- `POST /parse/reset` - 重置解析状态

#### 候选人管理
- `GET /candidates` - 候选人列表
- `GET /candidates/{id}` - 候选人详情
- `POST /candidates/{id}/add_email` - 添加邮箱
- `POST /candidates/{id}/add_homepage` - 添加主页

#### 统计分析
- `GET /dashboard/stats` - 完整统计数据
- `GET /dashboard/coverage` - 字段覆盖率
- `GET /dashboard/health` - 系统健康状态

## 🔧 配置说明

### 数据库配置

系统使用MySQL 8.0作为主数据库，支持以下配置项：

```json
{
  "databases": {
    "default": {
      "host": "localhost",        // 数据库主机
      "port": 3306,              // 端口
      "username": "spidermind",   // 用户名
      "password": "password",     // 密码
      "database": "Spidermind"    // 数据库名
    }
  }
}
```

### GitHub Token配置

为避免API限制，建议配置多个GitHub Token：

```json
{
  "tokens": [
    "ghp_token_1",
    "ghp_token_2", 
    "ghp_token_3"
  ]
}
```

### LLM API配置

支持通义千问API进行智能标签提取：

```json
{
  "qwen_api": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-your-api-key",
    "model": "qwen-turbo"
  }
}
```

## 🐛 常见问题排查

### 数据库连接问题

**错误**: `Database connection failed`

**解决方案**:
```bash
# 1. 检查MySQL服务状态
sudo systemctl status mysql

# 2. 检查数据库配置
cat config/database.json

# 3. 测试连接
mysql -h localhost -u spidermind -p Spidermind

# 4. 检查防火墙
sudo ufw status
```

### 端口占用问题

**错误**: `Address already in use`

**解决方案**:
```bash
# 查看端口占用
sudo netstat -tlnp | grep :8000

# 终止进程
sudo kill -9 <PID>

# 或使用其他端口
uvicorn main:app --port 8001
```

### 权限问题

**错误**: `Permission denied`

**解决方案**:
```bash
# 检查文件权限
ls -la

# 修改权限
chmod +x main.py
sudo chown -R $USER:$USER /path/to/Spidermind

# 检查数据库权限
SHOW GRANTS FOR 'spidermind'@'localhost';
```

### Playwright安装问题

**错误**: `Playwright browsers not found`

**解决方案**:
```bash
# 重新安装Playwright
pip uninstall playwright
pip install playwright
python -m playwright install --with-deps

# 或仅安装Chromium
python -m playwright install chromium
```

### 内存不足问题

**错误**: `Memory error` 或系统卡顿

**解决方案**:
```bash
# 检查内存使用
free -h
htop

# 增加swap空间
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 调整批次大小
# 在爬虫启动时设置更小的batch_size
```

## 📊 性能优化

### 数据库优化

```sql
-- 添加必要索引
ALTER TABLE crawl_tasks ADD INDEX idx_source_status (source, status);
ALTER TABLE candidates ADD INDEX idx_llm_processed (llm_processed);
ALTER TABLE candidate_emails ADD INDEX idx_email (email);

-- 定期清理日志
DELETE FROM crawl_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

### 应用优化

```bash
# 1. 使用生产级WSGI服务器
pip install gunicorn
gunicorn main:app -w 4 -b 0.0.0.0:8000

# 2. 启用HTTP缓存
# 在Nginx中配置静态文件缓存

# 3. 数据库连接池
# 已在SQLAlchemy中配置
```

## 🔒 安全配置

### 基础安全

```bash
# 1. 防火墙配置
sudo ufw enable
sudo ufw allow 22    # SSH
sudo ufw allow 8000  # 应用端口

# 2. 定期更新依赖
pip list --outdated
pip install --upgrade package_name

# 3. 使用HTTPS（生产环境）
# 配置Nginx + Let's Encrypt SSL证书
```

### 数据安全

- 定期备份数据库
- 敏感配置使用环境变量
- API Token定期轮换
- 限制数据库用户权限

## 📈 监控和日志

### 应用日志

```bash
# 查看实时日志
tail -f app.log

# 按级别过滤日志
grep "ERROR" app.log
grep "WARNING" app.log

# 日志分析
cat app.log | grep "爬取失败" | wc -l
```

### 系统监控

```bash
# 资源使用情况
htop
iostat -x 1
df -h

# 网络连接
netstat -an | grep :8000
ss -tulpn | grep :8000
```

## 🤝 开发指南

### 添加新的爬虫源

1. 在 `services/` 下创建新服务类
2. 在 `controllers/` 下添加对应控制器
3. 在 `main.py` 中注册路由
4. 更新数据库模型（如需要）

### 代码规范

- 使用类型提示
- 遵循PEP 8规范
- 编写单元测试
- 添加详细注释

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙋‍♂️ 支持

如有问题或建议，请：

1. 查看本文档的常见问题部分
2. 检查GitHub Issues
3. 联系项目维护者

---

**快速启动命令总结**：

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps
uvicorn main:app --host 0.0.0.0 --port 8000
```

**首次使用建议**：先在测试环境验证完整流程，确认无误后再部署到生产环境。