#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计服务

提供系统各类统计数据
Author: Spidermind
"""

import logging
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case
from datetime import datetime, timedelta

from models.candidate import (
    Candidate, CandidateEmail, CandidateHomepage, 
    CandidateFile, CandidateInstitution, CandidateRepo,
    RawText
)
from models.crawl import CrawlTask, CrawlLog

logger = logging.getLogger(__name__)


class StatsService:
    """统计服务类"""
    
    def __init__(self):
        """初始化统计服务"""
        pass
    
    def get_task_statistics(self, db: Session) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 任务统计数据
        """
        try:
            # 按源和类型分组统计任务状态
            task_stats = db.query(
                CrawlTask.source,
                CrawlTask.type,
                CrawlTask.status,
                func.count(CrawlTask.id).label('count')
            ).group_by(
                CrawlTask.source,
                CrawlTask.type,
                CrawlTask.status
            ).all()
            
            # 组织数据结构
            stats_by_source = {}
            total_stats = {'pending': 0, 'done': 0, 'failed': 0, 'running': 0}
            
            for stat in task_stats:
                source = stat.source
                task_type = stat.type
                status = stat.status
                count = stat.count
                
                if source not in stats_by_source:
                    stats_by_source[source] = {
                        'total': 0,
                        'by_type': {},
                        'by_status': {'pending': 0, 'done': 0, 'failed': 0, 'running': 0}
                    }
                
                # 按类型统计
                if task_type not in stats_by_source[source]['by_type']:
                    stats_by_source[source]['by_type'][task_type] = {
                        'pending': 0, 'done': 0, 'failed': 0, 'running': 0, 'total': 0
                    }
                
                stats_by_source[source]['by_type'][task_type][status] = count
                stats_by_source[source]['by_type'][task_type]['total'] += count
                
                # 按状态汇总
                stats_by_source[source]['by_status'][status] += count
                stats_by_source[source]['total'] += count
                
                # 全局统计
                total_stats[status] += count
            
            total_stats['total'] = sum(total_stats.values())
            
            return {
                'by_source': stats_by_source,
                'total': total_stats,
                'sources': list(stats_by_source.keys())
            }
            
        except Exception as e:
            logger.error(f"获取任务统计失败: {e}")
            return {
                'by_source': {},
                'total': {'pending': 0, 'done': 0, 'failed': 0, 'running': 0, 'total': 0},
                'sources': []
            }
    
    def get_candidate_parse_progress(self, db: Session) -> Dict[str, Any]:
        """
        获取候选人解析进度
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 解析进度数据
        """
        try:
            # 总候选人数
            total_candidates = db.query(func.count(Candidate.id)).scalar()
            
            # 已解析候选人数
            parsed_candidates = db.query(func.count(Candidate.id)).filter(
                Candidate.llm_processed == True
            ).scalar()
            
            # 未解析候选人数
            unparsed_candidates = total_candidates - parsed_candidates
            
            # 有原文的候选人数
            candidates_with_texts = db.query(func.count(func.distinct(Candidate.id))).join(
                RawText, Candidate.id == RawText.candidate_id
            ).scalar()
            
            # 待解析候选人数（有原文但未解析）
            pending_parse = db.query(func.count(func.distinct(Candidate.id))).join(
                RawText, Candidate.id == RawText.candidate_id
            ).filter(
                and_(
                    Candidate.llm_processed == False,
                    func.length(RawText.plain_text) >= 100
                )
            ).scalar()
            
            # 解析进度百分比
            parse_progress = round(parsed_candidates / max(1, candidates_with_texts) * 100, 1)
            
            # 最近解析活动 (跳过此统计，因为CrawlLog模型字段不匹配)
            recent_parse_logs = 0
            
            return {
                'total_candidates': total_candidates or 0,
                'parsed_candidates': parsed_candidates or 0,
                'unparsed_candidates': unparsed_candidates or 0,
                'candidates_with_texts': candidates_with_texts or 0,
                'pending_parse': pending_parse or 0,
                'parse_progress': parse_progress,
                'recent_parse_activity': recent_parse_logs or 0
            }
            
        except Exception as e:
            logger.error(f"获取解析进度失败: {e}")
            return {
                'total_candidates': 0,
                'parsed_candidates': 0,
                'unparsed_candidates': 0,
                'candidates_with_texts': 0,
                'pending_parse': 0,
                'parse_progress': 0.0,
                'recent_parse_activity': 0
            }
    
    def get_field_coverage_statistics(self, db: Session) -> Dict[str, Any]:
        """
        获取字段覆盖率统计（≥1条即算覆盖）
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 字段覆盖率数据
        """
        try:
            # 总候选人数
            total_candidates = db.query(func.count(Candidate.id)).scalar() or 0
            
            if total_candidates == 0:
                return {
                    'total_candidates': 0,
                    'coverage': {},
                    'coverage_percentages': {}
                }
            
            # 邮箱覆盖率
            email_coverage = db.query(func.count(func.distinct(CandidateEmail.candidate_id))).scalar() or 0
            
            # 电话覆盖率（暂时设为0，因为没有CandidatePhone表）
            phone_coverage = 0
            
            # 主页覆盖率
            homepage_coverage = db.query(func.count(func.distinct(CandidateHomepage.candidate_id))).scalar() or 0
            
            # 简历覆盖率（文件类型为resume的）
            resume_coverage = db.query(func.count(func.distinct(CandidateFile.candidate_id))).filter(
                CandidateFile.file_type.in_(['resume', 'cv', 'pdf'])
            ).scalar() or 0
            
            # 社交覆盖率（GitHub，通过github_login字段）
            github_coverage = db.query(func.count(Candidate.id)).filter(
                Candidate.github_login.isnot(None)
            ).scalar() or 0
            
            # 机构覆盖率
            institution_coverage = db.query(func.count(func.distinct(CandidateInstitution.candidate_id))).scalar() or 0
            
            # 仓库覆盖率
            repo_coverage = db.query(func.count(func.distinct(CandidateRepo.candidate_id))).scalar() or 0
            
            # 原文覆盖率
            raw_text_coverage = db.query(func.count(func.distinct(RawText.candidate_id))).scalar() or 0
            
            # 计算覆盖率百分比
            coverage_data = {
                'email': email_coverage,
                'phone': phone_coverage,
                'homepage': homepage_coverage,
                'resume': resume_coverage,
                'github': github_coverage,
                'institution': institution_coverage,
                'repository': repo_coverage,
                'raw_text': raw_text_coverage
            }
            
            coverage_percentages = {}
            for field, count in coverage_data.items():
                coverage_percentages[field] = round(count / total_candidates * 100, 1)
            
            # 综合覆盖率（至少有邮箱或主页中的一项）
            basic_contact_coverage = db.query(func.count(func.distinct(Candidate.id))).filter(
                or_(
                    Candidate.id.in_(db.query(CandidateEmail.candidate_id).distinct()),
                    Candidate.id.in_(db.query(CandidateHomepage.candidate_id).distinct())
                )
            ).scalar() or 0
            
            basic_contact_percentage = round(basic_contact_coverage / total_candidates * 100, 1)
            
            return {
                'total_candidates': total_candidates,
                'coverage': coverage_data,
                'coverage_percentages': coverage_percentages,
                'basic_contact_coverage': basic_contact_coverage,
                'basic_contact_percentage': basic_contact_percentage
            }
            
        except Exception as e:
            logger.error(f"获取字段覆盖率统计失败: {e}")
            return {
                'total_candidates': 0,
                'coverage': {},
                'coverage_percentages': {},
                'basic_contact_coverage': 0,
                'basic_contact_percentage': 0.0
            }
    
    def get_recent_activity(self, db: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近活动
        
        Args:
            db: 数据库会话
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 最近活动列表
        """
        try:
            recent_logs = db.query(CrawlLog).order_by(
                CrawlLog.created_at.desc()
            ).limit(limit).all()
            
            activities = []
            for log in recent_logs:
                # 简化活动信息（跳过候选人关联，因为字段不匹配）
                activity = {
                    'id': log.id,
                    'source': log.source,
                    'task_type': 'unknown',  # CrawlLog没有task_type字段
                    'status': log.status,
                    'message': log.message or '无消息',
                    'candidate_name': '未知',
                    'candidate_id': None,
                    'url': log.url,
                    'created_at': log.created_at.isoformat() if log.created_at else None
                }
                activities.append(activity)
            
            return activities
            
        except Exception as e:
            logger.error(f"获取最近活动失败: {e}")
            return []
    
    def get_system_health(self, db: Session) -> Dict[str, Any]:
        """
        获取系统健康状态
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 系统健康状态
        """
        try:
            # 数据库连接状态
            db_status = 'healthy'
            try:
                db.execute('SELECT 1')
            except Exception:
                db_status = 'error'
            
            # 最近错误数量
            recent_errors = db.query(func.count(CrawlLog.id)).filter(
                and_(
                    CrawlLog.status == 'fail',
                    CrawlLog.created_at >= datetime.now() - timedelta(hours=24)
                )
            ).scalar() or 0
            
            # 正在运行的任务数
            running_tasks = db.query(func.count(CrawlTask.id)).filter(
                CrawlTask.status == 'running'
            ).scalar() or 0
            
            # 系统状态评估
            if db_status == 'error':
                system_status = 'critical'
            elif recent_errors > 10:
                system_status = 'warning'
            else:
                system_status = 'healthy'
            
            return {
                'system_status': system_status,
                'database_status': db_status,
                'recent_errors': recent_errors,
                'running_tasks': running_tasks,
                'last_check': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {
                'system_status': 'error',
                'database_status': 'error',
                'recent_errors': 0,
                'running_tasks': 0,
                'last_check': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def get_dashboard_stats(self, db: Session) -> Dict[str, Any]:
        """
        获取仪表盘统计数据
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 仪表盘统计数据
        """
        try:
            # 获取各类统计数据
            task_stats = self.get_task_statistics(db)
            parse_progress = self.get_candidate_parse_progress(db)
            coverage_stats = self.get_field_coverage_statistics(db)
            recent_activity = self.get_recent_activity(db, limit=5)
            system_health = self.get_system_health(db)
            
            return {
                'tasks': task_stats,
                'parsing': parse_progress,
                'coverage': coverage_stats,
                'recent_activity': recent_activity,
                'system_health': system_health,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取仪表盘统计失败: {e}")
            return {
                'tasks': {'by_source': {}, 'total': {'pending': 0, 'done': 0, 'failed': 0, 'running': 0, 'total': 0}},
                'parsing': {'total_candidates': 0, 'parsed_candidates': 0, 'parse_progress': 0.0},
                'coverage': {'total_candidates': 0, 'coverage_percentages': {}},
                'recent_activity': [],
                'system_health': {'system_status': 'error'},
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }


# 全局实例
stats_service = StatsService()