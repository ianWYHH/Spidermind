#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 服务层

处理GitHub爬虫的核心业务逻辑，包括智能选仓库、去重、数据提取等
Author: Spidermind
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from crawlers.github_client import github_client
from extractors.regex_extractors import regex_extractors
from models.candidate import Candidate, CandidateEmail, CandidateHomepage, CandidateRepo
from models.crawl import CrawlTask, CrawlLog
from models.mapping import GitHubUser
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)


class GitHubService:
    """GitHub服务类"""
    
    def __init__(self):
        """初始化GitHub服务"""
        self.client = github_client
        self.extractors = regex_extractors
    
    def process_profile_task(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理GitHub用户profile任务
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        github_login = task.github_login
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub login 为空'
            }
        
        try:
            # 检查是否已经爬取过此用户
            existing_user = db.query(GitHubUser).filter(
                GitHubUser.github_login == github_login
            ).first()
            
            if existing_user and existing_user.last_crawled_at:
                # 检查是否需要重新爬取（比如7天内不重复爬取）
                if existing_user.last_crawled_at > datetime.now() - timedelta(days=7):
                    return {
                        'status': 'skip',
                        'message': f'用户 {github_login} 近期已爬取过，跳过',
                        'candidate_id': existing_user.candidate_id
                    }
            
            # 获取用户信息
            user_info = self.client.get_user(github_login)
            if not user_info:
                return {
                    'status': 'fail',
                    'message': f'无法获取用户信息: {github_login}'
                }
            
            # 创建或更新候选人记录
            candidate = self._create_or_update_candidate(user_info, db)
            
            # 创建或更新GitHubUser记录
            github_user = self._create_or_update_github_user(user_info, candidate.id, db)
            
            # 提取并保存联系信息
            contact_info = self._extract_contact_info(user_info)
            self._save_contact_info(candidate.id, contact_info, db)
            
            # 获取用户组织信息
            orgs = self.client.get_user_orgs(github_login)
            self._save_organization_info(candidate.id, orgs, db)
            
            # 创建仓库爬取任务
            self._create_repo_tasks(github_login, candidate.id, task.batch_id, db)
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'成功处理用户 {github_login}',
                'candidate_id': candidate.id,
                'github_user_id': github_user.id
            }
            
        except Exception as e:
            logger.error(f"处理GitHub profile任务失败: {github_login}, 错误: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def process_repo_task(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理GitHub仓库任务
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        github_login = task.github_login
        candidate_id = task.candidate_id
        
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub login 为空'
            }
        
        try:
            # 获取用户仓库列表
            repos = self.client.get_user_repos(github_login, sort="updated")
            if not repos:
                return {
                    'status': 'skip',
                    'message': f'用户 {github_login} 没有公开仓库'
                }
            
            # 智能选择仓库
            selected_repos = self._smart_select_repos(repos)
            
            saved_count = 0
            homepage_tasks_created = 0
            
            for repo_info in selected_repos:
                try:
                    # 保存仓库信息
                    repo_record = self._save_repository_info(candidate_id, repo_info, db)
                    saved_count += 1
                    
                    # 获取README并提取信息
                    readme_content = self.client.get_readme(repo_info['owner']['login'], repo_info['name'])
                    if readme_content:
                        # 从README提取联系信息和主页
                        extracted_info = self.extractors.extract_all(readme_content)
                        
                        # 保存邮箱信息
                        self._save_extracted_emails(candidate_id, extracted_info.get('emails', []), db)
                        
                        # 创建主页任务
                        homepage_count = self._create_homepage_tasks_from_readme(
                            candidate_id, extracted_info, task.batch_id, db
                        )
                        homepage_tasks_created += homepage_count
                    
                except Exception as e:
                    logger.warning(f"处理仓库失败: {repo_info.get('name', 'unknown')}, 错误: {e}")
                    continue
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'成功处理 {saved_count} 个仓库，创建 {homepage_tasks_created} 个主页任务',
                'repos_processed': saved_count,
                'homepage_tasks_created': homepage_tasks_created
            }
            
        except Exception as e:
            logger.error(f"处理GitHub repo任务失败: {github_login}, 错误: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def process_follow_scan_task(self, task: CrawlTask, db: Session) -> Dict[str, Any]:
        """
        处理GitHub关注/粉丝扫描任务
        
        Args:
            task: 爬虫任务
            db: 数据库会话
            
        Returns:
            Dict: 处理结果
        """
        github_login = task.github_login
        depth = task.depth or 1
        
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub login 为空'
            }
        
        try:
            # 获取关注列表和粉丝列表
            following = self.client.get_user_following(github_login, per_page=50)
            followers = self.client.get_user_followers(github_login, per_page=50)
            
            # 合并并去重
            all_users = {}
            for user in following + followers:
                login = user.get('login')
                if login and login not in all_users:
                    all_users[login] = user
            
            if not all_users:
                return {
                    'status': 'skip',
                    'message': f'用户 {github_login} 没有关注或粉丝信息'
                }
            
            # 过滤和评分
            filtered_users = self._filter_and_score_users(list(all_users.values()))
            
            # 创建profile任务
            tasks_created = self._create_profile_tasks_from_follow(
                filtered_users, depth, task.batch_id, db
            )
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'从 {len(all_users)} 个用户中筛选出 {tasks_created} 个任务',
                'total_users_found': len(all_users),
                'tasks_created': tasks_created
            }
            
        except Exception as e:
            logger.error(f"处理GitHub follow_scan任务失败: {github_login}, 错误: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'处理失败: {str(e)}'
            }
    
    def _create_or_update_candidate(self, user_info: Dict[str, Any], db: Session) -> Candidate:
        """创建或更新候选人记录"""
        github_id = user_info.get('id')
        login = user_info.get('login')
        
        # 查找现有候选人
        candidate = None
        if github_id:
            github_user = db.query(GitHubUser).filter(GitHubUser.github_id == github_id).first()
            if github_user and github_user.candidate_id:
                candidate = db.query(Candidate).filter(Candidate.id == github_user.candidate_id).first()
        
        # 创建新候选人
        if not candidate:
            candidate = Candidate(
                name=user_info.get('name') or login,
                primary_affiliation=user_info.get('company'),
                bio=user_info.get('bio'),
                location=user_info.get('location'),
                source='github'
            )
            db.add(candidate)
            db.flush()  # 获取ID
        else:
            # 更新现有候选人信息
            if user_info.get('name'):
                candidate.name = user_info.get('name')
            if user_info.get('company'):
                candidate.primary_affiliation = user_info.get('company')
            if user_info.get('bio'):
                candidate.bio = user_info.get('bio')
            if user_info.get('location'):
                candidate.location = user_info.get('location')
            candidate.updated_at = datetime.now()
        
        return candidate
    
    def _create_or_update_github_user(self, user_info: Dict[str, Any], candidate_id: int, db: Session) -> GitHubUser:
        """创建或更新GitHubUser记录"""
        github_id = user_info.get('id')
        login = user_info.get('login')
        
        # 查找现有记录
        github_user = None
        if github_id:
            github_user = db.query(GitHubUser).filter(GitHubUser.github_id == github_id).first()
        
        if not github_user and login:
            github_user = db.query(GitHubUser).filter(GitHubUser.github_login == login).first()
        
        # 创建或更新记录
        if not github_user:
            github_user = GitHubUser(
                github_id=github_id,
                github_login=login,
                candidate_id=candidate_id,
                last_crawled_at=datetime.now()
            )
            db.add(github_user)
        else:
            github_user.candidate_id = candidate_id
            github_user.last_crawled_at = datetime.now()
        
        return github_user
    
    def _extract_contact_info(self, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """从用户信息中提取联系信息"""
        contact_info = {
            'emails': [],
            'homepages': []
        }
        
        # 从各个字段提取信息
        text_fields = [
            user_info.get('bio', ''),
            user_info.get('company', ''),
            user_info.get('location', ''),
            user_info.get('blog', '')
        ]
        
        combined_text = ' '.join(filter(None, text_fields))
        
        # 提取邮箱
        emails = self.extractors.extract_emails(combined_text)
        contact_info['emails'] = emails
        
        # 处理blog字段作为主页
        blog_url = user_info.get('blog', '').strip()
        if blog_url:
            if not blog_url.startswith('http'):
                blog_url = 'https://' + blog_url
            contact_info['homepages'].append({
                'url': blog_url,
                'source': 'github_blog_field'
            })
        
        # 从文本中提取其他主页
        extracted_homepages = self.extractors.extract_homepages(combined_text)
        for homepage in extracted_homepages:
            contact_info['homepages'].append({
                'url': homepage['url'],
                'source': f"github_profile_{homepage['type']}"
            })
        
        return contact_info
    
    def _save_contact_info(self, candidate_id: int, contact_info: Dict[str, Any], db: Session):
        """保存联系信息"""
        # 保存邮箱
        for email in contact_info.get('emails', []):
            existing = db.query(CandidateEmail).filter(
                and_(CandidateEmail.candidate_id == candidate_id, CandidateEmail.email == email)
            ).first()
            
            if not existing:
                candidate_email = CandidateEmail(
                    candidate_id=candidate_id,
                    email=email,
                    source='github_profile',
                    is_primary=False
                )
                db.add(candidate_email)
        
        # 保存主页
        for homepage in contact_info.get('homepages', []):
            existing = db.query(CandidateHomepage).filter(
                and_(CandidateHomepage.candidate_id == candidate_id, CandidateHomepage.url == homepage['url'])
            ).first()
            
            if not existing:
                candidate_homepage = CandidateHomepage(
                    candidate_id=candidate_id,
                    url=homepage['url'],
                    source=homepage['source']
                )
                db.add(candidate_homepage)
    
    def _save_organization_info(self, candidate_id: int, orgs: List[Dict[str, Any]], db: Session):
        """保存组织信息"""
        from models.candidate import CandidateInstitution
        
        for org in orgs[:5]:  # 最多保存5个组织
            org_name = org.get('login') or org.get('name')
            if not org_name:
                continue
            
            existing = db.query(CandidateInstitution).filter(
                and_(CandidateInstitution.candidate_id == candidate_id, CandidateInstitution.institution_name == org_name)
            ).first()
            
            if not existing:
                institution = CandidateInstitution(
                    candidate_id=candidate_id,
                    institution_name=org_name,
                    institution_type='organization',
                    source='github_orgs'
                )
                db.add(institution)
    
    def _smart_select_repos(self, repos: List[Dict[str, Any]], recent_n: int = 5, star_n: int = 5) -> List[Dict[str, Any]]:
        """
        智能选择仓库
        
        Args:
            repos: 仓库列表
            recent_n: 最近更新的仓库数量
            star_n: 最高星标的仓库数量
            
        Returns:
            List[Dict]: 选中的仓库列表，包含picked_reason
        """
        if len(repos) <= 10:
            # 仓库数量<=10，全部选择
            for repo in repos:
                repo['picked_reason'] = 'all_repos_selected'
            return repos
        
        selected_repos = {}
        
        # 选择最近更新的仓库
        sorted_by_update = sorted(repos, key=lambda x: x.get('updated_at', ''), reverse=True)
        for i, repo in enumerate(sorted_by_update[:recent_n]):
            repo_id = repo.get('id')
            if repo_id not in selected_repos:
                repo['picked_reason'] = f'recent_update_rank_{i+1}'
                selected_repos[repo_id] = repo
        
        # 选择星标最高的仓库
        sorted_by_stars = sorted(repos, key=lambda x: x.get('stargazers_count', 0), reverse=True)
        for i, repo in enumerate(sorted_by_stars[:star_n]):
            repo_id = repo.get('id')
            if repo_id not in selected_repos:
                repo['picked_reason'] = f'top_stars_rank_{i+1}'
                selected_repos[repo_id] = repo
        
        return list(selected_repos.values())
    
    def _save_repository_info(self, candidate_id: int, repo_info: Dict[str, Any], db: Session) -> CandidateRepo:
        """保存仓库信息"""
        repo_name = repo_info.get('name')
        repo_url = repo_info.get('html_url')
        
        existing = db.query(CandidateRepo).filter(
            and_(CandidateRepo.candidate_id == candidate_id, CandidateRepo.repo_name == repo_name)
        ).first()
        
        if existing:
            # 更新现有记录
            existing.repo_url = repo_url
            existing.description = repo_info.get('description')
            existing.stars = repo_info.get('stargazers_count', 0)
            existing.forks = repo_info.get('forks_count', 0)
            existing.language = repo_info.get('language')
            existing.picked_reason = repo_info.get('picked_reason', 'updated')
            existing.updated_at = datetime.now()
            return existing
        else:
            # 创建新记录
            repo_record = CandidateRepo(
                candidate_id=candidate_id,
                repo_name=repo_name,
                repo_url=repo_url,
                description=repo_info.get('description'),
                stars=repo_info.get('stargazers_count', 0),
                forks=repo_info.get('forks_count', 0),
                language=repo_info.get('language'),
                picked_reason=repo_info.get('picked_reason', 'selected'),
                source='github'
            )
            db.add(repo_record)
            return repo_record
    
    def _save_extracted_emails(self, candidate_id: int, emails: List[str], db: Session):
        """保存从README提取的邮箱"""
        for email in emails:
            existing = db.query(CandidateEmail).filter(
                and_(CandidateEmail.candidate_id == candidate_id, CandidateEmail.email == email)
            ).first()
            
            if not existing:
                candidate_email = CandidateEmail(
                    candidate_id=candidate_id,
                    email=email,
                    source='github_readme',
                    is_primary=False
                )
                db.add(candidate_email)
    
    def _create_homepage_tasks_from_readme(self, candidate_id: int, extracted_info: Dict[str, Any], 
                                         batch_id: str, db: Session) -> int:
        """从README提取的信息创建主页任务"""
        tasks_created = 0
        
        # 从主页信息创建任务
        for homepage in extracted_info.get('homepages', []):
            url = homepage.get('url')
            if not url:
                continue
            
            # 检查是否已存在相同任务
            existing_task = db.query(CrawlTask).filter(
                and_(
                    CrawlTask.source == 'homepage',
                    CrawlTask.url == url,
                    CrawlTask.status == 'pending'
                )
            ).first()
            
            if not existing_task:
                task = CrawlTask(
                    source='homepage',
                    type='homepage',
                    url=url,
                    candidate_id=candidate_id,
                    batch_id=batch_id,
                    priority=3,  # 较低优先级
                    status='pending'
                )
                db.add(task)
                tasks_created += 1
        
        return tasks_created
    
    def _create_repo_tasks(self, github_login: str, candidate_id: int, batch_id: str, db: Session):
        """创建仓库爬取任务"""
        # 检查是否已存在相同任务
        existing_task = db.query(CrawlTask).filter(
            and_(
                CrawlTask.source == 'github',
                CrawlTask.type == 'repo',
                CrawlTask.github_login == github_login,
                CrawlTask.status == 'pending'
            )
        ).first()
        
        if not existing_task:
            task = CrawlTask(
                source='github',
                type='repo',
                url=f"https://github.com/{github_login}",
                github_login=github_login,
                candidate_id=candidate_id,
                batch_id=batch_id,
                priority=2,
                status='pending'
            )
            db.add(task)
    
    def _filter_and_score_users(self, users: List[Dict[str, Any]], 
                               per_seed_cap: int = 20, global_cap: int = 100) -> List[Dict[str, Any]]:
        """过滤和评分用户"""
        scored_users = []
        
        # 关键词评分
        academic_keywords = [
            'research', 'phd', 'professor', 'university', 'lab', 'student',
            'science', 'machine learning', 'ai', 'data science', 'computer science'
        ]
        
        for user in users:
            score = 0
            bio = (user.get('bio') or '').lower()
            name = (user.get('name') or '').lower()
            login = (user.get('login') or '').lower()
            
            # 关键词匹配评分
            combined_text = f"{bio} {name} {login}"
            for keyword in academic_keywords:
                if keyword in combined_text:
                    score += 1
            
            # 活跃度评分
            public_repos = user.get('public_repos', 0)
            followers = user.get('followers', 0)
            
            if public_repos > 10:
                score += 2
            elif public_repos > 5:
                score += 1
            
            if followers > 100:
                score += 2
            elif followers > 50:
                score += 1
            
            user['_score'] = score
            scored_users.append(user)
        
        # 按评分排序并限制数量
        scored_users.sort(key=lambda x: x['_score'], reverse=True)
        return scored_users[:min(per_seed_cap, global_cap)]
    
    def _create_profile_tasks_from_follow(self, users: List[Dict[str, Any]], 
                                        depth: int, batch_id: str, db: Session) -> int:
        """从关注/粉丝创建profile任务"""
        tasks_created = 0
        
        for user in users:
            login = user.get('login')
            if not login:
                continue
            
            # 检查是否已爬取过
            existing_user = db.query(GitHubUser).filter(GitHubUser.github_login == login).first()
            if existing_user and existing_user.last_crawled_at:
                continue
            
            # 检查是否已有待处理任务
            existing_task = db.query(CrawlTask).filter(
                and_(
                    CrawlTask.source == 'github',
                    CrawlTask.type == 'profile',
                    CrawlTask.github_login == login,
                    CrawlTask.status == 'pending'
                )
            ).first()
            
            if not existing_task:
                task = CrawlTask(
                    source='github',
                    type='profile',
                    url=f"https://github.com/{login}",
                    github_login=login,
                    depth=depth,
                    batch_id=batch_id,
                    priority=1,
                    status='pending'
                )
                db.add(task)
                tasks_created += 1
        
        return tasks_created


# 全局实例
github_service = GitHubService()