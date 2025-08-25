#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主页爬虫服务层 - 严格按蓝图实现兜底策略

处理homepage任务的核心业务逻辑，包括requests+trafilatura→Playwright兜底机制
Author: Spidermind
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.base import SessionLocal
from crawlers.fetcher import web_fetcher
from crawlers.playwright_fetcher import playwright_manager
from extractors.regex_extractors import regex_extractors
from models.candidate import Candidate, CandidateEmail, CandidateHomepage, CandidateFile, RawText
from models.crawl import CrawlTask, CrawlLog
from services.progress_service import progress_tracker
from services.error_handler import error_handler

logger = logging.getLogger(__name__)


class HomepageService:
    """主页爬虫服务类 - 实现兜底策略"""
    
    def __init__(self):
        """初始化主页爬虫服务"""
        self.min_content_length = 200  # 蓝图要求：正文<200字则兜底
        self.max_content_length = 1000000  # 最大内容长度（1MB）
        
        # 文件扩展名模式 - 蓝图要求：发现pdf/image简历
        self.pdf_patterns = re.compile(r'\.pdf(?:\?|#|$)', re.IGNORECASE)
        self.image_patterns = re.compile(r'\.(jpg|jpeg|png|gif|bmp|webp)(?:\?|#|$)', re.IGNORECASE)
        self.resume_keywords = ['cv', 'resume', 'curriculum', 'vitae', '简历', '履历']
    
    async def process_homepage_task(self, task: CrawlTask) -> Dict[str, Any]:
        """
        处理主页爬虫任务 (蓝图核心方法 - 异步版本)
        
        Args:
            task: 爬虫任务
            
        Returns:
            Dict: 处理结果
        """
        url = task.url
        candidate_id = task.candidate_id
        
        if not url:
            return {
                'status': 'fail',
                'message': 'URL为空',
                'error': 'Missing URL in task'
            }
        
        db = SessionLocal()
        try:
            # 检查是否已存在相同URL的记录 (蓝图要求：去重检查)
            existing_raw_text = None
            if candidate_id:
                existing_raw_text = db.query(RawText).filter(
                    and_(
                        RawText.candidate_id == candidate_id,
                        RawText.url == url
                    )
                ).first()
                
                if existing_raw_text:
                    return {
                        'status': 'skip',
                        'message': f'URL {url} 已存在于raw_texts中，跳过重复爬取',
                        'skipped': True,
                        'existing_record_id': existing_raw_text.id
                    }
            
            # 第一阶段：使用requests + trafilatura (蓝图要求：先走fetcher)
            logger.info(f"开始抓取主页: {url}")
            result = web_fetcher.fetch_content(url)
            
            used_playwright = False
            fallback_reason = ''
            message_parts = []
            
            # 判断是否需要兜底 (蓝图要求：失败或正文<200字→走Playwright)
            needs_fallback = False
            if not result['success']:
                fallback_reason = f"requests失败: {result.get('error', 'Unknown error')}"
                needs_fallback = True
            elif not web_fetcher.is_content_sufficient(result['text'], self.min_content_length):
                fallback_reason = f"内容过短: {len(result.get('text', ''))}字符 < {self.min_content_length}"
                needs_fallback = True
            
            # 第二阶段：Playwright兜底 (蓝图要求：兜底机制)
            if needs_fallback:
                logger.warning(f"触发Playwright兜底 - {fallback_reason}: {url}")
                try:
                    playwright_result = playwright_manager.fetch_content_sync(url)
                    if playwright_result['success'] and playwright_result.get('text'):
                        result = playwright_result
                        used_playwright = True
                        message_parts.append("[兜底:Playwright]")
                        logger.info(f"Playwright兜底抓取成功: {url}")
                    else:
                        logger.warning(f"Playwright兜底也失败: {url} - {playwright_result.get('error', 'Unknown error')}")
                except RuntimeError as e:
                    if "Playwright not installed" in str(e):
                        logger.warning(f"Playwright未安装，跳过兜底: {url}")
                        message_parts.append("[兜底:跳过-Playwright未安装]")
                    else:
                        logger.error(f"Playwright兜底运行时错误: {url} - {e}")
                        error_handler.log_error('homepage', 'homepage', f"Playwright兜底运行时错误: {str(e)}", task.id)
                except Exception as e:
                    logger.error(f"Playwright兜底异常: {url} - {e}")
                    error_handler.log_error('homepage', 'homepage', f"Playwright兜底异常: {str(e)}", task.id)
            
            # 检查最终结果
            if not result['success'] or not result.get('text'):
                return {
                    'status': 'fail',
                    'message': f"内容抓取失败: {result.get('error', 'No content extracted')}",
                    'error': result.get('error', 'No content extracted'),
                    'used_playwright': used_playwright,
                    'fallback_reason': fallback_reason if used_playwright else None
                }
            
            # 限制内容长度
            text_content = result['text']
            if len(text_content) > self.max_content_length:
                text_content = text_content[:self.max_content_length] + '...[内容被截断]'
                logger.warning(f"内容过长，已截断: {url}")
            
            # 保存到raw_texts表 (蓝图要求：全文保存到raw_texts)
            raw_text_record = self._save_raw_text(
                db, candidate_id, url, text_content, result, used_playwright
            )
            
            # 提取联系信息 (蓝图要求：正则抽邮箱/电话/社交)
            contact_info = self._extract_contact_info(text_content, result.get('html', ''))
            contacts_saved = 0
            if candidate_id and contact_info:
                contacts_saved = self._save_contact_info(db, candidate_id, contact_info)
            
            # 发现文件链接 (蓝图要求：发现pdf/image简历→candidate_files(status='unparsed'))
            files_found = 0
            if candidate_id and result.get('html'):
                files_found = self._discover_and_save_files(db, candidate_id, result['html'], url)
            
            db.commit()
            
            # 构建成功消息 (蓝图要求：日志message标注是否触发兜底)
            message_parts.insert(0, f"成功抓取主页: {url}")
            if contacts_saved > 0:
                message_parts.append(f"提取联系信息 {contacts_saved} 条")
            if files_found > 0:
                message_parts.append(f"发现文件 {files_found} 个")
            if used_playwright:
                message_parts.append(f"触发兜底: {fallback_reason}")
            
            return {
                'status': 'success',
                'message': ', '.join(message_parts),
                'success': True,
                'raw_text_id': raw_text_record.id,
                'content_length': len(text_content),
                'contacts_saved': contacts_saved,
                'files_found': files_found,
                'used_playwright': used_playwright,
                'fallback_reason': fallback_reason if used_playwright else None,
                'title': result.get('title', ''),
                'final_url': result.get('final_url', url),
                'stats': {
                    'text_length': len(text_content),
                    'html_length': len(result.get('html', '')),
                    'contacts_extracted': contacts_saved,
                    'files_discovered': files_found
                }
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"处理主页任务失败 {url}: {str(e)}"
            logger.error(error_msg)
            error_handler.log_error('homepage', 'homepage', error_msg, task.id)
            
            return {
                'status': 'fail',
                'message': error_msg,
                'error': str(e)
            }
        finally:
            db.close()
    
    def process_homepage_task_sync(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理主页爬虫任务 (同步版本 - 向后兼容)
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        url = task.url
        candidate_id = task.candidate_id
        
        if not url:
            return {
                'status': 'fail',
                'message': 'URL为空'
            }
        
        try:
            # 检查是否已存在相同URL的记录
            existing_raw_text = None
            if candidate_id:
                existing_raw_text = db.query(RawText).filter(
                    and_(
                        RawText.candidate_id == candidate_id,
                        RawText.url == url
                    )
                ).first()
                
                if existing_raw_text:
                    return {
                        'status': 'skip',
                        'message': f'URL {url} 已存在于raw_texts中，跳过重复爬取',
                        'existing_record_id': existing_raw_text.id
                    }
            
            # 第一阶段：使用requests + trafilatura
            logger.info(f"开始抓取主页: {url}")
            result = web_fetcher.fetch_content(url)
            
            used_playwright = False
            fallback_reason = ''
            
            # 判断是否需要兜底
            if not result['success']:
                fallback_reason = f"requests失败: {result.get('error', 'Unknown error')}"
                needs_fallback = True
            elif not web_fetcher.is_content_sufficient(result['text'], self.min_content_length):
                fallback_reason = f"内容过短: {len(result.get('text', ''))}字符 < {self.min_content_length}"
                needs_fallback = True
            else:
                needs_fallback = False
            
            # 第二阶段：Playwright兜底
            if needs_fallback:
                logger.warning(f"触发兜底抓取 - {fallback_reason}: {url}")
                try:
                    playwright_result = playwright_manager.fetch_content_sync(url)
                    if playwright_result['success']:
                        result = playwright_result
                        used_playwright = True
                        logger.info(f"兜底抓取成功: {url}")
                    else:
                        logger.warning(f"兜底抓取也失败: {url} - {playwright_result.get('error', 'Unknown error')}")
                except RuntimeError as e:
                    if "Playwright not installed" in str(e):
                        logger.warning(f"Playwright未安装，跳过兜底: {url}")
                    else:
                        logger.error(f"兜底抓取运行时错误: {url} - {e}")
                except Exception as e:
                    logger.error(f"兜底抓取异常: {url} - {e}")
            
            # 检查最终结果
            if not result['success'] or not result.get('text'):
                return {
                    'status': 'fail',
                    'message': f"内容抓取失败: {result.get('error', 'No content extracted')}",
                    'used_playwright': used_playwright,
                    'fallback_reason': fallback_reason if used_playwright else None
                }
            
            # 限制内容长度
            text_content = result['text']
            if len(text_content) > self.max_content_length:
                text_content = text_content[:self.max_content_length] + '...[内容被截断]'
                logger.warning(f"内容过长，已截断: {url}")
            
            # 保存到raw_texts表
            raw_text_record = self._save_raw_text(
                db, candidate_id, url, text_content, result, used_playwright
            )
            
            # 提取联系信息
            contact_info = self._extract_contact_info(text_content, result.get('html', ''))
            contacts_saved = 0
            if candidate_id and contact_info:
                contacts_saved = self._save_contact_info(db, candidate_id, contact_info)
            
            # 发现文件链接
            files_found = 0
            if candidate_id and result.get('html'):
                files_found = self._discover_and_save_files(db, candidate_id, result['html'], url)
            
            return {
                'status': 'success',
                'message': f"成功抓取主页: {url}{'，触发兜底' if used_playwright else ''}",
                'raw_text_id': raw_text_record.id,
                'content_length': len(text_content),
                'contacts_saved': contacts_saved,
                'files_found': files_found,
                'used_playwright': used_playwright,
                'fallback_reason': fallback_reason if used_playwright else None,
                'title': result.get('title', ''),
                'final_url': result.get('final_url', url)
            }
            
        except Exception as e:
            logger.error(f"处理主页任务失败: {url}, 错误: {e}")
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def _save_raw_text(self, db: Session, candidate_id: Optional[int], url: str, 
                      text_content: str, result: Dict[str, Any], used_playwright: bool = False) -> RawText:
        """保存原文到raw_texts表 (蓝图要求：保存到raw_texts)"""
        
        # 确定来源类型
        source_type = self._determine_source_type(url, result.get('html', ''), used_playwright)
        
        raw_text = RawText(
            candidate_id=candidate_id,
            url=url,
            plain_text=text_content,
            source=source_type,  # 蓝图要求：source字段
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(raw_text)
        db.flush()  # 获取ID
        
        logger.info(f"保存原文到raw_texts: {len(text_content)}字符, 来源={source_type}, ID={raw_text.id}")
        return raw_text
    
    def _determine_source_type(self, url: str, html: str, used_playwright: bool = False) -> str:
        """确定源类型"""
        url_lower = url.lower()
        
        if used_playwright:
            return 'homepage_playwright'  # 标记使用了兜底
        elif 'github.io' in url_lower:
            return 'github_io'
        elif any(domain in url_lower for domain in ['.edu', 'university', 'academic']):
            return 'homepage'
        else:
            return 'homepage'
    
    def _extract_contact_info(self, text: str, html: str) -> Dict[str, List[str]]:
        """提取联系信息 (蓝图要求：正则抽邮箱/电话/社交)"""
        contact_info = {
            'emails': [],
            'phones': [],
            'social_urls': {},
            'homepages': []
        }
        
        try:
            # 从文本和HTML中提取邮箱 (蓝图要求：正则抽邮箱)
            text_emails = regex_extractors.extract_emails(text)
            html_emails = regex_extractors.extract_emails(html)
            contact_info['emails'] = list(set(text_emails + html_emails))
            
            # 提取电话号码 (蓝图要求：正则抽电话)
            text_phones = regex_extractors.extract_phones(text)
            html_phones = regex_extractors.extract_phones(html)
            contact_info['phones'] = list(set(text_phones + html_phones))
            
            # 提取社交媒体链接 (蓝图要求：正则抽社交)
            social_profiles = regex_extractors.extract_social_profiles(html)
            contact_info['social_urls'] = social_profiles
            
            # 提取其他主页链接
            contact_info['homepages'] = regex_extractors.extract_homepages(html)
            
        except Exception as e:
            logger.warning(f"提取联系信息失败: {e}")
        
        return contact_info
    
    def _save_contact_info(self, db: Session, candidate_id: int, 
                          contact_info: Dict[str, Any]) -> int:
        """保存联系信息到子表"""
        saved_count = 0
        
        try:
            # 保存邮箱
            for email in contact_info.get('emails', []):
                if self._is_valid_email(email):
                    existing = db.query(CandidateEmail).filter(
                        and_(
                            CandidateEmail.candidate_id == candidate_id,
                            CandidateEmail.email == email
                        )
                    ).first()
                    
                    if not existing:
                        candidate_email = CandidateEmail(
                            candidate_id=candidate_id,
                            email=email,
                            source='homepage_crawl',
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        db.add(candidate_email)
                        saved_count += 1
            
            # 保存主页链接
            all_homepages = list(contact_info.get('homepages', []))
            
            # 添加社交媒体链接
            social_urls = contact_info.get('social_urls', {})
            for platform, urls in social_urls.items():
                all_homepages.extend(urls)
            
            for homepage_data in all_homepages:
                # 处理不同格式的主页数据
                if isinstance(homepage_data, dict):
                    homepage_url = homepage_data.get('url', '')
                else:
                    homepage_url = str(homepage_data)
                
                if self._is_valid_url(homepage_url):
                    existing = db.query(CandidateHomepage).filter(
                        and_(
                            CandidateHomepage.candidate_id == candidate_id,
                            CandidateHomepage.url == homepage_url
                        )
                    ).first()
                    
                    if not existing:
                        candidate_homepage = CandidateHomepage(
                            candidate_id=candidate_id,
                            url=homepage_url,
                            source='homepage_crawl',
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        db.add(candidate_homepage)
                        saved_count += 1
            
        except Exception as e:
            logger.warning(f"保存联系信息失败: {e}")
        
        return saved_count
    
    def _discover_and_save_files(self, db: Session, candidate_id: int, 
                                html: str, base_url: str) -> int:
        """发现并保存文件链接 (蓝图要求：发现pdf/image简历→candidate_files(status='unparsed'))"""
        saved_count = 0
        
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找所有链接
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                # 构建完整URL
                full_url = urljoin(base_url, href)
                
                # 检查是否是文件链接 (蓝图要求：检测pdf/image简历)
                file_type = self._detect_file_type(full_url, link.get_text(strip=True))
                
                if file_type:
                    # 检查是否已存在
                    existing = db.query(CandidateFile).filter(
                        and_(
                            CandidateFile.candidate_id == candidate_id,
                            CandidateFile.file_url_or_path == full_url
                        )
                    ).first()
                    
                    if not existing:
                        candidate_file = CandidateFile(
                            candidate_id=candidate_id,
                            file_url_or_path=full_url,
                            file_type=file_type,
                            status='unparsed',  # 蓝图要求：status='unparsed'
                            source='homepage_crawl',
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        db.add(candidate_file)
                        saved_count += 1
                        logger.info(f"发现简历文件: {file_type} - {full_url}")
        
        except Exception as e:
            logger.warning(f"发现文件失败: {e}")
        
        return saved_count
    
    def _detect_file_type(self, url: str, link_text: str) -> Optional[str]:
        """检测文件类型 (蓝图要求：pdf/image简历检测)"""
        url_lower = url.lower()
        text_lower = link_text.lower()
        
        # 检查PDF (蓝图要求：发现pdf简历)
        if self.pdf_patterns.search(url) or 'pdf' in text_lower:
            # 检查是否是简历相关
            if any(keyword in url_lower or keyword in text_lower for keyword in self.resume_keywords):
                return 'pdf'
        
        # 检查图片 (蓝图要求：发现image简历)  
        if self.image_patterns.search(url):
            # 检查是否是简历相关的图片
            if any(keyword in url_lower or keyword in text_lower for keyword in self.resume_keywords):
                return 'image'
        
        return None
    
    def _is_valid_email(self, email: str) -> bool:
        """验证邮箱地址有效性"""
        if not email or len(email) > 254:
            return False
        
        # 基本格式检查
        if '@' not in email or '.' not in email.split('@')[1]:
            return False
        
        # 排除明显的垃圾邮箱
        blacklist_domains = [
            'example.com', 'test.com', 'noreply.com', 'no-reply.com',
            'localhost', '127.0.0.1'
        ]
        
        domain = email.split('@')[1].lower()
        return domain not in blacklist_domains
    
    def _is_valid_url(self, url: str) -> bool:
        """验证URL有效性"""
        if not url or len(url) > 500:
            return False
        
        return url.startswith(('http://', 'https://'))


# 全局实例
homepage_service = HomepageService()