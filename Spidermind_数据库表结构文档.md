# Spidermind 数据库表结构文档

## 概述

Spidermind 项目使用 MySQL 数据库，包含 **16 个表**，主要用于管理学术研究人员信息的爬取、存储和分析。数据库采用 SQLAlchemy ORM 框架，遵循标准化设计原则，支持断点续传和会话管理。

### 数据库信息
- **数据库名称**: Spidermind
- **字符集**: utf8mb4
- **排序规则**: utf8mb4_unicode_ci
- **ORM框架**: SQLAlchemy
- **连接池配置**: 连接池大小10，最大溢出20，30分钟回收连接

## 表分类结构

### 1. 候选人主表及相关子表 (7个表)

#### 1.1 candidates (候选人主表)
**用途**: 存储候选人基本信息的主表

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 候选人ID |
| name | VARCHAR(255) | NOT NULL | - | 姓名 |
| alt_names | JSON | - | - | 别名列表 |
| primary_email | VARCHAR(255) | - | - | 主邮箱 |
| github_login | VARCHAR(100) | - | - | GitHub用户名 |
| openreview_id | VARCHAR(100) | - | - | OpenReview用户ID |
| avatar_url | VARCHAR(2048) | - | - | 头像URL |
| current_institution | VARCHAR(500) | - | - | 当前机构 |
| homepage_main | VARCHAR(2048) | - | - | 主要个人主页 |
| research_tags | JSON | - | - | 研究方向标签 |
| skill_tags | JSON | - | - | 技能标签 |
| completeness_score | INTEGER | - | 0 | 完整度评分 |
| llm_processed | BOOLEAN | - | FALSE | 是否经过LLM处理 |
| status | ENUM('raw', 'parsed', 'validated') | - | 'raw' | 状态 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**索引**:
- `idx_candidates_name`: name
- `idx_candidates_primary_email`: primary_email
- `idx_candidates_github_login`: github_login
- `idx_candidates_openreview_id`: openreview_id
- `idx_candidates_status`: status
- `idx_candidates_created_at`: created_at
- `idx_candidates_updated_at`: updated_at

**关联关系**: 一对多关联到所有候选人子表

#### 1.2 candidate_emails (候选人邮箱表)
**用途**: 存储候选人的多个邮箱地址

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| email | VARCHAR(255) | NOT NULL | - | 邮箱地址 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_email`: (candidate_id, email)

**索引**:
- `idx_candidate_emails_candidate_id`: candidate_id
- `idx_candidate_emails_email`: email
- `idx_candidate_emails_created_at`: created_at

#### 1.3 candidate_institutions (候选人机构表)
**用途**: 存储候选人的教育和工作机构历史

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| institution | VARCHAR(500) | NOT NULL | - | 机构名称 |
| start_year | INTEGER | - | - | 开始年份 |
| end_year | INTEGER | - | - | 结束年份 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_institution`: (candidate_id, institution, start_year, end_year)

**索引**:
- `idx_candidate_institutions_candidate_id`: candidate_id
- `idx_candidate_institutions_institution`: institution
- `idx_candidate_institutions_created_at`: created_at

#### 1.4 candidate_homepages (候选人主页表)
**用途**: 存储候选人的个人主页链接

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| url | VARCHAR(2048) | NOT NULL | - | 主页URL |
| url_hash | CHAR(32) | NOT NULL | - | URL的MD5哈希 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_homepage`: (candidate_id, url_hash)

**索引**:
- `idx_candidate_homepages_candidate_id`: candidate_id
- `idx_candidate_homepages_url_hash`: url_hash
- `idx_candidate_homepages_created_at`: created_at

#### 1.5 candidate_files (候选人文件表)
**用途**: 存储候选人相关的文件信息（如简历、论文等）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| file_url_or_path | VARCHAR(2048) | NOT NULL | - | 文件URL或路径 |
| url_hash | CHAR(32) | NOT NULL | - | URL的MD5哈希 |
| file_type | ENUM('pdf', 'image') | - | - | 文件类型 |
| status | ENUM('parsed', 'unparsed') | - | 'unparsed' | 解析状态 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_file`: (candidate_id, url_hash)

**索引**:
- `idx_candidate_files_candidate_id`: candidate_id
- `idx_candidate_files_url_hash`: url_hash
- `idx_candidate_files_status`: status
- `idx_candidate_files_created_at`: created_at

#### 1.6 candidate_repos (候选人代码仓库表)
**用途**: 存储候选人的GitHub代码仓库信息

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| repo_name | VARCHAR(255) | NOT NULL | - | 仓库名称 |
| repo_url | VARCHAR(2048) | NOT NULL | - | 仓库URL |
| url_hash | CHAR(32) | NOT NULL | - | URL的MD5哈希 |
| description | TEXT | - | - | 仓库描述 |
| language | VARCHAR(100) | - | - | 主要编程语言 |
| stars | INTEGER | - | 0 | Star数量 |
| forks | INTEGER | - | 0 | Fork数量 |
| last_commit | DATETIME | - | - | 最后提交时间 |
| picked_reason | ENUM('recent', 'star') | - | - | 选择原因 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_repo`: (candidate_id, url_hash)

**索引**:
- `idx_candidate_repos_candidate_id`: candidate_id
- `idx_candidate_repos_url_hash`: url_hash
- `idx_candidate_repos_stars`: stars
- `idx_candidate_repos_language`: language
- `idx_candidate_repos_picked_reason`: picked_reason
- `idx_candidate_repos_created_at`: created_at

#### 1.7 candidate_papers (候选人论文表)
**用途**: 存储候选人发表的学术论文信息

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| title | VARCHAR(1000) | NOT NULL | - | 论文标题 |
| source_url | VARCHAR(2048) | - | - | 论文来源链接 |
| url_hash | CHAR(32) | - | - | URL的MD5哈希 |
| venue | VARCHAR(200) | - | - | 会议/期刊 |
| source | VARCHAR(100) | - | - | 来源 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_paper_title`: (candidate_id, title)

**索引**:
- `idx_candidate_papers_candidate_id`: candidate_id
- `idx_candidate_papers_url_hash`: url_hash
- `idx_candidate_papers_title`: title
- `idx_candidate_papers_source`: source
- `idx_candidate_papers_created_at`: created_at

### 2. 原文与解析表 (1个表)

#### 2.1 raw_texts (原文与解析表)
**用途**: 存储从各种来源爬取的原始文本内容

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 关联候选人ID |
| url | VARCHAR(2048) | NOT NULL | - | URL |
| url_hash | CHAR(32) | NOT NULL | - | URL的MD5哈希 |
| plain_text | LONGTEXT | - | - | 纯文本内容 |
| source | ENUM('homepage', 'github_io', 'pdf_ocr') | - | - | 来源类型 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_candidate_raw_text`: (candidate_id, url_hash)

**索引**:
- `idx_raw_texts_candidate_id`: candidate_id
- `idx_raw_texts_url_hash`: url_hash
- `idx_raw_texts_source`: source
- `idx_raw_texts_created_at`: created_at

### 3. 爬虫任务/日志表 (3个表)

#### 3.1 crawl_tasks (爬虫任务表)
**用途**: 存储爬虫任务的配置和状态信息，支持断点续传

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 任务ID |
| source | ENUM('github', 'openreview', 'homepage') | NOT NULL | - | 爬虫来源 |
| type | ENUM('profile', 'repo', 'follow_scan', 'homepage', 'forum') | NOT NULL | - | 爬虫类型 |
| url | VARCHAR(2048) | - | - | 目标URL |
| github_login | VARCHAR(100) | - | - | GitHub用户名 |
| openreview_profile_id | VARCHAR(100) | - | - | OpenReview用户ID |
| candidate_id | INTEGER | FOREIGN KEY | - | 关联候选人ID |
| depth | INTEGER | - | 0 | 爬取深度 |
| status | ENUM('pending', 'done', 'failed', 'running') | - | 'pending' | 任务状态 |
| retries | INTEGER | - | 0 | 重试次数 |
| priority | INTEGER | - | 0 | 优先级 |
| batch_id | VARCHAR(100) | - | - | 批次ID |
| retry_at | DATETIME | - | - | 下次重试时间 |
| error_message | TEXT | - | - | 错误消息 |
| session_id | VARCHAR(36) | - | - | 所属会话ID |
| progress_stage | VARCHAR(50) | - | - | 处理阶段 |
| checkpoint_data | TEXT | - | - | 检查点数据 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |
| started_at | DATETIME | - | - | 开始处理时间 |
| completed_at | DATETIME | - | - | 完成时间 |

**索引**:
- `idx_crawl_tasks_source`: source
- `idx_crawl_tasks_type`: type
- `idx_crawl_tasks_status`: status
- `idx_crawl_tasks_candidate_id`: candidate_id
- `idx_crawl_tasks_batch_id`: batch_id
- `idx_crawl_tasks_url`: url
- `idx_crawl_tasks_github_login`: github_login
- `idx_crawl_tasks_openreview_profile_id`: openreview_profile_id
- `idx_crawl_tasks_created_at`: created_at
- `idx_crawl_tasks_updated_at`: updated_at
- `idx_crawl_tasks_dedup`: (source, type, url, github_login, openreview_profile_id) - 去重索引

**关联关系**: 一对多关联到 crawl_logs；多对一关联到 candidates（可选）

#### 3.2 crawl_logs (爬虫日志表)
**用途**: 记录爬虫任务的执行日志

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 日志ID |
| task_id | INTEGER | FOREIGN KEY, NOT NULL | - | 任务ID |
| source | ENUM('github', 'openreview', 'homepage', 'parse', 'manual') | NOT NULL | - | 爬虫来源 |
| task_type | VARCHAR(100) | - | - | 任务类型 |
| url | VARCHAR(2048) | - | - | 爬取URL |
| status | ENUM('success', 'fail', 'skip') | NOT NULL | - | 爬取状态 |
| message | TEXT | - | - | 日志消息 |
| trace_id | VARCHAR(36) | - | - | 跟踪ID (UUID) |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**索引**:
- `idx_crawl_logs_task_id`: task_id
- `idx_crawl_logs_source`: source
- `idx_crawl_logs_status`: status
- `idx_crawl_logs_task_type`: task_type
- `idx_crawl_logs_url`: url
- `idx_crawl_logs_trace_id`: trace_id
- `idx_crawl_logs_created_at`: created_at

**关联关系**: 多对一关联到 crawl_tasks；一对多关联到 crawl_log_candidates

#### 3.3 crawl_log_candidates (爬虫日志与候选人关联表)
**用途**: 关联爬虫日志与候选人的多对多关系

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 关联ID |
| log_id | INTEGER | FOREIGN KEY, NOT NULL | - | 日志ID |
| candidate_id | INTEGER | FOREIGN KEY, NOT NULL | - | 候选人ID |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- `uk_log_candidate`: (log_id, candidate_id)

**索引**:
- `idx_crawl_log_candidates_log_id`: log_id
- `idx_crawl_log_candidates_candidate_id`: candidate_id
- `idx_crawl_log_candidates_created_at`: created_at

### 4. 会话管理表（断点续传支持）(3个表)

#### 4.1 crawl_sessions (爬虫会话表)
**用途**: 管理爬虫会话，支持断点续传和进度跟踪

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 会话ID |
| session_id | VARCHAR(36) | UNIQUE, NOT NULL | - | 会话UUID |
| source | ENUM('github', 'openreview', 'homepage', 'parse') | NOT NULL | - | 爬虫来源 |
| session_type | VARCHAR(50) | NOT NULL | - | 会话类型 |
| status | ENUM('running', 'completed', 'paused', 'failed', 'interrupted') | - | 'running' | 会话状态 |
| config | JSON | - | - | 会话配置参数 |
| total_tasks | INTEGER | - | 0 | 总任务数 |
| processed_tasks | INTEGER | - | 0 | 已处理任务数 |
| success_tasks | INTEGER | - | 0 | 成功任务数 |
| failed_tasks | INTEGER | - | 0 | 失败任务数 |
| skipped_tasks | INTEGER | - | 0 | 跳过任务数 |
| batch_id | VARCHAR(100) | - | - | 批次ID |
| trace_id | VARCHAR(36) | - | - | 跟踪ID |
| last_checkpoint | DATETIME | - | - | 最后检查点时间 |
| checkpoint_data | JSON | - | - | 检查点数据 |
| error_message | TEXT | - | - | 错误消息 |
| error_count | INTEGER | - | 0 | 错误次数 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |
| started_at | DATETIME | - | - | 开始时间 |
| completed_at | DATETIME | - | - | 完成时间 |

**唯一约束**: 
- session_id (UNIQUE)

**关联关系**: 一对多关联到 session_checkpoints 和 task_progress

#### 4.2 session_checkpoints (会话检查点表)
**用途**: 细粒度进度保存，支持精确的断点续传

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 检查点ID |
| session_id | INTEGER | FOREIGN KEY, NOT NULL | - | 会话ID |
| checkpoint_name | VARCHAR(100) | NOT NULL | - | 检查点名称 |
| checkpoint_type | ENUM('progress', 'error', 'milestone', 'config_change') | - | 'progress' | 检查点类型 |
| current_position | VARCHAR(200) | - | - | 当前处理位置 |
| progress_data | JSON | - | - | 进度详细数据 |
| statistics | JSON | - | - | 统计信息 |
| message | TEXT | - | - | 检查点消息 |
| extra_data | JSON | - | - | 额外元数据 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |

**关联关系**: 多对一关联到 crawl_sessions

#### 4.3 task_progress (任务进度表)
**用途**: 扩展任务状态跟踪，提供详细的进度信息

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 进度ID |
| task_id | INTEGER | FOREIGN KEY, NOT NULL | - | 任务ID |
| session_id | INTEGER | FOREIGN KEY, NOT NULL | - | 会话ID |
| stage | VARCHAR(50) | - | - | 当前阶段 |
| substage | VARCHAR(50) | - | - | 子阶段 |
| progress_percent | INTEGER | - | 0 | 进度百分比 |
| items_total | INTEGER | - | 0 | 总项目数 |
| items_processed | INTEGER | - | 0 | 已处理项目数 |
| items_remaining | INTEGER | - | 0 | 剩余项目数 |
| results_success | INTEGER | - | 0 | 成功结果数 |
| results_failed | INTEGER | - | 0 | 失败结果数 |
| results_skipped | INTEGER | - | 0 | 跳过结果数 |
| estimated_completion | DATETIME | - | - | 预计完成时间 |
| last_activity | DATETIME | - | - | 最后活动时间 |
| progress_details | JSON | - | - | 进度详细信息 |
| error_details | JSON | - | - | 错误详细信息 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**关联关系**: 多对一关联到 crawl_tasks 和 crawl_sessions

### 5. 映射表（去重关键）(2个表)

#### 5.1 github_users (GitHub用户映射表)
**用途**: 维护GitHub用户与候选人的映射关系，用于去重

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| github_login | VARCHAR(100) | UNIQUE, NOT NULL | - | GitHub用户名 |
| github_id | BIGINT | UNIQUE, NOT NULL | - | GitHub用户ID |
| candidate_id | INTEGER | FOREIGN KEY | - | 关联候选人ID |
| last_crawled_at | DATETIME | - | - | 最后爬取时间 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- github_login (UNIQUE)
- github_id (UNIQUE)

**索引**:
- `idx_github_users_login`: github_login
- `idx_github_users_id`: github_id
- `idx_github_users_candidate_id`: candidate_id
- `idx_github_users_last_crawled`: last_crawled_at
- `idx_github_users_created_at`: created_at

**关联关系**: 多对一关联到 candidates（可选）

#### 5.2 openreview_users (OpenReview用户映射表)
**用途**: 维护OpenReview用户与候选人的映射关系，用于去重

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | - | 自增ID |
| openreview_profile_id | VARCHAR(100) | UNIQUE, NOT NULL | - | OpenReview用户ID |
| candidate_id | INTEGER | FOREIGN KEY | - | 关联候选人ID |
| last_crawled_at | DATETIME | - | - | 最后爬取时间 |
| created_at | DATETIME | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | - | CURRENT_TIMESTAMP ON UPDATE | 更新时间 |

**唯一约束**: 
- openreview_profile_id (UNIQUE)

**索引**:
- `idx_openreview_users_profile_id`: openreview_profile_id
- `idx_openreview_users_candidate_id`: candidate_id
- `idx_openreview_users_last_crawled`: last_crawled_at
- `idx_openreview_users_created_at`: created_at

**关联关系**: 多对一关联到 candidates（可选）

## 数据库关系图

```
candidates (主表)
├── candidate_emails (1:N)
├── candidate_institutions (1:N)
├── candidate_homepages (1:N)
├── candidate_files (1:N)
├── candidate_repos (1:N)
├── candidate_papers (1:N)
├── raw_texts (1:N)
└── crawl_log_candidates (1:N)

crawl_tasks
├── crawl_logs (1:N)
├── candidates (N:1, 可选)
└── task_progress (1:N)

crawl_logs
├── crawl_log_candidates (1:N)
└── crawl_tasks (N:1)

crawl_sessions
├── session_checkpoints (1:N)
└── task_progress (1:N)

github_users
└── candidates (N:1, 可选)

openreview_users
└── candidates (N:1, 可选)
```

## 重要设计特点

### 1. 去重策略
- **URL去重**: 通过MD5哈希值实现长URL的高效去重
- **用户去重**: 通过映射表防止同一GitHub/OpenReview用户重复爬取
- **复合去重**: 通过唯一约束组合实现多字段去重
- **任务去重**: 通过复合索引防止重复任务创建

### 2. 断点续传支持
- **会话管理**: 通过crawl_sessions表管理爬虫会话状态
- **检查点机制**: 通过session_checkpoints表保存细粒度进度
- **任务跟踪**: 通过task_progress表扩展任务状态跟踪
- **错误恢复**: 支持任务失败后的重试和恢复

### 3. 索引优化
- **主键自动索引**: 所有表的主键都有自动索引
- **外键索引**: 所有外键字段都有专门索引
- **查询优化索引**: 根据常用查询模式创建复合索引
- **时间索引**: 所有时间字段都有索引，便于按时间查询
- **哈希索引**: URL哈希字段索引，优化URL查重性能

### 4. 数据完整性
- **级联删除**: 主表删除时，子表数据自动删除
- **级联设NULL**: 映射表删除时，相关字段设为NULL
- **外键约束**: 确保数据引用完整性
- **枚举约束**: 限制状态字段的合法值
- **唯一约束**: 防止重复数据插入

### 5. 性能优化
- **连接池配置**: 连接池大小10，最大溢出20
- **连接回收**: 30分钟自动回收连接
- **查询优化**: 通过合理的索引设计提升查询性能
- **文本存储**: 使用LONGTEXT存储大文本内容
- **JSON存储**: 使用JSON字段存储结构化数据

### 6. 扩展性设计
- **模块化表结构**: 按功能模块组织表结构
- **JSON字段**: 支持灵活的数据结构扩展
- **枚举扩展**: 预留枚举值扩展空间
- **检查点系统**: 支持复杂任务的精确进度管理

## 数据统计

当前数据库包含 **16个表**，分为以下几类：
- **候选人相关表**: 7个 (主表1个 + 子表6个)
- **原文解析表**: 1个
- **爬虫相关表**: 3个 
- **会话管理表**: 3个 (支持断点续传)
- **映射表**: 2个 (用于去重)

## 使用说明

### 创建数据库
```sql
CREATE DATABASE Spidermind CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 自动创建表
应用启动时会自动创建所有表结构：
```python
from models.base import create_all_tables
create_all_tables()
```

### 表计数统计
```python
from models.base import get_table_counts
counts = get_table_counts()
```

### 健康检查
- 数据库连接检查: `GET /health/db`
- 表计数统计: 通过 `get_table_counts()` 函数
- 数据库连接测试: 通过 `test_database_connection()` 函数

### 断点续传使用
1. 创建会话: 使用 `CrawlSession` 创建新的爬虫会话
2. 设置检查点: 定期调用 `SessionCheckpoint` 保存进度
3. 恢复会话: 从检查点数据恢复中断的任务
4. 进度跟踪: 使用 `TaskProgress` 跟踪详细进度

---

**文档版本**: 2.0  
**更新时间**: 2024年12月  
**更新内容**: 添加会话管理表支持断点续传，更新crawl_tasks表结构，完善索引和约束设计  
**作者**: Spidermind 项目组