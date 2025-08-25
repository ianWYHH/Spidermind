#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenReview API/HTML 客户端

实现OpenReview网站的数据抓取，包括论文信息和作者profile
Author: Spidermind
"""

import requests
import logging
import time
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class OpenReviewClient:
    """OpenReview客户端"""
    
    def __init__(self):
        """初始化OpenReview客户端"""
        self.base_url = "https://openreview.net"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.request_delay = 1.0  # 请求间隔
    
    def _make_request(self, url: str, max_retries: int = 3) -> Optional[requests.Response]:
        """
        发起HTTP请求，包含重试和错误处理
        
        Args:
            url: 请求URL
            max_retries: 最大重试次数
            
        Returns:
            requests.Response: 成功的响应，或None
        """
        for attempt in range(max_retries):
            try:
                # 请求间延迟
                if attempt > 0:
                    time.sleep(self.request_delay * (2 ** attempt))
                else:
                    time.sleep(self.request_delay)
                
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 404:
                    logger.debug(f"页面不存在: {url}")
                    return response
                elif response.status_code == 429:
                    # 速率限制
                    logger.warning(f"触发速率限制，等待更长时间: {url}")
                    time.sleep(5)
                    continue
                else:
                    logger.warning(f"请求失败 {response.status_code}: {url}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 (尝试 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return None
        
        return None
    
    def get_forum_info(self, forum_url: str) -> Optional[Dict[str, Any]]:
        """
        获取论文论坛信息，提取作者列表
        
        Args:
            forum_url: 论文论坛URL
            
        Returns:
            Dict: 论文和作者信息，或None
        """
        try:
            response = self._make_request(forum_url)
            if not response or response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return self._parse_forum_content(soup, forum_url)
            
        except Exception as e:
            logger.error(f"解析论文页面失败: {forum_url}, 错误: {e}")
            return None
    
    def _parse_forum_content(self, soup: BeautifulSoup, forum_url: str) -> Optional[Dict[str, Any]]:
        """解析论文论坛HTML内容"""
        try:
            # 提取论文标题
            title_element = soup.find('h2', class_='citation_title')
            if not title_element:
                title_element = soup.find('h1')
            if not title_element:
                title_element = soup.find('title')
            
            title = ""
            if title_element:
                title = title_element.get_text(strip=True)
                # 清理标题
                title = re.sub(r'\s+', ' ', title)
                title = title.replace('OpenReview', '').strip()
            
            # 提取作者信息
            authors = self._extract_authors_from_forum(soup, forum_url)
            
            # 提取基本论文信息
            paper_info = {
                'title': title,
                'url': forum_url,
                'authors': authors,
                'venue': self._extract_venue(soup),
                'abstract': self._extract_abstract(soup)
            }
            
            logger.debug(f"提取论文信息: {title}, 作者数: {len(authors)}")
            return paper_info
            
        except Exception as e:
            logger.error(f"解析论文内容失败: {forum_url}, 错误: {e}")
            return None
    
    def _extract_authors_from_forum(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """从论文页面提取作者信息"""
        authors = []
        
        # 尝试多种作者提取模式
        author_patterns = [
            # 模式1: 作者链接
            {'selector': 'a[href*="/profile"]', 'type': 'link'},
            # 模式2: 作者列表
            {'selector': '.authors a', 'type': 'link'},
            {'selector': '.author-list a', 'type': 'link'},
            # 模式3: 文本模式
            {'selector': '.authors', 'type': 'text'},
            {'selector': '.author-list', 'type': 'text'},
        ]
        
        for pattern in author_patterns:
            elements = soup.select(pattern['selector'])
            if elements:
                if pattern['type'] == 'link':
                    for element in elements:
                        author_info = self._parse_author_link(element, base_url)
                        if author_info and author_info not in authors:
                            authors.append(author_info)
                elif pattern['type'] == 'text':
                    for element in elements:
                        text_authors = self._parse_author_text(element.get_text())
                        authors.extend(text_authors)
                
                if authors:  # 如果找到作者就停止尝试其他模式
                    break
        
        # 如果没有找到作者，尝试从页面文本中提取
        if not authors:
            authors = self._extract_authors_from_text(soup)
        
        return authors[:10]  # 限制最多10个作者
    
    def _parse_author_link(self, element, base_url: str) -> Optional[Dict[str, Any]]:
        """解析作者链接元素"""
        href = element.get('href', '')
        name = element.get_text(strip=True)
        
        if not name or len(name) < 2:
            return None
        
        # 构建完整的profile URL
        profile_url = ""
        if href:
            if href.startswith('/'):
                profile_url = urljoin("https://openreview.net", href)
            elif href.startswith('http'):
                profile_url = href
        
        return {
            'name': name,
            'profile_url': profile_url,
            'affiliation': '',
            'email': ''
        }
    
    def _parse_author_text(self, text: str) -> List[Dict[str, Any]]:
        """从文本中解析作者列表"""
        authors = []
        
        # 清理文本
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 尝试按分隔符分割
        separators = [',', ';', '·', '、', ' and ', ' & ']
        author_names = [text]
        
        for sep in separators:
            new_names = []
            for name in author_names:
                new_names.extend([n.strip() for n in name.split(sep) if n.strip()])
            author_names = new_names
        
        # 过滤和验证作者名
        for name in author_names:
            name = name.strip()
            # 基本验证：包含字母，长度合理
            if re.search(r'[a-zA-Z]', name) and 2 <= len(name) <= 50:
                # 移除常见的非人名词汇
                if not any(word in name.lower() for word in ['university', 'institute', 'lab', 'department', 'email']):
                    authors.append({
                        'name': name,
                        'profile_url': '',
                        'affiliation': '',
                        'email': ''
                    })
        
        return authors
    
    def _extract_authors_from_text(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """从页面文本中提取作者信息"""
        authors = []
        
        # 查找可能包含作者信息的元素
        text_elements = soup.find_all(['p', 'div', 'span'], string=re.compile(r'[A-Z][a-z]+\s+[A-Z][a-z]+'))
        
        for element in text_elements:
            text = element.get_text()
            # 使用正则表达式查找人名模式
            name_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]*\.?){1,3}\b'
            matches = re.findall(name_pattern, text)
            
            for match in matches[:5]:  # 限制每个元素最多5个
                if len(match) >= 6 and len(match) <= 50:  # 名字长度限制
                    authors.append({
                        'name': match.strip(),
                        'profile_url': '',
                        'affiliation': '',
                        'email': ''
                    })
        
        return authors[:10]  # 总共限制10个
    
    def _extract_venue(self, soup: BeautifulSoup) -> str:
        """提取会议/期刊信息"""
        venue_selectors = [
            '.venue', '.conference', '.journal',
            '[class*="venue"]', '[class*="conference"]'
        ]
        
        for selector in venue_selectors:
            element = soup.select_one(selector)
            if element:
                venue = element.get_text(strip=True)
                if venue and len(venue) < 100:
                    return venue
        
        return ""
    
    def _extract_abstract(self, soup: BeautifulSoup) -> str:
        """提取摘要（简化版，仅用于检索关键信息）"""
        abstract_selectors = [
            '.abstract', '.note-content-value',
            '[class*="abstract"]', '.summary'
        ]
        
        for selector in abstract_selectors:
            element = soup.select_one(selector)
            if element:
                abstract = element.get_text(strip=True)
                if abstract and len(abstract) > 50:
                    # 截取前500字符
                    return abstract[:500] + ('...' if len(abstract) > 500 else '')
        
        return ""
    
    def get_profile_info(self, profile_url: str) -> Optional[Dict[str, Any]]:
        """
        获取用户profile信息
        
        Args:
            profile_url: 用户profile URL
            
        Returns:
            Dict: 用户信息，或None
        """
        try:
            response = self._make_request(profile_url)
            if not response or response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return self._parse_profile_content(soup, profile_url)
            
        except Exception as e:
            logger.error(f"解析profile页面失败: {profile_url}, 错误: {e}")
            return None
    
    def _parse_profile_content(self, soup: BeautifulSoup, profile_url: str) -> Optional[Dict[str, Any]]:
        """解析用户profile HTML内容"""
        try:
            # 提取profile信息
            profile_info = {
                'name': self._extract_profile_name(soup),
                'affiliation': self._extract_profile_affiliation(soup),
                'email': self._extract_profile_email(soup),
                'homepage': self._extract_profile_homepage(soup),
                'github': self._extract_profile_github(soup),
                'bio': self._extract_profile_bio(soup),
                'profile_url': profile_url
            }
            
            logger.debug(f"提取profile信息: {profile_info['name']}")
            return profile_info
            
        except Exception as e:
            logger.error(f"解析profile内容失败: {profile_url}, 错误: {e}")
            return None
    
    def _extract_profile_name(self, soup: BeautifulSoup) -> str:
        """提取用户姓名"""
        name_selectors = [
            'h1', 'h2.profile-name', '.profile-header h1',
            '.name', '[class*="name"]'
        ]
        
        for selector in name_selectors:
            element = soup.select_one(selector)
            if element:
                name = element.get_text(strip=True)
                if name and len(name) >= 2 and len(name) <= 50:
                    return name
        
        return ""
    
    def _extract_profile_affiliation(self, soup: BeautifulSoup) -> str:
        """提取机构信息"""
        affiliation_selectors = [
            '.affiliation', '.institution', '.organization',
            '[class*="affiliation"]', '[class*="institution"]'
        ]
        
        for selector in affiliation_selectors:
            element = soup.select_one(selector)
            if element:
                affiliation = element.get_text(strip=True)
                if affiliation and len(affiliation) <= 200:
                    return affiliation
        
        return ""
    
    def _extract_profile_email(self, soup: BeautifulSoup) -> str:
        """提取邮箱地址"""
        # 查找邮箱链接
        email_links = soup.find_all('a', href=re.compile(r'mailto:'))
        for link in email_links:
            href = link.get('href', '')
            if href.startswith('mailto:'):
                email = href.replace('mailto:', '').strip()
                if '@' in email and '.' in email:
                    return email
        
        # 从文本中提取邮箱
        text_content = soup.get_text()
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text_content)
        
        if emails:
            return emails[0]  # 返回第一个找到的邮箱
        
        return ""
    
    def _extract_profile_homepage(self, soup: BeautifulSoup) -> str:
        """提取个人主页链接"""
        homepage_patterns = [
            r'homepage', r'personal.*page', r'website',
            r'blog', r'www\.', r'http[s]?://[^/]*\.edu',
            r'http[s]?://[^/]*\.io', r'http[s]?://[^/]*\.me'
        ]
        
        # 查找链接
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            
            # 检查链接文本或URL是否匹配主页模式
            for pattern in homepage_patterns:
                if re.search(pattern, text) or re.search(pattern, href):
                    if href.startswith('http') and len(href) < 200:
                        return href
        
        return ""
    
    def _extract_profile_github(self, soup: BeautifulSoup) -> str:
        """提取GitHub链接"""
        github_links = soup.find_all('a', href=re.compile(r'github\.com'))
        
        for link in github_links:
            href = link.get('href', '')
            if 'github.com' in href and href.startswith('http'):
                return href
        
        return ""
    
    def _extract_profile_bio(self, soup: BeautifulSoup) -> str:
        """提取个人简介"""
        bio_selectors = [
            '.bio', '.biography', '.about', '.description',
            '[class*="bio"]', '[class*="about"]'
        ]
        
        for selector in bio_selectors:
            element = soup.select_one(selector)
            if element:
                bio = element.get_text(strip=True)
                if bio and len(bio) > 20:
                    # 截取前500字符
                    return bio[:500] + ('...' if len(bio) > 500 else '')
        
        return ""
    
    def extract_profile_id_from_url(self, profile_url: str) -> str:
        """从profile URL中提取profile ID"""
        try:
            # OpenReview profile URL格式: https://openreview.net/profile?id=xxxx
            # 或 https://openreview.net/profile/xxxx
            if '?id=' in profile_url:
                return profile_url.split('?id=')[1].split('&')[0]
            elif '/profile/' in profile_url:
                return profile_url.split('/profile/')[1].split('/')[0].split('?')[0]
            else:
                # 从URL中提取可能的ID
                parsed = urlparse(profile_url)
                if parsed.path:
                    parts = [p for p in parsed.path.split('/') if p]
                    if parts:
                        return parts[-1]
                return ""
        except:
            return ""


# 全局实例
openreview_client = OpenReviewClient()