#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub README 联系方式爬虫 - 主运行器

严格按照数据库约束执行：
1. 从 crawl_tasks 表读取 source='github' 的任务
2. 使用 github_login 字段作为用户名
3. 强制仓库优先，完成后立即置任务为 done
4. 所有状态映射到 crawl_logs 的三值枚举
5. 支持优雅退出和结构化日志

验收自检：
- dry-run 模式列出强制仓库 + 前50个普通仓库
- 强制仓库处理完成后立即置任务 done
- 内部状态正确映射到 crawl_logs.status
- 支持 Ctrl+C 优雅退出并记录 ABORT 状态
"""

import argparse
import logging
import signal
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from .states import (
    SUCCESS_FOUND, SUCCESS_NONE, FAIL_NO_README, FAIL_FETCH, FAIL_PARSE, ABORT,
    map_to_crawl_logs, classify_exception, is_failure_status, get_status_message
)
from .targets import get_forced_targets, get_normal_targets, validate_targets, Target
from .readme_fetch import fetch_readme
from .readme_extract import extract_plain_text
from .profile_info import parse_profile_info, validate_profile_info
from .follow_discovery import discover_logins, create_discovery_session


logger = logging.getLogger(__name__)

# 全局变量用于优雅退出
_shutdown_requested = False
_current_task_id = None


def setup_signal_handlers():
    """设置信号处理器"""
    def signal_handler(signum, frame):
        global _shutdown_requested
        logger.warning(f"收到退出信号 {signum}，准备优雅停止...")
        _shutdown_requested = True
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='GitHub README 联系方式爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 自动选择任务
  python -m spiders.github_readme.runner
  
  # 指定任务ID
  python -m spiders.github_readme.runner --task-id 123
  
  # 调试模式
  python -m spiders.github_readme.runner --dry-run --verbose
  
  # 启用Selenium
  python -m spiders.github_readme.runner --use-selenium
        """
    )
    
    parser.add_argument('--task-id', type=int, help='指定要处理的任务ID')
    parser.add_argument('--timeout', type=int, default=30, choices=range(3, 121),
                        help='请求超时时间，3-120秒 (默认: 30)')
    parser.add_argument('--retries', type=int, default=3, choices=[0, 1, 2, 3],
                        help='重试次数，0-3次 (默认: 3)')
    parser.add_argument('--threads', type=int, default=1, choices=[1, 2],
                        help='工作线程数，仅用于普通仓库 (默认: 1)')
    parser.add_argument('--use-selenium', action='store_true',
                        help='启用 Selenium 浏览器渲染 (默认: false)')
    parser.add_argument('--dry-run', action='store_true',
                        help='试运行模式，不写入数据库 (默认: false)')
    parser.add_argument('--verbose', action='store_true',
                        help='详细输出模式')
    parser.add_argument('--disable-repo-validation', action='store_true',
                        help='禁用仓库存在性检查（可能产生404错误）')
    
    # Follow Discovery 参数
    parser.add_argument('--follow-depth', type=int, default=0, choices=[0, 1, 2],
                        help='关注发现深度：0=关闭，1=仅第一层，2=两层穿透 (默认: 0)')
    parser.add_argument('--follow-limit-per-side', type=int, default=50,
                        help='每个用户 followers 与 following 各取前N个 (默认: 50)')
    parser.add_argument('--follow-d2-cap', type=int, default=5000,
                        help='第二层发现到的去重后的 login 全局上限 (默认: 5000)')
    parser.add_argument('--follow-sleep-min-ms', type=int, default=300,
                        help='关注发现请求间隔最小毫秒数 (默认: 300)')
    parser.add_argument('--follow-sleep-max-ms', type=int, default=800,
                        help='关注发现请求间隔最大毫秒数 (默认: 800)')
    parser.add_argument('--follow-user-agent', type=str,
                        help='关注发现使用的 User-Agent（可选）')
    
    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 设置第三方库日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def create_session(args: Dict[str, Any]) -> requests.Session:
    """创建HTTP会话"""
    session = requests.Session()
    
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    # 设置超时
    timeout = args.get('timeout', 10)
    session.timeout = timeout
    
    return session


def log_structured_event(event_type: str, task_id: int, login: str, repo: str = "", 
                        status: str = "", found: int = 0, types: str = "", 
                        duration_ms: int = 0, message: str = ""):
    """记录结构化事件日志"""
    log_msg = (
        f"EVT|task={task_id}|login={login}|repo={repo}|status={status}|"
        f"found={found}|types={types}|dur_ms={duration_ms}|msg={message}"
    )
    logger.info(log_msg)


def fetch_task_from_db(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从数据库获取待处理任务 - 使用真实数据库查询
    """
    task_id = args.get('task_id')
    
    try:
        # 使用真实的数据库查询
        from db.dao import DatabaseDAO
        dao = DatabaseDAO()
        
        task = dao.fetch_one_pending_task(source='github', task_id=task_id)
        
        if task:
            if task_id:
                logger.info(f"查询指定任务ID: {task_id}")
            else:
                logger.info("自动选择待处理任务")
            
            logger.info(f"获取到任务: ID={task['id']}, 用户={task['github_login']}")
            return task
        else:
            if task_id:
                logger.error(f"未找到指定任务ID: {task_id}")
            else:
                logger.warning("未找到待处理的GitHub任务")
            return None
            
    except Exception as e:
        logger.error(f"获取任务失败: {e}")
        return None


def update_task_status_in_db(task_id: int, status: str, message: str = "", args: Dict[str, Any] = None):
    """
    更新任务状态到数据库 - 使用真实数据库操作
    """
    if args and args.get('dry_run'):
        logger.info(f"[DRY-RUN] 更新任务状态: task_id={task_id}, status={status}, message={message}")
        return
    
    try:
        # 使用真实的数据库更新
        from db.dao import DatabaseDAO
        dao = DatabaseDAO()
        
        success = dao.update_task_status(task_id, status)
        if success:
            logger.info(f"任务状态已更新: task_id={task_id}, status={status}")
        else:
            logger.error(f"任务状态更新失败: task_id={task_id}, status={status}")
        
    except Exception as e:
        logger.error(f"更新任务状态失败: {e}")


def write_log_to_db_original(task_id: int, target: Target, internal_status: str, message: str, args: Dict[str, Any]) -> int:
    """
    写入爬取日志到数据库 - 使用真实数据库操作 (原版本，用于仓库处理)
    """
    crawl_logs_status = map_to_crawl_logs(internal_status)
    
    if args.get('dry_run'):
        logger.info(f"[DRY-RUN] 写入日志: task_id={task_id}, repo={target.repo_full_name}, "
                   f"status={crawl_logs_status}, message={message}")
        return 0
    
    try:
        # 使用真实的数据库写入
        from db.dao import DatabaseDAO
        dao = DatabaseDAO()
        
        log_id = dao.write_crawl_log(
            task_id=task_id,
            source='github',
            status=crawl_logs_status,
            message=message,
            url=target.repo_url,
            task_type=target.meta.get('type', '')
        )
        
        if log_id:
            logger.debug(f"日志已写入: log_id={log_id}, task_id={task_id}, repo={target.repo_full_name}")
            return log_id
        else:
            logger.error(f"日志写入失败: task_id={task_id}, repo={target.repo_full_name}")
            return 0
        
    except Exception as e:
        logger.error(f"写入日志失败: {e}")
        return 0


def process_single_target(target: Target, task_row: Dict[str, Any], session: requests.Session, args: Dict[str, Any]) -> tuple[str, str, int]:
    """
    处理单个目标仓库
    
    Returns:
        tuple: (internal_status, message, contacts_found)
    """
    global _shutdown_requested
    
    if _shutdown_requested:
        return ABORT, "abort by signal", 0
    
    start_time = time.time()
    task_id = task_row['id']
    login = task_row['github_login']
    
    try:
        logger.info(f"开始处理: {target.repo_full_name} (强制: {target.is_forced})")
        
        # 第1步：获取README
        fetch_result = fetch_readme(target, session, args)
        
        if fetch_result.status != SUCCESS_FOUND:
            duration_ms = int((time.time() - start_time) * 1000)
            log_structured_event(
                "FETCH_FAILED", task_id, login, target.repo_full_name, 
                fetch_result.status, 0, "", duration_ms, fetch_result.message
            )
            return fetch_result.status, fetch_result.message, 0
        
        # 第2步：抽取纯文本（原文入库模式）
        extract_result = extract_plain_text(fetch_result, args)
        
        if extract_result.status in [FAIL_PARSE]:
            duration_ms = int((time.time() - start_time) * 1000)
            log_structured_event(
                "EXTRACT_FAILED", task_id, login, target.repo_full_name,
                extract_result.status, 0, "", duration_ms, extract_result.message
            )
            return extract_result.status, extract_result.message, 0
        
        # 第3步：强制仓库的额外处理
        if target.is_forced and extract_result.status in [SUCCESS_FOUND, SUCCESS_NONE]:
            try:
                # 获取个人信息
                profile_info = parse_profile_info(login, session, args)
                profile_info = validate_profile_info(profile_info)
                
                # 候选人绑定和原文入库（原文入库模式）
                if not args.get('dry_run'):
                    try:
                        from db.dao import DatabaseDAO
                        dao = DatabaseDAO()
                        
                        # 确保候选人绑定
                        candidate_id = dao.ensure_candidate_binding(login, profile_info)
                        if candidate_id:
                            # 确定source类型
                            source = 'github_io' if target.repo_full_name.endswith('.github.io') else 'homepage'
                            
                            # 保存原文
                            save_result = dao.save_raw_text(
                                candidate_id=candidate_id,
                                url=target.repo_url,
                                plain_text=extract_result.plain_text,
                                source=source
                            )
                            logger.debug(f"原文入库结果: {save_result}")
                        else:
                            logger.warning(f"候选人绑定失败: {login}")
                    except Exception as e:
                        logger.error(f"原文入库失败: {e}")
                else:
                    source = 'github_io' if target.repo_full_name.endswith('.github.io') else 'homepage'
                    logger.info(f"[DRY-RUN] 将保存 raw_texts(url={target.repo_url}, source={source}, 长度={len(extract_result.plain_text)})")
                
                logger.debug(f"强制仓库额外信息处理完成: {target.repo_full_name}")
                
            except Exception as e:
                logger.warning(f"强制仓库额外处理失败: {e}")
        
        # 第4步：数据持久化（原文入库模式不再处理联系方式）
        contacts_found = 0  # 原文入库模式不计算联系方式数量
        
        if not args.get('dry_run'):
            try:
                # TODO: 实现联系方式持久化
                # TODO: 实现候选人绑定
                # candidate_id = ensure_candidate_binding(login, profile_info if target.is_forced else None)
                # found_count, skipped_count = persist_contacts(candidate_id, extract_result.findings)
                
                logger.debug(f"联系方式持久化完成: 找到 {contacts_found} 个")
                
            except Exception as e:
                logger.error(f"持久化失败: {e}")
                return FAIL_PARSE, f"persist_error: {str(e)}", contacts_found
        
        # 记录成功
        duration_ms = int((time.time() - start_time) * 1000)
        found_types = ','.join(sorted(extract_result.kind_summary)) if extract_result.kind_summary else ""
        
        log_structured_event(
            "PROCESS_SUCCESS", task_id, login, target.repo_full_name,
            extract_result.status, contacts_found, found_types, duration_ms, extract_result.message
        )
        
        return extract_result.status, extract_result.message, contacts_found
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        internal_status, message = classify_exception(e)
        
        log_structured_event(
            "PROCESS_ERROR", task_id, login, target.repo_full_name,
            internal_status, 0, "", duration_ms, message
        )
        
        return internal_status, message, 0


def process_forced_targets(forced_targets: List[Target], task_row: Dict[str, Any], session: requests.Session, args: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    处理强制仓库
    
    Returns:
        tuple: (should_mark_done, failure_statuses)
    """
    global _shutdown_requested
    
    task_id = task_row['id']
    login = task_row['github_login']
    failure_statuses = []
    
    logger.info(f"开始处理 {len(forced_targets)} 个强制仓库")
    
    for target in forced_targets:
        if _shutdown_requested:
            failure_statuses.append(ABORT)
            break
        
        start_time = time.time()
        internal_status, message, contacts_found = process_single_target(target, task_row, session, args)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # FORCED 结构化日志
        kind = 'github_io' if target.repo_full_name.endswith('.github.io') else 'profile'
        status_msg = 'success' if internal_status in [SUCCESS_FOUND, SUCCESS_NONE] else ('skip' if internal_status == SUCCESS_NONE and 'dup' in message else 'fail')
        forced_log = f"FORCED|kind={kind}|url={target.repo_url}|status={status_msg}|msg={message}|dur_ms={duration_ms}"
        logger.info(forced_log)
        
        # 写入日志
        write_log_to_db_original(task_id, target, internal_status, message, args)
        
        # 记录失败状态
        if is_failure_status(internal_status):
            failure_statuses.append(internal_status)
        
        # 添加延迟避免请求过快
        if not _shutdown_requested:
            time.sleep(1)
    
    # 判断是否应该标记任务完成
    # 新逻辑：如果没有强制仓库，或者有任何一个强制仓库成功处理，则标记为完成
    if not forced_targets:
        # 没有强制仓库（都被过滤掉了），标记为完成但记录原因
        should_mark_done = True
        logger.info("强制仓库处理完成: 无有效强制仓库，任务状态: done")
    else:
        # 有强制仓库，只要不是全部失败就标记为完成
        should_mark_done = len(failure_statuses) < len(forced_targets)
        success_count = len(forced_targets) - len(failure_statuses)
        logger.info(f"强制仓库处理完成: {success_count} 个成功, {len(failure_statuses)} 个失败，任务状态: {'done' if should_mark_done else 'failed'}")
    
    return should_mark_done, failure_statuses


def process_normal_targets(normal_targets: List[Target], task_row: Dict[str, Any], session: requests.Session, args: Dict[str, Any]):
    """
    处理普通仓库（多线程）
    """
    global _shutdown_requested
    
    if not normal_targets or _shutdown_requested:
        return
    
    task_id = task_row['id']
    login = task_row['github_login']
    threads = args.get('threads', 1)
    
    logger.info(f"开始处理 {len(normal_targets)} 个普通仓库，使用 {threads} 个线程")
    
    def process_target_with_logging(target):
        if _shutdown_requested:
            return
        
        internal_status, message, contacts_found = process_single_target(target, task_row, session, args)
        write_log_to_db_original(task_id, target, internal_status, message, args)
        
        # 添加延迟
        time.sleep(0.5)
    
    # 使用线程池处理
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        
        for target in normal_targets:
            if _shutdown_requested:
                break
            
            future = executor.submit(process_target_with_logging, target)
            futures.append(future)
        
        # 等待完成
        for future in as_completed(futures):
            if _shutdown_requested:
                # 取消未完成的任务
                for f in futures:
                    f.cancel()
                break
            
            try:
                future.result()
            except Exception as e:
                logger.error(f"普通仓库处理异常: {e}")
    
    logger.info("普通仓库处理完成")


def run_dry_mode(task_row: Dict[str, Any], session: requests.Session, args: Dict[str, Any]):
    """试运行模式"""
    login = task_row['github_login']
    task_id = task_row['id']
    
    logger.info(f"=== 试运行模式: 任务 {task_id}, 用户 {login} ===")
    
    # 获取目标
    forced_targets = get_forced_targets(task_row)
    normal_targets = get_normal_targets(task_row, limit=50, session=session)
    
    forced_targets = validate_targets(forced_targets)
    normal_targets = validate_targets(normal_targets)
    
    print(f"\n强制仓库 ({len(forced_targets)} 个):")
    for i, target in enumerate(forced_targets, 1):
        print(f"  {i}. {target.repo_full_name}")
        print(f"     URL: {target.repo_url}")
        print(f"     类型: {target.meta.get('type', 'unknown')}")
    
    print(f"\n普通仓库 ({len(normal_targets)} 个，按 pushed_at 降序):")
    for i, target in enumerate(normal_targets, 1):
        print(f"  {i}. {target.repo_full_name}")
        print(f"     URL: {target.repo_url}")
        pushed_at = target.meta.get('pushed_at', 'unknown')
        print(f"     最后推送: {pushed_at}")
    
    print(f"\n预期日志条目:")
    print(f"  - 强制仓库: {len(forced_targets)} 条日志")
    print(f"  - 普通仓库: {len(normal_targets)} 条日志")
    print(f"  - 总计: {len(forced_targets) + len(normal_targets)} 条日志")
    
    print(f"\n任务状态预期:")
    print(f"  - 强制仓库处理完成后 → status='done'")
    print(f"  - 仅当所有强制仓库都失败 → status='failed'")
    
    logger.info("试运行完成")


def process_follow_discovery(task_row: Dict[str, Any], args: Dict[str, Any]):
    """
    处理关注发现逻辑
    
    Args:
        task_row: 任务记录
        args: 命令行参数字典
    """
    global _shutdown_requested
    
    task_id = task_row['id']
    seed_login = task_row['github_login']
    
    # 提取参数
    follow_depth = args.get('follow_depth', 0)
    per_side = args.get('follow_limit_per_side', 50)
    d2_cap = args.get('follow_d2_cap', 5000)
    sleep_min = args.get('follow_sleep_min_ms', 300)
    sleep_max = args.get('follow_sleep_max_ms', 800)
    user_agent = args.get('follow_user_agent')
    
    logger.info(f"FOLLOW|seed={seed_login}|depth={follow_depth}|per_side={per_side}|d2_cap={d2_cap}")
    
    try:
        # 创建专用会话
        discovery_session = create_discovery_session(user_agent)
        
        # 执行关注发现
        discovery_result = discover_logins(
            seed_login=seed_login,
            depth=follow_depth,
            per_side=per_side,
            d2_cap=d2_cap,
            session=discovery_session,
            sleep_range=(sleep_min, sleep_max)
        )
        
        if _shutdown_requested:
            logger.warning("关注发现被用户中断")
            return
        
        # 收集所有发现的登录名
        d1_followers = discovery_result["d1_followers"]
        d1_following = discovery_result["d1_following"]
        d2_logins = discovery_result["d2"]
        
        all_discovered_logins = d1_followers | d1_following | d2_logins
        
        # 写入数据库
        inserted_count = 0
        duplicate_count = 0
        
        if not args.get('dry_run') and all_discovered_logins:
            from db.dao import DatabaseDAO
            dao = DatabaseDAO()
            
            for login in all_discovered_logins:
                if _shutdown_requested:
                    break
                
                try:
                    is_new, record_id = dao.upsert_github_login(login)
                    if is_new:
                        inserted_count += 1
                    else:
                        duplicate_count += 1
                except Exception as e:
                    logger.warning(f"插入登录名 {login} 失败: {e}")
                    continue
        
        # 写入概要日志到 crawl_logs
        message = (
            f"d1_followers={len(d1_followers)}; d1_following={len(d1_following)}; "
            f"d2_total={len(d2_logins)}; inserted={inserted_count}; dup={duplicate_count}"
        )
        
        if args.get('dry_run'):
            message = f"[DRY-RUN] {message}"
        
        write_log_to_db(
            task_id=task_id,
            target=None,  # 没有具体的target
            internal_status='SUCCESS_FOUND',  # 映射为success
            message=message,
            args=args,
            task_type='follow_discovery'
        )
        
        logger.info(f"关注发现完成: 发现 {len(all_discovered_logins)} 个登录名，新增 {inserted_count} 个，重复 {duplicate_count} 个")
        
    except Exception as e:
        logger.error(f"关注发现失败: {e}")
        
        # 写入失败日志
        write_log_to_db(
            task_id=task_id,
            target=None,
            internal_status='FAIL_FETCH',  # 映射为fail
            message="fetch_failed",
            args=args,
            task_type='follow_discovery'
        )


def write_log_to_db(task_id: int, target: Optional[Target], internal_status: str, message: str, args: Dict[str, Any], task_type: Optional[str] = None) -> int:
    """
    写入爬取日志到数据库（原文入库模式）
    """
    crawl_logs_status = map_to_crawl_logs(internal_status)
    
    # 特殊处理：原文入库模式的日志映射
    if internal_status == SUCCESS_NONE and message == "dup":
        crawl_logs_status = "skip"  # 重复内容映射为skip
    
    if args.get('dry_run'):
        logger.info(f"[DRY-RUN] 写入日志: task_id={task_id}, task_type={task_type}, "
                   f"status={crawl_logs_status}, message={message}")
        return 0
    
    try:
        # 使用真实的数据库写入
        from db.dao import DatabaseDAO
        dao = DatabaseDAO()
        
        url = target.repo_url if target else None
        
        # 确定task_type
        if task_type:
            task_type_final = task_type
        elif target:
            if target.repo_full_name.endswith('.github.io'):
                task_type_final = 'github_io'
            else:
                task_type_final = 'profile_readme'
        else:
            task_type_final = ''
        
        log_id = dao.write_crawl_log(
            task_id=task_id,
            source='github',
            status=crawl_logs_status,
            message=message,
            url=url,
            task_type=task_type_final
        )
        
        if log_id:
            logger.debug(f"日志已写入: log_id={log_id}, task_id={task_id}, task_type={task_type_final}")
            return log_id
        else:
            logger.error(f"日志写入失败: task_id={task_id}, task_type={task_type_final}")
            return 0
        
    except Exception as e:
        logger.error(f"写入日志失败: {e}")
        return 0


def main():
    """主函数"""
    global _current_task_id
    
    # 解析参数
    args = parse_args()
    args_dict = vars(args)
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 设置信号处理
    setup_signal_handlers()
    
    logger.info("GitHub README 原文入库爬虫启动")
    
    # 结构化BOOT日志
    boot_log = (
        f"BOOT|timeout={args_dict.get('timeout', 30)}"
        f"|retries={args_dict.get('retries', 3)}"
        f"|threads={args_dict.get('threads', 1)}"
        f"|use_selenium={args_dict.get('use_selenium', False)}"
        f"|dry_run={args_dict.get('dry_run', False)}"
        f"|follow_depth={args_dict.get('follow_depth', 0)}"
    )
    logger.info(boot_log)
    
    try:
        # 获取任务
        task_row = fetch_task_from_db(args_dict)
        if not task_row:
            logger.info("无待处理任务（github）")
            return 0
        
        _current_task_id = task_row['id']
        login = task_row['github_login']
        
        # 验证任务
        if task_row.get('source') != 'github':
            logger.warning(f"任务 {task_row['id']} 不是 GitHub 任务，跳过")
            return 0
        
        # TASK_PICKED 结构化日志
        task_picked_log = f"TASK_PICKED|task_id={task_row['id']}|login={login}"
        logger.info(task_picked_log)
        
        # 创建HTTP会话
        session = create_session(args_dict)
        
        # 试运行模式
        if args.dry_run:
            run_dry_mode(task_row, session, args_dict)
            return 0
        
        # 更新任务状态为运行中
        update_task_status_in_db(task_row['id'], 'running', "开始处理", args_dict)
        
        # 获取目标仓库
        logger.info("获取目标仓库列表...")
        # 根据参数决定是否启用仓库存在性检查
        validate_existence = not args_dict.get('disable_repo_validation', False)
        forced_targets = get_forced_targets(task_row, validate_existence=validate_existence, session=session)
        normal_targets = get_normal_targets(task_row, limit=50, session=session)
        
        forced_targets = validate_targets(forced_targets)
        normal_targets = validate_targets(normal_targets)
        
        logger.info(f"目标统计: 强制={len(forced_targets)}, 普通={len(normal_targets)}")
        
        # 处理强制仓库
        should_mark_done, failure_statuses = process_forced_targets(forced_targets, task_row, session, args_dict)
        
        if _shutdown_requested:
            update_task_status_in_db(task_row['id'], 'failed', "用户中断", args_dict)
            return 2
        
        # 更新任务状态
        if should_mark_done:
            if not forced_targets:
                update_task_status_in_db(task_row['id'], 'done', "无有效强制仓库，跳过处理", args_dict)
            else:
                success_count = len(forced_targets) - len(failure_statuses)
                update_task_status_in_db(task_row['id'], 'done', f"强制仓库处理完成 ({success_count}/{len(forced_targets)} 成功)", args_dict)
        else:
            failure_msg = f"所有强制仓库失败: {','.join(failure_statuses)}"
            update_task_status_in_db(task_row['id'], 'failed', failure_msg, args_dict)
        
        # 处理普通仓库（原文入库模式已禁用）
        if normal_targets and not _shutdown_requested:
            logger.info("原文入库模式: 跳过普通仓库处理")
            # process_normal_targets(normal_targets, task_row, session, args_dict)
        
        if _shutdown_requested:
            logger.warning("处理被用户中断")
            return 2
        
        # Follow Discovery 处理（在强制仓库流程结束后）
        follow_depth = args_dict.get('follow_depth', 0)
        if follow_depth > 0 and not _shutdown_requested:
            process_follow_discovery(task_row, args_dict)
        
        logger.info("任务处理完成")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("收到中断信号")
        if _current_task_id:
            update_task_status_in_db(_current_task_id, 'failed', "用户中断", args_dict)
        return 2
    except Exception as e:
        logger.error(f"任务处理失败: {e}", exc_info=True)
        if _current_task_id:
            update_task_status_in_db(_current_task_id, 'failed', f"系统错误: {str(e)}", args_dict)
        return 1


if __name__ == "__main__":
    sys.exit(main())