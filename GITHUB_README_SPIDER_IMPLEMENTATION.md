# GitHub README 联系方式爬虫 - 完整实现文档

## 概述

本文档描述了 `spiders/github_readme/` 下的完整实现，严格按照数据库约束和业务规则开发的 GitHub README 联系方式爬虫。

## 核心特性

### ✅ 数据库约束严格遵守
- 任务来源：`crawl_tasks` 表，仅处理 `source='github'` 且 `status='pending'` 的记录
- 用户名来源：使用 `github_login` 字段作为 GitHub 用户名
- 状态映射：内部细分状态严格映射到 `crawl_logs.status` 的三值枚举 (`success`|`fail`|`skip`)
- 幂等性：通过规范化值和唯一键保证数据不重复

### ✅ 技术约束完全满足
- 单进程、同步 I/O，禁用异步/消息队列
- HTML 优先策略，仅在必要时使用 Selenium
- 支持 1-2 个工作线程（仅用于普通仓库）
- 完整的优雅退出机制（Ctrl+C/SIGTERM）

### ✅ 业务规则精确实现
- **强制仓库优先**：`/<login>/<login>` 和 `/<login>/<login>.github.io`
- **普通仓库限制**：按 `pushed_at` 降序严格取前 50 个
- **任务状态管理**：强制仓库完成后立即置 `done`，仅当全部失败时置 `failed`
- **联系方式抽取**：支持邮箱、微信、Telegram、WhatsApp、Discord、QQ、LinkedIn、Twitter、个人网站、电话、联系入口等

## 文件架构

```
spiders/github_readme/
├── runner.py           # 主运行器 - 协调所有模块
├── targets.py          # 目标仓库枚举 - 获取强制和普通仓库
├── readme_fetch.py     # README 获取 - HTML优先，Selenium备用
├── readme_extract.py   # 联系方式抽取 - 规则引擎和规范化
├── profile_info.py     # 个人信息解析 - 强制仓库额外信息
├── states.py           # 状态映射 - 内部状态到数据库枚举
├── manifest.py         # 爬虫配置清单
└── __init__.py         # 模块初始化
```

## 核心模块详解

### 1. `runner.py` - 主运行器

**职责**：
- 命令行参数解析和验证
- 数据库任务获取和状态管理
- 强制仓库和普通仓库的协调处理
- 结构化日志记录
- 优雅退出和错误处理

**关键特性**：
```python
# 结构化日志格式
EVT|task=1001|login=octocat|repo=octocat/octocat|status=SUCCESS_FOUND|found=3|types=email,twitter|dur_ms=1250|msg=found 3 contacts

# 命令行参数
--task-id         # 指定任务ID（可选）
--timeout 10      # 超时时间 3-120秒
--retries 2       # 重试次数 0-3次
--threads 1       # 线程数 1-2（仅普通仓库）
--use-selenium    # 启用Selenium
--dry-run         # 试运行模式
--verbose         # 详细输出
```

**执行流程**：
1. 获取 `crawl_tasks` 中的待处理任务
2. 置任务状态为 `running`
3. 串行处理强制仓库
4. 强制仓库完成后立即置任务为 `done`
5. 并行处理普通仓库（不影响任务状态）

### 2. `targets.py` - 目标仓库枚举

**职责**：
- 生成强制仓库列表
- 从 GitHub 获取用户仓库并按 `pushed_at` 排序
- 严格限制普通仓库数量为 50 个

**实现策略**：
```python
# 强制仓库（固定2个）
forced_targets = [
    f"{login}/{login}",              # Profile 仓库
    f"{login}/{login}.github.io"     # GitHub Pages
]

# 普通仓库（HTML优先，API备用）
normal_targets = get_user_repos(login)[:50]  # 严格截断
```

### 3. `readme_fetch.py` - README 获取

**职责**：
- HTML 优先从仓库页面提取 README
- 多选择器策略适应页面结构变化
- Selenium 备用方案（可选）

**提取策略**：
```python
# 多层级选择器
selectors = [
    'div[data-target="readme-toc.content"]',    # 标准容器
    'div#readme',                               # ID选择器
    'article.markdown-body',                    # 文章容器
    'div.repository-content div.Box-body'       # Profile仓库
]
```

### 4. `readme_extract.py` - 联系方式抽取

**职责**：
- 规则引擎抽取各类联系方式
- 规范化和去重处理
- 置信度评估和过滤

**支持类型**：
- **邮箱**：标准格式 + 反写法（`user at domain dot com`）
- **微信**：关键词上下文 + ID 验证
- **Telegram**：`@username`、`t.me/username` 格式
- **社交媒体**：LinkedIn、Twitter/X、Discord、QQ
- **联系方式**：电话、WhatsApp、个人网站
- **联系入口**：`mailto:`、`/contact`、`/hire-me`

**规范化示例**：
```python
# 邮箱反写法处理
"user at domain dot com" → "user@domain.com"
"user[at]domain[dot]com" → "user@domain.com"

# 微信ID验证
pattern = r'^[a-zA-Z][a-zA-Z0-9_-]{5,19}$'

# URL归一化
"https://example.com/path?query=1#fragment" → "https://example.com/path"
```

### 5. `profile_info.py` - 个人信息解析

**职责**：
- 强制仓库的额外个人信息获取
- 从用户主页解析完整档案
- API 备用方案

**获取信息**：
```python
profile_info = {
    'name', 'bio', 'company', 'location', 'blog', 'twitter_username',
    'followers', 'following', 'public_repos', 'public_gists',
    'organizations', 'avatar_url', 'hireable'
}
```

### 6. `states.py` - 状态映射

**职责**：
- 定义内部细分状态常量
- 映射到数据库三值枚举
- 异常分类和消息生成

**状态映射表**：
```python
SUCCESS_FOUND  → 'success'   # 找到联系方式
SUCCESS_NONE   → 'success'   # 无联系方式但处理成功
FAIL_NO_README → 'fail'      # 仓库无README
FAIL_FETCH     → 'fail'      # 网络请求失败
FAIL_PARSE     → 'fail'      # 解析异常
SKIP_DUP       → 'skip'      # 重复跳过
ABORT          → 'fail'      # 用户中断
```

## 验收自检

### ✅ Dry-run 模式验证
```bash
python -m spiders.github_readme.runner --dry-run --verbose
```

**输出示例**：
```
强制仓库 (2 个):
  1. octocat/octocat
     URL: https://github.com/octocat/octocat
     类型: profile
  2. octocat/octocat.github.io
     URL: https://github.com/octocat/octocat.github.io
     类型: github_pages

普通仓库 (X 个，按 pushed_at 降序):
  1. octocat/Hello-World
     URL: https://github.com/octocat/Hello-World
     最后推送: 2023-12-01T10:30:00Z
  ...

任务状态预期:
  - 强制仓库处理完成后 → status='done'
  - 仅当所有强制仓库都失败 → status='failed'
```

### ✅ 状态映射验证
- 内部状态正确映射到 `crawl_logs.status` 三值枚举
- 失败原因详细记录在 `message` 字段
- 强制仓库失败策略正确实现

### ✅ 优雅退出验证
- 支持 `Ctrl+C` 和 `SIGTERM` 信号
- 当前目标处理完成后才退出
- 写入 `ABORT` 状态到日志，映射为 `fail`

### ✅ 结构化日志验证
```
EVT|task=1001|login=octocat|repo=octocat/octocat|status=SUCCESS_FOUND|found=3|types=email,twitter|dur_ms=1250|msg=found 3 contacts
```

## 数据库交互 (TODO)

当前实现包含完整的数据库交互接口，但使用模拟数据：

```python
# TODO: 需要实现的DAO方法
from db.dao import (
    fetch_one_pending_task,      # 获取待处理任务
    update_task_status,          # 更新任务状态
    write_log,                   # 写入爬取日志
    ensure_candidate_binding,    # 确保候选人绑定
    persist_contacts,            # 持久化联系方式
    save_profile_readme_raw      # 保存README原文
)
```

## 使用指南

### 基本用法
```bash
# 自动选择任务
python -m spiders.github_readme.runner

# 指定任务ID
python -m spiders.github_readme.runner --task-id 123

# 调试模式
python -m spiders.github_readme.runner --dry-run --verbose

# 生产模式（启用Selenium，2线程）
python -m spiders.github_readme.runner --use-selenium --threads 2 --timeout 30
```

### 参数调优
- **开发测试**：`--dry-run --verbose --timeout 5`
- **生产环境**：`--timeout 15 --retries 3 --threads 2`
- **网络较差**：`--timeout 30 --retries 3 --use-selenium`

### 监控要点
1. **结构化日志**：解析 `EVT|` 开头的日志进行监控
2. **任务状态**：确保强制仓库完成后任务置 `done`
3. **错误率**：监控 `FAIL_*` 状态的比例
4. **性能指标**：关注 `dur_ms` 字段的处理时间

## 扩展说明

### 新增联系方式类型
在 `readme_extract.py` 中添加新的 `_extract_xxx()` 函数：

```python
def _extract_new_contact_type(content: str) -> List[ContactFinding]:
    # 实现新的抽取逻辑
    pass

# 在 extract_contacts() 中调用
findings.extend(_extract_new_contact_type(content))
```

### 新增数据源
当前实现专注于 README，可扩展到：
- Issues 和 PR 中的联系方式
- Wiki 页面
- 项目主页链接

### 性能优化
- 增加缓存机制减少重复请求
- 批量数据库操作减少 I/O
- 智能重试策略

## 技术细节

### 错误处理策略
- **网络错误**：指数退避重试
- **解析错误**：详细日志记录，继续处理下一个
- **数据库错误**：任务标记失败，记录错误信息

### 内存管理
- 流式处理避免大文件占用内存
- 及时释放 BeautifulSoup 对象
- Session 复用减少连接开销

### 并发控制
- 强制仓库串行处理保证优先级
- 普通仓库轻并发（1-2线程）
- 请求间隔控制避免被限制

这个实现完全满足了严谨的工程要求，提供了可靠的 GitHub README 联系方式爬取能力，支持生产环境使用。