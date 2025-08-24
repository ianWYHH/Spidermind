#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主页爬虫控制器

实现主页爬虫任务启动和管理
Author: Spidermind
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio

from models.base import get_db
from models.crawl import CrawlTask
from models.candidate import RawText
from services.progress_service import progress_tracker
from services.task_runner import TaskRunner
from services.homepage_service import homepage_service

router = APIRouter(prefix="/crawl/homepage", tags=["主页爬虫"])


class HomepageCrawlRequest(BaseModel):
    """主页爬虫请求参数"""
    batch_size: int = 3  # 每批处理数量（主页爬取较慢，建议小批次）
    max_tasks: Optional[int] = None  # 最大处理任务数，None表示处理所有
    priority_filter: Optional[int] = None  # 优先级过滤
    custom_batch_id: Optional[str] = None  # 自定义批次ID
    enable_playwright: bool = True  # 是否启用Playwright兜底


@router.post("/start")
async def start_homepage_crawl(
    request: HomepageCrawlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动主页爬虫任务
    
    Args:
        request: 爬虫请求参数
        background_tasks: FastAPI后台任务
        db: 数据库会话
    
    Returns:
        Dict: 启动结果和批次信息
    """
    # 检查是否有待处理的任务
    pending_count = db.query(CrawlTask).filter(
        CrawlTask.source == 'homepage',
        CrawlTask.type == 'homepage',
        CrawlTask.status == 'pending'
    ).count()
    
    if pending_count == 0:
        return {
            "status": "no_tasks",
            "message": "没有找到待处理的主页任务",
            "pending_count": 0
        }
    
    # 检查是否已有运行中的任务
    current_stats = progress_tracker.get_current_stats('homepage', 'homepage')
    if current_stats and current_stats.get('status') == 'running':
        return {
            "status": "already_running",
            "message": "主页爬虫任务已在运行中",
            "current_batch": current_stats,
            "pending_count": pending_count
        }
    
    # 开始新的批次
    batch_id = progress_tracker.start_batch(
        source='homepage',
        task_type='homepage',
        batch_id=request.custom_batch_id
    )
    
    # 在后台启动任务处理
    background_tasks.add_task(
        _run_homepage_crawl_task,
        batch_id=batch_id,
        batch_size=request.batch_size,
        max_tasks=request.max_tasks,
        priority_filter=request.priority_filter,
        enable_playwright=request.enable_playwright
    )
    
    return {
        "status": "started",
        "message": "主页爬虫任务已启动",
        "batch_id": batch_id,
        "pending_count": pending_count,
        "config": {
            "batch_size": request.batch_size,
            "max_tasks": request.max_tasks,
            "priority_filter": request.priority_filter,
            "enable_playwright": request.enable_playwright
        }
    }


@router.get("/status")
async def get_homepage_crawl_status():
    """
    获取主页爬虫任务状态
    
    Returns:
        Dict: 任务状态信息
    """
    # 获取当前运行状态
    current_stats = progress_tracker.get_current_stats('homepage', 'homepage')
    
    # 获取历史记录
    history = progress_tracker.get_batch_history('homepage', 'homepage', limit=5)
    
    return {
        "task_type": "homepage",
        "current_batch": current_stats,
        "recent_history": history,
        "is_running": current_stats is not None and current_stats.get('status') == 'running'
    }


@router.post("/stop")
async def stop_homepage_crawl():
    """
    停止主页爬虫任务
    
    Returns:
        Dict: 停止结果
    """
    # 获取当前状态
    current_stats = progress_tracker.get_current_stats('homepage', 'homepage')
    
    if not current_stats or current_stats.get('status') != 'running':
        return {
            "status": "not_running",
            "message": "主页爬虫任务当前未运行"
        }
    
    # 标记批次为完成状态
    progress_tracker.finish_batch('homepage', 'homepage')
    
    return {
        "status": "stopped",
        "message": "主页爬虫任务已停止",
        "final_stats": current_stats
    }


@router.get("/tasks/pending")
async def get_pending_homepage_tasks(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    获取待处理的主页任务列表
    
    Args:
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 待处理任务列表
    """
    tasks = db.query(CrawlTask).filter(
        CrawlTask.source == 'homepage',
        CrawlTask.type == 'homepage',
        CrawlTask.status == 'pending'
    ).order_by(
        CrawlTask.priority.desc(), 
        CrawlTask.created_at.asc()
    ).limit(limit).all()
    
    task_list = []
    for task in tasks:
        task_data = {
            "id": task.id,
            "url": task.url,
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
            "source": "homepage",
            "status": "pending"
        }
    }


@router.get("/stats")
async def get_homepage_stats(db: Session = Depends(get_db)):
    """
    获取主页爬虫统计信息
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 统计信息
    """
    # 任务统计
    pending = db.query(CrawlTask).filter(
        CrawlTask.source == 'homepage',
        CrawlTask.type == 'homepage',
        CrawlTask.status == 'pending'
    ).count()
    
    done = db.query(CrawlTask).filter(
        CrawlTask.source == 'homepage',
        CrawlTask.type == 'homepage',
        CrawlTask.status == 'done'
    ).count()
    
    failed = db.query(CrawlTask).filter(
        CrawlTask.source == 'homepage',
        CrawlTask.type == 'homepage',
        CrawlTask.status == 'failed'
    ).count()
    
    # 内容统计
    total_raw_texts = db.query(RawText).filter(
        RawText.source.in_(['homepage', 'github_io'])
    ).count()
    
    # 按来源统计
    homepage_texts = db.query(RawText).filter(
        RawText.source == 'homepage'
    ).count()
    
    github_io_texts = db.query(RawText).filter(
        RawText.source == 'github_io'
    ).count()
    
    return {
        "tasks": {
            "pending": pending,
            "completed": done,
            "failed": failed,
            "total": pending + done + failed
        },
        "content": {
            "total_raw_texts": total_raw_texts,
            "homepage_texts": homepage_texts,
            "github_io_texts": github_io_texts
        },
        "summary": {
            "completion_rate": round(done / max(1, pending + done + failed) * 100, 2),
            "success_rate": round(done / max(1, done + failed) * 100, 2) if (done + failed) > 0 else 0
        }
    }


@router.get("/content/{raw_text_id}")
async def get_raw_text_content(
    raw_text_id: int,
    db: Session = Depends(get_db)
):
    """
    获取已抓取的原文内容
    
    Args:
        raw_text_id: 原文记录ID
        db: 数据库会话
    
    Returns:
        Dict: 原文内容和元数据
    """
    raw_text = db.query(RawText).filter(RawText.id == raw_text_id).first()
    
    if not raw_text:
        raise HTTPException(status_code=404, detail="Raw text not found")
    
    return {
        "id": raw_text.id,
        "candidate_id": raw_text.candidate_id,
        "url": raw_text.url,
        "source": raw_text.source,
        "content_length": len(raw_text.plain_text) if raw_text.plain_text else 0,
        "content_preview": raw_text.plain_text[:500] + "..." if raw_text.plain_text and len(raw_text.plain_text) > 500 else raw_text.plain_text,
        "created_at": raw_text.created_at.isoformat() if raw_text.created_at else None
    }


@router.get("/content/{raw_text_id}/full")
async def get_full_raw_text_content(
    raw_text_id: int,
    db: Session = Depends(get_db)
):
    """
    获取完整的原文内容（谨慎使用，可能很大）
    
    Args:
        raw_text_id: 原文记录ID
        db: 数据库会话
    
    Returns:
        Dict: 完整原文内容
    """
    raw_text = db.query(RawText).filter(RawText.id == raw_text_id).first()
    
    if not raw_text:
        raise HTTPException(status_code=404, detail="Raw text not found")
    
    return {
        "id": raw_text.id,
        "candidate_id": raw_text.candidate_id,
        "url": raw_text.url,
        "source": raw_text.source,
        "full_content": raw_text.plain_text,
        "created_at": raw_text.created_at.isoformat() if raw_text.created_at else None
    }


async def _run_homepage_crawl_task(
    batch_id: str,
    batch_size: int = 3,
    max_tasks: Optional[int] = None,
    priority_filter: Optional[int] = None,
    enable_playwright: bool = True
):
    """
    后台运行主页爬虫任务
    
    Args:
        batch_id: 批次ID
        batch_size: 批次大小
        max_tasks: 最大任务数
        priority_filter: 优先级过滤
        enable_playwright: 是否启用Playwright兜底
    """
    try:
        # 创建任务运行器
        runner = TaskRunner()
        
        # 定义任务过滤条件
        task_filters = {
            'source': 'homepage',
            'type': 'homepage',
            'status': 'pending'
        }
        
        if priority_filter is not None:
            task_filters['priority'] = priority_filter
        
        # 定义处理函数
        async def homepage_task_processor(task):
            """主页任务处理函数"""
            try:
                from models.base import SessionLocal
                db = SessionLocal()
                
                try:
                    # 处理主页任务
                    result = homepage_service.process_homepage_task(task, db)
                    return result
                    
                finally:
                    db.close()
                    
            except Exception as e:
                return {
                    'status': 'fail',
                    'message': f'处理主页任务异常: {task.id}',
                    'error': str(e)
                }
        
        # 运行任务处理循环
        await runner.run_batch(
            task_filters=task_filters,
            processor=homepage_task_processor,
            batch_size=batch_size,
            max_tasks=max_tasks,
            progress_source='homepage',
            progress_type='homepage',
            batch_id=batch_id
        )
        
    except Exception as e:
        # 记录批次失败
        progress_tracker.record_failure(
            'homepage', 
            'homepage', 
            f"批次执行异常: {str(e)}", 
            batch_id
        )
        
        # 结束批次
        progress_tracker.finish_batch('homepage', 'homepage', batch_id)
        
        print(f"主页爬虫批次 {batch_id} 执行异常: {e}")