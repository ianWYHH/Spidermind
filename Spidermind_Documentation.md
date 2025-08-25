# 项目说明 / 架构设计 / 开发顺序 + Cursor 提示词手册（v1）

> 面向：单人使用、长期扩展、**无调度器/多线程**、可手动触发、可实时查看日志。
> 技术栈：Python 3.11 + FastAPI + Jinja2（简易前端）+ MySQL 8 + requests + trafilatura + Playwright（兜底）+ SQLAlchemy ORM。

---

## 0. TL;DR（一眼看懂）

* **目标**：统一抓取 GitHub / OpenReview / 个人主页信息，构建“候选人画像”，并支持后续解析与人工补录。
* **核心机制**：任务表驱动；点击一次按钮→消费 `pending` 直到为空→停止；**实时日志**可见。
* **三爬虫并行**：GitHub / OpenReview 主动跑；通用主页爬虫**实时消费** homepage 任务，同时可单独补跑。
* **数据规范**：一切一对多字段拆分子表；去重唯一约束；**同一用户不重复爬**，补充信息走“补充任务”。
* **解析**：规则优先，只有需要大模型时才调用；标签放主表；**缺失字段提示**优先于复杂评级。
* **部署**：`nohup + uvicorn` 最简单；MySQL 自备；可后续加 Nginx/HTTPS。

---

## 1. 项目说明（目标 / 范围 / 非目标）

### 1.1 目标

* 最大化收集 **AI/机器人**领域高级人才信息（非商用，个人使用）。
* 在 **已有 13 万论文数据 + 4000+ 简历数据** 基础上持续扩展与补全。
* 确保流程 **可控、可溯源、可人工复查/补录**，而不是自动化黑箱。

### 1.2 范围

* 爬虫：GitHub、OpenReview、通用主页（requests 优先，Playwright/Selenium 兜底）。
* 数据库：候选人主表 + 一对多子表；任务表；日志表；映射表；论文标题一对多。
* 前端：

  * 控制面板：启动三个爬虫、解析；参数设置（repo 智能选择 N/N）。
  * 日志：三独立窗口（GitHub / OpenReview / Homepage）。
  * 候选人列表：姓名 / 主邮箱/联系方式 / 机构 / 分数 / 缺失字段提示。
  * 详情页：主信息 + 子表信息 + 日志追溯 + **人工补录表单**。
  * 统计面板：任务 pending/done/failed、解析进度、**各字段覆盖率（≥1 计覆盖）**。

### 1.3 非目标

* 不引入调度器、消息队列、复杂并发框架；不做自动后台常驻任务。
* 不做公开登录系统与权限体系；地址不公开即可。

---

## 2. 系统架构（模块视图）

```
FastAPI App
├── webui（Jinja2 模板+少量JS轮询）
├── controllers（路由层）
│   ├── crawl_github.py
│   ├── crawl_openreview.py
│   ├── crawl_homepage.py
│   ├── parse_llm.py
│   ├── candidates.py  （列表/详情/补录）
│   └── dashboard.py   （统计面板/健康）
├── services（业务逻辑层）
│   ├── github_service.py
│   ├── openreview_service.py
│   ├── homepage_service.py
│   ├── parse_service.py   （规则+LLM，仅必要时）
│   ├── progress_service.py（进度与轮询）
│   └── stats_service.py    （覆盖率/任务统计）
├── crawlers（抓取层）
│   ├── github_client.py    （token 池/限速/API 封装）
│   ├── openreview_client.py
│   ├── fetcher.py          （requests + trafilatura 基础抓取）
│   └── playwright_fetcher.py（兜底渲染）
├── extractors（解析层）
│   ├── regex_extractors.py （邮箱/电话/社交/URL）
│   ├── text_clean.py       （正文抽取、去噪）
│   └── tags_rules.py       （关键词→研究方向/技能 标签）
├── repos（数据访问层/DAO）
│   ├── task_repo.py / log_repo.py
│   ├── candidate_repo.py  （主表+子表）
│   └── mapping_repo.py    （github_users/openreview_users）
├── models（SQLAlchemy ORM）
├── config
│   ├── settings.py (.env)
│   └── tokens.github.json  （多token轮换）
└── main.py（FastAPI 入口）
```

---

## 3. 数据流（统一流程）

1. **任务表入口**：`crawl_tasks(source, type, url/login/profile_id, depth, status)` → 所有爬虫只消费与自己相关的任务类型。
2. **GitHub 爬虫**：profile→orgs→智能挑选 repos→README 正则；发现 homepage→插入 homepage 任务；**同一用户不重复爬**。
3. **OpenReview 爬虫**：论文地址仅用于**发现人**，转为 profile 任务；profile 提取机构/邮箱/主页/GitHub→插任务。
4. **通用爬虫**：消费 homepage 任务；requests 成功→正文抽取；失败或文本过短→Playwright 兜底；全文保存 `raw_texts`。
5. **解析（手动按钮）**：仅对需要 LLM 的非结构化文本调用；规则关键词优先，LLM 结果合并；更新主表标签与 `llm_processed`。
6. **展示 & 补录**：列表（缺失提示）、详情（子表+日志）、补录（邮箱/电话/主页/文件）。
7. **统计**：任务状态、解析进度、字段覆盖率（≥1 计覆盖）。

---

## 4. 数据库结构（ORM/DDL 指南）

> 采用 SQLAlchemy 建模，启动时 `Base.metadata.create_all()`；唯一约束用于去重。以下为字段建议（可按需裁剪）。

### 4.1 主表

* **candidates**：

  * id(PK), name, alt\_names(JSON), primary\_email, github\_login, openreview\_id,
  * current\_institution, homepage\_main,
  * research\_tags(JSON or comma text), skill\_tags(JSON or comma text),
  * completeness\_score(INT), llm\_processed(BOOL), status(ENUM: raw/parsed/validated),
  * created\_at, updated\_at

### 4.2 子表（1\:N）

* **candidate\_emails**：id, candidate\_id, email, source, created\_at

  * 唯一： (candidate\_id, email)
* **candidate\_institutions**：id, candidate\_id, institution, start\_year, end\_year, source

  * 唯一： (candidate\_id, institution, COALESCE(start\_year,0), COALESCE(end\_year,0))
* **candidate\_homepages**：id, candidate\_id, url, source, created\_at

  * 唯一： (candidate\_id, url)
* **candidate\_files**：id, candidate\_id, file\_url\_or\_path, file\_type(pdf/image), status(parsed/unparsed), source, created\_at
* **candidate\_repos**：id, candidate\_id, repo\_name, repo\_url, description, language, stars, forks, last\_commit, picked\_reason(recent/star), source

  * 唯一： (candidate\_id, repo\_url)
* **candidate\_papers**：id, candidate\_id, title, source\_url, created\_at

### 4.3 原文与解析

* **raw\_texts**：id, candidate\_id, url, plain\_text(LONGTEXT), source(homepage/github\_io/pdf\_ocr), created\_at

  * 唯一： (candidate\_id, url)

### 4.4 爬虫任务/日志

* **crawl\_tasks**：

  * id, source( github/openreview/homepage ), type( profile/repo/follow\_scan/homepage ),
  * url, github\_login, openreview\_profile\_id, candidate\_id, depth, status(pending/done/failed), retries, created\_at, updated\_at, priority, batch\_id
  * 去重键： (source, type, COALESCE(url,''), COALESCE(github\_login,''), COALESCE(openreview\_profile\_id,''))
* **crawl\_logs**：id, task\_id, source, url, status(success/fail/skip), message, created\_at
* **crawl\_log\_candidates**：id, log\_id, candidate\_id  （一条日志可关联多个候选人）

### 4.5 映射（去重关键）

* **github\_users**：github\_login(UNIQUE), github\_id(UNIQUE), candidate\_id(NULLABLE), last\_crawled\_at
* **openreview\_users**：openreview\_profile\_id(UNIQUE), candidate\_id(NULLABLE), last\_crawled\_at

---

## 5. API（最小集合）

* **控制台**

  * `POST /crawl/github/start`  {recent\_n=5, star\_n=5, follow\_depth=1|2, per\_seed\_cap=200, global\_cap=5000}
  * `POST /crawl/openreview/start`
  * `POST /crawl/homepage/start`  （补跑 homepage）
  * `POST /parse/start`  （仅处理需要 LLM 的非结构化文本）
  * `GET  /progress/{source}`  （返回已处理数/剩余 pending/本轮成功失败数）
  * `GET  /logs/{source}`  （支持 `?since_id=` 增量获取，前端轮询）

* **候选人**

  * `GET  /candidates?query=&missing=email|phone|resume...` （列表 + 缺失提示）
  * `GET  /candidates/{id}` （详情页）
  * `POST /candidates/{id}/add_email|add_phone|add_homepage|add_file` （人工补录）

* **统计**

  * `GET  /dashboard/stats` （任务计数、覆盖率、解析进度）

---

## 6. 前端页面（Jinja2 简版）

* **首页仪表盘**：三按钮（GitHub/OpenReview/Homepage 补跑）+ 解析按钮 + 参数表单（repo recent/star N）+ 统计卡片。
* **日志页（Tab）**：GitHub / OpenReview / Homepage 三个窗口，实时增量加载（轮询 `since_id`）。
* **候选人列表**：表格列：姓名、主邮箱/电话、机构、分数、缺失提示；搜索框（姓名/机构/邮箱）。
* **候选人详情**：主信息卡片 + 子表 Tabs（邮箱/机构/主页/repos/files/raw\_texts）+ 关联日志 + 补录表单（弹层）。

---

## 7. 配置与运行参数

* `config/tokens.github.json`：

```json
{
  "tokens": [
    {"value": "ghp_xxx1", "status": "active", "last_used_at": null},
    {"value": "ghp_xxx2", "status": "active", "last_used_at": null}
  ],
  "per_request_sleep_seconds": 0.8,
  "rate_limit_backoff_seconds": 60
}
```

* `.env`：`MYSQL_DSN=mysql+pymysql://user:pass@host:3306/dbname`

---

## 8. 关键算法与策略

### 8.1 GitHub 智能选仓库

* 若总仓库 ≤ 10 → 全存。>10 → 取 `recent_n`（默认5）+ `star_n`（默认5）；记录 `picked_reason`。

### 8.2 社交扩展（follow/following）

* 深度默认 1（可选 2）；每入口上限 `per_seed_cap`；全局上限 `global_cap`；命中关键词与活跃度做轻量打分（阈值可配）。
* **同一用户永不重复爬**；仅补充未覆盖 scope 的子任务（如仅补 repos）。

### 8.3 token 轮换

* Round-Robin 选择；遇 403/耗尽 → 标记冷却、指数退避并切下一枚；日志记录。

### 8.4 通用爬虫兜底

* requests + trafilatura；若失败或正文 < 200 字 → Playwright 渲染再抽取。

### 8.5 completeness\_score（已定） & 缺失提示

* 联系方式权重最高；**前端显式列缺失项**（邮箱/电话/微信/主页/简历…）。

### 8.6 覆盖率统计

* 字段覆盖率按“≥1 条即覆盖”计算（邮箱/电话/主页/简历/社交）。

---

## 9. 部署（方式一：最简）

```bash
# 服务器准备
sudo apt update
sudo apt install -y python3-pip python3-venv

# 项目
cd /home/youruser/project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Playwright 仅在需要兜底时
pip install playwright
python -m playwright install --with-deps

# 启动（后台）
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
```

---

## 10. 开发顺序（里程碑 & 交付物）

1. **M1. 项目骨架**：FastAPI + Jinja2 + SQLAlchemy + MySQL 连接 + 基本首页。
2. **M2. 数据模型**：建表（ORM 模型+唯一约束）；`create_all()` 自建。
3. **M3. 任务与日志基础**：`crawl_tasks` 消费循环（直到无 pending 停），`crawl_logs` 增量 API。
4. **M4. GitHub 爬虫**：profile/orgs/repos 智能选、README 邮箱正则、homepage 任务派生、token 轮换。
5. **M5. OpenReview 爬虫**：论文→作者→profile；profile→邮箱/机构/主页/GitHub；`candidate_papers` 标题入库。
6. **M6. 通用爬虫**：requests+trafilatura→兜底 Playwright；全文 `raw_texts` 入库。
7. **M7. 前端列表/详情/补录**：候选人列表、详情、补录表单、关联日志。
8. **M8. 解析按钮**：规则关键词→必要时 LLM；更新标签与 `llm_processed`；可复查列表。
9. **M9. 统计面板**：任务状态、解析进度、覆盖率卡片；参数表单（repo N/N）。
10. **M10. 清理与验收**：异常处理、错误提示、日志完善、说明文档。

---

## 11. Cursor / Claude4 提示词（逐步开发用）

> 用法：把每段提示词复制到 Cursor Chat，让它**直接生成/修改具体文件**。若文件结构不同，请让它“**对齐本文档指定的路径**”。
	已经整理后放在13中
 

## 12. 验收清单（你这边快速确认）

* [ ] 三个爬虫按钮可用，点击后能“跑到无 pending 即停”。
* [ ] 三个日志窗口能实时看到 success/fail/skip，含候选人ID/姓名。
* [ ] GitHub 智能选仓库生效，README 邮箱/主页能被抽到。
* [ ] OpenReview 论文→作者→profile→主页/GitHub 任务链条跑通，论




---

## 13. 开发顺序标准提问模板（M1–M10）

> 用法：将对应步骤的整段提示词直接粘贴到 Cursor/Claude4，对现有项目进行增量开发。所有模板均已包含**反幻觉/省 token 约束**。

### M1｜项目骨架（FastAPI + Jinja2 + SQLAlchemy + 基础首页）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。请严格按照我提供的架构开发，禁止添加未指定依赖；禁止引入多线程/调度器/队列。

【任务描述】
在一个全新或空仓的项目中，创建最小可运行骨架：
- FastAPI 应用、Jinja2 模板渲染、SQLAlchemy 连接 MySQL。
- 首页模板包含 4 个占位按钮：开始 GitHub 爬虫 / 开始 OpenReview 爬虫 / 补跑 Homepage / 开始解析。
- 目录结构需与文档一致（controllers/services/crawlers/models/config/templates/static）。

【功能要求】
1. main.py：创建 FastAPI 实例、Jinja2Templates、DB 会话生命周期（依赖注入）。
2. config/settings.py：读取 .env 中 MYSQL_DSN。
3. models/base.py：声明 Base、engine、SessionLocal。
4. controllers/dashboard.py：GET / 显示首页（按钮仅占位，先不绑定实际逻辑）。
5. templates/base.html、index.html：基础布局 + 4 按钮。
6. requirements.txt：按 Python 3.9 友好版本固定依赖（fastapi / uvicorn / jinja2 / sqlalchemy / pymysql / python-dotenv 等）。

【约束条件】
- 不要实现任何爬虫逻辑；仅搭好骨架与页面。
- 不要重写无关文件；只输出新增/修改文件的**完整代码**。

【输入/输出说明】
- 输入：.env 中 MYSQL_DSN。
- 输出：uvicorn 可启动首页（无报错）。

【检查点】
- 运行 `uvicorn main:app --reload` 可访问 `/`，能看到 4 个占位按钮。
- 控制台无异常，数据库连接延后到 M2。
```

### M2｜数据库模型与建表（ORM + 唯一约束）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。严格按我指定的表与字段实现 SQLAlchemy 模型与建表逻辑；禁止添加未指定依赖。

【任务描述】
在 models/ 目录新增所有 ORM 模型，并在应用启动时 `Base.metadata.create_all(engine)` 自动建表。

【功能要求】
1. 定义以下表（含唯一约束/索引）：
   - candidates, candidate_emails, candidate_institutions, candidate_homepages,
     candidate_files, candidate_repos, candidate_papers, raw_texts,
     crawl_tasks, crawl_logs, crawl_log_candidates,
     github_users, openreview_users。
2. 字段、唯一键按照文档第 4 章建议；所有表包含 created_at/updated_at（必要处）。
3. main.py 中在应用启动事件里执行 create_all。
4. controllers/dashboard.py 增加 `/health/db`：连接测试 & 返回各表计数（只需简单 SELECT COUNT）。

【约束条件】
- 严格使用 SQLAlchemy ORM；不要写原生 SQL 除非无法避免。
- 不要重写无关文件；只输出新增/修改文件的**完整代码**。

【输入/输出说明】
- 输入：.env 中 MYSQL_DSN 指向可用 MySQL。
- 输出：启动后建表成功，/health/db 返回各表计数。

【检查点】
- MySQL 中能看到全部表；唯一约束生效（可用重复插入试验验证被拒）。
```

### M3｜任务消费循环与日志 API（基础设施）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现“按钮触发→消费 pending→无任务即停”的通用循环，以及日志增量拉取 API。

【任务描述】
1. controllers/logs.py：实现 `GET /logs/{source}?since_id=`，返回 id、created_at、status、url、message、candidate_ids[]。
2. services/progress_service.py：内存态统计器（本轮处理总数/成功/失败/跳过）。
3. controllers/crawl_github.py：先搭一个通用入口 `POST /crawl/github/start`，内部调用通用消费器（暂时只是桩函数）。
4. services/task_runner.py：实现通用消费循环框架（传入 source/type 过滤、处理函数），循环取 `status=pending` 的任务直到为空，处理中写 crawl_logs 与进度。

【约束条件】
- 不实现具体爬虫，仅有循环框架 + 日志 API。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：crawl_tasks 预置若干 pending（可手工插入）。
- 输出：调用 /crawl/github/start 后，循环会尝试消费并写日志（当前可写成模拟处理）。

【检查点】
- /logs/{source} 能分页拉取日志；progress 可统计到次数。
```

### M4｜GitHub 爬虫（token 池、智能选仓库、README 正则、homepage 派生）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现 GitHub 爬虫端到端：client、service、controller 集成，遵守“同一用户不重复爬”。

【任务描述】
1. crawlers/github_client.py：
   - 读取 config/tokens.github.json（Round-Robin 轮换、403/RateLimit 冷却、请求间 sleep、重试2次）。
   - 提供 get_user(login), get_user_orgs(login), get_user_repos(login), get_readme(owner, repo)。
2. extractors/regex_extractors.py：提供邮箱/电话/社交/URL 的正则提取函数。
3. services/github_service.py：
   - 处理任务 type=profile / repo / follow_scan。
   - 智能选仓库：≤10 全取；>10 取 recent_n + star_n，记录 picked_reason。
   - README 中提取邮箱/主页，写入子表；发现 github.io/blog → 创建 homepage 任务。
   - 去重：查 github_users；已完整爬过则写 skip 日志。
4. controllers/crawl_github.py：`POST /crawl/github/start` 读取 recent_n/star_n/follow_depth 等参数，调用通用消费循环绑定到 github_service。

【约束条件】
- 严格 ORM；遵守唯一约束；所有结果入库并写 crawl_logs。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：crawl_tasks 中 (source=github) 的 profile/repo/follow_scan 任务。
- 输出：候选人/子表写入、homepage 任务派生、日志记录。

【检查点】
- 运行 /crawl/github/start 能消费到无 pending 即停；日志显示 success/fail/skip；repos 被智能筛选入库。
```

### M5｜OpenReview 爬虫（论文→作者→profile，profile→邮箱/机构/主页/GitHub）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现 OpenReview 爬虫：论文地址只为发现“人”，存论文标题到 candidate_papers。

【任务描述】
1. crawlers/openreview_client.py：最小 API/HTML 抽取客户端（forum→作者列表；profile→基本信息与链接）。
2. services/openreview_service.py：
   - 论文 URL：提取作者（姓名、profile 链接、机构/邮箱若可得），为每位作者创建 openreview_profile 任务；将论文标题写入 candidate_papers（关联到候选人）。
   - profile URL：抽取人名/机构/邮箱/主页/GitHub，更新候选人与子表，并派生 homepage/github_profile 任务。
3. controllers/crawl_openreview.py：`POST /crawl/openreview/start` 接入通用消费循环。

【约束条件】
- 不保存论文正文；只抓“人”相关字段与论文标题。
- 严格 ORM；唯一约束；日志全记录。

【输入/输出说明】
- 输入：crawl_tasks 中 (source=openreview) 的 forum/profile 任务。
- 输出：候选人/子表更新、candidate_papers 新增、派生任务、日志。

【检查点】
- 启动后能从论文任务生成多位作者的 profile 任务，并正确写入论文标题；日志中可见生成任务计数。
```

### M6｜通用主页爬虫（requests→兜底 Playwright，全文 raw\_texts）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现通用主页爬虫：requests + trafilatura 抓正文，失败或过短再用 Playwright 渲染兜底。

【任务描述】
1. crawlers/fetcher.py：requests 获取 HTML，trafilatura 提取正文。
2. crawlers/playwright_fetcher.py：使用 Playwright 渲染页面并返回渲染后的 HTML，再用 trafilatura 提取正文。
3. services/homepage_service.py：
   - 消费 (source=homepage) pending 任务。
   - 抓正文：先 fetcher，若失败或正文 < 200 字 → playwright_fetcher 兜底。
   - 将全文保存 raw_texts；用 regex_extractors 提取邮箱/电话/社交；发现 PDF/图片简历写 candidate_files(status=unparsed)。
4. controllers/crawl_homepage.py：`POST /crawl/homepage/start`，也可被“实时消费”模式复用。

【约束条件】
- 日志需标注是否触发兜底；严格 ORM；唯一约束。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：crawl_tasks 中 (source=homepage) 的任务。
- 输出：raw_texts/子表入库，日志记录。

【检查点】
- 对于正常页面只走 requests；对 JS-heavy 页面触发兜底并在日志 message 中注明；全文成功写入 raw_texts。
```

### M7｜候选人列表/详情/人工补录（缺失提示 + 子表展示）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现候选人列表与详情页，以及人工补录表单（邮箱/电话/主页/文件）。

【任务描述】
1. controllers/candidates.py：
   - GET /candidates：表格列=姓名、主邮箱/电话、当前机构、completeness_score、缺失提示；支持 query 搜索（姓名/机构/邮箱）。
   - GET /candidates/{id}：详情页（主信息卡片 + Tabs：emails/institutions/homepages/repos/files/raw_texts + 关联日志）。
   - POST /candidates/{id}/add_email|add_phone|add_homepage|add_file：写对应子表并刷新 completeness_score；写“人工补录”日志。
2. templates：列表页、详情页、补录弹层表单。

【约束条件】
- 缺失提示按“至少一个”规则（邮箱/电话/微信/主页/简历）。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：数据库已有候选人数据。
- 输出：列表/详情可视；提交补录表单能成功写库并刷新分数。

【检查点】
- 列表能搜索与分页（可简易实现）；详情能展示各子表；补录成功后分数与缺失提示更新。
```

### M8｜解析按钮（规则优先 + 必要时 LLM 占位，支持复查/重解析）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现解析入口：仅对需要的大文本调用 LLM 占位，规则关键词优先；可复查并重置为待解析。

【任务描述】
1. extractors/tags_rules.py：提供基于关键词的研究方向/技能提取函数（输入文本→返回标签集合）。
2. services/parse_service.py：
   - 扫描与 raw_texts 关联且 `llm_processed=false` 的候选人。
   - 先用规则生成标签；如判定不足再调用占位函数 call_llm(text)->tags 并合并。
   - 更新 candidates.research_tags/skill_tags、llm_processed=true。
   - 提供重置接口，将指定候选人标记为 `llm_processed=false` 进入重解析队列。
3. controllers/parse_llm.py：`POST /parse/start` 触发解析；`GET /parse/review` 列出最近解析的记录，支持重置。

【约束条件】
- 此阶段仅写好 LLM 占位函数，不接真实 API；规则优先。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：raw_texts 全文与候选人关联。
- 输出：主表标签字段更新，llm_processed 标记变化；可在 /parse/review 查看并重置。

【检查点】
- 点击 /parse/start 后有解析进度；/parse/review 能看到解析摘要并支持重置后再解析。
```

### M9｜统计面板（任务计数 + 覆盖率 + 解析进度）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。实现首页仪表盘的统计 API 与展示：任务状态、候选人解析进度、字段覆盖率（≥1 即覆盖）。

【任务描述】
1. services/stats_service.py：
   - 任务统计：按 source/type 汇总 pending/done/failed。
   - 候选人解析进度：总数/llm_processed=true/false。
   - 覆盖率：邮箱/电话/主页/简历/社交（存在≥1条即算覆盖）。
2. controllers/dashboard.py：`GET /dashboard/stats` 返回上述数据；首页 index.html 以卡片形式展示。

【约束条件】
- 查询注意效率；可添加必要索引。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：数据库现有数据。
- 输出：首页展示统计结果。

【检查点】
- 首页能看到任务计数、解析进度、覆盖率百分比；接口响应快速。
```

### M10｜清理与验收（异常处理、错误提示、README）

```
约束条件（请务必遵守）：
- 我的运行环境是 Linux 云服务器，Python 3.9。
- 我只使用 venv 虚拟环境（python3.9 -m venv venv），禁止使用 conda 或 poetry。
- 依赖安装方式只能用 pip install，不要写 conda/poetry/docker。
- 数据库是 MySQL 8，驱动使用 pymysql。
- 项目依赖需要写入 requirements.txt，并且指定版本（兼容 Python 3.9）。
- 项目结构必须与我提供的设计文档一致，不能随意改动目录。
- 禁止引入 Celery、调度器、消息队列、多线程框架。
- 不要重写无关文件，只输出修改过的文件完整代码。

你是资深 Python 工程师。对项目进行收尾与验收，使之可按“手动按钮→到无 pending 停”的模式稳定运行。

【任务描述】
1. 统一异常处理：所有服务层在失败时写 crawl_logs（status=fail, message=原因）。
2. 日志 message 规范（含兜底标记、跳过原因，如“已完整爬取/唯一约束冲突”）。
3. README.md：运行步骤、依赖安装（含 Playwright 安装命令）、环境变量、常见错误排查（MySQL/端口/权限）。
4. 提供一个端到端演示脚本或步骤：手工插入示例任务→运行三个爬虫→实时日志→homepage 派生→通用爬虫→解析→列表/详情可见数据。

【约束条件】
- 保持架构与依赖稳定；不添加新框架。
- 不要重写无关文件；只输出新增/修改文件完整代码。

【输入/输出说明】
- 输入：示例任务与现有数据。
- 输出：README 完整、系统端到端可用。

【检查点】
- 三个爬虫按钮工作正常；日志/统计/列表详情/补录/解析全链路跑通；`nohup + uvicorn` 可部署运行。

```


Spidermind 开发喂给 Cursor 的手册
 

M1 项目骨架

需要贴：

文档 第 2 章 系统架构（目录结构）

文档 第 6 章 前端页面（首页占位按钮）

开头固定段落

M1 的标准提问模板


M2 数据库模型与建表

需要贴：

文档 第 4 章 数据库结构（表 + 字段 + 唯一约束 + 子表设计）

开头固定段落

M2 的标准提问模板

M3 任务消费循环与日志 API

需要贴：

文档 第 3 章 数据流（任务表驱动流程）

文档 第 4.4 爬虫任务/日志 表结构

开头固定段落

M3 的标准提问模板

M4 GitHub 爬虫

需要贴：

文档 第 8.1 GitHub 智能选仓库

文档 第 8.2 社交扩展（follow/following）

文档 第 8.3 token 轮换

文档 第 4.5 github_users 表

开头固定段落

M4 的标准提问模板

M5 OpenReview 爬虫

需要贴：

文档 第 3 章 数据流（OpenReview 爬虫部分）

文档 第 4.5 openreview_users 表

文档 第 8.5 completeness_score（缺失提示）（有助于理解 profile 信息提取）

开头固定段落

M5 的标准提问模板

M6 通用主页爬虫

需要贴：

文档 第 3 章 数据流（通用爬虫部分）

文档 第 8.4 通用爬虫兜底策略

文档 第 4.3 原文与解析 raw_texts 表

开头固定段落

M6 的标准提问模板

M7 候选人列表/详情/补录

需要贴：

文档 第 6 章 前端页面（候选人列表 + 详情页设计）

文档 第 8.5 completeness_score 与缺失提示

开头固定段落

M7 的标准提问模板

M8 解析按钮（规则 + LLM 占位）

需要贴：

文档 第 3 章 数据流（解析阶段）

文档 第 8.6 覆盖率统计

文档 第 4.3 原文与解析 raw_texts 表

开头固定段落

M8 的标准提问模板

M9 统计面板

需要贴：

文档 第 6 章 前端页面（统计面板设计）

文档 第 8.6 覆盖率统计

开头固定段落

M9 的标准提问模板

M10 清理与验收

需要贴：

文档 第 12 验收清单

文档 第 9 部署（nohup + uvicorn 方式）

开头固定段落

M10 的标准提问模板

3. 使用方法总结

每次提问时，粘贴 开头固定段落

然后粘贴 对应 Mx 阶段需要的文档片段

最后粘贴 该阶段的标准提问模板

然后直接让 Cursor/Claude 写代码

📌 这样你就完全不用动脑，只要复制粘贴，就能稳定驱动 Cursor/Claude 按照你设计的蓝图生成代码。


第一版修改


老王，我把你这个仓库看了（结构基本对齐你之前那份蓝图），先给你一份“审阅报告 + 立刻能丢给 Cursor 的改造指令包”。我会把每条结论都落到可执行的 Cursor 提示词上，方便你一段段贴进去让它改。

— 仓库：`ianWYHH/Spidermind`（我能看到的文件树、README 概述与部署指引等）([GitHub][1])
— 设计蓝图：你上传的《项目说明 / 架构设计 / 开发顺序 + Cursor 提示词手册（v1）》

---

# 总评（TL;DR）

* ✅ 目录结构与蓝图基本一致（controllers/services/crawlers/models/config/...）。
* ⚠️ 若干关键点与蓝图不一致或易踩坑：

  1. **配置来源分裂**：README 走 `config/database.json`，蓝图要求 `.env` 的 `MYSQL_DSN`；建议统一为“.env 优先、JSON 兜底”。([GitHub][1])&#x20;
  2. **GitHub token 文件格式不一致**：README 用“字符串数组”，蓝图要求带状态的对象结构并含速率控制参数。([GitHub][1])&#x20;
  3. **验收关键项需要补齐/自检**：按钮触发→“消费 pending 直到为空即停”、日志 since\_id 增量拉取、覆盖率与解析进度卡片等。
  4. **解析服务**应“规则优先 + LLM 仅在必要时”，且默认在无 API Key 时**不触发外部推理**。
  5. **通用爬虫兜底**要严格：正文 <200 字或请求失败再走 Playwright，并记录兜底标记到日志。
  6. **唯一约束/索引**：需对照蓝图全面核对（特别是子表唯一键、raw\_texts 唯一、github\_users/openreview\_users 映射）。

下面是按“最高优先级 → 快速见效”的**6 个改造任务**，每个任务都附带你可以直接粘到 Cursor 的**精准提示词**（会让 Cursor 只输出修改文件的完整代码，且与蓝图对齐）。

---

# 改造任务 A：统一配置读取（.env 优先，database.json 兜底）

**为什么**：蓝图规定 `config/settings.py` 读取 `.env` 里的 `MYSQL_DSN`；你仓库 README 用的是 `config/database.json`。建议**向下兼容**两者：若 `.env` 存在则优先，缺省再拼接 JSON。&#x20;

**给 Cursor 的提示词（直接粘）**：

> 你是资深 Python 工程师。对齐我的设计文档。
> 目标：统一配置入口（.env 优先，config/database.json 兜底），不破坏现有代码。
>
> **修改/新增文件**：
>
> 1. `config/settings.py`：
>
>    * 用 `python-dotenv` 读取 `.env`；优先取 `MYSQL_DSN`。
>    * 若无 `MYSQL_DSN`，尝试读取 `config/database.json`（`host/port/username/password/database`）并拼成 `mysql+pymysql://...`。
>    * 提供 `get_mysql_dsn()` 方法给其他模块使用。
> 2. `models/base.py`：改为**统一**从 `get_mysql_dsn()` 拿连接串构建 engine。
> 3. `.gitignore`：确认包含 `.env` 与 `config/database.json`。
> 4. `README.md`：更新“配置”章节，说明“.env 优先，JSON 兜底”的策略（保留示例）。
>
> **约束**：
>
> * 仅使用 pip 依赖，保持现有结构与蓝图一致；不要引入新框架。
> * 只输出修改过的文件**完整代码**。
>
> 参考：蓝图明确 `settings.py (.env)`、`.env` 示例。&#x20;

---

# 改造任务 B：标准化 GitHub Token 池与轮换退避

**为什么**：README 用数组；蓝图是对象结构+冷却/退避参数，便于限速与 403 轮换。([GitHub][1])&#x20;

**给 Cursor 的提示词**：

> 目标：`crawlers/github_client.py` 支持**两种 tokens 配置**：
>
> * 旧格式：`["ghp_xxx1", "ghp_xxx2"]`
> * 新格式（蓝图）：
>
>   ```json
>   {
>     "tokens":[{"value":"ghp_xxx1","status":"active","last_used_at":null},{"value":"ghp_xxx2","status":"active","last_used_at":null}],
>     "per_request_sleep_seconds":0.8,
>     "rate_limit_backoff_seconds":60
>   }
>   ```
>
> 实现：
>
> * Round-Robin 取 token；遇 403/速率耗尽：标记该 token 冷却，按 `rate_limit_backoff_seconds` 退避并切到下一枚。
> * 每次请求间 sleep `per_request_sleep_seconds`。
> * 兼容两种配置并记录日志（source=github，status=fail/skip，message 里包含“rate\_limit/backoff/rotated\_token”）。
>
> **改动文件**：`crawlers/github_client.py`（完整代码）+ 必要的 `services/github_service.py` 里调用处（若有）。
> **日志规范**：与蓝图一致。

---

# 改造任务 C：校准 ORM 模型（唯一约束 / 时间戳 / 索引）

**为什么**：保证“去重不脏写、统计与查询高效”，对齐蓝图列出的**所有表 + 唯一键**。

**给 Cursor 的提示词**：

> 目标：严格按设计蓝图核对并修补 ORM：
>
> * 表集合：`candidates, candidate_emails, candidate_institutions, candidate_homepages, candidate_files, candidate_repos, candidate_papers, raw_texts, crawl_tasks, crawl_logs, crawl_log_candidates, github_users, openreview_users`。
> * 唯一键：详见蓝图（子表各自唯一组合、raw\_texts 按 `(candidate_id, url)`、crawl\_tasks 去重键、github\_users/openreview\_users 唯一）。
> * 每表 `created_at/updated_at`（`server_default=func.now()`, `onupdate=func.now()`）。
> * 常用查询字段加索引（如 `crawl_tasks.status/source/type`、`github_users.github_login`、`openreview_users.openreview_profile_id`）。
> * 在 `main.py` 启动事件执行 `Base.metadata.create_all(engine)`。
> * 新增 `GET /health/db`：返回各表 count。
>
> **改动文件**：`models/*.py`、`controllers/dashboard.py`（health）如缺则新增；只输出修改文件完整代码。
> 参考蓝图章节。&#x20;

---

# 改造任务 D：通用“任务消费循环”与“增量日志 API”

**为什么**：满足“按钮触发→消费 `pending` 直到为空即停”，以及日志 since\_id 轮询。

**给 Cursor 的提示词**：

> 目标：实现通用任务消费器与日志增量拉取：
>
> 1. `services/task_runner.py`：
>
>    * `run_until_empty(source: str, handler: Callable, filter_types: Optional[List[str]] = None)`
>    * 循环拉取 `crawl_tasks(status='pending', source=source)`；每处理一条写 `crawl_logs`（success/fail/skip），空则停止；提供内存计数器。
> 2. `controllers/logs.py`：`GET /logs/{source}?since_id=` 按自增 id 返回日志列表（含 `candidate_ids[]`）。
> 3. `services/progress_service.py`：维护本轮 processed/success/fail/skip；`GET /progress/{source}` 返回统计。
> 4. `controllers/crawl_github.py`（以及 openreview/homepage）：`POST /crawl/{source}/start` 接入消费器，参数如 `recent_n/star_n`。
>
> **日志 message 规范**：包含跳过原因/兜底标记/唯一约束冲突说明。
> **改动文件**：按需新增/补全上述模块；只输出修改文件完整代码。
> 参考蓝图。

---

# 改造任务 E：GitHub 服务“智能选仓库 + README 抽取 + homepage 派生”

**为什么**：核心命中率来源；需要严格遵守“≤10 全取；>10 取 recent\_n + star\_n，记录 picked\_reason；从 README 正则邮箱/主页；发现 github.io/blog → 插 homepage 任务；同一用户不重复爬”。

**给 Cursor 的提示词**：

> 目标：在 `services/github_service.py` 落实：
>
> * 任务类型：profile / repo / follow\_scan；“同一用户不重复爬”（检查 `github_users`）。
> * 智能选仓库策略（见上）；`candidate_repos` 记录 `picked_reason`、stars、forks、last\_commit。
> * `extractors/regex_extractors.py`：提供邮箱/URL 抽取函数；从 README 抽邮箱与 homepage 入 `candidate_emails` 与 `candidate_homepages`。
> * 发现 `*.github.io` / “blog/个人站” → 创建 `crawl_tasks(source='homepage', type='homepage', url=...)`。
> * 全流程写 `crawl_logs`；唯一约束与跳过要写明原因。
>
> **改动文件**：`services/github_service.py`、`extractors/regex_extractors.py`、必要的 `crawlers/github_client.py` 调用；只输出修改文件完整代码。
> 参考蓝图策略。

---

# 改造任务 F：通用主页爬虫（requests→Playwright 兜底）+ 原文入库

**为什么**：保障个人主页/简历命中率与文本供解析；小于 200 字或失败才兜底。

**给 Cursor 的提示词**：

> 目标：实现/完善以下模块：
>
> * `crawlers/fetcher.py`：requests + 超时 + UA + 重试（少量），用 trafilatura 抽正文；返回 (html, text)。
> * `crawlers/playwright_fetcher.py`：渲染后再抽正文。
> * `services/homepage_service.py`：
>
>   1. 消费 `source=homepage` pending 任务；
>   2. 先走 fetcher，若失败或正文 `< 200` 字 → 走 Playwright；
>   3. 全文保存到 `raw_texts(candidate_id,url,plain_text,source)`；
>   4. 正则抽邮箱/电话/社交，若发现 pdf/image 简历则写入 `candidate_files(status='unparsed')`；
>   5. 日志 message 标注是否触发兜底（如 `"fallback=playwright"`）。
>
> **改动文件**：上述 3 个模块如缺则新增；只输出修改文件完整代码。
> 参考蓝图兜底策略。

---

# 加固项（建议列入后续批次）

* **解析服务**：规则优先、LLM 占位；增加 `/parse/review` 与“重置”入口；无 Key 时自动跳过 LLM。
* **前端**：首页四按钮 + 统计卡片、日志 Tab `since_id` 轮询、候选人列表缺失提示、详情+补录表单。
* **验收脚本/步骤**：手工插入示例任务→跑三爬虫→日志→homepage 派生→通用爬虫→解析→列表/详情可见数据。

---

# 你现在就可以做的验证（3 步）

1. **配置**：在根目录放 `.env`（`MYSQL_DSN=...`），保留 `config/database.json` 作为兜底；启动 `/health/db` 看表统计是否正常（Cursor 完成任务 A/C 后）。
2. **按钮运行**：用 `POST /crawl/github/start` 跑到“无 pending 即停”，观察 `/logs/github?since_id=` 是否有规范化 message。
3. **兜底验证**：给 homepage 任务一条 JS-heavy 的学者主页，确认日志里出现 `fallback=playwright`，且 `raw_texts` 有入库记录。

---

# 接下来怎么干？

* 先把 **A→F** 六条改造跑完（都是“高收益/低风险”的基础项），跑通后我们再上“解析/前端/统计”的体验优化一批（我再给你第二包 Cursor 指令）。
* 你把 Cursor 改完的关键文件（或运行报错）发我，我就按错误栈继续细化“修 BUG 提示词”。

如果你愿意，我也可以把上面六条再合并成**一个“大提示词”**，让 Cursor 一次性批量修改；但分步做更稳。👉 你先从**任务 A**开始贴给 Cursor，改完我就给你第二批（解析/前端/统计）的精准提示词。

（以上结论与改造方向以你的蓝图为准：`settings.py (.env)`、tokens 结构、兜底策略、验收要点与表结构等都来自你那份文档。）  &#x20;

[1]: https://github.com/ianWYHH/Spidermind "GitHub - ianWYHH/Spidermind"


收到老王！你先冲 A–F。我又把仓库（能看到的 README、目录和指令）过了一遍，基于当前结构和说明再补一批**高概率问题/隐患**，你把下面这批也列进待办，一次性让 Cursor 改掉就行。

小前提（我引用到的都是你仓库里的 README/结构说明）：

* 项目用 **MySQL 8**、FastAPI、Playwright（可选）等；README 以 `config/database.json` 为主并给出了 `tokens.github.json` 的数组格式，以及通义千问 Qwen 的可选配置与安装步骤。([GitHub][1])

---

# 额外疑似 BUG / 隐患清单（G → N）

**G. 后台长任务阻塞事件循环**
症状：如果 `POST /crawl/*/start` 在协程里直接做网络 IO / DB 重任务，可能阻塞 uvicorn 导致页面卡顿；多次点击会叠加重复跑。
修法：把消费循环放到**单例后台 runner**里（`asyncio.create_task` + 互斥锁），重复点击直接返回“已在运行”。（与 A–F 的“run\_until\_empty”配套）

**给 Cursor：**

> 目标：防止 `/crawl/*/start` 重复并发与事件循环阻塞。
> 修改：
>
> 1. `services/task_runner.py` 增加模块级 `asyncio.Lock()` 与 `is_running: Dict[str,bool]`；在 `run_until_empty()` 外包 `async with lock`；已在跑则快速返回。
> 2. `controllers/crawl_*.py` 的 `start` 改为**只**创建后台任务：`asyncio.create_task(task_runner.run_until_empty(...))`，接口立刻返回 `{status:"started"}`。
> 3. 新增 `GET /crawl/{source}/status` 返回 `{running, processed, pending}`。
>    输出修改过文件完整代码。

---

**H. 数据库会话泄漏 / 连接池老化**
症状：FastAPI 每请求开会话但未 `close()`；MySQL 长时间空闲导致“server has gone away”。
修法：统一 `SessionLocal` 依赖（`yield` 关闭）、Engine 开启 `pool_pre_ping=True, pool_recycle=1800`。

**给 Cursor：**

> 目标：修复会话泄漏与断链。
> 修改：
>
> * `models/base.py`：`create_engine(dsn, pool_pre_ping=True, pool_recycle=1800, pool_size=10, max_overflow=20)`；导出 `SessionLocal = sessionmaker(...)`。
> * `main.py`：提供 `get_db()` 依赖（`yield db; finally db.close()`），所有控制器注入 `db: Session = Depends(get_db)`。
> * 在启动时 `Base.metadata.create_all(engine)` 仅在 `ENV!=prod`。
>   输出完整代码。

---

**I. requirements 版本与可选依赖护栏**
症状：Pydantic v1/v2、SQLAlchemy 1.x/2.x 混用最容易崩；Playwright 未安装时报错启动失败。
修法：**显式钉版本**，并在运行时对 Playwright 做“按需导入/缺失降级”。

**给 Cursor：**

> 目标：钉版本与按需依赖。
>
> 1. `requirements.txt`（覆盖）：
>
> ```
> fastapi>=0.111,<0.116
> uvicorn[standard]>=0.30,<0.33
> sqlalchemy>=2.0.30,<2.1
> pymysql>=1.1,<2
> pydantic>=2.7,<3
> httpx>=0.27,<0.28
> trafilatura>=1.8,<2
> beautifulsoup4>=4.12,<5
> jinja2>=3.1,<4
> python-dotenv>=1.0,<2
> ```
>
> 可选：`playwright` 只在 README 的“可选安装”保留（已有说明）。([GitHub][1])
> 2\) `crawlers/playwright_fetcher.py` 顶部用 `try: import playwright ... except ImportError: raise RuntimeError("Playwright not installed")`，在 `homepage_service` 捕获并降级为常规 fetch。
> 输出完整代码（两文件）。

---

**J. 模板与静态资源挂载错误**
症状：`templates/` 和 `static/` 存在，但若未 `app.mount("/static")` 或 `Jinja2Templates(directory="templates")`，页面 404。
修法：在 `main.py` 补挂载与模板实例，并加一个 `/health/app`。

**给 Cursor：**

> 目标：挂载模板/静态与健康检查。
> 修改 `main.py`：
>
> * `from fastapi.templating import Jinja2Templates`、`templates = Jinja2Templates("templates")`；
> * `app.mount("/static", StaticFiles(directory="static"), name="static")`；
> * `GET /health/app` 返回 `{ok: true, version, time}`；
>   若已有则对齐命名。输出完整代码。

---

**K. 安全：管理端点缺少保护（尤其 `/parse/reset`）**
症状：任何人命中端点就能清空/重跑。
修法：加**简易 API-Key 头**或环境变量白名单来源 IP；生产可替换为 JWT。

**给 Cursor：**

> 目标：为敏感端点加 API Key 保护。
> 修改：
>
> * `config/settings.py` 增 `ADMIN_API_KEY`（.env 优先）并提供 `require_admin(request)` 依赖，校验 `X-Admin-Key`。
> * 在 `controllers/parse_llm.py` 的 `reset`、各 `start` 路由上 `Depends(require_admin)`。
> * README 增“管理接口保护”段落（如何传 `X-Admin-Key`）。
>   输出修改过文件完整代码。

---

**L. 结构化日志 & Trace Id**
症状：跨爬虫链路难以串日志。
修法：统一 `logging` JSON 格式，自动注入 `trace_id`（每次 `/crawl/*/start` 生成），并把 `trace_id` 写进 `crawl_logs`。

**给 Cursor：**

> 目标：统一 JSON 日志并携带 trace。
> 修改/新增：
>
> * `services/logging.py`：封装 `get_logger(name, trace_id=None)`；
> * `controllers/crawl_*.py`：启动时生成 `trace_id = uuid4()`，传入 `run_until_empty()`；
> * `services/task_runner.py` & 各 service 写 `crawl_logs.trace_id` 字段；
> * `GET /logs/{source}?trace_id=` 支持按 trace 过滤。
>   输出完整代码（涉及文件）。

---

**M. OpenReview 速率与异常处理**
症状：OpenReview 有时返回 429/502；没有指数退避会雪崩。
修法：使用 `httpx` + 重试（429/5xx 指数退避，尊重 `Retry-After`），并把“跳过/失败原因”落入日志。

**给 Cursor：**

> 目标：健壮化 `openreview_service.py`。
>
> * 所有请求经一个 `fetch_json(url, params)` 包装，遇 429/5xx → 退避 1s, 2s, 4s, …（上限 60s），支持 `Retry-After`。
> * 失败写 `crawl_logs(message="openreview: {status} {reason}")`。
>   输出完整代码。

---

**N. 数据列类型与索引上限**
症状：`utf8mb4` 下长 `VARCHAR` 做唯一/索引会超 MySQL 索引长度；`raw_texts` 若不是 `LONGTEXT` 容易截断。
修法：

* `raw_texts.plain_text` 用 `LONGTEXT`；
* 索引列长度控制（如对 URL 做 `VARCHAR(512)`，必要时用 `prefix length index` 或改为 `HASH(url)` 辅助去重）；
* 统一 `created_at/updated_at TIMESTAMP`（默认 `CURRENT_TIMESTAMP`，`ON UPDATE`）。

**给 Cursor：**

> 目标：修正字段类型与索引。
>
> * 调整 `models/*.py` 中：`raw_texts.plain_text = Text().with_variant(LONGTEXT, "mysql")`；
> * URL/邮箱字段限定长度并建索引；
> * 对超长唯一约束，增加 `url_hash = CHAR(32)`（MD5）实现唯一去重 `(candidate_id, url_hash)`。
>   输出修改文件完整代码。

---

# 辅助检查（你本地顺手自测）

1. **依赖与启动**
   `pip install -r requirements.txt` → 未装 Playwright 也能启动（Homepage 渲染时才提示可选安装）。README 已声明 Playwright 安装为“仅在需要时”。([GitHub][1])

2. **配置与安全**

* `.gitignore` 中必须忽略 `.env`、`config/tokens.*.json`；
* `ADMIN_API_KEY` 生效后，未带 `X-Admin-Key` 的重置/启动接口应 401。

3. **OpenReview / GitHub 速率**

* 连续触发两次 `/crawl/openreview/start`，第二次应提示“已有运行中”；
* GitHub token 轮换 & 退避逻辑按你前一批（B 任务）实现即可配合此处。

4. **日志可追踪**

* `/crawl/github/start` → 查看 `/logs/github?trace_id=...` 能全链路串起来；
* 失败/兜底原因（如 `fallback=playwright`）清晰可见（与 F 任务一致）。

---

# 🧩 我建议的执行顺序（在你做完 A–F 之后）

G（并发防抖） → H（DB 连接与会话） → I（版本钉住 & 可选依赖） → J（模板/静态） → K（安全） → L（日志链路） → M（OpenReview 退避） → N（字段/索引）。

如果你愿意，我也可以把 **G–N** 合并成**一条“大提示词”**给 Cursor 一次提交；但分批合并更稳。等你这轮改造推进到位，把 Cursor 的修改（或报错栈）贴我，我继续给你**精确修 BUG 提示词**跟进。

[1]: https://github.com/ianWYHH/Spidermind "GitHub - ianWYHH/Spidermind"

