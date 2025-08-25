"""
爬虫任务与日志数据模型 - 严格按设计蓝图实现

Author: Spidermind
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Enum, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from .base import Base


class CrawlTask(Base):
    """爬虫任务表"""
    __tablename__ = 'crawl_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='任务ID')
    
    # 任务类型与来源
    source = Column(Enum('github', 'openreview', 'homepage', name='crawl_source'), 
                   nullable=False, comment='爬虫来源')
    type = Column(Enum('profile', 'repo', 'follow_scan', 'homepage', 'forum', name='crawl_type'), 
                  nullable=False, comment='爬虫类型')
    
    # 目标信息
    url = Column(String(2048), comment='目标URL')
    github_login = Column(String(100), comment='GitHub用户名')
    openreview_profile_id = Column(String(100), comment='OpenReview用户ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='SET NULL'), comment='关联候选人ID')
    
    # 任务控制
    depth = Column(Integer, default=0, comment='爬取深度')
    status = Column(Enum('pending', 'done', 'failed', 'running', name='task_status'), 
                   default='pending', comment='任务状态')
    retries = Column(Integer, default=0, comment='重试次数')
    priority = Column(Integer, default=0, comment='优先级')
    batch_id = Column(String(100), comment='批次ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    logs = relationship("CrawlLog", back_populates="task", cascade="all, delete-orphan")
    
    # 唯一约束和索引 (蓝图要求：source, type, COALESCE(url,''), COALESCE(github_login,''), COALESCE(openreview_profile_id,''))
    __table_args__ = (
        Index('idx_crawl_tasks_source', 'source'),
        Index('idx_crawl_tasks_type', 'type'),
        Index('idx_crawl_tasks_status', 'status'),
        Index('idx_crawl_tasks_candidate_id', 'candidate_id'),
        Index('idx_crawl_tasks_batch_id', 'batch_id'),
        Index('idx_crawl_tasks_url', 'url'),
        Index('idx_crawl_tasks_github_login', 'github_login'),
        Index('idx_crawl_tasks_openreview_profile_id', 'openreview_profile_id'),
        Index('idx_crawl_tasks_created_at', 'created_at'),
        Index('idx_crawl_tasks_updated_at', 'updated_at'),
        # 去重索引 (用复合索引代替唯一约束，因为涉及可空字段)
        Index('idx_crawl_tasks_dedup', 'source', 'type', 'url', 'github_login', 'openreview_profile_id'),
    )


class CrawlLog(Base):
    """爬虫日志表"""
    __tablename__ = 'crawl_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='日志ID')
    task_id = Column(Integer, ForeignKey('crawl_tasks.id', ondelete='CASCADE'), nullable=False, comment='任务ID')
    source = Column(Enum('github', 'openreview', 'homepage', 'parse', 'manual', name='log_source'), 
                   nullable=False, comment='爬虫来源')
    task_type = Column(String(100), comment='任务类型')
    url = Column(String(2048), comment='爬取URL')
    status = Column(Enum('success', 'fail', 'skip', name='log_status'), 
                   nullable=False, comment='爬取状态')
    message = Column(Text, comment='日志消息')
    trace_id = Column(String(36), comment='跟踪ID (UUID)')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    task = relationship("CrawlTask", back_populates="logs")
    log_candidates = relationship("CrawlLogCandidate", back_populates="log", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index('idx_crawl_logs_task_id', 'task_id'),
        Index('idx_crawl_logs_source', 'source'),
        Index('idx_crawl_logs_status', 'status'),
        Index('idx_crawl_logs_task_type', 'task_type'),
        Index('idx_crawl_logs_url', 'url'),
        Index('idx_crawl_logs_trace_id', 'trace_id'),
        Index('idx_crawl_logs_created_at', 'created_at'),
    )


class CrawlLogCandidate(Base):
    """爬虫日志与候选人关联表"""
    __tablename__ = 'crawl_log_candidates'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='关联ID')
    log_id = Column(Integer, ForeignKey('crawl_logs.id', ondelete='CASCADE'), nullable=False, comment='日志ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False, comment='候选人ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    log = relationship("CrawlLog", back_populates="log_candidates")
    candidate = relationship("Candidate")
    
    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint('log_id', 'candidate_id', name='uk_log_candidate'),
        Index('idx_crawl_log_candidates_log_id', 'log_id'),
        Index('idx_crawl_log_candidates_candidate_id', 'candidate_id'),
        Index('idx_crawl_log_candidates_created_at', 'created_at'),
    )