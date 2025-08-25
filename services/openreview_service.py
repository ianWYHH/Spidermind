#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenReview 服务层

处理OpenReview爬虫的核心业务逻辑，包括论文作者发现和profile信息提取
Author: Spidermind
"""

import logging
import asyncio
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from crawlers.openreview_client import openreview_client
from extractors.regex_extractors import regex_extractors
from models.candidate import Candidate, CandidateEmail, CandidateHomepage, CandidatePaper, CandidateInstitution
from models.crawl import CrawlTask, CrawlLog
from models.mapping import OpenReviewUser
from models.base import SessionLocal
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)


class OpenReviewService:
    """OpenReview服务类"""
    
    def __init__(self):
        """初始化OpenReview服务"""
        self.client = openreview_client
        self.extractors = regex_extractors
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
    
    def fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None, 
                   trace_id: Optional[str] = None, task_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        健壮的HTTP JSON请求包装器，支持指数退避重试
        
        Args:
            url: 请求URL
            params: 查询参数
            trace_id: 跟踪ID
            task_id: 任务ID（用于日志记录）
            
        Returns:
            Dict: JSON响应数据，或None
        """
        max_retries = 6  # 最多重试6次: 1s, 2s, 4s, 8s, 16s, 32s, 60s
        base_delay = 1.0  # 基础延迟1秒
        max_delay = 60.0  # 最大延迟60秒
        
        for attempt in range(max_retries + 1):
            try:
                # 请求前延迟（除了第一次）
                if attempt > 0:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.info(f"重试前等待 {delay:.1f}s (第{attempt}次重试)")
                    time.sleep(delay)
                
                response = self.session.get(url, params=params, timeout=30)
                
                # 成功响应
                if response.status_code == 200:
                    try:
                        # 尝试解析JSON
                        if 'application/json' in response.headers.get('content-type', ''):
                            return response.json()
                        else:
                            # 如果不是JSON，返回原始文本用于HTML解析
                            return {'html_content': response.text, 'url': url}
                    except ValueError as e:
                        # JSON解析失败，记录但不重试
                        self._log_fetch_failure(
                            url, 200, f"JSON解析失败: {str(e)}", 
                            trace_id, task_id
                        )
                        return None
                
                # 404错误不重试
                elif response.status_code == 404:
                    self._log_fetch_failure(
                        url, 404, "资源不存在", 
                        trace_id, task_id
                    )
                    return None
                
                # 429和5xx错误需要重试
                elif response.status_code == 429 or response.status_code >= 500:
                    retry_after = self._parse_retry_after(response.headers.get('Retry-After'))
                    if retry_after and attempt < max_retries:
                        wait_time = min(retry_after, max_delay)
                        logger.warning(f"OpenReview API限制，等待 {wait_time:.1f}s (Retry-After: {retry_after})")
                        time.sleep(wait_time)
                        continue
                    
                    # 如果是最后一次重试或没有Retry-After，按正常逻辑处理
                    if attempt == max_retries:
                        self._log_fetch_failure(
                            url, response.status_code, 
                            f"openreview: {response.status_code} {response.reason}",
                            trace_id, task_id
                        )
                        return None
                    
                    logger.warning(f"请求失败 {response.status_code}: {url}，将重试")
                    continue
                
                # 其他4xx错误不重试
                elif 400 <= response.status_code < 500:
                    self._log_fetch_failure(
                        url, response.status_code, 
                        f"openreview: {response.status_code} {response.reason}",
                        trace_id, task_id
                    )
                    return None
                
                # 其他状态码重试
                else:
                    if attempt == max_retries:
                        self._log_fetch_failure(
                            url, response.status_code, 
                            f"openreview: {response.status_code} {response.reason}",
                            trace_id, task_id
                        )
                        return None
                    
                    logger.warning(f"意外状态码 {response.status_code}: {url}，将重试")
                    continue
                    
            except requests.exceptions.Timeout:
                if attempt == max_retries:
                    self._log_fetch_failure(
                        url, 0, "openreview: 请求超时", 
                        trace_id, task_id
                    )
                    return None
                logger.warning(f"请求超时: {url}，将重试")
                continue
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    self._log_fetch_failure(
                        url, 0, f"openreview: 网络错误 {str(e)}", 
                        trace_id, task_id
                    )
                    return None
                logger.warning(f"网络异常: {url}, 错误: {e}，将重试")
                continue
        
        return None
    
    def _parse_retry_after(self, retry_after_header: Optional[str]) -> Optional[float]:
        """解析Retry-After头部"""
        if not retry_after_header:
            return None
        
        try:
            # 尝试解析为秒数
            return float(retry_after_header)
        except ValueError:
            try:
                # 尝试解析为HTTP日期格式
                from email.utils import parsedate
                parsed_date = parsedate(retry_after_header)
                if parsed_date:
                    retry_time = time.mktime(parsed_date)
                    current_time = time.time()
                    return max(0, retry_time - current_time)
            except:
                pass
        
        return None
    
    def _log_fetch_failure(self, url: str, status_code: int, message: str, 
                          trace_id: Optional[str] = None, task_id: Optional[int] = None):
        """记录请求失败到crawl_logs"""
        if not task_id:
            return
        
        db = SessionLocal()
        try:
            log = CrawlLog(
                task_id=task_id,
                source='openreview',
                task_type='api_request',
                url=url,
                status='fail',
                message=message,
                trace_id=trace_id,
                created_at=datetime.now()
            )
            db.add(log)
            db.commit()
            
            logger.error(f"OpenReview请求失败: {message} - {url}")
            
        except Exception as e:
            logger.error(f"记录OpenReview请求失败日志失败: {e}")
            db.rollback()
        finally:
            db.close()
    
    def process_forum_task(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理OpenReview论文论坛任务
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        forum_url = task.url
        if not forum_url:
            return {
                'status': 'fail',
                'message': 'Forum URL 为空'
            }
        
        try:
            # 获取论文信息（使用健壮的请求包装器）
            response_data = self.fetch_json(forum_url, trace_id=getattr(task, 'trace_id', None), task_id=task.id)
            if not response_data:
                return {
                    'status': 'fail',
                    'message': f'无法获取论文信息: {forum_url}'
                }
            
            # 如果是HTML内容，使用原客户端解析
            if 'html_content' in response_data:
                paper_info = self._parse_forum_html(response_data['html_content'], forum_url)
            else:
                paper_info = response_data
            
            if not paper_info:
                return {
                    'status': 'fail',
                    'message': f'无法获取论文信息: {forum_url}'
                }
            
            title = paper_info.get('title', '')
            authors = paper_info.get('authors', [])
            
            if not title:
                return {
                    'status': 'fail',
                    'message': '无法提取论文标题'
                }
            
            if not authors:
                return {
                    'status': 'skip',
                    'message': '未找到作者信息'
                }
            
            # 为每个作者创建或关联候选人记录，并保存论文信息
            candidates_processed = 0
            profile_tasks_created = 0
            
            for author in authors:
                try:
                    # 为作者创建候选人记录（如果不存在）
                    candidate = self._get_or_create_candidate_for_author(author, db)
                    
                    # 保存论文信息到candidate_papers
                    self._save_paper_info(candidate.id, paper_info, db)
                    candidates_processed += 1
                    
                    # 如果有profile URL，创建profile任务
                    if author.get('profile_url'):
                        profile_id = self.client.extract_profile_id_from_url(author['profile_url'])
                        if profile_id:
                            task_created = self._create_profile_task(
                                profile_id, author['profile_url'], candidate.id, task.batch_id, db
                            )
                            if task_created:
                                profile_tasks_created += 1
                
                except Exception as e:
                    logger.warning(f"处理作者失败: {author.get('name', 'unknown')}, 错误: {e}")
                    continue
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'成功处理论文: {title}',
                'paper_title': title,
                'authors_processed': candidates_processed,
                'profile_tasks_created': profile_tasks_created
            }
            
        except Exception as e:
            logger.error(f"处理OpenReview forum任务失败: {forum_url}, 错误: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def process_profile_task(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理OpenReview用户profile任务
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        profile_url = task.url
        openreview_profile_id = task.openreview_profile_id
        
        if not profile_url or not openreview_profile_id:
            return {
                'status': 'fail',
                'message': 'Profile URL 或 Profile ID 为空'
            }
        
        try:
            # 检查是否已经爬取过此用户
            existing_user = db.query(OpenReviewUser).filter(
                OpenReviewUser.openreview_profile_id == openreview_profile_id
            ).first()
            
            if existing_user and existing_user.last_crawled_at:
                # 检查是否需要重新爬取（比如7天内不重复爬取）
                if existing_user.last_crawled_at > datetime.now() - timedelta(days=7):
                    return {
                        'status': 'skip',
                        'message': f'用户 {openreview_profile_id} 近期已爬取过，跳过',
                        'candidate_id': existing_user.candidate_id
                    }
            
            # 获取用户profile信息（使用健壮的请求包装器）
            response_data = self.fetch_json(profile_url, trace_id=getattr(task, 'trace_id', None), task_id=task.id)
            if not response_data:
                return {
                    'status': 'fail',
                    'message': f'无法获取profile信息: {profile_url}'
                }
            
            # 如果是HTML内容，使用原客户端解析
            if 'html_content' in response_data:
                profile_info = self._parse_profile_html(response_data['html_content'], profile_url)
            else:
                profile_info = response_data
            
            if not profile_info:
                return {
                    'status': 'fail',
                    'message': f'无法获取profile信息: {profile_url}'
                }
            
            # 创建或更新候选人记录
            candidate = self._create_or_update_candidate_from_profile(profile_info, task.candidate_id, db)
            
            # 创建或更新OpenReviewUser记录
            openreview_user = self._create_or_update_openreview_user(
                openreview_profile_id, profile_url, candidate.id, db
            )
            
            # 提取并保存联系信息
            contact_info = self._extract_contact_info_from_profile(profile_info)
            self._save_contact_info(candidate.id, contact_info, db)
            
            # 保存机构信息
            if profile_info.get('affiliation'):
                self._save_institution_info(candidate.id, profile_info['affiliation'], db)
            
            # 创建派生任务
            derived_tasks_created = self._create_derived_tasks(
                candidate.id, profile_info, task.batch_id, db
            )
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'成功处理用户: {profile_info.get("name", openreview_profile_id)}',
                'candidate_id': candidate.id,
                'openreview_user_id': openreview_user.id,
                'derived_tasks_created': derived_tasks_created
            }
            
        except Exception as e:
            logger.error(f"处理OpenReview profile任务失败: {profile_url}, 错误: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def _get_or_create_candidate_for_author(self, author: Dict[str, Any], db: Session) -> Candidate:
        """为作者获取或创建候选人记录"""
        name = author.get('name', '').strip()
        affiliation = author.get('affiliation', '').strip()
        
        if not name:
            # 如果没有姓名，创建一个临时候选人
            name = "Unknown Author"
        
        # 尝试查找现有候选人（基于姓名）
        existing_candidate = db.query(Candidate).filter(
            Candidate.name == name
        ).first()
        
        if existing_candidate:
            # 更新机构信息（如果有新信息）
            if affiliation and not existing_candidate.primary_affiliation:
                existing_candidate.primary_affiliation = affiliation
                existing_candidate.updated_at = datetime.now()
            return existing_candidate
        
        # 创建新候选人
        candidate = Candidate(
            name=name,
            primary_affiliation=affiliation,
            source='openreview'
        )
        db.add(candidate)
        db.flush()  # 获取ID
        
        return candidate
    
    def _save_paper_info(self, candidate_id: int, paper_info: Dict[str, Any], db: Session):
        """保存论文信息到candidate_papers表"""
        title = paper_info.get('title', '').strip()
        url = paper_info.get('url', '')
        venue = paper_info.get('venue', '')
        
        if not title:
            return
        
        # 检查是否已存在相同论文
        existing_paper = db.query(CandidatePaper).filter(
            and_(
                CandidatePaper.candidate_id == candidate_id,
                CandidatePaper.title == title
            )
        ).first()
        
        if existing_paper:
            # 更新URL和会议信息
            if url and not existing_paper.url:
                existing_paper.url = url
            if venue and not existing_paper.venue:
                existing_paper.venue = venue
            existing_paper.updated_at = datetime.now()
        else:
            # 创建新论文记录
            paper = CandidatePaper(
                candidate_id=candidate_id,
                title=title,
                url=url,
                venue=venue,
                source='openreview'
            )
            db.add(paper)
    
    def _create_profile_task(self, profile_id: str, profile_url: str, candidate_id: int, 
                           batch_id: str, db: Session) -> bool:
        """创建profile任务"""
        # 检查是否已存在相同任务
        existing_task = db.query(CrawlTask).filter(
            and_(
                CrawlTask.source == 'openreview',
                CrawlTask.type == 'profile',
                CrawlTask.openreview_profile_id == profile_id,
                CrawlTask.status == 'pending'
            )
        ).first()
        
        if existing_task:
            return False
        
        # 创建新任务
        task = CrawlTask(
            source='openreview',
            type='profile',
            url=profile_url,
            openreview_profile_id=profile_id,
            candidate_id=candidate_id,
            batch_id=batch_id,
            priority=2,
            status='pending'
        )
        db.add(task)
        return True
    
    def _create_or_update_candidate_from_profile(self, profile_info: Dict[str, Any], 
                                               existing_candidate_id: Optional[int], 
                                               db: Session) -> Candidate:
        """从profile信息创建或更新候选人记录"""
        name = profile_info.get('name', '').strip()
        affiliation = profile_info.get('affiliation', '').strip()
        bio = profile_info.get('bio', '').strip()
        
        # 如果有现有候选人ID，先尝试获取
        candidate = None
        if existing_candidate_id:
            candidate = db.query(Candidate).filter(Candidate.id == existing_candidate_id).first()
        
        # 如果没有现有候选人，尝试根据姓名查找
        if not candidate and name:
            candidate = db.query(Candidate).filter(Candidate.name == name).first()
        
        if candidate:
            # 更新现有候选人
            if name and not candidate.name:
                candidate.name = name
            if affiliation and not candidate.primary_affiliation:
                candidate.primary_affiliation = affiliation
            if bio and not candidate.bio:
                candidate.bio = bio
            candidate.updated_at = datetime.now()
        else:
            # 创建新候选人
            candidate = Candidate(
                name=name or "Unknown",
                primary_affiliation=affiliation,
                bio=bio,
                source='openreview'
            )
            db.add(candidate)
            db.flush()  # 获取ID
        
        return candidate
    
    def _create_or_update_openreview_user(self, profile_id: str, profile_url: str, 
                                        candidate_id: int, db: Session) -> OpenReviewUser:
        """创建或更新OpenReviewUser记录"""
        # 查找现有记录
        openreview_user = db.query(OpenReviewUser).filter(
            OpenReviewUser.openreview_profile_id == profile_id
        ).first()
        
        if openreview_user:
            # 更新现有记录
            openreview_user.candidate_id = candidate_id
            openreview_user.last_crawled_at = datetime.now()
        else:
            # 创建新记录
            openreview_user = OpenReviewUser(
                openreview_profile_id=profile_id,
                candidate_id=candidate_id,
                last_crawled_at=datetime.now()
            )
            db.add(openreview_user)
        
        return openreview_user
    
    def _extract_contact_info_from_profile(self, profile_info: Dict[str, Any]) -> Dict[str, Any]:
        """从profile信息中提取联系信息"""
        contact_info = {
            'emails': [],
            'homepages': []
        }
        
        # 提取邮箱
        email = profile_info.get('email', '').strip()
        if email:
            contact_info['emails'].append(email)
        
        # 从bio中提取额外邮箱
        bio = profile_info.get('bio', '')
        if bio:
            bio_emails = self.extractors.extract_emails(bio)
            contact_info['emails'].extend(bio_emails)
        
        # 去重邮箱
        contact_info['emails'] = list(set(contact_info['emails']))
        
        # 提取主页
        homepage = profile_info.get('homepage', '').strip()
        if homepage:
            contact_info['homepages'].append({
                'url': homepage,
                'source': 'openreview_homepage_field'
            })
        
        # 从bio中提取其他主页
        if bio:
            extracted_homepages = self.extractors.extract_homepages(bio)
            for hp in extracted_homepages:
                contact_info['homepages'].append({
                    'url': hp['url'],
                    'source': f"openreview_bio_{hp['type']}"
                })
        
        return contact_info
    
    def _save_contact_info(self, candidate_id: int, contact_info: Dict[str, Any], db: Session):
        """保存联系信息"""
        # 保存邮箱
        for email in contact_info.get('emails', []):
            if not email:
                continue
                
            existing = db.query(CandidateEmail).filter(
                and_(CandidateEmail.candidate_id == candidate_id, CandidateEmail.email == email)
            ).first()
            
            if not existing:
                candidate_email = CandidateEmail(
                    candidate_id=candidate_id,
                    email=email,
                    source='openreview_profile',
                    is_primary=False
                )
                db.add(candidate_email)
        
        # 保存主页
        for homepage in contact_info.get('homepages', []):
            url = homepage.get('url', '').strip()
            if not url:
                continue
                
            existing = db.query(CandidateHomepage).filter(
                and_(CandidateHomepage.candidate_id == candidate_id, CandidateHomepage.url == url)
            ).first()
            
            if not existing:
                candidate_homepage = CandidateHomepage(
                    candidate_id=candidate_id,
                    url=url,
                    source=homepage.get('source', 'openreview_profile')
                )
                db.add(candidate_homepage)
    
    def _save_institution_info(self, candidate_id: int, affiliation: str, db: Session):
        """保存机构信息"""
        if not affiliation or len(affiliation.strip()) < 2:
            return
        
        affiliation = affiliation.strip()
        
        # 检查是否已存在
        existing = db.query(CandidateInstitution).filter(
            and_(
                CandidateInstitution.candidate_id == candidate_id,
                CandidateInstitution.institution_name == affiliation
            )
        ).first()
        
        if not existing:
            institution = CandidateInstitution(
                candidate_id=candidate_id,
                institution_name=affiliation,
                institution_type='academic',  # OpenReview多为学术机构
                source='openreview_profile'
            )
            db.add(institution)
    
    def _create_derived_tasks(self, candidate_id: int, profile_info: Dict[str, Any], 
                            batch_id: str, db: Session) -> int:
        """创建派生任务"""
        tasks_created = 0
        
        # 创建GitHub任务
        github_url = profile_info.get('github', '').strip()
        if github_url and 'github.com' in github_url:
            # 提取GitHub用户名
            import re
            github_match = re.search(r'github\.com/([^/\?]+)', github_url)
            if github_match:
                github_login = github_match.group(1)
                
                # 检查是否已有相同任务
                existing_task = db.query(CrawlTask).filter(
                    and_(
                        CrawlTask.source == 'github',
                        CrawlTask.type == 'profile',
                        CrawlTask.github_login == github_login,
                        CrawlTask.status == 'pending'
                    )
                ).first()
                
                if not existing_task:
                    github_task = CrawlTask(
                        source='github',
                        type='profile',
                        url=github_url,
                        github_login=github_login,
                        candidate_id=candidate_id,
                        batch_id=batch_id,
                        priority=2,
                        status='pending'
                    )
                    db.add(github_task)
                    tasks_created += 1
        
        # 创建homepage任务
        homepage = profile_info.get('homepage', '').strip()
        if homepage and homepage.startswith('http'):
            # 检查是否已有相同任务
            existing_task = db.query(CrawlTask).filter(
                and_(
                    CrawlTask.source == 'homepage',
                    CrawlTask.type == 'homepage',
                    CrawlTask.url == homepage,
                    CrawlTask.status == 'pending'
                )
            ).first()
            
            if not existing_task:
                homepage_task = CrawlTask(
                    source='homepage',
                    type='homepage',
                    url=homepage,
                    candidate_id=candidate_id,
                    batch_id=batch_id,
                    priority=3,
                    status='pending'
                )
                db.add(homepage_task)
                tasks_created += 1
        
        return tasks_created
    
    def _parse_forum_html(self, html_content: str, forum_url: str) -> Optional[Dict[str, Any]]:
        """解析论文论坛HTML内容"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 重用原客户端的解析逻辑
            return self.client._parse_forum_content(soup, forum_url)
            
        except Exception as e:
            logger.error(f"解析论文HTML失败: {forum_url}, 错误: {e}")
            return None
    
    def _parse_profile_html(self, html_content: str, profile_url: str) -> Optional[Dict[str, Any]]:
        """解析用户profile HTML内容"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 重用原客户端的解析逻辑
            return self.client._parse_profile_content(soup, profile_url)
            
        except Exception as e:
            logger.error(f"解析profile HTML失败: {profile_url}, 错误: {e}")
            return None
    
    def set_config(self, config: Dict[str, Any]):
        """设置服务配置"""
        if 'max_tasks' in config:
            self.max_tasks = config['max_tasks']


# 全局实例
openreview_service = OpenReviewService()