#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenReview 服务层

处理OpenReview爬虫的核心业务逻辑，包括论文作者发现和profile信息提取
Author: Spidermind
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from crawlers.openreview_client import openreview_client
from extractors.regex_extractors import regex_extractors
from models.candidate import Candidate, CandidateEmail, CandidateHomepage, CandidatePaper, CandidateInstitution
from models.crawl import CrawlTask, CrawlLog
from models.mapping import OpenReviewUser
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)


class OpenReviewService:
    """OpenReview服务类"""
    
    def __init__(self):
        """初始化OpenReview服务"""
        self.client = openreview_client
        self.extractors = regex_extractors
    
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
            # 获取论文信息
            paper_info = self.client.get_forum_info(forum_url)
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
            
            # 获取用户profile信息
            profile_info = self.client.get_profile_info(profile_url)
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


# 全局实例
openreview_service = OpenReviewService()