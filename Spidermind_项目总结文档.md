# Spidermind 项目总结文档

## 📋 项目概述

**Spidermind** 是一个专为学术人才信息收集设计的智能爬虫系统，通过多源数据爬取、智能解析和可视化分析，构建完整的学术人才数据库。

### 🎯 核心价值
- **多源整合**：统一从 GitHub、OpenReview、个人主页等渠道获取学者信息
- **智能解析**：基于规则引擎 + LLM 增强的标签提取和信息补全
- **完整度评估**：多维度评估候选人信息完整性，提供缺失字段提示
- **人工协作**：支持手动补录和信息修正，确保数据质量
- **实时监控**：可视化仪表盘，实时跟踪爬虫进度和系统状态

---

## 🏗️ 技术架构

### 核心技术栈
- **后端框架**：FastAPI (异步Web框架)
- **数据库**：MySQL 8.0 + SQLAlchemy 2.x (ORM)
- **前端模板**：Jinja2 + 简易JS (轻量级交互)
- **爬虫引擎**：requests + trafilatura + Playwright (兜底)
- **数据处理**：BeautifulSoup4 + 正则表达式 + LLM API
- **部署运行**：uvicorn + 虚拟环境

### 分层架构设计

```
┌─────────────────┐
│   Web UI Layer  │  ← Jinja2模板 + 轻量JS
├─────────────────┤
│ Controller Layer│  ← FastAPI路由控制器
├─────────────────┤  
│ Service Layer   │  ← 业务逻辑服务
├─────────────────┤
│ Crawler Layer   │  ← 爬虫客户端封装
├─────────────────┤
│ Extractor Layer │  ← 数据提取器
├─────────────────┤
│ Model Layer     │  ← SQLAlchemy ORM模型
└─────────────────┘
```

---

## 🚀 核心功能模块

### 1. 多源爬虫系统

#### GitHub 爬虫 (`controllers/crawl_github.py` + `services/github_service.py`)
- **用户画像爬取**：个人信息、机构、社交链接
- **智能仓库筛选**：≤10个全取，>10个按recent_n + star_n策略筛选
- **README信息提取**：正则提取邮箱、个人主页链接
- **社交网络扩展**：follow/following链路发现新候选人
- **Token池管理**：多token轮换，403/限速自动退避

#### OpenReview 爬虫 (`controllers/crawl_openreview.py` + `services/openreview_service.py`)
- **论文作者发现**：从论文页面提取作者信息
- **学者画像构建**：profile页面抓取机构、邮箱、主页、GitHub
- **论文标题关联**：维护候选人-论文关系 (`candidate_papers`)
- **速率控制**：429/5xx指数退避，遵守Retry-After

#### 通用主页爬虫 (`controllers/crawl_homepage.py` + `services/homepage_service.py`)
- **两级抓取策略**：requests优先，失败或内容过短时Playwright兜底
- **全文保存**：原始HTML和提取的纯文本保存至 `raw_texts`
- **联系方式提取**：正则提取邮箱、电话、社交媒体链接
- **简历文档发现**：识别PDF/图片简历并标记为待解析

### 2. 智能解析系统 (`controllers/parse_llm.py` + `services/parse_service.py`)

#### 规则引擎优先
- **关键词匹配**：基于 `extractors/tags_rules.py` 的领域标签提取
- **结构化信息**：邮箱、电话、URL等结构化数据的精确提取
- **机构识别**：教育背景和工作经历的时间线构建

#### LLM增强解析（可选）
- **大模型支持**：集成通义千问等LLM API
- **智能标签生成**：对非结构化文本进行研究方向、技能标签提取
- **信息补全**：补充规则引擎遗漏的关键信息
- **解析状态管理**：支持重置和重新解析

### 3. 数据管理系统

#### 完整度评估 (`services/completeness_service.py`)
- **多维度评分**：联系方式、教育背景、工作经历、研究成果等
- **缺失字段提示**：前端显式列出缺失的关键信息项
- **权重配置**：联系方式权重最高，确保可联系性

#### 人工补录界面 (`controllers/candidates.py`)
- **候选人列表**：支持搜索、筛选、分页浏览
- **详情页展示**：主信息 + 子表tabs（邮箱/机构/主页/repos/文件/原文）
- **补录表单**：邮箱、电话、主页、文件上传等快速添加
- **操作日志**：所有人工操作都有完整的日志记录

### 4. 任务调度系统 (`services/task_runner.py`)

#### 任务驱动架构
- **统一任务表**：`crawl_tasks` 表驱动所有爬虫活动
- **按需消费**：点击按钮→消费pending任务→无任务即停
- **并发控制**：防止重复运行，支持后台长任务
- **进度监控**：实时统计处理数量、成功失败率

#### 日志系统 (`controllers/logs.py` + `services/logging.py`)
- **结构化日志**：JSON格式，支持trace_id链路追踪
- **增量拉取**：`since_id` 机制支持前端实时日志显示
- **多源分离**：GitHub/OpenReview/Homepage 独立日志窗口
- **详细记录**：包含跳过原因、兜底标记、错误详情

### 5. 统计分析系统 (`controllers/dashboard.py` + `services/stats_service.py`)

#### 实时统计
- **任务状态**：按源和类型统计pending/done/failed任务数
- **解析进度**：候选人总数/已解析数/待解析数
- **字段覆盖率**：各类信息字段的覆盖率统计（≥1条即覆盖）
- **系统健康**：数据库连接、API状态等健康检查

#### 可视化展示
- **仪表盘首页**：核心指标卡片 + 快速操作按钮
- **进度监控**：实时进度条 + 成功/失败统计
- **覆盖率分析**：各维度信息完整度可视化

---

## 💾 数据模型设计

### 核心表结构

#### 候选人主表 (`models/candidate.py`)
```sql
candidates: 
- 基本信息：name, alt_names, current_institution
- 联系方式：primary_email, github_login, openreview_id, homepage_main
- 分析字段：research_tags, skill_tags, completeness_score
- 状态控制：llm_processed, status
```

#### 子表设计（一对多关系）
```sql
candidate_emails: 候选人邮箱（多个来源）
candidate_institutions: 机构经历（含时间线）
candidate_homepages: 个人主页（多个URL）
candidate_files: 简历文档（PDF/图片）
candidate_repos: GitHub仓库（智能筛选）
candidate_papers: 关联论文标题
raw_texts: 原始抓取文本（全文保存）
```

#### 任务与日志 (`models/crawl.py`)
```sql
crawl_tasks: 任务队列（source/type/url/status）
crawl_logs: 执行日志（支持trace_id链路追踪）
crawl_log_candidates: 日志-候选人关联
```

#### 映射去重 (`models/mapping.py`)
```sql
github_users: GitHub用户映射（防重复爬取）
openreview_users: OpenReview用户映射
```

### 数据完整性保障
- **唯一约束**：防止重复数据（候选人去重、URL去重等）
- **外键关系**：确保数据一致性
- **索引优化**：高频查询字段建索引
- **时间戳**：created_at/updated_at自动维护

---

## 🔧 配置管理系统

### 统一配置策略 (`config/settings.py`)
- **.env 优先**：环境变量配置优先级最高
- **JSON 兜底**：`config/database.json` 作为兜底配置
- **多环境支持**：dev/test/prod环境独立配置

### 关键配置项
- **数据库连接**：支持MYSQL_DSN直接指定或分项配置
- **GitHub Token池**：支持多token轮换和速率控制
- **LLM API**：通义千问等大模型API配置
- **爬虫参数**：超时、重试、并发数等可调参数

---

## 📊 系统特色功能

### 1. 智能防重机制
- **用户级去重**：同一GitHub/OpenReview用户不重复爬取
- **URL级去重**：同一URL不重复抓取
- **数据级去重**：唯一约束防止脏数据

### 2. 渐进式数据收集
- **任务派生**：从GitHub README发现个人主页→自动创建homepage任务
- **链式发现**：OpenReview论文→作者→profile→GitHub/主页→仓库
- **增量更新**：支持对已有候选人补充新信息

### 3. 容错与兜底
- **多级重试**：网络失败、限速等场景的指数退避重试
- **兜底渲染**：requests失败时Playwright接管JavaScript渲染
- **优雅降级**：LLM不可用时回退到规则引擎
- **错误隔离**：单个任务失败不影响整体流程

### 4. 运营友好设计
- **手动触发**：无后台常驻任务，按需点击启动
- **实时监控**：WebUI实时显示爬虫进度和日志
- **人工介入**：支持暂停、重置、手动补录
- **可追溯性**：完整的操作日志和数据来源记录

---

## 🛠️ 部署与运维

### 环境要求
- **操作系统**：Linux/Windows/macOS
- **Python**：3.9+
- **数据库**：MySQL 8.0+
- **内存**：建议4GB+
- **存储**：建议10GB+

### 部署方式
```bash
# 1. 环境准备
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 2. 依赖安装
pip install -r requirements.txt

# 3. 可选：Playwright（仅在需要JS渲染时）
pip install playwright
python -m playwright install --with-deps

# 4. 配置文件
# 创建 .env 文件或 config/database.json

# 5. 启动应用
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 生产环境优化
- **进程管理**：nohup + uvicorn 后台运行
- **反向代理**：Nginx + SSL证书
- **监控报警**：日志监控 + 系统资源监控
- **数据备份**：定期数据库备份

---

## 📈 使用流程

### 典型工作流程
1. **配置准备**：设置数据库连接、GitHub Token等
2. **任务初始化**：手动插入种子任务或导入候选人列表
3. **启动爬虫**：依次启动GitHub → OpenReview → Homepage爬虫
4. **监控进度**：实时查看日志和统计数据
5. **智能解析**：对抓取的文本进行标签提取和信息补全
6. **人工审核**：通过候选人列表查看结果，手动补录遗漏信息
7. **数据导出**：通过API或数据库查询获取最终数据

### API使用示例
```bash
# 启动GitHub爬虫
curl -X POST "http://localhost:8000/crawl/github/start" \
     -H "Content-Type: application/json" \
     -d '{"recent_n": 5, "star_n": 5, "follow_depth": 1}'

# 查看爬虫进度
curl "http://localhost:8000/progress/github"

# 查看实时日志
curl "http://localhost:8000/logs/github?since_id=100"

# 启动智能解析
curl -X POST "http://localhost:8000/parse/start"

# 查看候选人列表
curl "http://localhost:8000/candidates?query=machine%20learning"
```

---

## 🔍 性能特点

### 数据处理能力
- **单次爬取**：可处理数千个GitHub用户profile
- **智能筛选**：通过关键词和活跃度过滤，提高目标命中率
- **批量处理**：支持批量任务处理，可配置并发数
- **增量更新**：避免重复劳动，仅处理新增或变更数据

### 系统稳定性
- **容错设计**：网络异常、API限制等场景的自动恢复
- **资源控制**：合理的请求频率和超时设置
- **状态持久化**：任务状态保存在数据库，支持中断恢复
- **日志完备**：详细的执行日志便于问题排查

---

## 📝 项目特色总结

### 创新点
1. **任务驱动架构**：通过统一任务表实现灵活的爬虫调度
2. **渐进式发现**：从一个源头出发，通过链式发现扩展数据边界
3. **智能兜底机制**：多层次的容错和降级策略
4. **规则+AI混合**：规则引擎处理结构化数据，LLM处理非结构化文本
5. **完整度导向**：以信息完整度为核心指标，指导数据收集优先级

### 技术亮点
- **轻量级架构**：无需复杂的调度器和消息队列
- **配置灵活性**：支持多种配置方式和环境
- **数据质量保障**：唯一约束 + 人工审核双重保障
- **运维友好**：简单的部署流程和直观的监控界面
- **扩展性设计**：模块化架构便于添加新的数据源

---

## 🎯 适用场景

- **学术机构**：人才库建设、同行发现、合作伙伴识别
- **科研团队**：领域专家查找、技术跟踪、竞品分析
- **人力资源**：技术人才挖掘、背景调研、能力评估
- **投资机构**：创业者背景分析、技术团队评估
- **个人研究**：学术网络分析、研究趋势跟踪

---

*本文档概述了Spidermind项目的核心功能、技术架构和使用方法。系统采用现代化的技术栈，通过智能化的数据收集和处理，为学术人才信息管理提供了完整的解决方案。*