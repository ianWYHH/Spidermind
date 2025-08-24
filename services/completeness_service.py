#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
候选人完整度计算服务

计算候选人信息完整度得分和缺失项提示
Author: Spidermind
"""

import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.candidate import (
    Candidate, CandidateEmail, CandidateInstitution, 
    CandidateHomepage, CandidateRepo, CandidateFile, 
    CandidatePaper, RawText
)

logger = logging.getLogger(__name__)


class CompletenessService:
    """候选人完整度服务"""
    
    def __init__(self):
        """初始化完整度服务"""
        # 完整度权重配置（总分100）
        self.weights = {
            'basic_info': 15,      # 基本信息：姓名、bio等
            'contact': 35,         # 联系方式：邮箱、电话（权重最高）
            'professional': 25,    # 专业信息：机构、主页、GitHub
            'content': 15,         # 内容：论文、仓库、原文
            'files': 10           # 文件：简历、图片等
        }
        
        # 缺失项检查规则
        self.required_items = {
            'email': {'weight': 20, 'description': '邮箱地址'},
            'phone': {'weight': 15, 'description': '电话号码'},
            'institution': {'weight': 15, 'description': '所属机构'},
            'homepage': {'weight': 10, 'description': '个人主页'},
            'github': {'weight': 10, 'description': 'GitHub链接'},
            'resume': {'weight': 10, 'description': '简历文件'},
            'papers': {'weight': 10, 'description': '学术论文'},
            'bio': {'weight': 5, 'description': '个人简介'},
            'location': {'weight': 5, 'description': '所在地区'}
        }
    
    def calculate_completeness_score(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """
        计算候选人完整度得分
        
        Args:
            candidate: 候选人对象
            db: 数据库会话
            
        Returns:
            Dict: 包含得分、缺失项等信息
        """
        try:
            score_details = {
                'basic_info': 0,
                'contact': 0,
                'professional': 0,
                'content': 0,
                'files': 0
            }
            
            missing_items = []
            available_items = []
            
            # 1. 基本信息评分
            basic_score = self._calculate_basic_info_score(candidate)
            score_details['basic_info'] = basic_score
            
            # 2. 联系方式评分
            contact_info = self._get_contact_info(candidate, db)
            contact_score, contact_missing = self._calculate_contact_score(contact_info)
            score_details['contact'] = contact_score
            missing_items.extend(contact_missing)
            available_items.extend([item for item in ['email', 'phone'] if item not in contact_missing])
            
            # 3. 专业信息评分
            professional_info = self._get_professional_info(candidate, db)
            professional_score, professional_missing = self._calculate_professional_score(professional_info)
            score_details['professional'] = professional_score
            missing_items.extend(professional_missing)
            available_items.extend([item for item in ['institution', 'homepage', 'github'] if item not in professional_missing])
            
            # 4. 内容评分
            content_info = self._get_content_info(candidate, db)
            content_score, content_missing = self._calculate_content_score(content_info)
            score_details['content'] = content_score
            missing_items.extend(content_missing)
            available_items.extend([item for item in ['papers'] if item not in content_missing])
            
            # 5. 文件评分
            files_info = self._get_files_info(candidate, db)
            files_score, files_missing = self._calculate_files_score(files_info)
            score_details['files'] = files_score
            missing_items.extend(files_missing)
            available_items.extend([item for item in ['resume'] if item not in files_missing])
            
            # 额外检查
            extra_missing = self._check_extra_missing_items(candidate)
            missing_items.extend(extra_missing)
            available_items.extend([item for item in ['bio', 'location'] if item not in extra_missing])
            
            # 计算总分
            total_score = sum(score_details.values())
            
            # 生成缺失提示
            missing_descriptions = [
                self.required_items[item]['description'] 
                for item in missing_items 
                if item in self.required_items
            ]
            
            return {
                'total_score': round(total_score, 1),
                'score_details': score_details,
                'missing_items': missing_items,
                'missing_descriptions': missing_descriptions,
                'available_items': available_items,
                'completeness_level': self._get_completeness_level(total_score)
            }
            
        except Exception as e:
            logger.error(f"计算完整度得分失败: {candidate.id}, 错误: {e}")
            return {
                'total_score': 0,
                'score_details': {},
                'missing_items': [],
                'missing_descriptions': ['计算失败'],
                'available_items': [],
                'completeness_level': 'unknown'
            }
    
    def _calculate_basic_info_score(self, candidate: Candidate) -> float:
        """计算基本信息得分"""
        score = 0
        max_score = self.weights['basic_info']
        
        # 姓名（必须有）
        if candidate.name and len(candidate.name.strip()) > 0:
            score += max_score * 0.4
        
        # 其他名称（JSON字段）
        if candidate.alt_names and isinstance(candidate.alt_names, (list, dict)) and len(str(candidate.alt_names)) > 10:
            score += max_score * 0.3
        
        # 技能标签（JSON字段）
        if candidate.skill_tags and isinstance(candidate.skill_tags, (list, dict)) and len(str(candidate.skill_tags)) > 10:
            score += max_score * 0.2
        
        # 主页
        if candidate.homepage_main:
            score += max_score * 0.1
        
        return min(score, max_score)
    
    def _get_contact_info(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """获取联系信息"""
        emails = db.query(CandidateEmail).filter(CandidateEmail.candidate_id == candidate.id).all()
        
        return {
            'emails': emails,
            'has_email': len(emails) > 0,
            'has_phone': bool(candidate.primary_email and '@' in candidate.primary_email),  # 简化检查
            'primary_email': emails[0].email if emails else candidate.primary_email
        }
    
    def _calculate_contact_score(self, contact_info: Dict[str, Any]) -> tuple[float, List[str]]:
        """计算联系方式得分"""
        score = 0
        max_score = self.weights['contact']
        missing = []
        
        # 邮箱（权重最高）
        if contact_info['has_email']:
            score += max_score * 0.6
        else:
            missing.append('email')
        
        # 电话
        if contact_info['has_phone']:
            score += max_score * 0.4
        else:
            missing.append('phone')
        
        return min(score, max_score), missing
    
    def _get_professional_info(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """获取专业信息"""
        institutions = db.query(CandidateInstitution).filter(
            CandidateInstitution.candidate_id == candidate.id
        ).all()
        
        homepages = db.query(CandidateHomepage).filter(
            CandidateHomepage.candidate_id == candidate.id
        ).all()
        
        # 检查是否有GitHub相关信息
        has_github = bool(candidate.github_login) or any(
            'github.com' in homepage.url.lower() 
            for homepage in homepages 
            if homepage.url
        )
        
        return {
            'institutions': institutions,
            'homepages': homepages,
            'has_institution': len(institutions) > 0 or bool(candidate.current_institution),
            'has_homepage': len(homepages) > 0 or bool(candidate.homepage_main),
            'has_github': has_github
        }
    
    def _calculate_professional_score(self, professional_info: Dict[str, Any]) -> tuple[float, List[str]]:
        """计算专业信息得分"""
        score = 0
        max_score = self.weights['professional']
        missing = []
        
        # 机构信息
        if professional_info['has_institution']:
            score += max_score * 0.4
        else:
            missing.append('institution')
        
        # 个人主页
        if professional_info['has_homepage']:
            score += max_score * 0.3
        else:
            missing.append('homepage')
        
        # GitHub
        if professional_info['has_github']:
            score += max_score * 0.3
        else:
            missing.append('github')
        
        return min(score, max_score), missing
    
    def _get_content_info(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """获取内容信息"""
        papers = db.query(CandidatePaper).filter(CandidatePaper.candidate_id == candidate.id).all()
        repos = db.query(CandidateRepo).filter(CandidateRepo.candidate_id == candidate.id).all()
        raw_texts = db.query(RawText).filter(RawText.candidate_id == candidate.id).all()
        
        return {
            'papers': papers,
            'repos': repos,
            'raw_texts': raw_texts,
            'has_papers': len(papers) > 0,
            'has_repos': len(repos) > 0,
            'has_content': len(raw_texts) > 0
        }
    
    def _calculate_content_score(self, content_info: Dict[str, Any]) -> tuple[float, List[str]]:
        """计算内容得分"""
        score = 0
        max_score = self.weights['content']
        missing = []
        
        # 学术论文
        if content_info['has_papers']:
            score += max_score * 0.5
        else:
            missing.append('papers')
        
        # 代码仓库
        if content_info['has_repos']:
            score += max_score * 0.3
        
        # 网页内容
        if content_info['has_content']:
            score += max_score * 0.2
        
        return min(score, max_score), missing
    
    def _get_files_info(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """获取文件信息"""
        files = db.query(CandidateFile).filter(CandidateFile.candidate_id == candidate.id).all()
        
        # 检查是否有简历文件
        resume_files = [
            f for f in files 
            if f.file_type == 'pdf' and any(
                keyword in f.file_url_or_path.lower() 
                for keyword in ['cv', 'resume', 'curriculum', '简历']
            )
        ]
        
        return {
            'files': files,
            'resume_files': resume_files,
            'has_files': len(files) > 0,
            'has_resume': len(resume_files) > 0
        }
    
    def _calculate_files_score(self, files_info: Dict[str, Any]) -> tuple[float, List[str]]:
        """计算文件得分"""
        score = 0
        max_score = self.weights['files']
        missing = []
        
        # 简历文件
        if files_info['has_resume']:
            score += max_score * 0.7
        else:
            missing.append('resume')
        
        # 其他文件
        if files_info['has_files']:
            score += max_score * 0.3
        
        return min(score, max_score), missing
    
    def _check_extra_missing_items(self, candidate: Candidate) -> List[str]:
        """检查额外的缺失项"""
        missing = []
        
        # 研究标签
        if not candidate.research_tags or (isinstance(candidate.research_tags, (list, dict)) and len(str(candidate.research_tags)) < 10):
            missing.append('bio')
        
        # 技能标签
        if not candidate.skill_tags or (isinstance(candidate.skill_tags, (list, dict)) and len(str(candidate.skill_tags)) < 5):
            missing.append('location')
        
        return missing
    
    def _get_completeness_level(self, score: float) -> str:
        """获取完整度等级"""
        if score >= 90:
            return 'excellent'
        elif score >= 75:
            return 'good'
        elif score >= 60:
            return 'fair'
        elif score >= 40:
            return 'poor'
        else:
            return 'incomplete'
    
    def get_missing_items_summary(self, missing_descriptions: List[str]) -> str:
        """生成缺失项摘要"""
        if not missing_descriptions:
            return "信息完整"
        
        if len(missing_descriptions) <= 3:
            return f"缺少：{', '.join(missing_descriptions)}"
        else:
            return f"缺少：{', '.join(missing_descriptions[:3])}等{len(missing_descriptions)}项"
    
    def batch_calculate_scores(self, candidates: List[Candidate], db: Session) -> Dict[int, Dict[str, Any]]:
        """批量计算完整度得分"""
        results = {}
        
        for candidate in candidates:
            try:
                score_info = self.calculate_completeness_score(candidate, db)
                results[candidate.id] = score_info
            except Exception as e:
                logger.error(f"批量计算得分失败: {candidate.id}, 错误: {e}")
                results[candidate.id] = {
                    'total_score': 0,
                    'missing_descriptions': ['计算失败'],
                    'completeness_level': 'unknown'
                }
        
        return results


# 全局实例
completeness_service = CompletenessService()