"""
候选人相关数据模型 - 严格按设计蓝图实现

Author: Spidermind
"""
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DECIMAL, Enum, DateTime, ForeignKey, UniqueConstraint, Index, CHAR
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func as sql_func
import hashlib
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class Candidate(Base):
    """候选人主表"""
    __tablename__ = 'candidates'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='候选人ID')
    
    # 基本信息
    name = Column(String(255), nullable=False, comment='姓名')
    alt_names = Column(JSON, comment='别名列表')
    primary_email = Column(String(255), comment='主邮箱')
    github_login = Column(String(100), comment='GitHub用户名')
    openreview_id = Column(String(100), comment='OpenReview用户ID')
    avatar_url = Column(String(2048), comment='头像URL')
    
    # 机构与主页
    current_institution = Column(String(500), comment='当前机构')
    homepage_main = Column(String(2048), comment='主要个人主页')
    
    # 标签信息
    research_tags = Column(JSON, comment='研究方向标签')
    skill_tags = Column(JSON, comment='技能标签')
    
    # 状态信息
    completeness_score = Column(Integer, default=0, comment='完整度评分')
    llm_processed = Column(Boolean, default=False, comment='是否经过LLM处理')
    status = Column(Enum('raw', 'parsed', 'validated', name='candidate_status'), 
                   default='raw', comment='状态')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    emails = relationship("CandidateEmail", back_populates="candidate", cascade="all, delete-orphan")
    institutions = relationship("CandidateInstitution", back_populates="candidate", cascade="all, delete-orphan")
    homepages = relationship("CandidateHomepage", back_populates="candidate", cascade="all, delete-orphan")
    files = relationship("CandidateFile", back_populates="candidate", cascade="all, delete-orphan")
    repos = relationship("CandidateRepo", back_populates="candidate", cascade="all, delete-orphan")
    papers = relationship("CandidatePaper", back_populates="candidate", cascade="all, delete-orphan")
    raw_texts = relationship("RawText", back_populates="candidate", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index('idx_candidates_name', 'name'),
        Index('idx_candidates_primary_email', 'primary_email'),
        Index('idx_candidates_github_login', 'github_login'),
        Index('idx_candidates_openreview_id', 'openreview_id'),
        Index('idx_candidates_status', 'status'),
        Index('idx_candidates_created_at', 'created_at'),
        Index('idx_candidates_updated_at', 'updated_at'),
    )


class CandidateEmail(Base):
    """候选人邮箱表"""
    __tablename__ = 'candidate_emails'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), nullable=False, comment='邮箱地址')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="emails")
    
    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint('candidate_id', 'email', name='uk_candidate_email'),
        Index('idx_candidate_emails_candidate_id', 'candidate_id'),
        Index('idx_candidate_emails_email', 'email'),
        Index('idx_candidate_emails_created_at', 'created_at'),
    )


class CandidateInstitution(Base):
    """候选人机构表"""
    __tablename__ = 'candidate_institutions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    institution = Column(String(500), nullable=False, comment='机构名称')
    start_year = Column(Integer, comment='开始年份')
    end_year = Column(Integer, comment='结束年份')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="institutions")
    
    # 唯一约束和索引 (蓝图要求：candidate_id, institution, COALESCE(start_year,0), COALESCE(end_year,0))
    __table_args__ = (
        UniqueConstraint('candidate_id', 'institution', 'start_year', 'end_year', 
                        name='uk_candidate_institution'),
        Index('idx_candidate_institutions_candidate_id', 'candidate_id'),
        Index('idx_candidate_institutions_institution', 'institution'),
        Index('idx_candidate_institutions_created_at', 'created_at'),
    )


class CandidateHomepage(Base):
    """候选人主页表"""
    __tablename__ = 'candidate_homepages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    url = Column(String(2048), nullable=False, comment='主页URL')
    url_hash = Column(CHAR(32), nullable=False, comment='URL的MD5哈希')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="homepages")
    
    def __init__(self, **kwargs):
        if 'url' in kwargs and 'url_hash' not in kwargs:
            kwargs['url_hash'] = hashlib.md5(kwargs['url'].encode('utf-8')).hexdigest()
        super().__init__(**kwargs)
    
    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url_hash', name='uk_candidate_homepage'),
        Index('idx_candidate_homepages_candidate_id', 'candidate_id'),
        Index('idx_candidate_homepages_url_hash', 'url_hash'),
        Index('idx_candidate_homepages_created_at', 'created_at'),
    )


class CandidateFile(Base):
    """候选人文件表"""
    __tablename__ = 'candidate_files'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    file_url_or_path = Column(String(2048), nullable=False, comment='文件URL或路径')
    url_hash = Column(CHAR(32), nullable=False, comment='URL的MD5哈希')
    file_type = Column(Enum('pdf', 'image', name='file_type'), comment='文件类型')
    status = Column(Enum('parsed', 'unparsed', name='file_status'), default='unparsed', comment='解析状态')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="files")
    
    def __init__(self, **kwargs):
        if 'file_url_or_path' in kwargs and 'url_hash' not in kwargs:
            kwargs['url_hash'] = hashlib.md5(kwargs['file_url_or_path'].encode('utf-8')).hexdigest()
        super().__init__(**kwargs)
    
    # 索引
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url_hash', name='uk_candidate_file'),
        Index('idx_candidate_files_candidate_id', 'candidate_id'),
        Index('idx_candidate_files_url_hash', 'url_hash'),
        Index('idx_candidate_files_status', 'status'),
        Index('idx_candidate_files_created_at', 'created_at'),
    )


class CandidateRepo(Base):
    """候选人代码仓库表"""
    __tablename__ = 'candidate_repos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    repo_name = Column(String(255), nullable=False, comment='仓库名称')
    repo_url = Column(String(2048), nullable=False, comment='仓库URL')
    url_hash = Column(CHAR(32), nullable=False, comment='URL的MD5哈希')
    description = Column(Text, comment='仓库描述')
    language = Column(String(100), comment='主要编程语言')
    stars = Column(Integer, default=0, comment='Star数量')
    forks = Column(Integer, default=0, comment='Fork数量')
    last_commit = Column(DateTime, comment='最后提交时间')
    picked_reason = Column(Enum('recent', 'star', name='picked_reason'), comment='选择原因')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="repos")
    
    def __init__(self, **kwargs):
        if 'repo_url' in kwargs and 'url_hash' not in kwargs:
            kwargs['url_hash'] = hashlib.md5(kwargs['repo_url'].encode('utf-8')).hexdigest()
        super().__init__(**kwargs)
    
    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url_hash', name='uk_candidate_repo'),
        Index('idx_candidate_repos_candidate_id', 'candidate_id'),
        Index('idx_candidate_repos_url_hash', 'url_hash'),
        Index('idx_candidate_repos_stars', 'stars'),
        Index('idx_candidate_repos_language', 'language'),
        Index('idx_candidate_repos_created_at', 'created_at'),
    )


class CandidatePaper(Base):
    """候选人论文表"""
    __tablename__ = 'candidate_papers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(1000), nullable=False, comment='论文标题')
    url = Column(String(2048), comment='论文链接')
    url_hash = Column(CHAR(32), comment='URL的MD5哈希')
    venue = Column(String(200), comment='会议/期刊')
    source = Column(String(100), comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="papers")
    
    def __init__(self, **kwargs):
        if 'url' in kwargs and kwargs['url'] and 'url_hash' not in kwargs:
            kwargs['url_hash'] = hashlib.md5(kwargs['url'].encode('utf-8')).hexdigest()
        super().__init__(**kwargs)
    
    # 索引
    __table_args__ = (
        UniqueConstraint('candidate_id', 'title', name='uk_candidate_paper_title'),
        Index('idx_candidate_papers_candidate_id', 'candidate_id'),
        Index('idx_candidate_papers_url_hash', 'url_hash'),
        Index('idx_candidate_papers_title', 'title'),
        Index('idx_candidate_papers_source', 'source'),
        Index('idx_candidate_papers_created_at', 'created_at'),
    )


class RawText(Base):
    """原文与解析表"""
    __tablename__ = 'raw_texts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    url = Column(String(2048), nullable=False, comment='URL')
    url_hash = Column(CHAR(32), nullable=False, comment='URL的MD5哈希')
    plain_text = Column(Text().with_variant(LONGTEXT, "mysql"), comment='纯文本内容')
    source = Column(Enum('homepage', 'github_io', 'pdf_ocr', name='text_source'), comment='来源类型')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="raw_texts")
    
    def __init__(self, **kwargs):
        if 'url' in kwargs and 'url_hash' not in kwargs:
            kwargs['url_hash'] = hashlib.md5(kwargs['url'].encode('utf-8')).hexdigest()
        super().__init__(**kwargs)
    
    # 唯一约束和索引 (蓝图要求：candidate_id, url)
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url_hash', name='uk_candidate_raw_text'),
        Index('idx_raw_texts_candidate_id', 'candidate_id'),
        Index('idx_raw_texts_url_hash', 'url_hash'),
        Index('idx_raw_texts_source', 'source'),
        Index('idx_raw_texts_created_at', 'created_at'),
    )