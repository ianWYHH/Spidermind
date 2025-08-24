#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正则表达式提取器

提供邮箱、电话、社交网络、URL等信息的正则提取功能
Author: Spidermind
"""

import re
import logging
from typing import List, Set, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RegexExtractors:
    """正则表达式提取器类"""
    
    def __init__(self):
        """初始化正则表达式模式"""
        # 邮箱正则 - 较为宽松，支持常见格式
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        )
        
        # 电话号码正则 - 支持多种格式
        self.phone_patterns = [
            # 中国手机号
            re.compile(r'\b1[3-9]\d{9}\b'),
            # 国际格式 +86 或 0086
            re.compile(r'\+?86\s*1[3-9]\d{9}\b'),
            # 美国电话号码
            re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
            # 国际格式 +1
            re.compile(r'\+1\s*\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
            # 通用国际格式
            re.compile(r'\+\d{1,3}\s*\d{6,14}\b'),
            # 带括号格式 (123) 456-7890
            re.compile(r'\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'),
        ]
        
        # URL正则 - 匹配http/https链接
        self.url_pattern = re.compile(
            r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?',
            re.IGNORECASE
        )
        
        # 社交网络平台模式
        self.social_patterns = {
            'twitter': re.compile(r'(?:twitter\.com/|@)([A-Za-z0-9_]{1,15})', re.IGNORECASE),
            'linkedin': re.compile(r'linkedin\.com/in/([A-Za-z0-9-]{3,100})', re.IGNORECASE),
            'github': re.compile(r'github\.com/([A-Za-z0-9-]{1,39})', re.IGNORECASE),
            'researchgate': re.compile(r'researchgate\.net/profile/([A-Za-z0-9-_]{1,100})', re.IGNORECASE),
            'orcid': re.compile(r'orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[0-9X])', re.IGNORECASE),
            'scholar': re.compile(r'scholar\.google\.com/citations\?user=([A-Za-z0-9-_]{12})', re.IGNORECASE),
            'facebook': re.compile(r'facebook\.com/([A-Za-z0-9.]{5,50})', re.IGNORECASE),
        }
        
        # 个人主页识别模式
        self.homepage_patterns = [
            # GitHub Pages
            re.compile(r'([A-Za-z0-9-]+)\.github\.io', re.IGNORECASE),
            # 个人域名常见模式
            re.compile(r'([A-Za-z0-9-]+)\.(me|dev|io|com|org|net)/([A-Za-z0-9-_/]*)', re.IGNORECASE),
            # 学术主页
            re.compile(r'([A-Za-z0-9-]+)\.(edu|ac\.uk|ac\.cn)/~?([A-Za-z0-9-_/]*)', re.IGNORECASE),
        ]
        
        # 邮箱黑名单 - 过滤无效邮箱
        self.email_blacklist = {
            'noreply', 'no-reply', 'donotreply', 'example.com', 'test.com',
            'localhost', 'dummy', 'fake', 'invalid', 'none'
        }
    
    def extract_emails(self, text: str) -> List[str]:
        """
        从文本中提取邮箱地址
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 唯一的有效邮箱列表
        """
        if not text:
            return []
        
        emails = set()
        matches = self.email_pattern.findall(text)
        
        for email in matches:
            email = email.lower().strip()
            # 过滤黑名单邮箱
            if not any(blacklist in email for blacklist in self.email_blacklist):
                # 基本有效性检查
                if '@' in email and '.' in email.split('@')[1]:
                    emails.add(email)
        
        return list(emails)
    
    def extract_phones(self, text: str) -> List[str]:
        """
        从文本中提取电话号码
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 唯一的电话号码列表
        """
        if not text:
            return []
        
        phones = set()
        
        for pattern in self.phone_patterns:
            matches = pattern.findall(text)
            for phone in matches:
                # 清理电话号码格式
                clean_phone = re.sub(r'[-.()\s]', '', phone)
                if len(clean_phone) >= 10:  # 最少10位数字
                    phones.add(clean_phone)
        
        return list(phones)
    
    def extract_urls(self, text: str) -> List[str]:
        """
        从文本中提取URL
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 唯一的URL列表
        """
        if not text:
            return []
        
        urls = set()
        matches = self.url_pattern.findall(text)
        
        for url in matches:
            url = url.strip()
            try:
                # 基本URL有效性检查
                parsed = urlparse(url)
                if parsed.netloc:
                    urls.add(url)
            except:
                continue
        
        return list(urls)
    
    def extract_social_profiles(self, text: str) -> Dict[str, List[str]]:
        """
        从文本中提取社交网络档案
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, List[str]]: 按平台分组的社交档案
        """
        if not text:
            return {}
        
        social_profiles = {}
        
        for platform, pattern in self.social_patterns.items():
            matches = pattern.findall(text)
            if matches:
                # 去重并过滤
                unique_profiles = set()
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]  # 如果是元组，取第一个捕获组
                    
                    match = match.strip()
                    if match and len(match) > 2:  # 基本长度检查
                        unique_profiles.add(match)
                
                if unique_profiles:
                    social_profiles[platform] = list(unique_profiles)
        
        return social_profiles
    
    def extract_homepages(self, text: str) -> List[Dict[str, str]]:
        """
        从文本中提取可能的个人主页
        
        Args:
            text: 输入文本
            
        Returns:
            List[Dict[str, str]]: 个人主页信息列表，包含url和type
        """
        if not text:
            return []
        
        homepages = []
        
        # 先提取所有URL
        urls = self.extract_urls(text)
        
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                path = parsed.path.lower()
                
                # GitHub Pages检测
                if '.github.io' in domain:
                    homepages.append({
                        'url': url,
                        'type': 'github_pages',
                        'confidence': 0.9
                    })
                    continue
                
                # 个人博客检测
                blog_indicators = ['blog', 'personal', 'portfolio', 'homepage', 'about']
                if any(indicator in domain or indicator in path for indicator in blog_indicators):
                    homepages.append({
                        'url': url,
                        'type': 'personal_blog',
                        'confidence': 0.7
                    })
                    continue
                
                # 学术主页检测
                if any(edu_domain in domain for edu_domain in ['.edu', '.ac.', '.university']):
                    if any(indicator in path for indicator in ['~', 'people', 'faculty', 'staff']):
                        homepages.append({
                            'url': url,
                            'type': 'academic_homepage',
                            'confidence': 0.8
                        })
                        continue
                
                # 其他个人网站检测
                personal_domains = ['.me', '.dev', '.io']
                if any(domain.endswith(pd) for pd in personal_domains):
                    homepages.append({
                        'url': url,
                        'type': 'personal_website',
                        'confidence': 0.6
                    })
            
            except Exception as e:
                logger.debug(f"解析URL失败: {url}, 错误: {e}")
                continue
        
        return homepages
    
    def extract_all(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取所有信息
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, Any]: 包含所有提取结果的字典
        """
        if not text:
            return {
                'emails': [],
                'phones': [],
                'urls': [],
                'social_profiles': {},
                'homepages': []
            }
        
        return {
            'emails': self.extract_emails(text),
            'phones': self.extract_phones(text),
            'urls': self.extract_urls(text),
            'social_profiles': self.extract_social_profiles(text),
            'homepages': self.extract_homepages(text)
        }
    
    def is_academic_email(self, email: str) -> bool:
        """
        判断是否为学术邮箱
        
        Args:
            email: 邮箱地址
            
        Returns:
            bool: 是否为学术邮箱
        """
        academic_domains = [
            '.edu', '.ac.uk', '.ac.cn', '.edu.cn', '.edu.au', '.ac.au',
            '.edu.sg', '.edu.hk', '.ac.jp', '.ac.kr', '.ac.in', '.edu.in',
            '.university', '.univ', '.college'
        ]
        
        email_lower = email.lower()
        return any(domain in email_lower for domain in academic_domains)
    
    def clean_text_for_extraction(self, text: str) -> str:
        """
        清理文本以便更好地进行信息提取
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""
        
        # 移除Markdown语法
        text = re.sub(r'[*_`#]', ' ', text)
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # 标准化空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除过多的标点符号
        text = re.sub(r'[^\w\s@.:/+-]', ' ', text)
        
        return text.strip()


# 全局实例
regex_extractors = RegexExtractors()