"""
候选人相关数据模型

Author: Spidermind
"""
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DECIMAL, Enum, DateTime, ForeignKey, UniqueConstraint, Index
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
    
    # 机构与主页
    current_institution = Column(String(500), comment='当前机构')
    homepage_main = Column(String(500), comment='主要个人主页')
    
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
        Index('idx_candidates_github_login', 'github_login'),
        Index('idx_candidates_openreview_id', 'openreview_id'),
        Index('idx_candidates_status', 'status'),
        Index('idx_candidates_created_at', 'created_at'),
    )


class CandidateEmail(Base):
    """候选人邮箱表"""
    __tablename__ = 'candidate_emails'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), nullable=False, comment='邮箱地址')
    source = Column(String(100), comment='来源')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="emails")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('candidate_id', 'email', name='uk_candidate_email'),
        Index('idx_candidate_emails_candidate_id', 'candidate_id'),
        Index('idx_candidate_emails_email', 'email'),
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
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="institutions")
    
    # 索引 (注意：包含NULL值的唯一约束在MySQL中需要特殊处理)
    __table_args__ = (
        Index('idx_candidate_institutions_candidate_id', 'candidate_id'),
        Index('idx_candidate_institutions_institution', 'institution'),
        Index('idx_candidate_institutions_unique', 'candidate_id', 'institution', 'start_year', 'end_year'),
    )


class CandidateHomepage(Base):
    """候选人主页表"""
    __tablename__ = 'candidate_homepages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    url = Column(String(500), nullable=False, comment='主页URL')
    source = Column(String(100), comment='来源')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="homepages")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url', name='uk_candidate_homepage'),
        Index('idx_candidate_homepages_candidate_id', 'candidate_id'),
        Index('idx_candidate_homepages_url', 'url'),
    )


class CandidateFile(Base):
    """候选人文件表"""
    __tablename__ = 'candidate_files'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    file_url_or_path = Column(String(500), nullable=False, comment='文件URL或路径')
    file_type = Column(Enum('pdf', 'image', name='file_type'), comment='文件类型')
    status = Column(Enum('parsed', 'unparsed', name='file_status'), default='unparsed', comment='解析状态')
    source = Column(String(100), comment='来源')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="files")
    
    # 索引
    __table_args__ = (
        Index('idx_candidate_files_candidate_id', 'candidate_id'),
        Index('idx_candidate_files_status', 'status'),
    )


class CandidateRepo(Base):
    """候选人代码仓库表"""
    __tablename__ = 'candidate_repos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    repo_name = Column(String(255), nullable=False, comment='仓库名称')
    repo_url = Column(String(500), nullable=False, comment='仓库URL')
    description = Column(Text, comment='仓库描述')
    language = Column(String(100), comment='主要编程语言')
    stars = Column(Integer, default=0, comment='Star数量')
    forks = Column(Integer, default=0, comment='Fork数量')
    last_commit = Column(DateTime, comment='最后提交时间')
    picked_reason = Column(Enum('recent', 'star', name='picked_reason'), comment='选择原因')
    source = Column(String(100), comment='来源')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="repos")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('candidate_id', 'repo_url', name='uk_candidate_repo'),
        Index('idx_candidate_repos_candidate_id', 'candidate_id'),
        Index('idx_candidate_repos_stars', 'stars'),
        Index('idx_candidate_repos_language', 'language'),
    )


class CandidatePaper(Base):
    """候选人论文表"""
    __tablename__ = 'candidate_papers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(500), nullable=False, comment='论文标题')
    url = Column(String(500), comment='论文链接')  # 重命名为url保持一致性
    venue = Column(String(200), comment='会议/期刊')
    source = Column(String(100), comment='来源')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="papers")
    
    # 索引
    __table_args__ = (
        Index('idx_candidate_papers_candidate_id', 'candidate_id'),
        Index('idx_candidate_papers_title', 'title'),
        Index('idx_candidate_papers_source', 'source'),
    )


class RawText(Base):
    """原文与解析表"""
    __tablename__ = 'raw_texts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    url = Column(String(500), nullable=False, comment='URL')
    plain_text = Column(Text, comment='纯文本内容')
    source = Column(Enum('homepage', 'github_io', 'pdf_ocr', name='text_source'), comment='来源类型')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    # 关系
    candidate = relationship("Candidate", back_populates="raw_texts")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('candidate_id', 'url', name='uk_candidate_raw_text'),
        Index('idx_raw_texts_candidate_id', 'candidate_id'),
        Index('idx_raw_texts_source', 'source'),
    )