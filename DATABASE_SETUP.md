# 数据库设置指南

## 1. 创建数据库

在 MySQL 中执行以下SQL命令创建数据库：

```sql
-- 创建数据库（注意用户指定数据库名为 Spidermind）
CREATE DATABASE Spidermind CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 授权用户访问（可选，如果需要）
GRANT ALL PRIVILEGES ON Spidermind.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

## 2. 更新配置文件

修改 `.env` 文件中的数据库配置：

```env
# 将数据库名更新为 Spidermind
DB_DATABASE=Spidermind
MYSQL_DSN=mysql+pymysql://root:111111@127.0.0.1:3306/Spidermind
```

## 3. 启动应用

数据库创建完成后，启动应用：

```bash
# 激活虚拟环境
venv\Scripts\activate

# 启动应用（会自动创建表）
uvicorn main:app --reload
```

## 4. 验证数据库

访问健康检查端点验证：

- 应用首页: http://127.0.0.1:8000/
- 数据库健康检查: http://127.0.0.1:8000/health/db

## 5. 数据表结构

应用会自动创建以下 13 个表：

### 主表
- `candidates` - 候选人主表

### 子表 (1:N)
- `candidate_emails` - 候选人邮箱表
- `candidate_institutions` - 候选人机构表  
- `candidate_homepages` - 候选人主页表
- `candidate_files` - 候选人文件表
- `candidate_repos` - 候选人代码仓库表
- `candidate_papers` - 候选人论文表

### 原文与解析
- `raw_texts` - 原文与解析表

### 爬虫任务/日志
- `crawl_tasks` - 爬虫任务表
- `crawl_logs` - 爬虫日志表
- `crawl_log_candidates` - 爬虫日志与候选人关联表

### 映射表（去重关键）
- `github_users` - GitHub用户映射表
- `openreview_users` - OpenReview用户映射表

## 6. 唯一约束

以下表包含重要的唯一约束以防止重复数据：

- `candidate_emails`: (candidate_id, email)
- `candidate_homepages`: (candidate_id, url)  
- `candidate_repos`: (candidate_id, repo_url)
- `raw_texts`: (candidate_id, url)
- `github_users`: github_login (UNIQUE), github_id (UNIQUE)
- `openreview_users`: openreview_profile_id (UNIQUE)

## 7. 索引优化

所有表都包含必要的索引以优化查询性能：

- 主键自动索引
- 外键关联字段索引
- 常用查询字段索引（如 status, created_at 等）
- 唯一约束自动创建唯一索引