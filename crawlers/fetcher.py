#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用网页抓取器

使用requests + trafilatura进行网页正文提取
Author: Spidermind
"""

import requests
import trafilatura
import logging
import time
from typing import Dict, Optional, Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class WebFetcher:
    """通用网页抓取器"""
    
    def __init__(self):
        """初始化抓取器"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1
    
    def fetch_content(self, url: str) -> Dict[str, Any]:
        """
        抓取网页内容并提取正文
        
        Args:
            url: 目标URL
            
        Returns:
            Dict: 包含原始HTML、提取的正文、元数据等信息
        """
        result = {
            'success': False,
            'url': url,
            'html': '',
            'text': '',
            'title': '',
            'author': '',
            'date': '',
            'language': '',
            'error': '',
            'status_code': None,
            'content_length': 0,
            'is_redirect': False,
            'final_url': url
        }
        
        try:
            # 发起HTTP请求
            response = self._make_request(url)
            if not response:
                result['error'] = 'Failed to fetch URL after retries'
                return result
            
            result['status_code'] = response.status_code
            result['final_url'] = response.url
            result['is_redirect'] = response.url != url
            
            # 检查响应状态
            if response.status_code != 200:
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            # 获取HTML内容
            html_content = response.text
            result['html'] = html_content
            result['content_length'] = len(html_content)
            
            # 使用trafilatura提取正文
            extracted_data = self._extract_content(html_content, url)
            result.update(extracted_data)
            
            # 判断提取是否成功
            if result['text'] and len(result['text'].strip()) > 0:
                result['success'] = True
            else:
                result['error'] = 'No content extracted'
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {e}")
            result['error'] = str(e)
            return result
    
    def _make_request(self, url: str) -> Optional[requests.Response]:
        """
        发起HTTP请求，包含重试机制
        
        Args:
            url: 目标URL
            
        Returns:
            requests.Response: 成功的响应，或None
        """
        for attempt in range(self.max_retries):
            try:
                # 请求间延迟
                if attempt > 0:
                    time.sleep(self.retry_delay * attempt)
                
                response = self.session.get(
                    url, 
                    timeout=self.timeout,
                    allow_redirects=True
                )
                
                return response
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {url} (attempt {attempt + 1})")
                if attempt == self.max_retries - 1:
                    logger.error(f"Final timeout for {url}")
                continue
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error for {url}: {e} (attempt {attempt + 1})")
                if attempt == self.max_retries - 1:
                    logger.error(f"Final connection error for {url}")
                continue
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {url}: {e} (attempt {attempt + 1})")
                if attempt == self.max_retries - 1:
                    logger.error(f"Final request error for {url}")
                continue
        
        return None
    
    def _extract_content(self, html: str, url: str) -> Dict[str, Any]:
        """
        使用trafilatura提取正文内容
        
        Args:
            html: HTML源码
            url: 原始URL
            
        Returns:
            Dict: 提取的内容和元数据
        """
        extracted = {
            'text': '',
            'title': '',
            'author': '',
            'date': '',
            'language': ''
        }
        
        try:
            # 使用trafilatura提取正文
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_formatting=False,
                favor_precision=True
            )
            
            if text:
                extracted['text'] = text.strip()
            
            # 提取元数据
            metadata = trafilatura.extract_metadata(html, fast=True)
            if metadata:
                extracted['title'] = metadata.title or ''
                extracted['author'] = metadata.author or ''
                extracted['date'] = metadata.date or ''
                extracted['language'] = metadata.language or ''
            
            # 如果没有提取到标题，尝试其他方法
            if not extracted['title']:
                title = self._extract_title_fallback(html)
                extracted['title'] = title
            
            logger.debug(f"Extracted {len(extracted['text'])} characters from {url}")
            
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            extracted['text'] = ''
        
        return extracted
    
    def _extract_title_fallback(self, html: str) -> str:
        """
        备用标题提取方法
        
        Args:
            html: HTML源码
            
        Returns:
            str: 提取的标题
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # 尝试多种标题提取方法
            title_selectors = [
                'title',
                'h1',
                'h2',
                '.title',
                '.page-title',
                '[property="og:title"]',
                '[name="title"]'
            ]
            
            for selector in title_selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text(strip=True) if selector == 'title' or selector.startswith('h') else element.get('content', element.get_text(strip=True))
                    if title and len(title) < 200:  # 合理的标题长度
                        return title
                        
        except Exception as e:
            logger.warning(f"Error in fallback title extraction: {e}")
        
        return ''
    
    def is_content_sufficient(self, text: str, min_length: int = 200) -> bool:
        """
        检查提取的内容是否足够
        
        Args:
            text: 提取的文本
            min_length: 最小长度要求
            
        Returns:
            bool: 内容是否足够
        """
        if not text:
            return False
        
        # 清理文本并检查长度
        cleaned_text = text.strip()
        return len(cleaned_text) >= min_length
    
    def detect_content_type(self, url: str, html: str) -> str:
        """
        检测页面内容类型
        
        Args:
            url: 页面URL
            html: HTML内容
            
        Returns:
            str: 内容类型 (personal_page, academic_page, blog, social, other)
        """
        url_lower = url.lower()
        html_lower = html.lower()
        
        # 学术相关关键词
        academic_keywords = [
            'research', 'publication', 'paper', 'cv', 'resume',
            'university', 'professor', 'researcher', 'phd', 'scholar'
        ]
        
        # 个人博客关键词
        blog_keywords = [
            'blog', 'post', 'article', 'diary', 'journal'
        ]
        
        # 社交媒体标识
        social_patterns = [
            'github.io', 'medium.com', 'linkedin.com', 'twitter.com'
        ]
        
        # 检查URL模式
        if any(pattern in url_lower for pattern in social_patterns):
            return 'social'
        
        # 检查内容中的关键词
        academic_count = sum(1 for keyword in academic_keywords if keyword in html_lower)
        blog_count = sum(1 for keyword in blog_keywords if keyword in html_lower)
        
        if academic_count >= 2:
            return 'academic_page'
        elif blog_count >= 1 or 'github.io' in url_lower:
            return 'blog'
        elif any(keyword in url_lower for keyword in ['~', 'people', 'staff', 'faculty']):
            return 'personal_page'
        else:
            return 'other'


# 全局实例
web_fetcher = WebFetcher()