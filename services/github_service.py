#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 服务层 - 严格按设计蓝图实现

处理GitHub爬虫的核心业务逻辑，包括智能选仓库、去重、数据提取等
Author: Spidermind
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from models.base import SessionLocal
from crawlers.github_client import github_client
from extractors.regex_extractors import regex_extractors
from models.candidate import Candidate, CandidateEmail, CandidateHomepage, CandidateRepo, CandidateInstitution
from models.crawl import CrawlTask, CrawlLog
from models.mapping import GitHubUser
from services.progress_service import progress_tracker
from services.error_handler import error_handler

logger = logging.getLogger(__name__)


class GitHubService:
    """GitHub服务类 - 实现三种任务类型处理"""
    
    def __init__(self):
        """初始化GitHub服务"""
        self.client = github_client
        self.extractors = regex_extractors
        self.config = {
            'recent_n': 5,
            'star_n': 5, 
            'follow_depth': 1,
            'per_seed_cap': 20,
            'global_cap': 100
        }
    
    def set_config(self, config: Dict[str, Any]):
        """设置服务配置"""
        self.config.update(config)
    
    async def process_profile_task(self, task: CrawlTask) -> Dict[str, Any]:
        """
        处理GitHub用户profile任务 (蓝图核心方法)
        
        Args:
            task: 爬虫任务
            
        Returns:
            Dict: 处理结果 {status, message, error, skipped, success}
        """
        github_login = task.github_login
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub用户名为空',
                'error': 'Missing github_login in task'
            }
        
        db = SessionLocal()
        try:
            # 检查是否已经爬取过此用户 (蓝图要求：同一用户不重复爬)
            existing_user = db.query(GitHubUser).filter(
                GitHubUser.github_login == github_login
            ).first()
            
            if existing_user and existing_user.last_crawled_at:
                # 检查是否需要重新爬取（7天内不重复爬取）
                days_since_crawl = (datetime.now() - existing_user.last_crawled_at).days
                if days_since_crawl < 7:
                    return {
                        'status': 'skip',
                        'message': f'用户 {github_login} 已在 {days_since_crawl} 天前爬取过，跳过重复爬取',
                        'skipped': True,
                        'candidate_id': existing_user.candidate_id
                    }
            
            # 获取用户信息
            logger.info(f"获取GitHub用户信息: {github_login}")
            user_info = await self.client.get_json(f"/users/{github_login}")
            if not user_info:
                return {
                    'status': 'fail',
                    'message': f'无法获取GitHub用户信息: {github_login}',
                    'error': 'GitHub API returned empty user info'
                }
            
            # 创建或更新候选人记录
            candidate = self._create_or_update_candidate(user_info, db)
            
            # 创建或更新GitHubUser记录 (蓝图要求：去重映射)
            github_user = self._create_or_update_github_user(user_info, candidate.id, db)
            
            # 提取并保存联系信息 (蓝图要求：regex_extractors提取邮箱)
            contact_info = self._extract_contact_info_from_profile(user_info)
            contacts_saved = self._save_contact_info(candidate.id, contact_info, db)
            
            # 获取用户组织信息
            try:
                orgs = await self.client.get_json(f"/users/{github_login}/orgs")
            except Exception as e:
                logger.warning(f"获取用户组织信息失败: {github_login}, 错误: {e}")
                orgs = []
            orgs_saved = self._save_organization_info(candidate.id, orgs, db)
            
            # 创建仓库爬取任务
            repo_tasks_created = self._create_repo_tasks(github_login, candidate.id, task.batch_id, db)
            
            # 检查是否发现个人主页并创建homepage任务
            homepage_tasks_created = self._create_homepage_tasks_from_profile(
                candidate.id, user_info, task.batch_id, db
            )
            
            db.commit()
            
            message_parts = [f'成功处理GitHub用户 {github_login}']
            if contacts_saved['emails'] > 0:
                message_parts.append(f'提取邮箱 {contacts_saved["emails"]} 个')
            if contacts_saved['homepages'] > 0:
                message_parts.append(f'发现主页 {contacts_saved["homepages"]} 个')
            if homepage_tasks_created > 0:
                message_parts.append(f'创建homepage任务 {homepage_tasks_created} 个')
            if repo_tasks_created > 0:
                message_parts.append(f'创建repo任务 {repo_tasks_created} 个')
            
            return {
                'status': 'success',
                'message': ', '.join(message_parts),
                'success': True,
                'candidate_id': candidate.id,
                'github_user_id': github_user.id,
                'stats': {
                    'emails_saved': contacts_saved['emails'],
                    'homepages_saved': contacts_saved['homepages'],
                    'orgs_saved': orgs_saved,
                    'repo_tasks_created': repo_tasks_created,
                    'homepage_tasks_created': homepage_tasks_created
                }
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"处理GitHub profile任务失败 {github_login}: {str(e)}"
            logger.error(error_msg)
            error_handler.log_error('github', 'profile', error_msg, task.id)
            
            return {
                'status': 'fail',
                'message': error_msg,
                'error': str(e)
            }
        finally:
            db.close()
    
    async def process_repo_task(self, task: CrawlTask) -> Dict[str, Any]:
        """
        处理GitHub仓库任务 (蓝图核心方法：智能选仓库)
        
        Args:
            task: 爬虫任务
            
        Returns:
            Dict: 处理结果
        """
        github_login = task.github_login
        candidate_id = task.candidate_id
        
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub用户名为空',
                'error': 'Missing github_login in task'
            }
        
        db = SessionLocal()
        try:
            # 获取用户仓库列表
            logger.info(f"获取GitHub用户 {github_login} 的仓库列表")
            repos = await self.client.get_json(f"/users/{github_login}/repos", {
                "sort": "updated",
                "per_page": 100
            })
            if not repos:
                return {
                    'status': 'skip',
                    'message': f'用户 {github_login} 没有公开仓库，跳过repo任务',
                    'skipped': True
                }
            
            # 智能选择仓库 (蓝图要求：智能选仓库策略)
            selected_repos = self._smart_select_repos(
                repos, 
                recent_n=self.config['recent_n'], 
                star_n=self.config['star_n']
            )
            
            logger.info(f"从 {len(repos)} 个仓库中智能选择了 {len(selected_repos)} 个")
            
            saved_count = 0
            homepage_tasks_created = 0
            emails_extracted = 0
            
            for repo_info in selected_repos:
                try:
                    # 保存仓库信息 (蓝图要求：记录picked_reason、stars、forks、last_commit)
                    repo_record = self._save_repository_info(candidate_id, repo_info, db)
                    saved_count += 1
                    
                    # 获取README并提取信息 (蓝图要求：从README抽取邮箱与homepage)
                    try:
                        readme_data = await self.client.get_json(f"/repos/{repo_info['owner']['login']}/{repo_info['name']}/readme")
                        # GitHub API返回的是base64编码的内容
                        import base64
                        readme_content = base64.b64decode(readme_data.get('content', '')).decode('utf-8') if readme_data else ''
                    except Exception as e:
                        logger.debug(f"获取README失败: {repo_info['name']}, 错误: {e}")
                        readme_content = ''
                    if readme_content:
                        # 清理README文本以便提取
                        clean_readme = self.extractors.clean_text_for_extraction(readme_content)
                        
                        # 从README提取所有信息
                        extracted_info = self.extractors.extract_all(clean_readme)
                        
                        # 保存邮箱信息 (蓝图要求：入candidate_emails)
                        emails_saved = self._save_extracted_emails(
                            candidate_id, extracted_info.get('emails', []), 'github_readme', db
                        )
                        emails_extracted += emails_saved
                        
                        # 保存主页信息 (蓝图要求：入candidate_homepages)
                        homepages_saved = self._save_extracted_homepages(
                            candidate_id, extracted_info.get('homepages', []), 'github_readme', db
                        )
                        
                        # 创建主页任务 (蓝图要求：发现*.github.io/blog等创建homepage任务)
                        homepage_count = self._create_homepage_tasks_from_extracted(
                            candidate_id, extracted_info, task.batch_id, db
                        )
                        homepage_tasks_created += homepage_count
                    
                except Exception as e:
                    logger.warning(f"处理仓库失败: {repo_info.get('name', 'unknown')}, 错误: {e}")
                    continue
            
            db.commit()
            
            message_parts = [f'成功处理 {saved_count} 个GitHub仓库']
            if emails_extracted > 0:
                message_parts.append(f'从README提取邮箱 {emails_extracted} 个')
            if homepage_tasks_created > 0:
                message_parts.append(f'创建homepage任务 {homepage_tasks_created} 个')
            
            return {
                'status': 'success',
                'message': ', '.join(message_parts),
                'success': True,
                'stats': {
                    'repos_processed': saved_count,
                    'emails_extracted': emails_extracted,
                    'homepage_tasks_created': homepage_tasks_created,
                    'selected_from_total': f'{len(selected_repos)}/{len(repos)}'
                }
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"处理GitHub repo任务失败 {github_login}: {str(e)}"
            logger.error(error_msg)
            error_handler.log_error('github', 'repo', error_msg, task.id)
            
            return {
                'status': 'fail',
                'message': error_msg,
                'error': str(e)
            }
        finally:
            db.close()
    
    async def process_follow_scan_task(self, task: CrawlTask) -> Dict[str, Any]:
        """
        处理GitHub关注/粉丝扫描任务 (蓝图核心方法)
        
        Args:
            task: 爬虫任务
            
        Returns:
            Dict: 处理结果
        """
        github_login = task.github_login
        depth = task.depth or self.config['follow_depth']
        
        if not github_login:
            return {
                'status': 'fail',
                'message': 'GitHub用户名为空',
                'error': 'Missing github_login in task'
            }
        
        db = SessionLocal()
        try:
            # 获取关注列表和粉丝列表
            logger.info(f"获取GitHub用户 {github_login} 的关注和粉丝")
            try:
                following = await self.client.get_json(f"/users/{github_login}/following", {"per_page": 100})
            except Exception as e:
                logger.warning(f"获取关注列表失败: {github_login}, 错误: {e}")
                following = []
            
            try:
                followers = await self.client.get_json(f"/users/{github_login}/followers", {"per_page": 100})
            except Exception as e:
                logger.warning(f"获取粉丝列表失败: {github_login}, 错误: {e}")
                followers = []
            
            # 合并并去重
            all_users = {}
            for user in (following or []) + (followers or []):
                login = user.get('login')
                if login and login not in all_users:
                    all_users[login] = user
            
            if not all_users:
                return {
                    'status': 'skip',
                    'message': f'用户 {github_login} 没有公开的关注或粉丝信息，跳过follow_scan任务',
                    'skipped': True
                }
            
            logger.info(f"发现 {len(all_users)} 个关注/粉丝用户")
            
            # 过滤和评分 (学术相关用户优先)
            filtered_users = self._filter_and_score_users(
                list(all_users.values()),
                per_seed_cap=self.config['per_seed_cap'],
                global_cap=self.config['global_cap']
            )
            
            logger.info(f"经过评分筛选后保留 {len(filtered_users)} 个用户")
            
            # 创建profile任务
            tasks_created = self._create_profile_tasks_from_follow(
                filtered_users, depth, task.batch_id, db
            )
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'从 {len(all_users)} 个关注/粉丝中筛选出 {len(filtered_users)} 个，创建 {tasks_created} 个profile任务',
                'success': True,
                'stats': {
                    'total_users_found': len(all_users),
                    'users_after_filtering': len(filtered_users),
                    'profile_tasks_created': tasks_created,
                    'following_count': len(following or []),
                    'followers_count': len(followers or [])
                }
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"处理GitHub follow_scan任务失败 {github_login}: {str(e)}"
            logger.error(error_msg)
            error_handler.log_error('github', 'follow_scan', error_msg, task.id)
            
            return {
                'status': 'fail',
                'message': error_msg,
                'error': str(e)
            }
        finally:
            db.close()
    
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
                github_login=login,  # 记录GitHub登录名
                avatar_url=user_info.get('avatar_url'),
                current_institution=user_info.get('company'),
                homepage_main=user_info.get('blog') if user_info.get('blog') else None,
                status='raw',
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(candidate)
            db.flush()  # 获取ID
        else:
            # 更新现有候选人信息
            if user_info.get('name'):
                candidate.name = user_info.get('name')
            if user_info.get('company'):
                candidate.current_institution = user_info.get('company')
            if user_info.get('blog'):
                candidate.homepage_main = user_info.get('blog')
            if user_info.get('avatar_url'):
                candidate.avatar_url = user_info.get('avatar_url')
            candidate.updated_at = datetime.now()
        
        return candidate
    
    def _create_or_update_github_user(self, user_info: Dict[str, Any], candidate_id: int, db: Session) -> GitHubUser:
        """创建或更新GitHubUser记录 (蓝图要求：去重关键)"""
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
                last_crawled_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(github_user)
        else:
            github_user.candidate_id = candidate_id
            github_user.last_crawled_at = datetime.now()
            github_user.updated_at = datetime.now()
        
        return github_user
    
    def _extract_contact_info_from_profile(self, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """从用户profile信息中提取联系信息 (蓝图要求：使用regex_extractors)"""
        contact_info = {
            'emails': [],
            'homepages': []
        }
        
        # 从各个字段提取信息
        text_fields = [
            user_info.get('bio', ''),
            user_info.get('company', ''),
            user_info.get('location', ''),
            user_info.get('blog', ''),
            user_info.get('name', '')
        ]
        
        combined_text = ' '.join(filter(None, text_fields))
        if combined_text.strip():
            # 使用regex_extractors提取信息
            extracted_info = self.extractors.extract_all(combined_text)
            
            # 提取邮箱
            contact_info['emails'] = extracted_info.get('emails', [])
            
            # 处理homepages
            contact_info['homepages'] = extracted_info.get('homepages', [])
        
        # 处理blog字段作为主页
        blog_url = user_info.get('blog', '').strip()
        if blog_url:
            if not blog_url.startswith('http'):
                blog_url = 'https://' + blog_url
            contact_info['homepages'].append({
                'url': blog_url,
                'type': 'github_blog_field',
                'confidence': 0.9
            })
        
        return contact_info
    
    def _save_contact_info(self, candidate_id: int, contact_info: Dict[str, Any], db: Session) -> Dict[str, int]:
        """保存联系信息并返回统计"""
        stats = {'emails': 0, 'homepages': 0}
        
        # 保存邮箱
        for email in contact_info.get('emails', []):
            try:
                existing = db.query(CandidateEmail).filter(
                    and_(CandidateEmail.candidate_id == candidate_id, CandidateEmail.email == email)
                ).first()
                
                if not existing:
                    candidate_email = CandidateEmail(
                        candidate_id=candidate_id,
                        email=email,
                        source='github_profile',
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(candidate_email)
                    stats['emails'] += 1
            except Exception as e:
                logger.warning(f"保存邮箱失败: {email}, 错误: {e}")
                continue
        
        # 保存主页
        for homepage in contact_info.get('homepages', []):
            try:
                url = homepage.get('url') if isinstance(homepage, dict) else homepage
                if not url:
                    continue
                    
                existing = db.query(CandidateHomepage).filter(
                    and_(CandidateHomepage.candidate_id == candidate_id, CandidateHomepage.url == url)
                ).first()
                
                if not existing:
                    source = 'github_profile'
                    if isinstance(homepage, dict):
                        source = f"github_profile_{homepage.get('type', 'unknown')}"
                    
                    candidate_homepage = CandidateHomepage(
                        candidate_id=candidate_id,
                        url=url,
                        source=source,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(candidate_homepage)
                    stats['homepages'] += 1
            except Exception as e:
                logger.warning(f"保存主页失败: {homepage}, 错误: {e}")
                continue
        
        return stats
    
    def _save_organization_info(self, candidate_id: int, orgs: List[Dict[str, Any]], db: Session) -> int:
        """保存组织信息并返回保存数量"""
        saved_count = 0
        
        for org in (orgs or [])[:5]:  # 最多保存5个组织
            try:
                org_name = org.get('login') or org.get('name')
                if not org_name:
                    continue
                
                existing = db.query(CandidateInstitution).filter(
                    and_(CandidateInstitution.candidate_id == candidate_id, 
                         CandidateInstitution.institution == org_name)
                ).first()
                
                if not existing:
                    institution = CandidateInstitution(
                        candidate_id=candidate_id,
                        institution=org_name,
                        source='github_orgs',
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(institution)
                    saved_count += 1
            except Exception as e:
                logger.warning(f"保存组织失败: {org}, 错误: {e}")
                continue
        
        return saved_count
    
    def _smart_select_repos(self, repos: List[Dict[str, Any]], recent_n: int = 5, star_n: int = 5) -> List[Dict[str, Any]]:
        """
        智能选择仓库 (蓝图核心算法)
        
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
        """保存仓库信息 (蓝图要求：记录picked_reason、stars、forks、last_commit)"""
        repo_name = repo_info.get('name')
        repo_url = repo_info.get('html_url')
        
        try:
            existing = db.query(CandidateRepo).filter(
                and_(CandidateRepo.candidate_id == candidate_id, CandidateRepo.repo_url == repo_url)
            ).first()
            
            # 解析last_commit时间
            last_commit = None
            if repo_info.get('updated_at'):
                try:
                    last_commit = datetime.fromisoformat(repo_info['updated_at'].replace('Z', '+00:00'))
                except:
                    pass
            
            if existing:
                # 更新现有记录
                existing.repo_name = repo_name
                existing.description = repo_info.get('description')
                existing.stars = repo_info.get('stargazers_count', 0)
                existing.forks = repo_info.get('forks_count', 0)
                existing.language = repo_info.get('language')
                existing.last_commit = last_commit
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
                    last_commit=last_commit,
                    picked_reason=repo_info.get('picked_reason', 'selected'),
                    source='github',
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(repo_record)
                return repo_record
        except Exception as e:
            logger.error(f"保存仓库信息失败: {repo_name}, 错误: {e}")
            raise
    
    def _save_extracted_emails(self, candidate_id: int, emails: List[str], source: str, db: Session) -> int:
        """保存从README提取的邮箱 (蓝图要求：入candidate_emails)"""
        saved_count = 0
        
        for email in emails:
            try:
                existing = db.query(CandidateEmail).filter(
                    and_(CandidateEmail.candidate_id == candidate_id, CandidateEmail.email == email)
                ).first()
                
                if not existing:
                    candidate_email = CandidateEmail(
                        candidate_id=candidate_id,
                        email=email,
                        source=source,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(candidate_email)
                    saved_count += 1
            except Exception as e:
                logger.warning(f"保存提取的邮箱失败: {email}, 错误: {e}")
                continue
        
        return saved_count
    
    def _save_extracted_homepages(self, candidate_id: int, homepages: List[Dict[str, Any]], source: str, db: Session) -> int:
        """保存从README提取的主页 (蓝图要求：入candidate_homepages)"""
        saved_count = 0
        
        for homepage in homepages:
            try:
                url = homepage.get('url') if isinstance(homepage, dict) else homepage
                if not url:
                    continue
                    
                existing = db.query(CandidateHomepage).filter(
                    and_(CandidateHomepage.candidate_id == candidate_id, CandidateHomepage.url == url)
                ).first()
                
                if not existing:
                    homepage_source = source
                    if isinstance(homepage, dict) and homepage.get('type'):
                        homepage_source = f"{source}_{homepage['type']}"
                    
                    candidate_homepage = CandidateHomepage(
                        candidate_id=candidate_id,
                        url=url,
                        source=homepage_source,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(candidate_homepage)
                    saved_count += 1
            except Exception as e:
                logger.warning(f"保存提取的主页失败: {homepage}, 错误: {e}")
                continue
        
        return saved_count
    
    def _create_homepage_tasks_from_profile(self, candidate_id: int, user_info: Dict[str, Any], 
                                          batch_id: str, db: Session) -> int:
        """从profile信息创建主页任务"""
        tasks_created = 0
        
        # 检查blog字段
        blog_url = user_info.get('blog', '').strip()
        if blog_url:
            if not blog_url.startswith('http'):
                blog_url = 'https://' + blog_url
            
            # 检查是否是个人主页 (蓝图要求：发现*.github.io等)
            if self._is_personal_homepage(blog_url):
                tasks_created += self._create_homepage_task(candidate_id, blog_url, batch_id, db)
        
        return tasks_created
    
    def _create_homepage_tasks_from_extracted(self, candidate_id: int, extracted_info: Dict[str, Any], 
                                            batch_id: str, db: Session) -> int:
        """从README提取的信息创建主页任务 (蓝图要求：发现个人站创建homepage任务)"""
        tasks_created = 0
        
        # 从主页信息创建任务
        for homepage in extracted_info.get('homepages', []):
            url = homepage.get('url') if isinstance(homepage, dict) else homepage
            if not url:
                continue
            
            # 检查是否是个人主页
            if self._is_personal_homepage(url):
                tasks_created += self._create_homepage_task(candidate_id, url, batch_id, db)
        
        return tasks_created
    
    def _is_personal_homepage(self, url: str) -> bool:
        """判断是否是个人主页 (蓝图要求：*.github.io/blog/个人站检测)"""
        url_lower = url.lower()
        
        # GitHub Pages
        if '.github.io' in url_lower:
            return True
        
        # 个人博客指示词
        blog_indicators = [
            'blog', 'personal', 'portfolio', 'homepage', 'about',
            'me.', '.dev/', '.io/', 'pages', 'site'
        ]
        
        return any(indicator in url_lower for indicator in blog_indicators)
    
    def _create_homepage_task(self, candidate_id: int, url: str, batch_id: str, db: Session) -> int:
        """创建单个主页任务 (蓝图要求：创建crawl_tasks(source='homepage'))"""
        try:
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
                    status='pending',
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(task)
                return 1
        except Exception as e:
            logger.warning(f"创建homepage任务失败: {url}, 错误: {e}")
        
        return 0
    
    def _create_repo_tasks(self, github_login: str, candidate_id: int, batch_id: str, db: Session) -> int:
        """创建仓库爬取任务"""
        try:
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
                    status='pending',
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(task)
                return 1
        except Exception as e:
            logger.warning(f"创建repo任务失败: {github_login}, 错误: {e}")
        
        return 0
    
    def _filter_and_score_users(self, users: List[Dict[str, Any]], 
                               per_seed_cap: int = 20, global_cap: int = 100) -> List[Dict[str, Any]]:
        """过滤和评分用户 (学术相关用户优先)"""
        scored_users = []
        
        # 学术关键词
        academic_keywords = [
            'research', 'phd', 'professor', 'university', 'lab', 'student',
            'science', 'machine learning', 'ai', 'data science', 'computer science',
            'researcher', 'academic', 'scholar', 'postdoc', 'faculty'
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
            
            try:
                # 检查是否已爬取过 (蓝图要求：同一用户不重复爬)
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
                        status='pending',
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(task)
                    tasks_created += 1
            except Exception as e:
                logger.warning(f"创建profile任务失败: {login}, 错误: {e}")
                continue
        
        return tasks_created


# 全局实例
github_service = GitHubService()