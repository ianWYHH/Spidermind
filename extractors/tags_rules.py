#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于规则的标签提取器

通过关键词匹配提取研究方向和技能标签
Author: Spidermind
"""

import re
import logging
from typing import List, Set, Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class TagsRulesExtractor:
    """基于规则的标签提取器"""
    
    def __init__(self):
        """初始化标签提取器"""
        
        # 研究方向关键词字典
        self.research_keywords = {
            # 机器学习与AI
            'machine_learning': [
                'machine learning', 'ml', 'deep learning', 'neural network', 'artificial intelligence',
                'ai', 'supervised learning', 'unsupervised learning', 'reinforcement learning',
                'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'gradient descent',
                '机器学习', '深度学习', '神经网络', '人工智能', '强化学习', '监督学习'
            ],
            
            # 自然语言处理
            'natural_language_processing': [
                'natural language processing', 'nlp', 'language model', 'transformer', 'bert',
                'gpt', 'text mining', 'sentiment analysis', 'named entity recognition', 'ner',
                'information extraction', 'question answering', 'text classification',
                '自然语言处理', '语言模型', '文本挖掘', '情感分析', '命名实体识别', '信息抽取'
            ],
            
            # 计算机视觉
            'computer_vision': [
                'computer vision', 'cv', 'image processing', 'object detection', 'face recognition',
                'image classification', 'semantic segmentation', 'image generation', 'gan',
                'convolutional neural network', 'cnn', 'opencv', 'medical imaging',
                '计算机视觉', '图像处理', '目标检测', '人脸识别', '图像分类', '语义分割'
            ],
            
            # 数据科学与分析
            'data_science': [
                'data science', 'data analysis', 'data mining', 'big data', 'statistics',
                'statistical analysis', 'predictive modeling', 'feature engineering',
                'data visualization', 'business intelligence', 'analytics',
                '数据科学', '数据分析', '数据挖掘', '大数据', '统计分析', '数据可视化'
            ],
            
            # 系统与网络
            'systems_networking': [
                'distributed systems', 'cloud computing', 'microservices', 'kubernetes',
                'docker', 'networking', 'security', 'cybersecurity', 'blockchain',
                'system administration', 'devops', 'infrastructure',
                '分布式系统', '云计算', '微服务', '网络安全', '区块链', '系统管理'
            ],
            
            # 软件工程
            'software_engineering': [
                'software engineering', 'software development', 'full stack', 'backend',
                'frontend', 'mobile development', 'web development', 'agile', 'scrum',
                'software architecture', 'design patterns', 'code review',
                '软件工程', '软件开发', '全栈开发', '后端开发', '前端开发', '移动开发', '软件架构'
            ],
            
            # 数据库
            'database': [
                'database', 'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis',
                'data warehouse', 'etl', 'data pipeline', 'database design',
                '数据库', '数据仓库', '数据管道', '数据库设计'
            ],
            
            # 学术研究
            'academic_research': [
                'research', 'publication', 'paper', 'conference', 'journal', 'phd',
                'postdoc', 'professor', 'academic', 'scholar', 'thesis', 'dissertation',
                '研究', '论文', '学术', '博士', '教授', '学者', '会议发表'
            ]
        }
        
        # 技能关键词字典
        self.skill_keywords = {
            # 编程语言
            'programming_languages': [
                'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust',
                'php', 'ruby', 'swift', 'kotlin', 'scala', 'r', 'matlab', 'shell'
            ],
            
            # 框架和库
            'frameworks_libraries': [
                'react', 'vue', 'angular', 'django', 'flask', 'fastapi', 'spring',
                'express', 'node.js', 'tensorflow', 'pytorch', 'pandas', 'numpy',
                'scikit-learn', 'opencv', 'jquery', 'bootstrap'
            ],
            
            # 工具和平台
            'tools_platforms': [
                'git', 'github', 'gitlab', 'docker', 'kubernetes', 'aws', 'azure',
                'google cloud', 'jenkins', 'nginx', 'apache', 'linux', 'ubuntu',
                'centos', 'windows', 'macos', 'vim', 'vscode', 'intellij'
            ],
            
            # 数据库技术
            'database_technologies': [
                'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'cassandra',
                'oracle', 'sql server', 'sqlite', 'dynamodb', 'neo4j'
            ],
            
            # 云服务
            'cloud_services': [
                'aws', 'azure', 'google cloud platform', 'gcp', 'alibaba cloud',
                'tencent cloud', 'digitalocean', 'heroku', 'vercel', 'netlify'
            ],
            
            # 方法论和实践
            'methodologies': [
                'agile', 'scrum', 'kanban', 'devops', 'ci/cd', 'tdd', 'bdd',
                'pair programming', 'code review', 'microservices', 'restful api'
            ]
        }
    
    def extract_research_tags(self, text: str) -> List[str]:
        """
        从文本中提取研究方向标签
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 研究方向标签列表
        """
        if not text:
            return []
        
        text_lower = text.lower()
        research_tags = set()
        
        # 统计每个研究方向的关键词出现次数
        category_scores = defaultdict(int)
        
        for category, keywords in self.research_keywords.items():
            for keyword in keywords:
                # 使用词边界匹配，避免部分匹配
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                matches = len(re.findall(pattern, text_lower))
                if matches > 0:
                    category_scores[category] += matches
        
        # 根据得分和阈值确定标签
        for category, score in category_scores.items():
            if score >= 1:  # 至少出现1次
                # 转换为友好的标签名
                tag_name = self._category_to_tag_name(category, 'research')
                research_tags.add(tag_name)
        
        return sorted(list(research_tags))
    
    def extract_skill_tags(self, text: str) -> List[str]:
        """
        从文本中提取技能标签
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 技能标签列表
        """
        if not text:
            return []
        
        text_lower = text.lower()
        skill_tags = set()
        
        # 提取具体的技能关键词
        for category, keywords in self.skill_keywords.items():
            for keyword in keywords:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    # 对于技能，直接使用关键词作为标签
                    skill_tags.add(keyword.title())
        
        return sorted(list(skill_tags))
    
    def _category_to_tag_name(self, category: str, tag_type: str) -> str:
        """
        将分类名称转换为友好的标签名称
        
        Args:
            category: 分类名称
            tag_type: 标签类型 (research/skill)
            
        Returns:
            str: 友好的标签名称
        """
        research_tag_mapping = {
            'machine_learning': '机器学习',
            'natural_language_processing': '自然语言处理',
            'computer_vision': '计算机视觉',
            'data_science': '数据科学',
            'systems_networking': '系统与网络',
            'software_engineering': '软件工程',
            'database': '数据库',
            'academic_research': '学术研究'
        }
        
        if tag_type == 'research':
            return research_tag_mapping.get(category, category.replace('_', ' ').title())
        else:
            return category.replace('_', ' ').title()
    
    def extract_all_tags(self, text: str) -> Dict[str, List[str]]:
        """
        从文本中提取所有类型的标签
        
        Args:
            text: 输入文本
            
        Returns:
            Dict: 包含研究方向和技能标签的字典
        """
        return {
            'research_tags': self.extract_research_tags(text),
            'skill_tags': self.extract_skill_tags(text)
        }
    
    def get_tag_confidence(self, text: str, tag: str, tag_type: str) -> float:
        """
        计算标签的置信度
        
        Args:
            text: 输入文本
            tag: 标签名称
            tag_type: 标签类型 (research/skill)
            
        Returns:
            float: 置信度分数 (0-1)
        """
        if not text or not tag:
            return 0.0
        
        text_lower = text.lower()
        total_matches = 0
        total_keywords = 0
        
        # 根据标签类型选择关键词字典
        keywords_dict = self.research_keywords if tag_type == 'research' else self.skill_keywords
        
        # 查找匹配的分类
        for category, keywords in keywords_dict.items():
            if tag_type == 'research':
                category_tag = self._category_to_tag_name(category, tag_type)
                if category_tag == tag:
                    for keyword in keywords:
                        total_keywords += 1
                        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                        matches = len(re.findall(pattern, text_lower))
                        if matches > 0:
                            total_matches += min(matches, 3)  # 限制单个关键词的最大贡献
        
        if total_keywords == 0:
            return 0.0
        
        # 计算置信度
        confidence = min(total_matches / total_keywords, 1.0)
        return confidence
    
    def get_text_summary(self, text: str) -> Dict[str, Any]:
        """
        获取文本的标签提取摘要
        
        Args:
            text: 输入文本
            
        Returns:
            Dict: 包含标签、置信度等信息的摘要
        """
        tags = self.extract_all_tags(text)
        
        # 计算每个标签的置信度
        research_with_confidence = []
        for tag in tags['research_tags']:
            confidence = self.get_tag_confidence(text, tag, 'research')
            research_with_confidence.append({
                'tag': tag,
                'confidence': confidence
            })
        
        skill_with_confidence = []
        for tag in tags['skill_tags']:
            confidence = self.get_tag_confidence(text, tag, 'skill')
            skill_with_confidence.append({
                'tag': tag,
                'confidence': confidence
            })
        
        return {
            'research_tags': tags['research_tags'],
            'skill_tags': tags['skill_tags'],
            'research_with_confidence': research_with_confidence,
            'skill_with_confidence': skill_with_confidence,
            'total_research_tags': len(tags['research_tags']),
            'total_skill_tags': len(tags['skill_tags']),
            'text_length': len(text),
            'extraction_method': 'rules_based'
        }


# 全局实例
tags_rules_extractor = TagsRulesExtractor()