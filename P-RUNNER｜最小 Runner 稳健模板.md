你是一个严谨的资深 Python 工程师。请在当前仓库结构下，生成一套“最小但稳健”的爬虫 Runner 模板，满足下列 **硬性约束**，并输出完整代码（分文件给出）。不要写任何具体业务抓取逻辑，将业务点以 TODO 标注。

【硬性约束】
- 单进程、同步IO；禁止使用 asyncio、消息队列；可选使用 1~2 个工作线程处理“非关键子目标”，默认 1。
- 运行方式：python -m spiders.<SPIDER_DIR>.runner ；可通过 app/main_gui.py 以 subprocess 启动/停止。
- DOM 获取：HTML 优先（requests + BeautifulSoup + lxml）；仅当确需时才单次启用 Selenium（可通过命令行开关）。
- 稳健性：每个 URL 最大 2 次重试（指数退避），失败按口径落日志；超时、网络错误、解析错误必须分类记录。
- 任务与状态流：
  - 任务级：crawl_tasks.status = pending → running → done（仅当两个“强制目标”完成后置 done；否则 failed）
  - 子目标级（crawl_logs.status 枚举，必须一致）：SUCCESS_FOUND / SUCCESS_NONE / FAIL_NO_README / FAIL_FETCH / FAIL_PARSE / SKIP_DUP / ABORT（可选）
- 幂等：写库前先规范化并查唯一键（email/handle/phone/url_hash 等），命中则更新 last_seen，避免重复插入。
- 配置：读取 app/config/config.ini（DB、UA、超时、重试、线程数、是否启用Selenium 等）；支持命令行参数覆盖。
- 日志：标准 logging（文件 + 控制台），并提供“关键事件结构化字段”（task_id、login、repo、status、found_types、count、duration_ms）。
- 优雅退出：支持 OS 信号（Ctrl+C / terminate）→ 当前项收尾 → 记录 ABORT 日志 → 退出码非0。
- 依赖：仅允许使用你在仓库中已存在的库（requests、bs4、lxml、mysql-connector-python、PySide6 等）。不要引入 httpx/tenacity/pydantic 等新依赖。

【目录与文件】
在 spiders/template_minimal/ 下新增或完善以下文件：
1) runner.py
   - 作用：最小运行框架；主流程控制；任务级状态变更；参数解析；优雅退出。
   - 内容要点：
     - argparse：--task-id（可选）、--timeout、--retries（默认2）、--threads（默认1, 允许2）、--use-selenium（默认false）、--dry-run（默认false）
     - 读取 config.ini，命令行参数覆盖
     - 从 db.dao 读取一条 crawl_task（若传 --task-id 则按ID；否则自动取 pending）→ 标记 running（失败要报错退出）
     - 目标拆分：先生成“强制目标列表”（例如 Profile / <login>.github.io），再生成“普通目标列表”（例如按某排序取前N）
       · 注意：这是模板；具体如何产出目标列表由 TODO 占位，runner 只定义接口 & 顺序（强制目标先）
     - 执行顺序：
       1. 依次处理 强制目标（串行，失败重试2次）；每个子目标结束后写 crawl_logs
       2. 若强制目标均已走完（不要求都 SUCCESS_FOUND），立即把 crawl_tasks 置 done
       3. 普通目标再按线程数（1~2）轻并发处理；每个子目标结束后写 crawl_logs（失败不影响任务已置的 done）
     - 事件 & 时间：
       · 子目标开始/结束时间；整体 duration_ms
       · 失败分类：NO_README / FETCH / PARSE，分别记录异常摘要
     - 优雅退出：
       · 捕获 KeyboardInterrupt/信号，尽量完成当前子目标；写 ABORT 日志；退出码 2
     - Dry-run 模式：不写数据库，只打印将要写入的事件（便于演练规则）
     - TODO 钩子函数（供具体爬虫覆写）：
       get_forced_targets(task_row) -> List[Target]
       get_normal_targets(task_row, limit:int) -> List[Target]
       fetch_unit(target, session, args) -> FetchResult
       extract_from_unit(fetch_result, args) -> ExtractResult
       persist_findings(extract_result, dao, args) -> PersistOutcome
       · Target/FetchResult/ExtractResult/PersistOutcome 用 @dataclass 定义结构（含必要字段）

2) states.py
   - 定义任务级、子目标级状态的常量与枚举（字符串常量），与 crawl_logs.status 口径完全一致：
     TASK_PENDING / TASK_RUNNING / TASK_DONE / TASK_FAILED
     LOG_SUCCESS_FOUND / LOG_SUCCESS_NONE / LOG_FAIL_NO_README / LOG_FAIL_FETCH / LOG_FAIL_PARSE / LOG_SKIP_DUP / LOG_ABORT
   - 提供 classify_exception(e:Exception) -> (status, message) 的助手函数

3) types.py
   - dataclass 定义：
     Target(login:str, url:str, meta:dict)
     FetchResult(target:Target, ok:bool, content:str|None, raw:bytes|None, url:str, used_selenium:bool, message:str|None)
     ExtractResult(target:Target, ok:bool, findings:list, kind_summary:set[str], message:str|None)
     PersistOutcome(target:Target, status:str, found_count:int, message:str|None)
   - 这些结构只描述“最小必需字段”，业务爬虫可以扩展 meta

4) args_schema.py
   - 封装 argparse（默认值来自 config.ini，命令行可覆盖）
   - 校验 threads ∈ {1,2}，retries ∈ {0,1,2,3}，timeout ∈ [3,120]
   - 提供 load_args()，返回命名空间

5) lifecycle.py
   - 封装“统一的子目标执行生命周期”：
     run_one_unit(target, fetch_fn, extract_fn, persist_fn, args, logger)
     - 内置重试（最多 args.retries 次，指数退避）
     - 统计耗时，统一捕获异常并转成 LOG_FAIL_* 状态（使用 states.classify_exception）
     - 返回 PersistOutcome 或失败状态

6) dao_port.py
   - 声明 DAO 接口（由 db/dao.py 具体实现）：
     - fetch_one_pending_task(source:str=None, task_id:int|None=None) -> dict
     - update_task_status(task_id:int, status:str, message:str|None=None) -> None
     - write_log(task_id:int, candidate_id:int|None, target_url:str, status:str, found_types:str, found_count:int, message:str|None) -> None
     - ensure_candidate_binding(login:str, base_profile:dict|None) -> int  # 返回 candidate_id；可“最小建档”
     - persist_contacts(candidate_id:int, findings:list[dict]) -> (found_count:int, skipped:int)  # 幂等
     - save_profile_readme_raw(candidate_id:int, url:str, markdown:str) -> None  # 仅强制目标使用
   - runner 只能调用这些方法，不直接拼 SQL；具体 SQL 由 db/dao.py 已有实现或后续实现

7) README.md（放在 spiders/template_minimal/）
   - 说明本模板的设计目标、状态口径、如何扩展 hooks、如何接入 GUI（spiders_registry + manifest）、如何 dry-run 演练

【状态与口径（写在注释里，runner 内也要断言）】
- 强制目标成功“走完整流程”（包括 SUCCESS_NONE 这种“空结果成功”）即可视为完成强制目标；不要求一定 SUCCESS_FOUND。
- 只有当两个强制目标均 FAIL_* 才将 crawl_tasks 置 failed；正常情况是强制目标处理完就置 done。
- 非强制目标数量与上限（例如 50）由具体爬虫的 targets 模块决定；runner 只负责按 args.threads(1~2) 均衡处理。
- 幂等：
  · email/handle/phone 使用规范化值（小写、去零宽、去空格/符号）作为唯一键；命中则更新 last_seen_at。
  · URL 归一化并计算 url_hash；相同即写 SKIP_DUP。
- 质量与过滤规则（留 TODO 提示，具体在业务模块实现）：
  · 邮箱：真实 TLD、严格一次性域过滤、排除 *@users.noreply.github.com
  · WeChat：必须存在“微信/WeChat/vx/威信/加微/联系我”等提示词的上下文
  · 电话：带国家码≥8；无国家码≥11（去分隔后）
- 日志字段最小集合：task_id、login、target_url、status、found_types（逗号分隔，如 email,wechat,phone）、found_count、message、duration_ms、retries

【代码风格与可维护性】
- 使用 dataclass、类型注解，函数名/变量名清晰。
- 关键流程用 INFO 级日志，错误用 ERROR。
- 结构化日志行前缀形如：EVT|task=<id>|login=<login>|url=<url>|status=<status>|found=<n>|types=<...>|dur_ms=<...>|msg=<...>
- 所有 TODO 必须具体（比如“TODO: 在 get_forced_targets 中返回 Profile 与 <login>.github.io 的 Target 列表”），并给出参数/返回格式。

【输出要求】
- 逐个文件输出完整代码内容（runner.py / states.py / types.py / args_schema.py / lifecycle.py / dao_port.py / README.md），可以带必要注释；不得省略。
- 代码可直接 import 现有 app/core 与 db/dao.py，但不要在本次实现中写业务逻辑，保持为模板。
- 运行 runner.py（dry-run 模式）不应崩溃：若缺 DAO 实现或无任务，也要优雅打印提示并退出码 0。
