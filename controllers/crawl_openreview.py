#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenReview爬虫控制器

实现OpenReview爬虫任务启动和管理
Author: Spidermind
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio

from models.base import get_db
from models.crawl import CrawlTask
from services.progress_service import progress_tracker
from services.task_runner import TaskRunner
from services.openreview_service import openreview_service

router = APIRouter(prefix="/crawl/openreview", tags=["OpenReview爬虫"])


class OpenReviewCrawlRequest(BaseModel):
    """OpenReview爬虫请求参数"""
    task_type: str = "forum"  # forum/profile
    batch_size: int = 5  # 每批处理数量（OpenReview较慢，建议较小批次）
    max_tasks: Optional[int] = None  # 最大处理任务数，None表示处理所有
    priority_filter: Optional[int] = None  # 优先级过滤
    custom_batch_id: Optional[str] = None  # 自定义批次ID


@router.post("/start")
async def start_openreview_crawl(
    request: OpenReviewCrawlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动OpenReview爬虫任务
    
    Args:
        request: 爬虫请求参数
        background_tasks: FastAPI后台任务
        db: 数据库会话
    
    Returns:
        Dict: 启动结果和批次信息
    """
    # 验证task_type
    valid_types = ['forum', 'profile']
    if request.task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type. Must be one of: {valid_types}"
        )
    
    # 检查是否有待处理的任务
    pending_count = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.type == request.task_type,
        CrawlTask.status == 'pending'
    ).count()
    
    if pending_count == 0:
        return {
            "status": "no_tasks",
            "message": f"没有找到待处理的OpenReview {request.task_type}任务",
            "pending_count": 0
        }
    
    # 检查是否已有运行中的同类型任务
    current_stats = progress_tracker.get_current_stats('openreview', request.task_type)
    if current_stats and current_stats.get('status') == 'running':
        return {
            "status": "already_running",
            "message": f"OpenReview {request.task_type}任务已在运行中",
            "current_batch": current_stats,
            "pending_count": pending_count
        }
    
    # 开始新的批次
    batch_id = progress_tracker.start_batch(
        source='openreview',
        task_type=request.task_type,
        batch_id=request.custom_batch_id
    )
    
    # 在后台启动任务处理
    background_tasks.add_task(
        _run_openreview_crawl_task,
        batch_id=batch_id,
        task_type=request.task_type,
        batch_size=request.batch_size,
        max_tasks=request.max_tasks,
        priority_filter=request.priority_filter
    )
    
    return {
        "status": "started",
        "message": f"OpenReview {request.task_type}爬虫任务已启动",
        "batch_id": batch_id,
        "pending_count": pending_count,
        "config": {
            "task_type": request.task_type,
            "batch_size": request.batch_size,
            "max_tasks": request.max_tasks,
            "priority_filter": request.priority_filter
        }
    }


@router.get("/status/{task_type}")
async def get_crawl_status(task_type: str):
    """
    获取OpenReview爬虫任务状态
    
    Args:
        task_type: 任务类型
    
    Returns:
        Dict: 任务状态信息
    """
    # 验证task_type
    valid_types = ['forum', 'profile']
    if task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type. Must be one of: {valid_types}"
        )
    
    # 获取当前运行状态
    current_stats = progress_tracker.get_current_stats('openreview', task_type)
    
    # 获取历史记录
    history = progress_tracker.get_batch_history('openreview', task_type, limit=5)
    
    return {
        "task_type": task_type,
        "current_batch": current_stats,
        "recent_history": history,
        "is_running": current_stats is not None and current_stats.get('status') == 'running'
    }


@router.get("/status")
async def get_all_crawl_status():
    """
    获取所有OpenReview爬虫任务状态
    
    Returns:
        Dict: 所有任务状态信息
    """
    task_types = ['forum', 'profile']
    status_info = {}
    
    for task_type in task_types:
        current_stats = progress_tracker.get_current_stats('openreview', task_type)
        status_info[task_type] = {
            "current_batch": current_stats,
            "is_running": current_stats is not None and current_stats.get('status') == 'running'
        }
    
    # 获取全局统计
    overall_stats = progress_tracker.get_overall_stats()
    openreview_stats = overall_stats.get('by_source', {}).get('openreview', {})
    
    return {
        "openreview_overview": openreview_stats,
        "by_task_type": status_info,
        "summary": {
            "total_running": sum(1 for info in status_info.values() if info['is_running']),
            "available_types": task_types
        }
    }


@router.post("/stop/{task_type}")
async def stop_openreview_crawl(task_type: str):
    """
    停止指定类型的OpenReview爬虫任务
    
    Args:
        task_type: 任务类型
    
    Returns:
        Dict: 停止结果
    """
    # 验证task_type
    valid_types = ['forum', 'profile']
    if task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type. Must be one of: {valid_types}"
        )
    
    # 获取当前状态
    current_stats = progress_tracker.get_current_stats('openreview', task_type)
    
    if not current_stats or current_stats.get('status') != 'running':
        return {
            "status": "not_running",
            "message": f"OpenReview {task_type}任务当前未运行",
            "task_type": task_type
        }
    
    # 标记批次为完成状态
    progress_tracker.finish_batch('openreview', task_type)
    
    return {
        "status": "stopped",
        "message": f"OpenReview {task_type}任务已停止",
        "task_type": task_type,
        "final_stats": current_stats
    }


async def _run_openreview_crawl_task(
    batch_id: str,
    task_type: str,
    batch_size: int = 5,
    max_tasks: Optional[int] = None,
    priority_filter: Optional[int] = None
):
    """
    后台运行OpenReview爬虫任务
    
    Args:
        batch_id: 批次ID
        task_type: 任务类型
        batch_size: 批次大小
        max_tasks: 最大任务数
        priority_filter: 优先级过滤
    """
    try:
        # 创建任务运行器
        runner = TaskRunner()
        
        # 定义任务过滤条件
        task_filters = {
            'source': 'openreview',
            'type': task_type,
            'status': 'pending'
        }
        
        if priority_filter is not None:
            task_filters['priority'] = priority_filter
        
        # 定义处理函数
        async def openreview_task_processor(task):
            """OpenReview任务处理函数"""
            try:
                from models.base import SessionLocal
                db = SessionLocal()
                
                try:
                    # 根据任务类型调用相应的处理方法
                    if task_type == 'forum':
                        result = openreview_service.process_forum_task(task, db)
                    elif task_type == 'profile':
                        result = openreview_service.process_profile_task(task, db)
                    else:
                        result = {
                            'status': 'fail',
                            'message': f'未知任务类型: {task_type}'
                        }
                    
                    return result
                    
                finally:
                    db.close()
                    
            except Exception as e:
                return {
                    'status': 'fail',
                    'message': f'处理OpenReview {task_type}任务异常: {task.id}',
                    'error': str(e)
                }
        
        # 运行任务处理循环
        await runner.run_batch(
            task_filters=task_filters,
            processor=openreview_task_processor,
            batch_size=batch_size,
            max_tasks=max_tasks,
            progress_source='openreview',
            progress_type=task_type,
            batch_id=batch_id
        )
        
    except Exception as e:
        # 记录批次失败
        progress_tracker.record_failure(
            'openreview', 
            task_type, 
            f"批次执行异常: {str(e)}", 
            batch_id
        )
        
        # 结束批次
        progress_tracker.finish_batch('openreview', task_type, batch_id)
        
        print(f"OpenReview爬虫批次 {batch_id} 执行异常: {e}")


@router.get("/tasks/pending")
async def get_pending_tasks(
    task_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    获取待处理的OpenReview任务列表
    
    Args:
        task_type: 任务类型过滤
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 待处理任务列表
    """
    query = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.status == 'pending'
    )
    
    if task_type:
        valid_types = ['forum', 'profile']
        if task_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task_type. Must be one of: {valid_types}"
            )
        query = query.filter(CrawlTask.type == task_type)
    
    tasks = query.order_by(CrawlTask.priority.desc(), CrawlTask.created_at.asc()).limit(limit).all()
    
    task_list = []
    for task in tasks:
        task_data = {
            "id": task.id,
            "type": task.type,
            "url": task.url,
            "openreview_profile_id": task.openreview_profile_id,
            "candidate_id": task.candidate_id,
            "priority": task.priority,
            "retries": task.retries,
            "batch_id": task.batch_id,
            "created_at": task.created_at.isoformat() if task.created_at else None
        }
        task_list.append(task_data)
    
    return {
        "tasks": task_list,
        "total_returned": len(task_list),
        "filters": {
            "source": "openreview",
            "task_type": task_type,
            "status": "pending"
        }
    }


@router.get("/stats")
async def get_openreview_stats(db: Session = Depends(get_db)):
    """
    获取OpenReview爬虫统计信息
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 统计信息
    """
    # 任务统计
    forum_pending = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.type == 'forum',
        CrawlTask.status == 'pending'
    ).count()
    
    forum_done = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.type == 'forum',
        CrawlTask.status == 'done'
    ).count()
    
    profile_pending = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.type == 'profile',
        CrawlTask.status == 'pending'
    ).count()
    
    profile_done = db.query(CrawlTask).filter(
        CrawlTask.source == 'openreview',
        CrawlTask.type == 'profile',
        CrawlTask.status == 'done'
    ).count()
    
    # OpenReview用户统计
    from models.mapping import OpenReviewUser
    total_users = db.query(OpenReviewUser).count()
    
    # 候选人论文统计
    from models.candidate import CandidatePaper
    openreview_papers = db.query(CandidatePaper).filter(
        CandidatePaper.source == 'openreview'
    ).count()
    
    return {
        "tasks": {
            "forum": {
                "pending": forum_pending,
                "completed": forum_done,
                "total": forum_pending + forum_done
            },
            "profile": {
                "pending": profile_pending,
                "completed": profile_done,
                "total": profile_pending + profile_done
            }
        },
        "data": {
            "openreview_users": total_users,
            "papers_discovered": openreview_papers
        },
        "summary": {
            "total_pending": forum_pending + profile_pending,
            "total_completed": forum_done + profile_done,
            "completion_rate": round((forum_done + profile_done) / max(1, forum_pending + forum_done + profile_pending + profile_done) * 100, 2)
        }
    }