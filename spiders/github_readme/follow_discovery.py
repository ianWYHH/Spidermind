#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Follow Discovery 模块
从种子用户出发，抓取 followers 与 following，进行两层穿透发现
"""

import logging
import random
import re
import time
from typing import Dict, Set, Tuple, Optional, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

# GitHub 登录名验证正则
GITHUB_LOGIN_PATTERN = re.compile(r'^[a-zA-Z0-9-]{1,39}$')


def is_valid_github_login(login: str) -> bool:
    """
    验证 GitHub 登录名是否合法
    
    Args:
        login: 待验证的登录名
        
    Returns:
        bool: 是否为合法的 GitHub 登录名
    """
    if not login or not isinstance(login, str):
        return False
    
    # GitHub 用户名规则：1-39个字符，只能包含字母、数字、连字符
    # 不能以连字符开头或结尾，不能连续多个连字符
    if not GITHUB_LOGIN_PATTERN.match(login):
        return False
    
    # 不能以连字符开头或结尾
    if login.startswith('-') or login.endswith('-'):
        return False
    
    # 不能连续多个连字符
    if '--' in login:
        return False
    
    return True


def random_sleep(sleep_range: Tuple[int, int]):
    """
    随机休眠
    
    Args:
        sleep_range: (min_ms, max_ms) 休眠时间范围（毫秒）
    """
    min_ms, max_ms = sleep_range
    sleep_ms = random.randint(min_ms, max_ms)
    time.sleep(sleep_ms / 1000.0)


def parse_follow_page(html_content: str, base_url: str) -> Set[str]:
    """
    解析 GitHub followers/following 页面，提取登录名
    
    Args:
        html_content: HTML 页面内容
        base_url: 基础 URL
        
    Returns:
        Set[str]: 提取到的有效登录名集合
    """
    logins = set()
    
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # GitHub 用户列表的常见选择器
        # 尝试多种可能的选择器，适配DOM变更
        selectors = [
            'a[href^="/"][href*="/"]:not([href="/"])',  # 通用用户链接
            '.d-table-cell a[href^="/"]',               # 表格布局
            '.Box-row a[href^="/"]',                    # Box布局  
            '[data-hovercard-type="user"] a',          # 悬浮卡片
            '.follow-list-item a[href^="/"]',           # 关注列表项
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '')
                if not href or href == '/':
                    continue
                
                # 提取登录名 (href="/username" 或 "/username/...")
                parts = href.strip('/').split('/')
                if parts and parts[0]:
                    potential_login = parts[0]
                    
                    # 过滤掉明显的非用户链接
                    if potential_login.lower() in {
                        'orgs', 'organizations', 'settings', 'notifications', 
                        'explore', 'marketplace', 'pricing', 'team', 'login',
                        'join', 'about', 'contact', 'security', 'terms', 'privacy'
                    }:
                        continue
                    
                    if is_valid_github_login(potential_login):
                        logins.add(potential_login.lower())
            
            # 如果找到了用户，就不再尝试其他选择器
            if logins:
                break
        
        logger.debug(f"从页面解析到 {len(logins)} 个有效登录名")
        
    except Exception as e:
        logger.warning(f"解析页面失败: {e}")
    
    return logins


def fetch_follow_page(login: str, tab: str, session: requests.Session, 
                     sleep_range: Tuple[int, int], per_side: int) -> Set[str]:
    """
    抓取单个用户的 followers 或 following 页面
    
    Args:
        login: 用户登录名
        tab: 'followers' 或 'following'
        session: HTTP 会话
        sleep_range: 休眠时间范围
        per_side: 每个方向的限制数量
        
    Returns:
        Set[str]: 发现的登录名集合
    """
    all_logins = set()
    page = 1
    max_pages = 10  # 防止无限循环
    
    while len(all_logins) < per_side and page <= max_pages:
        try:
            url = f"https://github.com/{login}"
            params = {'tab': tab}
            if page > 1:
                params['page'] = page
            
            logger.debug(f"请求 {login} 的 {tab}，页面 {page}")
            
            # 随机休眠
            random_sleep(sleep_range)
            
            response = session.get(url, params=params, timeout=10)
            
            # 处理HTTP错误
            if response.status_code == 429:
                # 速率限制，指数退避
                backoff_time = random.uniform(2.0, 5.0)
                logger.warning(f"遇到速率限制，退避 {backoff_time:.1f} 秒")
                time.sleep(backoff_time)
                continue
            elif response.status_code >= 500:
                # 服务器错误，重试一次
                logger.warning(f"服务器错误 {response.status_code}，重试一次")
                time.sleep(random.uniform(2.0, 5.0))
                response = session.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"重试失败，跳过 {login} 的 {tab}")
                    break
            elif response.status_code == 404:
                logger.debug(f"用户 {login} 不存在或页面不可访问")
                break
            elif response.status_code != 200:
                logger.warning(f"HTTP {response.status_code}，跳过 {login} 的 {tab}")
                break
            
            # 解析页面
            page_logins = parse_follow_page(response.text, url)
            
            if not page_logins:
                # 没有更多数据，结束抓取
                logger.debug(f"{login} 的 {tab} 页面 {page} 无数据，结束抓取")
                break
            
            all_logins.update(page_logins)
            page += 1
            
            # 达到限制数量，截断
            if len(all_logins) >= per_side:
                break
                
        except Exception as e:
            logger.warning(f"抓取 {login} 的 {tab} 失败: {e}")
            break
    
    # 截断到指定数量
    result = set(list(all_logins)[:per_side])
    logger.info(f"用户 {login} 的 {tab}: 发现 {len(result)} 个登录名")
    
    return result


def discover_logins(seed_login: str, depth: int, per_side: int, d2_cap: int, 
                   session: requests.Session, sleep_range: Tuple[int, int]) -> Dict[str, Any]:
    """
    从种子用户出发，进行关注关系发现
    
    Args:
        seed_login: 种子用户登录名
        depth: 发现深度 (0/1/2)
        per_side: 每个用户 followers 与 following 各取前N个
        d2_cap: 第二层发现的全局上限
        session: HTTP 会话
        sleep_range: (min_ms, max_ms) 休眠时间范围
        
    Returns:
        dict: {
            "d1_followers": set[str],    # 第一层 followers
            "d1_following": set[str],    # 第一层 following  
            "d2": set[str],              # 第二层发现的所有登录名
            "seed_processed": bool,      # 种子用户是否处理成功
            "d1_processed": int,         # 第一层处理成功的用户数
            "d2_collected": int          # 第二层实际收集到的用户数
        }
    """
    result = {
        "d1_followers": set(),
        "d1_following": set(), 
        "d2": set(),
        "seed_processed": False,
        "d1_processed": 0,
        "d2_collected": 0
    }
    
    if depth == 0:
        logger.info("关注发现深度为0，跳过处理")
        return result
    
    logger.info(f"开始关注发现: seed={seed_login}, depth={depth}, per_side={per_side}, d2_cap={d2_cap}")
    
    # 第一层：抓取种子用户的 followers 和 following
    try:
        logger.info(f"处理种子用户: {seed_login}")
        
        # 抓取 followers
        d1_followers = fetch_follow_page(seed_login, 'followers', session, sleep_range, per_side)
        result["d1_followers"] = d1_followers
        
        # 抓取 following  
        d1_following = fetch_follow_page(seed_login, 'following', session, sleep_range, per_side)
        result["d1_following"] = d1_following
        
        result["seed_processed"] = True
        logger.info(f"种子用户处理完成: followers={len(d1_followers)}, following={len(d1_following)}")
        
    except Exception as e:
        logger.error(f"处理种子用户失败: {e}")
        return result
    
    # 如果只要求第一层，直接返回
    if depth == 1:
        logger.info("仅处理第一层，发现完成")
        return result
    
    # 第二层：对第一层的并集进行扩展
    d1_all = result["d1_followers"] | result["d1_following"]
    d2_logins = set()
    
    logger.info(f"开始第二层发现，处理 {len(d1_all)} 个第一层用户")
    
    for i, d1_login in enumerate(d1_all):
        if len(d2_logins) >= d2_cap:
            logger.info(f"达到第二层上限 {d2_cap}，停止扩展")
            break
        
        try:
            logger.debug(f"处理第一层用户 {i+1}/{len(d1_all)}: {d1_login}")
            
            # 为了控制总量，动态调整每个用户的抓取量
            remaining_cap = d2_cap - len(d2_logins)
            remaining_users = len(d1_all) - i
            
            # 保守估算：每个用户平均能贡献的新登录名
            per_user_limit = min(per_side, max(10, remaining_cap // max(1, remaining_users)))
            
            # 抓取该用户的 followers 和 following
            user_followers = fetch_follow_page(d1_login, 'followers', session, sleep_range, per_user_limit)
            user_following = fetch_follow_page(d1_login, 'following', session, sleep_range, per_user_limit)
            
            # 合并到第二层集合
            user_d2 = user_followers | user_following
            d2_logins.update(user_d2)
            
            result["d1_processed"] += 1
            
            # 每处理一定数量用户打印进度
            if (i + 1) % 10 == 0 or (i + 1) == len(d1_all):
                logger.info(f"第二层进度: {i+1}/{len(d1_all)}, 已收集 {len(d2_logins)} 个登录名")
            
        except Exception as e:
            logger.warning(f"处理第一层用户 {d1_login} 失败: {e}")
            continue
    
    # 从第二层结果中移除第一层已有的用户，避免重复
    d2_logins = d2_logins - d1_all - {seed_login}
    
    # 截断到上限
    if len(d2_logins) > d2_cap:
        d2_logins = set(list(d2_logins)[:d2_cap])
    
    result["d2"] = d2_logins
    result["d2_collected"] = len(d2_logins)
    
    logger.info(f"第二层发现完成: 处理了 {result['d1_processed']}/{len(d1_all)} 个用户，收集到 {len(d2_logins)} 个新登录名")
    
    return result


def create_discovery_session(user_agent: Optional[str] = None) -> requests.Session:
    """
    创建用于关注发现的 HTTP 会话
    
    Args:
        user_agent: 可选的用户代理字符串
        
    Returns:
        requests.Session: 配置好的会话对象
    """
    session = requests.Session()
    
    # 设置用户代理
    if not user_agent:
        user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
    
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    })
    
    return session


# 验收示例（注释中的测试用例）
"""
验收测试用例：

1. 指定种子 login=octocat，follow_depth=2，per_side=10，d2_cap=200：
   - 控制台应显示 BOOT 与 FOLLOW 概要日志
   - 数据库 github_users 应新增若干 login（重复被忽略）
   - crawl_logs 应出现一条 task_type='follow_discovery' 的 success 记录
   - message 应包含 d1_followers/d1_following/d2_total/inserted/dup 指标

2. 设置 follow_depth=0 时：
   - 不应触发发现逻辑
   - 不应有相关日志输出

测试命令示例：
python -m spiders.github_readme.runner --task-id <id> --follow-depth 2 --follow-limit-per-side 10 --follow-d2-cap 200 --verbose
"""