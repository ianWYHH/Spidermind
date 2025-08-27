"""
目标仓库枚举模块
负责获取强制仓库和普通仓库列表
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .states import FAIL_FETCH, classify_exception


logger = logging.getLogger(__name__)

# 仓库存在性缓存，避免重复检查
_repo_existence_cache: Dict[str, bool] = {}


@dataclass
class Target:
    """目标仓库信息"""
    login: str                    # GitHub 用户名
    repo_full_name: str          # 完整仓库名 (owner/repo)
    repo_url: str                # 仓库 URL
    is_forced: bool              # 是否为强制仓库
    meta: Dict[str, Any]         # 元数据 (pushed_at, repo_id 等)


def get_forced_targets(task_row: Dict[str, Any], validate_existence: bool = True, session: Optional[requests.Session] = None) -> List[Target]:
    """
    获取强制处理的目标仓库
    
    强制仓库规则：
    1. /<login>/<login> (Profile 仓库)
    2. /<login>/<login>.github.io (个人站点)
    
    Args:
        task_row: 任务记录，必须包含 github_login 字段
        validate_existence: 是否验证仓库存在性，默认True
        session: HTTP会话对象，用于存在性检查
        
    Returns:
        List[Target]: 强制目标列表（如果validate_existence=True，只返回存在的仓库）
    """
    login = task_row.get('github_login')
    if not login:
        logger.error("任务记录缺少 github_login 字段")
        return []
    
    targets = []
    
    # 1. Profile 仓库: /<login>/<login>
    profile_repo = f"{login}/{login}"
    profile_url = f"https://github.com/{profile_repo}"
    targets.append(Target(
        login=login,
        repo_full_name=profile_repo,
        repo_url=profile_url,
        is_forced=True,
        meta={'type': 'profile', 'priority': 1}
    ))
    
    # 2. GitHub Pages 仓库: /<login>/<login>.github.io
    pages_repo = f"{login}/{login}.github.io"
    pages_url = f"https://github.com/{pages_repo}"
    targets.append(Target(
        login=login,
        repo_full_name=pages_repo,
        repo_url=pages_url,
        is_forced=True,
        meta={'type': 'github_pages', 'priority': 1}
    ))
    
    logger.debug(f"生成强制目标: {[t.repo_full_name for t in targets]}")
    
    # 可选的存在性验证
    if validate_existence:
        targets = validate_repository_existence(targets, session)
        logger.info(f"强制仓库存在性检查完成，有效仓库: {len(targets)}/2")
    
    return targets


def get_normal_targets(task_row: Dict[str, Any], limit: int = 50, session: Optional[requests.Session] = None) -> List[Target]:
    """
    获取普通目标仓库列表（原文入库模式禁用）
    
    Args:
        task_row: 任务记录
        limit: 限制数量（忽略）
        session: HTTP 会话（忽略）
        
    Returns:
        List[Target]: 空列表（原文入库模式不处理普通仓库）
    """
    github_login = task_row['github_login']
    logger.info(f"原文入库模式: 跳过用户 {github_login} 的普通仓库处理")
    return []  # 原文入库模式禁用普通仓库


def _fetch_user_repositories(login: str, session: requests.Session, limit: int) -> List[Dict[str, Any]]:
    """
    从 GitHub 用户页面抓取仓库列表
    
    优先使用 HTML 解析，避免 API 限制
    
    Args:
        login: GitHub 用户名
        session: HTTP 会话
        limit: 限制数量
        
    Returns:
        List[Dict]: 仓库信息列表，按 pushed_at 降序
    """
    repos = []
    
    try:
        # 方法1: 尝试解析用户页面的仓库 tab
        repos = _parse_repositories_from_profile_page(login, session, limit)
        
        if repos:
            logger.debug(f"从用户页面获取到 {len(repos)} 个仓库")
            return repos
    except Exception as e:
        logger.warning(f"从用户页面解析仓库失败: {e}")
    
    try:
        # 方法2: 备用方案 - 使用 GitHub API（可能有限制）
        repos = _fetch_repositories_via_api(login, session, limit)
        
        if repos:
            logger.debug(f"从 API 获取到 {len(repos)} 个仓库")
            return repos
    except Exception as e:
        logger.warning(f"从 API 获取仓库失败: {e}")
    
    logger.error(f"无法获取用户 {login} 的仓库列表")
    return []


def _parse_repositories_from_profile_page(login: str, session: requests.Session, limit: int) -> List[Dict[str, Any]]:
    """
    从 GitHub 用户主页解析仓库列表
    """
    repos = []
    page = 1
    
    while len(repos) < limit and page <= 5:  # 最多尝试5页
        url = f"https://github.com/{login}"
        params = {
            'tab': 'repositories',
            'type': 'source',  # 只要源代码仓库
            'sort': 'updated',  # 按更新时间排序
            'page': page
        }
        
        logger.debug(f"请求用户仓库页面: {url} (page {page})")
        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 查找仓库列表容器
        repo_items = soup.find_all('div', {'class': re.compile(r'Box-row.*repo.*')})
        if not repo_items:
            # 尝试其他可能的选择器
            repo_items = soup.find_all('li', {'class': re.compile(r'.*repo.*')})
        
        if not repo_items:
            logger.debug(f"页面 {page} 未找到仓库项")
            break
        
        page_repos = []
        for item in repo_items:
            try:
                repo_info = _parse_single_repo_item(item, login)
                if repo_info:
                    page_repos.append(repo_info)
            except Exception as e:
                logger.debug(f"解析仓库项失败: {e}")
                continue
        
        if not page_repos:
            logger.debug(f"页面 {page} 未解析到有效仓库")
            break
        
        repos.extend(page_repos)
        page += 1
        
        # 添加延迟避免请求过快
        time.sleep(0.5)
    
    # 按 pushed_at 排序（如果有的话）
    repos.sort(key=lambda x: x.get('pushed_at', ''), reverse=True)
    
    return repos[:limit]


def _parse_single_repo_item(item, login: str) -> Optional[Dict[str, Any]]:
    """
    解析单个仓库项元素
    """
    # 查找仓库名链接
    repo_link = item.find('a', href=re.compile(r'^/' + re.escape(login) + r'/[^/]+/?$'))
    if not repo_link:
        return None
    
    repo_name = repo_link.get_text().strip()
    full_name = f"{login}/{repo_name}"
    html_url = f"https://github.com{repo_link['href']}"
    
    # 提取更新时间
    pushed_at = ""
    time_elem = item.find('relative-time')
    if time_elem and time_elem.get('datetime'):
        pushed_at = time_elem['datetime']
    
    # 提取编程语言
    language = ""
    lang_elem = item.find('span', {'itemprop': 'programmingLanguage'})
    if lang_elem:
        language = lang_elem.get_text().strip()
    
    return {
        'full_name': full_name,
        'name': repo_name,
        'html_url': html_url,
        'pushed_at': pushed_at,
        'language': language,
        'stargazers_count': 0,  # 难以从页面精确提取
        'id': 0  # 页面上没有 repo_id
    }


def _fetch_repositories_via_api(login: str, session: requests.Session, limit: int) -> List[Dict[str, Any]]:
    """
    通过 GitHub API 获取仓库列表（备用方案）
    """
    repos = []
    per_page = min(100, limit)
    page = 1
    
    while len(repos) < limit and page <= 5:
        url = f"https://api.github.com/users/{login}/repos"
        params = {
            'type': 'owner',
            'sort': 'updated',
            'direction': 'desc',
            'per_page': per_page,
            'page': page
        }
        
        logger.debug(f"请求 GitHub API: {url} (page {page})")
        response = session.get(url, params=params, timeout=10)
        
        if response.status_code == 403:
            logger.warning("GitHub API 限制，跳过 API 方式")
            break
        
        response.raise_for_status()
        page_repos = response.json()
        
        if not page_repos:
            break
        
        repos.extend(page_repos)
        page += 1
        
        # API 限制延迟
        time.sleep(1)
    
    return repos[:limit]


def check_repository_exists(repo_full_name: str, session: Optional[requests.Session] = None) -> bool:
    """
    检查GitHub仓库是否存在
    
    Args:
        repo_full_name: 仓库全名，格式为 owner/repo
        session: HTTP会话对象
        
    Returns:
        bool: 仓库是否存在
    """
    # 检查缓存
    if repo_full_name in _repo_existence_cache:
        logger.debug(f"从缓存获取仓库存在性: {repo_full_name} = {_repo_existence_cache[repo_full_name]}")
        return _repo_existence_cache[repo_full_name]
    
    if session is None:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    try:
        url = f"https://github.com/{repo_full_name}"
        logger.debug(f"检查仓库存在性: {url}")
        
        response = session.head(url, timeout=5, allow_redirects=True)
        exists = response.status_code == 200
        
        # 缓存结果
        _repo_existence_cache[repo_full_name] = exists
        
        logger.debug(f"仓库 {repo_full_name} 存在性: {exists} (状态码: {response.status_code})")
        return exists
        
    except Exception as e:
        logger.debug(f"检查仓库存在性失败 {repo_full_name}: {e}")
        # 异常时不缓存，下次再试
        return False


def validate_repository_existence(targets: List[Target], session: Optional[requests.Session] = None) -> List[Target]:
    """
    验证目标仓库的存在性
    
    Args:
        targets: 目标列表
        session: HTTP会话对象
        
    Returns:
        List[Target]: 存在的目标仓库列表
    """
    if not targets:
        return targets
    
    existing_targets = []
    
    for target in targets:
        exists = check_repository_exists(target.repo_full_name, session)
        
        if exists:
            existing_targets.append(target)
            logger.debug(f"✓ 仓库存在: {target.repo_full_name}")
        else:
            logger.info(f"✗ 仓库不存在，跳过: {target.repo_full_name}")
            
        # 添加延迟避免请求过快
        time.sleep(0.2)
    
    return existing_targets


def validate_targets(targets: List[Target], check_existence: bool = False, session: Optional[requests.Session] = None) -> List[Target]:
    """
    验证目标列表的有效性
    
    Args:
        targets: 目标列表
        check_existence: 是否检查仓库存在性
        session: HTTP会话对象
        
    Returns:
        List[Target]: 验证后的目标列表
    """
    valid_targets = []
    
    for target in targets:
        if not target.login or not target.repo_full_name or not target.repo_url:
            logger.warning(f"跳过无效目标: {target}")
            continue
        
        # 验证 URL 格式
        parsed = urlparse(target.repo_url)
        if not parsed.netloc or 'github.com' not in parsed.netloc:
            logger.warning(f"跳过无效 GitHub URL: {target.repo_url}")
            continue
        
        valid_targets.append(target)
    
    # 可选的存在性检查
    if check_existence:
        valid_targets = validate_repository_existence(valid_targets, session)
    
    return valid_targets


def clear_repository_cache():
    """清空仓库存在性缓存"""
    global _repo_existence_cache
    _repo_existence_cache.clear()
    logger.info("仓库存在性缓存已清空")