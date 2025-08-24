"""
映射表数据模型 - 用于去重关键

Author: Spidermind
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class GitHubUser(Base):
    """GitHub用户映射表"""
    __tablename__ = 'github_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增ID')
    github_login = Column(String(100), unique=True, nullable=False, comment='GitHub用户名')
    github_id = Column(BigInteger, unique=True, nullable=False, comment='GitHub用户ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='SET NULL'), comment='关联候选人ID')
    last_crawled_at = Column(DateTime, comment='最后爬取时间')
    
    # 关系
    candidate = relationship("Candidate")
    
    # 索引
    __table_args__ = (
        Index('idx_github_users_login', 'github_login'),
        Index('idx_github_users_id', 'github_id'),
        Index('idx_github_users_candidate_id', 'candidate_id'),
        Index('idx_github_users_last_crawled', 'last_crawled_at'),
    )


class OpenReviewUser(Base):
    """OpenReview用户映射表"""
    __tablename__ = 'openreview_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增ID')
    openreview_profile_id = Column(String(100), unique=True, nullable=False, comment='OpenReview用户ID')
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='SET NULL'), comment='关联候选人ID')
    last_crawled_at = Column(DateTime, comment='最后爬取时间')
    
    # 关系
    candidate = relationship("Candidate")
    
    # 索引
    __table_args__ = (
        Index('idx_openreview_users_profile_id', 'openreview_profile_id'),
        Index('idx_openreview_users_candidate_id', 'candidate_id'),
        Index('idx_openreview_users_last_crawled', 'last_crawled_at'),
    )