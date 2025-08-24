#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析服务

处理候选人原文解析、标签提取和LLM处理
Author: Spidermind
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from extractors.tags_rules import tags_rules_extractor
from models.candidate import Candidate, RawText
from models.crawl import CrawlLog
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)


class ParseService:
    """解析服务类"""
    
    def __init__(self):
        """初始化解析服务"""
        self.min_text_length = 100  # 最小文本长度阈值
        self.max_text_length = 50000  # 最大文本长度，超过则截断
        self.llm_threshold = 2  # LLM调用阈值，规则标签少于此数量时调用LLM
    
    def find_candidates_for_parsing(self, db: Session, limit: int = 50) -> List[Candidate]:
        """
        查找需要解析的候选人
        
        Args:
            db: 数据库会话
            limit: 返回数量限制
            
        Returns:
            List[Candidate]: 需要解析的候选人列表
        """
        try:
            # 查找有raw_texts且未LLM处理的候选人
            candidates = db.query(Candidate).join(RawText).filter(
                and_(
                    Candidate.llm_processed == False,
                    RawText.candidate_id == Candidate.id,
                    func.length(RawText.plain_text) >= self.min_text_length
                )
            ).distinct().limit(limit).all()
            
            logger.info(f"找到 {len(candidates)} 个候选人需要解析")
            return candidates
            
        except Exception as e:
            logger.error(f"查找待解析候选人失败: {e}")
            return []
    
    def get_candidate_raw_texts(self, candidate: Candidate, db: Session) -> List[RawText]:
        """
        获取候选人的所有原文
        
        Args:
            candidate: 候选人对象
            db: 数据库会话
            
        Returns:
            List[RawText]: 原文列表
        """
        try:
            raw_texts = db.query(RawText).filter(
                and_(
                    RawText.candidate_id == candidate.id,
                    func.length(RawText.plain_text) >= self.min_text_length
                )
            ).all()
            
            return raw_texts
            
        except Exception as e:
            logger.error(f"获取候选人 {candidate.id} 原文失败: {e}")
            return []
    
    def combine_texts(self, raw_texts: List[RawText]) -> str:
        """
        合并多个原文为一个文本
        
        Args:
            raw_texts: 原文列表
            
        Returns:
            str: 合并后的文本
        """
        if not raw_texts:
            return ""
        
        combined_text = ""
        for raw_text in raw_texts:
            if raw_text.plain_text:
                # 添加来源标识
                source_label = f"\n\n=== 来源: {raw_text.source} - {raw_text.url} ===\n"
                combined_text += source_label + raw_text.plain_text.strip() + "\n"
        
        # 限制文本长度
        if len(combined_text) > self.max_text_length:
            combined_text = combined_text[:self.max_text_length] + "\n...[文本已截断]"
        
        return combined_text.strip()
    
    def extract_tags_with_rules(self, text: str) -> Dict[str, Any]:
        """
        使用规则提取标签
        
        Args:
            text: 输入文本
            
        Returns:
            Dict: 包含标签和元信息的字典
        """
        try:
            # 使用规则提取器
            summary = tags_rules_extractor.get_text_summary(text)
            
            logger.debug(f"规则提取结果: 研究方向 {len(summary['research_tags'])} 个, 技能 {len(summary['skill_tags'])} 个")
            
            return {
                'research_tags': summary['research_tags'],
                'skill_tags': summary['skill_tags'],
                'method': 'rules',
                'confidence': 'high',
                'text_length': len(text),
                'extraction_details': summary
            }
            
        except Exception as e:
            logger.error(f"规则提取失败: {e}")
            return {
                'research_tags': [],
                'skill_tags': [],
                'method': 'rules',
                'confidence': 'low',
                'error': str(e)
            }
    
    def call_llm_for_tags(self, text: str, existing_tags: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        调用LLM提取标签（占位函数）
        
        Args:
            text: 输入文本
            existing_tags: 已有的标签
            
        Returns:
            Dict: LLM提取的标签结果
        """
        # 占位函数：模拟LLM调用
        logger.info(f"[占位] 调用LLM处理文本，长度: {len(text)}")
        
        # 模拟LLM返回一些补充标签
        llm_research_tags = []
        llm_skill_tags = []
        
        # 简单的模拟逻辑：基于文本内容添加一些通用标签
        text_lower = text.lower()
        
        # 模拟研究方向补充
        if 'algorithm' in text_lower or 'optimization' in text_lower:
            llm_research_tags.append('算法优化')
        if 'experiment' in text_lower or 'evaluation' in text_lower:
            llm_research_tags.append('实验评估')
        
        # 模拟技能补充
        if 'linux' in text_lower:
            llm_skill_tags.append('Linux')
        if 'git' in text_lower:
            llm_skill_tags.append('Git')
        
        return {
            'research_tags': llm_research_tags,
            'skill_tags': llm_skill_tags,
            'method': 'llm',
            'confidence': 'medium',
            'model_used': 'placeholder_model',
            'processing_time': 1.5  # 模拟处理时间
        }
    
    def merge_tags(self, rules_result: Dict[str, Any], llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并规则和LLM提取的标签
        
        Args:
            rules_result: 规则提取结果
            llm_result: LLM提取结果
            
        Returns:
            Dict: 合并后的标签结果
        """
        try:
            # 合并研究方向标签
            research_tags = list(set(
                rules_result.get('research_tags', []) + 
                llm_result.get('research_tags', [])
            ))
            
            # 合并技能标签
            skill_tags = list(set(
                rules_result.get('skill_tags', []) + 
                llm_result.get('skill_tags', [])
            ))
            
            return {
                'research_tags': sorted(research_tags),
                'skill_tags': sorted(skill_tags),
                'methods_used': ['rules', 'llm'],
                'rules_count': {
                    'research': len(rules_result.get('research_tags', [])),
                    'skill': len(rules_result.get('skill_tags', []))
                },
                'llm_count': {
                    'research': len(llm_result.get('research_tags', [])),
                    'skill': len(llm_result.get('skill_tags', []))
                },
                'total_count': {
                    'research': len(research_tags),
                    'skill': len(skill_tags)
                }
            }
            
        except Exception as e:
            logger.error(f"标签合并失败: {e}")
            return {
                'research_tags': rules_result.get('research_tags', []),
                'skill_tags': rules_result.get('skill_tags', []),
                'methods_used': ['rules'],
                'error': str(e)
            }
    
    def should_call_llm(self, rules_result: Dict[str, Any]) -> bool:
        """
        判断是否需要调用LLM
        
        Args:
            rules_result: 规则提取结果
            
        Returns:
            bool: 是否需要调用LLM
        """
        research_count = len(rules_result.get('research_tags', []))
        skill_count = len(rules_result.get('skill_tags', []))
        
        # 如果规则提取的标签数量不足，则调用LLM
        return research_count < self.llm_threshold or skill_count < self.llm_threshold
    
    def parse_candidate(self, candidate: Candidate, db: Session) -> Dict[str, Any]:
        """
        解析单个候选人
        
        Args:
            candidate: 候选人对象
            db: 数据库会话
            
        Returns:
            Dict: 解析结果
        """
        try:
            logger.info(f"开始解析候选人: {candidate.name} (ID: {candidate.id})")
            
            # 获取原文
            raw_texts = self.get_candidate_raw_texts(candidate, db)
            if not raw_texts:
                return {
                    'status': 'skip',
                    'message': '无可用原文',
                    'candidate_id': candidate.id
                }
            
            # 合并文本
            combined_text = self.combine_texts(raw_texts)
            if len(combined_text) < self.min_text_length:
                return {
                    'status': 'skip',
                    'message': f'文本过短: {len(combined_text)} < {self.min_text_length}',
                    'candidate_id': candidate.id
                }
            
            # 规则提取
            rules_result = self.extract_tags_with_rules(combined_text)
            
            # 判断是否需要LLM
            final_result = rules_result
            llm_used = False
            
            if self.should_call_llm(rules_result):
                logger.info(f"规则标签不足，调用LLM: 候选人 {candidate.id}")
                llm_result = self.call_llm_for_tags(combined_text, rules_result)
                final_result = self.merge_tags(rules_result, llm_result)
                llm_used = True
            
            # 更新候选人标签
            self.update_candidate_tags(candidate, final_result, db)
            
            # 记录解析日志
            self.log_parsing_result(candidate, final_result, raw_texts, llm_used, db)
            
            db.commit()
            
            return {
                'status': 'success',
                'message': f'解析完成',
                'candidate_id': candidate.id,
                'candidate_name': candidate.name,
                'llm_used': llm_used,
                'research_tags_count': len(final_result.get('research_tags', [])),
                'skill_tags_count': len(final_result.get('skill_tags', [])),
                'text_sources': len(raw_texts),
                'text_length': len(combined_text)
            }
            
        except Exception as e:
            logger.error(f"解析候选人 {candidate.id} 失败: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'解析失败: {str(e)}',
                'candidate_id': candidate.id
            }
    
    def update_candidate_tags(self, candidate: Candidate, result: Dict[str, Any], db: Session):
        """
        更新候选人标签
        
        Args:
            candidate: 候选人对象
            result: 解析结果
            db: 数据库会话
        """
        try:
            # 更新研究方向标签
            research_tags = result.get('research_tags', [])
            if research_tags:
                candidate.research_tags = research_tags
            
            # 更新技能标签
            skill_tags = result.get('skill_tags', [])
            if skill_tags:
                candidate.skill_tags = skill_tags
            
            # 标记为已LLM处理
            candidate.llm_processed = True
            
            # 更新时间
            candidate.updated_at = datetime.now()
            
            logger.info(f"更新候选人 {candidate.id} 标签: 研究方向 {len(research_tags)} 个, 技能 {len(skill_tags)} 个")
            
        except Exception as e:
            logger.error(f"更新候选人 {candidate.id} 标签失败: {e}")
            raise
    
    def log_parsing_result(self, candidate: Candidate, result: Dict[str, Any], 
                          raw_texts: List[RawText], llm_used: bool, db: Session):
        """
        记录解析结果日志
        
        Args:
            candidate: 候选人对象
            result: 解析结果
            raw_texts: 原文列表
            llm_used: 是否使用了LLM
            db: 数据库会话
        """
        try:
            message_parts = [
                f"解析候选人: {candidate.name}",
                f"研究方向: {len(result.get('research_tags', []))} 个",
                f"技能标签: {len(result.get('skill_tags', []))} 个",
                f"文本来源: {len(raw_texts)} 个",
                f"LLM使用: {'是' if llm_used else '否'}"
            ]
            
            log_entry = CrawlLog(
                source='parse',
                task_type='tags_extraction',
                url=f"candidate_{candidate.id}",
                candidate_id=candidate.id,
                status='success',
                message='; '.join(message_parts),
                created_at=datetime.now()
            )
            
            db.add(log_entry)
            
        except Exception as e:
            logger.error(f"记录解析日志失败: {e}")
    
    def reset_candidate_parsing(self, candidate_id: int, db: Session) -> Dict[str, Any]:
        """
        重置候选人解析状态
        
        Args:
            candidate_id: 候选人ID
            db: 数据库会话
            
        Returns:
            Dict: 重置结果
        """
        try:
            candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if not candidate:
                return {
                    'status': 'fail',
                    'message': '候选人不存在'
                }
            
            # 重置标签和处理状态
            candidate.research_tags = []
            candidate.skill_tags = []
            candidate.llm_processed = False
            candidate.updated_at = datetime.now()
            
            # 记录重置日志
            log_entry = CrawlLog(
                source='parse',
                task_type='reset_parsing',
                url=f"candidate_{candidate.id}",
                candidate_id=candidate.id,
                status='success',
                message=f'重置候选人 {candidate.name} 的解析状态',
                created_at=datetime.now()
            )
            db.add(log_entry)
            
            db.commit()
            
            logger.info(f"重置候选人 {candidate.id} 解析状态成功")
            
            return {
                'status': 'success',
                'message': f'候选人 {candidate.name} 解析状态已重置',
                'candidate_id': candidate.id
            }
            
        except Exception as e:
            logger.error(f"重置候选人 {candidate_id} 解析状态失败: {e}")
            db.rollback()
            return {
                'status': 'fail',
                'message': f'重置失败: {str(e)}'
            }
    
    def get_parsing_statistics(self, db: Session) -> Dict[str, Any]:
        """
        获取解析统计信息
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 统计信息
        """
        try:
            # 总候选人数
            total_candidates = db.query(Candidate).count()
            
            # 已解析候选人数
            parsed_candidates = db.query(Candidate).filter(Candidate.llm_processed == True).count()
            
            # 有原文的候选人数
            candidates_with_texts = db.query(Candidate).join(RawText).filter(
                RawText.candidate_id == Candidate.id
            ).distinct().count()
            
            # 待解析候选人数
            pending_candidates = db.query(Candidate).join(RawText).filter(
                and_(
                    Candidate.llm_processed == False,
                    RawText.candidate_id == Candidate.id,
                    func.length(RawText.plain_text) >= self.min_text_length
                )
            ).distinct().count()
            
            # 标签统计
            candidates_with_research_tags = db.query(Candidate).filter(
                and_(
                    Candidate.research_tags.isnot(None),
                    func.json_length(Candidate.research_tags) > 0
                )
            ).count()
            
            candidates_with_skill_tags = db.query(Candidate).filter(
                and_(
                    Candidate.skill_tags.isnot(None),
                    func.json_length(Candidate.skill_tags) > 0
                )
            ).count()
            
            return {
                'total_candidates': total_candidates,
                'parsed_candidates': parsed_candidates,
                'candidates_with_texts': candidates_with_texts,
                'pending_candidates': pending_candidates,
                'candidates_with_research_tags': candidates_with_research_tags,
                'candidates_with_skill_tags': candidates_with_skill_tags,
                'parsing_progress': round(parsed_candidates / max(1, candidates_with_texts) * 100, 2),
                'research_tags_coverage': round(candidates_with_research_tags / max(1, total_candidates) * 100, 2),
                'skill_tags_coverage': round(candidates_with_skill_tags / max(1, total_candidates) * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"获取解析统计失败: {e}")
            return {
                'error': str(e)
            }
    
    def get_recent_parsing_results(self, db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取最近的解析结果
        
        Args:
            db: 数据库会话
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 最近解析结果列表
        """
        try:
            # 获取最近的解析日志
            recent_logs = db.query(CrawlLog).filter(
                and_(
                    CrawlLog.source == 'parse',
                    CrawlLog.task_type.in_(['tags_extraction', 'reset_parsing'])
                )
            ).order_by(CrawlLog.created_at.desc()).limit(limit).all()
            
            results = []
            for log in recent_logs:
                # 获取候选人信息
                candidate = db.query(Candidate).filter(Candidate.id == log.candidate_id).first()
                
                result = {
                    'log_id': log.id,
                    'candidate_id': log.candidate_id,
                    'candidate_name': candidate.name if candidate else '未知',
                    'operation': log.task_type,
                    'status': log.status,
                    'message': log.message,
                    'created_at': log.created_at.isoformat() if log.created_at else None,
                    'can_reset': candidate and candidate.llm_processed if candidate else False
                }
                
                # 如果是解析操作，添加标签信息
                if candidate and log.task_type == 'tags_extraction':
                    result.update({
                        'research_tags': candidate.research_tags if candidate.research_tags else [],
                        'skill_tags': candidate.skill_tags if candidate.skill_tags else [],
                        'research_tags_count': len(candidate.research_tags) if candidate.research_tags else 0,
                        'skill_tags_count': len(candidate.skill_tags) if candidate.skill_tags else 0
                    })
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"获取最近解析结果失败: {e}")
            return []


# 全局实例
parse_service = ParseService()