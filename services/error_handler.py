#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一错误处理服务

为所有爬虫服务提供统一的异常处理和日志记录
Author: Spidermind
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from models.crawl import CrawlLog

logger = logging.getLogger(__name__)


class ErrorHandler:
    """统一错误处理类"""
    
    def __init__(self):
        """初始化错误处理器"""
        pass
    
    def log_error(
        self, 
        db: Session,
        source: str,
        url: str,
        error: Exception,
        task_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        记录错误日志到数据库
        
        Args:
            db: 数据库会话
            source: 爬虫来源 (github/openreview/homepage)
            url: 出错的URL
            error: 异常对象
            task_id: 任务ID
            candidate_id: 候选人ID
            context: 额外上下文信息
            
        Returns:
            int: 日志记录ID
        """
        try:
            # 构建错误消息
            error_message = self._build_error_message(error, context)
            
            # 创建日志记录
            log_entry = CrawlLog(
                task_id=task_id,
                source=source,
                url=url,
                status='fail',
                message=error_message,
                created_at=datetime.now()
            )
            
            db.add(log_entry)
            db.flush()  # 获取ID但不提交
            
            logger.error(f"[{source}] 爬取失败 {url}: {error_message}")
            
            return log_entry.id
            
        except Exception as log_error:
            logger.error(f"记录错误日志失败: {log_error}")
            return -1
    
    def log_skip(
        self,
        db: Session,
        source: str,
        url: str,
        reason: str,
        task_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        记录跳过日志
        
        Args:
            db: 数据库会话
            source: 爬虫来源
            url: 跳过的URL
            reason: 跳过原因
            task_id: 任务ID
            candidate_id: 候选人ID
            context: 额外上下文信息
            
        Returns:
            int: 日志记录ID
        """
        try:
            # 构建跳过消息
            skip_message = self._build_skip_message(reason, context)
            
            # 创建日志记录
            log_entry = CrawlLog(
                task_id=task_id,
                source=source,
                url=url,
                status='skip',
                message=skip_message,
                created_at=datetime.now()
            )
            
            db.add(log_entry)
            db.flush()
            
            logger.info(f"[{source}] 跳过 {url}: {skip_message}")
            
            return log_entry.id
            
        except Exception as log_error:
            logger.error(f"记录跳过日志失败: {log_error}")
            return -1
    
    def log_success(
        self,
        db: Session,
        source: str,
        url: str,
        message: str,
        task_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        记录成功日志
        
        Args:
            db: 数据库会话
            source: 爬虫来源
            url: 成功的URL
            message: 成功消息
            task_id: 任务ID
            candidate_id: 候选人ID
            context: 额外上下文信息
            
        Returns:
            int: 日志记录ID
        """
        try:
            # 构建成功消息
            success_message = self._build_success_message(message, context)
            
            # 创建日志记录
            log_entry = CrawlLog(
                task_id=task_id,
                source=source,
                url=url,
                status='success',
                message=success_message,
                created_at=datetime.now()
            )
            
            db.add(log_entry)
            db.flush()
            
            logger.info(f"[{source}] 成功 {url}: {success_message}")
            
            return log_entry.id
            
        except Exception as log_error:
            logger.error(f"记录成功日志失败: {log_error}")
            return -1
    
    def _build_error_message(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> str:
        """构建错误消息"""
        error_type = type(error).__name__
        error_msg = str(error)
        
        # 基础错误信息
        message_parts = [f"{error_type}: {error_msg}"]
        
        # 添加上下文信息
        if context:
            if 'candidate_name' in context:
                message_parts.append(f"候选人: {context['candidate_name']}")
            if 'operation' in context:
                message_parts.append(f"操作: {context['operation']}")
            if 'retry_count' in context:
                message_parts.append(f"重试次数: {context['retry_count']}")
            if 'fallback_used' in context and context['fallback_used']:
                message_parts.append("已使用兜底方案")
        
        return "; ".join(message_parts)
    
    def _build_skip_message(self, reason: str, context: Optional[Dict[str, Any]] = None) -> str:
        """构建跳过消息"""
        message_parts = [f"跳过原因: {reason}"]
        
        # 添加上下文信息
        if context:
            if 'candidate_name' in context:
                message_parts.append(f"候选人: {context['candidate_name']}")
            if 'last_crawled' in context:
                message_parts.append(f"上次爬取: {context['last_crawled']}")
            if 'conflict_field' in context:
                message_parts.append(f"冲突字段: {context['conflict_field']}")
        
        return "; ".join(message_parts)
    
    def _build_success_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """构建成功消息"""
        message_parts = [message]
        
        # 添加上下文信息
        if context:
            if 'candidate_name' in context:
                message_parts.append(f"候选人: {context['candidate_name']}")
            if 'items_found' in context:
                message_parts.append(f"发现项目: {context['items_found']}")
            if 'derived_tasks' in context:
                message_parts.append(f"派生任务: {context['derived_tasks']}")
            if 'processing_time' in context:
                message_parts.append(f"处理耗时: {context['processing_time']:.2f}s")
        
        return "; ".join(message_parts)
    
    def handle_service_error(
        self,
        db: Session,
        source: str,
        operation: str,
        error: Exception,
        url: str = "",
        task_id: Optional[int] = None,
        candidate_id: Optional[int] = None,
        **kwargs
    ):
        """
        服务层统一异常处理装饰器的核心逻辑
        
        Args:
            db: 数据库会话
            source: 爬虫来源
            operation: 操作名称
            error: 异常对象
            url: URL
            task_id: 任务ID
            candidate_id: 候选人ID
            **kwargs: 其他上下文信息
        """
        context = {
            'operation': operation,
            **kwargs
        }
        
        # 记录错误日志
        self.log_error(
            db=db,
            source=source,
            url=url or f"{operation}_operation",
            error=error,
            task_id=task_id,
            candidate_id=candidate_id,
            context=context
        )
        
        # 尝试提交日志（如果可能）
        try:
            db.commit()
        except Exception as commit_error:
            logger.error(f"提交错误日志失败: {commit_error}")
            db.rollback()


# 全局错误处理器实例
error_handler = ErrorHandler()


def log_service_error(source: str, operation: str = "unknown"):
    """
    服务层异常处理装饰器
    
    Args:
        source: 爬虫来源
        operation: 操作名称
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 尝试从参数中获取db会话
                db = None
                for arg in args:
                    if hasattr(arg, 'query'):  # SQLAlchemy Session
                        db = arg
                        break
                
                if db:
                    error_handler.handle_service_error(
                        db=db,
                        source=source,
                        operation=operation,
                        error=e,
                        url=kwargs.get('url', ''),
                        task_id=kwargs.get('task_id'),
                        candidate_id=kwargs.get('candidate_id')
                    )
                
                # 重新抛出异常
                raise e
        return wrapper
    return decorator