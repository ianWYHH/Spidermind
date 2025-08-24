"""
数据模型包

导入所有SQLAlchemy ORM模型
Author: Spidermind
"""

# 导入基础配置
from .base import Base, get_db, create_all_tables, drop_all_tables

# 导入候选人相关模型
from .candidate import (
    Candidate,
    CandidateEmail,
    CandidateInstitution,
    CandidateHomepage,
    CandidateFile,
    CandidateRepo,
    CandidatePaper,
    RawText
)

# 导入爬虫任务与日志模型
from .crawl import (
    CrawlTask,
    CrawlLog,
    CrawlLogCandidate
)

# 导入映射表模型
from .mapping import (
    GitHubUser,
    OpenReviewUser
)

# 所有模型列表
__all__ = [
    # 基础
    'Base', 'get_db', 'create_all_tables', 'drop_all_tables',
    
    # 候选人相关
    'Candidate',
    'CandidateEmail',
    'CandidateInstitution', 
    'CandidateHomepage',
    'CandidateFile',
    'CandidateRepo',
    'CandidatePaper',
    'RawText',
    
    # 爬虫任务与日志
    'CrawlTask',
    'CrawlLog',
    'CrawlLogCandidate',
    
    # 映射表
    'GitHubUser',
    'OpenReviewUser'
]