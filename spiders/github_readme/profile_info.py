"""
个人信息解析模块
用于强制仓库的额外个人信息获取
"""

import logging
import re
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .states import classify_exception


logger = logging.getLogger(__name__)


def parse_profile_info(login: str, session: requests.Session, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取 GitHub 用户的完整个人信息
    
    Args:
        login: GitHub 用户名
        session: HTTP 会话对象
        args: 命令行参数
        
    Returns:
        Dict[str, Any]: 个人信息字典
    """
    timeout = args.get('timeout', 10)
    
    profile_info = {
        # 基础信息
        'name': '',
        'bio': '',
        'company': '',
        'location': '',
        'blog': '',
        'twitter_username': '',
        'hireable': None,
        
        # 统计信息
        'followers': 0,
        'following': 0,
        'public_repos': 0,
        'public_gists': 0,
        
        # 组织信息
        'organizations': [],
        
        # 元数据
        'avatar_url': '',
        'gravatar_id': '',
        'created_at': '',
        'updated_at': '',
        
        # 获取状态
        'fetch_success': False,
        'fetch_method': '',
        'error': ''
    }
    
    try:
        # 方法1: 从用户主页解析
        profile_info = _parse_from_profile_page(login, session, timeout, profile_info)
        
        if profile_info['fetch_success']:
            logger.info(f"成功获取 {login} 的个人信息")
            return profile_info
        
        # 方法2: 备用 - 尝试 GitHub API（可能有限制）
        profile_info = _parse_from_api(login, session, timeout, profile_info)
        
        return profile_info
        
    except Exception as e:
        logger.error(f"获取个人信息异常 {login}: {e}")
        profile_info['error'] = str(e)
        return profile_info


def _parse_from_profile_page(login: str, session: requests.Session, timeout: int, profile_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 GitHub 用户主页解析个人信息
    """
    try:
        url = f"https://github.com/{login}"
        logger.debug(f"请求用户主页: {url}")
        
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 解析基础信息
        profile_info.update(_extract_basic_info(soup))
        
        # 解析统计信息
        profile_info.update(_extract_stats_info(soup))
        
        # 解析组织信息
        profile_info['organizations'] = _extract_organizations(soup)
        
        # 解析头像
        profile_info['avatar_url'] = _extract_avatar_url(soup)
        
        profile_info['fetch_success'] = True
        profile_info['fetch_method'] = 'profile_page'
        
        logger.debug(f"从主页解析成功: {login}")
        return profile_info
        
    except Exception as e:
        logger.warning(f"从主页解析失败 {login}: {e}")
        profile_info['error'] = f"profile_page_error: {str(e)}"
        return profile_info


def _extract_basic_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    从页面中提取基础信息
    """
    info = {}
    
    # 用户名
    name_selectors = [
        'span.p-name',
        '.h-card .p-name',
        '.vcard-fullname',
        'h1.vcard-names span'
    ]
    info['name'] = _extract_text_by_selectors(soup, name_selectors)
    
    # 个人简介
    bio_selectors = [
        '.p-note',
        '.user-profile-bio',
        '.js-user-profile-bio',
        '[data-bio-text]'
    ]
    info['bio'] = _extract_text_by_selectors(soup, bio_selectors)
    
    # 公司
    company_selectors = [
        '.p-org',
        '.vcard-detail[itemprop="worksFor"]',
        'span[itemprop="worksFor"]'
    ]
    info['company'] = _extract_text_by_selectors(soup, company_selectors)
    
    # 位置
    location_selectors = [
        '.p-label',
        '.vcard-detail[itemprop="homeLocation"]',
        'span[itemprop="homeLocation"]'
    ]
    info['location'] = _extract_text_by_selectors(soup, location_selectors)
    
    # 个人网站
    blog_selectors = [
        '.p-label a[href]',
        '.vcard-detail a[href]',
        'a.Link--primary[href]'
    ]
    blog_element = soup.select_one(', '.join(blog_selectors))
    if blog_element and blog_element.get('href'):
        href = blog_element['href']
        if href.startswith('http'):
            info['blog'] = href
        else:
            info['blog'] = ''
    else:
        info['blog'] = ''
    
    # Twitter 用户名
    twitter_selectors = [
        'a[href*="twitter.com"]',
        'a[href*="x.com"]'
    ]
    twitter_element = soup.select_one(', '.join(twitter_selectors))
    if twitter_element and twitter_element.get('href'):
        twitter_url = twitter_element['href']
        twitter_match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)', twitter_url)
        if twitter_match:
            info['twitter_username'] = twitter_match.group(1)
        else:
            info['twitter_username'] = ''
    else:
        info['twitter_username'] = ''
    
    # 可雇佣状态（较难从页面确定）
    info['hireable'] = None
    
    return info


def _extract_stats_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    提取统计信息
    """
    stats = {
        'followers': 0,
        'following': 0,
        'public_repos': 0,
        'public_gists': 0
    }
    
    # 粉丝数
    followers_selectors = [
        'a[href$="/followers"] span.text-bold',
        'a[href$="/followers"] strong',
        '.js-profile-editable-area a[href*="followers"] span'
    ]
    followers_text = _extract_text_by_selectors(soup, followers_selectors)
    stats['followers'] = _parse_number(followers_text)
    
    # 关注数
    following_selectors = [
        'a[href$="/following"] span.text-bold',
        'a[href$="/following"] strong',
        '.js-profile-editable-area a[href*="following"] span'
    ]
    following_text = _extract_text_by_selectors(soup, following_selectors)
    stats['following'] = _parse_number(following_text)
    
    # 仓库数
    repos_selectors = [
        'a[href$="?tab=repositories"] span.Counter',
        'nav a[href*="repositories"] span',
        '.UnderlineNav-item[href*="repositories"] span'
    ]
    repos_text = _extract_text_by_selectors(soup, repos_selectors)
    stats['public_repos'] = _parse_number(repos_text)
    
    # Gists 数（可能没有显示）
    gists_selectors = [
        'a[href*="gist.github.com"] span.Counter',
        'a[href$="?tab=gists"] span'
    ]
    gists_text = _extract_text_by_selectors(soup, gists_selectors)
    stats['public_gists'] = _parse_number(gists_text)
    
    return stats


def _extract_organizations(soup: BeautifulSoup) -> List[str]:
    """
    提取组织信息
    """
    organizations = []
    
    # 查找组织部分
    org_selectors = [
        '.border-top.py-3 a[data-hovercard-type="organization"]',
        '.js-profile-editable-area a[href*="/orgs/"]',
        'a[data-hovercard-type="organization"] img[alt]'
    ]
    
    org_elements = soup.select(', '.join(org_selectors))
    
    for element in org_elements:
        org_name = ''
        
        # 从链接中提取组织名
        href = element.get('href', '')
        if href:
            org_match = re.search(r'/orgs?/([^/]+)', href)
            if org_match:
                org_name = org_match.group(1)
        
        # 从 alt 属性提取
        if not org_name and element.name == 'img':
            alt = element.get('alt', '')
            if alt and alt.startswith('@'):
                org_name = alt[1:]
        
        # 从文本内容提取
        if not org_name:
            text = element.get_text().strip()
            if text and text.startswith('@'):
                org_name = text[1:]
        
        if org_name and org_name not in organizations:
            organizations.append(org_name)
    
    return organizations


def _extract_avatar_url(soup: BeautifulSoup) -> str:
    """
    提取头像 URL
    """
    avatar_selectors = [
        '.avatar-user',
        '.avatar img[src]',
        'img.avatar[src]'
    ]
    
    avatar_element = soup.select_one(', '.join(avatar_selectors))
    if avatar_element and avatar_element.get('src'):
        src = avatar_element['src']
        # 确保是完整 URL
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = 'https://github.com' + src
        return src
    
    return ''


def _parse_from_api(login: str, session: requests.Session, timeout: int, profile_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 GitHub API 获取个人信息（备用方案）
    """
    try:
        url = f"https://api.github.com/users/{login}"
        logger.debug(f"请求 GitHub API: {url}")
        
        response = session.get(url, timeout=timeout)
        
        if response.status_code == 403:
            logger.warning("GitHub API 限制，跳过 API 方式")
            profile_info['error'] = 'api_rate_limited'
            return profile_info
        
        response.raise_for_status()
        data = response.json()
        
        # 映射 API 字段到本地字段
        api_mapping = {
            'name': 'name',
            'bio': 'bio',
            'company': 'company',
            'location': 'location',
            'blog': 'blog',
            'twitter_username': 'twitter_username',
            'hireable': 'hireable',
            'followers': 'followers',
            'following': 'following',
            'public_repos': 'public_repos',
            'public_gists': 'public_gists',
            'avatar_url': 'avatar_url',
            'gravatar_id': 'gravatar_id',
            'created_at': 'created_at',
            'updated_at': 'updated_at'
        }
        
        for api_key, local_key in api_mapping.items():
            if api_key in data:
                profile_info[local_key] = data[api_key] or ''
        
        # 获取组织信息（需要额外请求）
        try:
            orgs_url = f"https://api.github.com/users/{login}/orgs"
            orgs_response = session.get(orgs_url, timeout=timeout)
            if orgs_response.status_code == 200:
                orgs_data = orgs_response.json()
                profile_info['organizations'] = [org['login'] for org in orgs_data]
            time.sleep(0.5)  # API 限制保护
        except:
            pass
        
        profile_info['fetch_success'] = True
        profile_info['fetch_method'] = 'api'
        
        logger.debug(f"从 API 解析成功: {login}")
        return profile_info
        
    except Exception as e:
        logger.warning(f"从 API 解析失败 {login}: {e}")
        profile_info['error'] = f"api_error: {str(e)}"
        return profile_info


def _extract_text_by_selectors(soup: BeautifulSoup, selectors: List[str]) -> str:
    """
    通过多个选择器尝试提取文本
    """
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text().strip()
            if text:
                return text
    return ''


def _parse_number(text: str) -> int:
    """
    解析数字文本（支持 k, m 等单位）
    """
    if not text:
        return 0
    
    # 移除空格和标点
    text = re.sub(r'[^\d.km]', '', text.lower())
    
    if not text:
        return 0
    
    try:
        if text.endswith('k'):
            return int(float(text[:-1]) * 1000)
        elif text.endswith('m'):
            return int(float(text[:-1]) * 1000000)
        else:
            return int(float(text))
    except (ValueError, IndexError):
        return 0


def validate_profile_info(profile_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证和清理个人信息
    """
    # 清理空字符串
    for key, value in profile_info.items():
        if isinstance(value, str) and not value.strip():
            profile_info[key] = ''
    
    # 验证数字字段
    numeric_fields = ['followers', 'following', 'public_repos', 'public_gists']
    for field in numeric_fields:
        if field in profile_info:
            try:
                profile_info[field] = max(0, int(profile_info[field] or 0))
            except (ValueError, TypeError):
                profile_info[field] = 0
    
    # 验证 URL 字段
    url_fields = ['blog', 'avatar_url']
    for field in url_fields:
        if field in profile_info and profile_info[field]:
            url = profile_info[field]
            if not url.startswith('http'):
                if field == 'blog' and '.' in url:
                    # 自动添加协议
                    profile_info[field] = f"https://{url}"
                else:
                    profile_info[field] = ''
    
    # 清理组织列表
    if 'organizations' in profile_info and isinstance(profile_info['organizations'], list):
        profile_info['organizations'] = [
            org for org in profile_info['organizations'] 
            if org and isinstance(org, str) and org.strip()
        ]
    
    return profile_info