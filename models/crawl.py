"""
爬虫任务与日志数据模型

Author: Spidermind
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Enum, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
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
    url = Column(String(500), comment='目标URL')
    github_login = Column(String(100), comment='GitHub用户名')
    openreview_profile_id = Column(String(100), comment='OpenReview用户ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='SET NULL'), comment='关联候选人ID')
    
    # 任务控制
    depth = Column(Integer, default=0, comment='爬取深度')
    status = Column(Enum('pending', 'done', 'failed', name='task_status'), 
                   default='pending', comment='任务状态')
    retries = Column(Integer, default=0, comment='重试次数')
    priority = Column(Integer, default=0, comment='优先级')
    batch_id = Column(String(100), comment='批次ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    logs = relationship("CrawlLog", back_populates="task", cascade="all, delete-orphan")
    
    # 索引 (注意：包含NULL值的唯一约束在MySQL中需要特殊处理)
    __table_args__ = (
        Index('idx_crawl_tasks_source', 'source'),
        Index('idx_crawl_tasks_status', 'status'),
        Index('idx_crawl_tasks_candidate_id', 'candidate_id'),
        Index('idx_crawl_tasks_batch_id', 'batch_id'),
        Index('idx_crawl_tasks_created_at', 'created_at'),
        Index('idx_crawl_tasks_dedup', 'source', 'type', 'url', 'github_login', 'openreview_profile_id'),
    )


class CrawlLog(Base):
    """爬虫日志表"""
    __tablename__ = 'crawl_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='日志ID')
    task_id = Column(Integer, ForeignKey('crawl_tasks.id', ondelete='CASCADE'), nullable=False, comment='任务ID')
    source = Column(Enum('github', 'openreview', 'homepage', name='log_source'), 
                   nullable=False, comment='爬虫来源')
    url = Column(String(500), comment='爬取URL')
    status = Column(Enum('success', 'fail', 'skip', name='log_status'), 
                   nullable=False, comment='爬取状态')
    message = Column(Text, comment='日志消息')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    task = relationship("CrawlTask", back_populates="logs")
    log_candidates = relationship("CrawlLogCandidate", back_populates="log", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index('idx_crawl_logs_task_id', 'task_id'),
        Index('idx_crawl_logs_source', 'source'),
        Index('idx_crawl_logs_status', 'status'),
        Index('idx_crawl_logs_created_at', 'created_at'),
    )


class CrawlLogCandidate(Base):
    """爬虫日志与候选人关联表"""
    __tablename__ = 'crawl_log_candidates'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='关联ID')
    log_id = Column(Integer, ForeignKey('crawl_logs.id', ondelete='CASCADE'), nullable=False, comment='日志ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False, comment='候选人ID')
    
    # 关系
    log = relationship("CrawlLog", back_populates="log_candidates")
    candidate = relationship("Candidate")
    
    # 索引
    __table_args__ = (
        Index('idx_crawl_log_candidates_log_id', 'log_id'),
        Index('idx_crawl_log_candidates_candidate_id', 'candidate_id'),
        UniqueConstraint('log_id', 'candidate_id', name='uk_log_candidate'),
    )