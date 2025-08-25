"""
GitHub爬虫控制器 - 简化实现，接入通用消费器

Author: Spidermind
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio
import logging
import uuid

from models.base import get_db
from models.crawl import CrawlTask
from services.task_runner import task_runner, dummy_task_handler
from services.progress_service import progress_tracker

router = APIRouter(prefix="/crawl/github", tags=["GitHub爬虫"])
logger = logging.getLogger(__name__)


class GitHubCrawlRequest(BaseModel):
    """GitHub爬虫请求参数"""
    task_types: Optional[List[str]] = None  # 任务类型过滤 ['profile', 'repo', 'follow_scan']
    recent_n: int = 5  # 智能选仓库：最近更新数量
    star_n: int = 5  # 智能选仓库：最高星标数量
    follow_depth: int = 1  # 关注扫描深度
    batch_id: Optional[str] = None  # 自定义批次ID
    max_tasks: Optional[int] = None  # 最大处理任务数限制


@router.post("/start")
async def start_github_crawl(
    request: GitHubCrawlRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    启动GitHub爬虫任务 (蓝图要求：接入通用消费器)
    
    Args:
        request: 爬虫请求参数
        db: 数据库会话
    
    Returns:
        Dict: 启动结果
    """
    # 检查是否有待处理的GitHub任务
    pending_count = _count_pending_tasks(db, 'github', request.task_types)
    if pending_count == 0:
        return {
            "status": "no_tasks",
            "message": "没有待处理的GitHub任务",
            "pending_count": 0,
            "task_types": request.task_types
        }
    
    logger.info(f"启动GitHub爬虫: 待处理任务 {pending_count} 个，类型过滤 {request.task_types}")
    
    # 生成 trace_id
    trace_id = str(uuid.uuid4())
    
    # 创建异步后台任务
    asyncio.create_task(_run_github_crawl_task(request, trace_id))
    
    return {
        "status": "started",
        "message": "GitHub爬虫已启动",
        "pending_count": pending_count,
        "config": {
            "task_types": request.task_types,
            "recent_n": request.recent_n,
            "star_n": request.star_n,
            "follow_depth": request.follow_depth,
            "batch_id": request.batch_id,
            "max_tasks": request.max_tasks
        },
        "progress_endpoint": "/progress/github"
    }


async def _run_github_crawl_task(request: GitHubCrawlRequest, trace_id: str):
    """
    执行GitHub爬虫任务 (蓝图核心：run_until_empty消费模式)
    
    Args:
        request: 爬虫配置请求
        trace_id: 跟踪ID
    """
    try:
        logger.info(f"开始执行GitHub爬虫任务, trace_id: {trace_id}")
        
        # 使用通用消费器运行 (蓝图要求)
        result = await task_runner.run_until_empty(
            source='github',
            handler=_github_task_handler,
            filter_types=request.task_types,
            trace_id=trace_id
        )
        
        logger.info(f"GitHub爬虫完成: {result}")
        
    except Exception as e:
        logger.error(f"GitHub爬虫执行失败: {e}")


async def _github_task_handler(task: CrawlTask) -> Dict[str, Any]:
    """
    GitHub任务处理函数 (简化桩实现)
    
    Args:
        task: 爬虫任务
    
    Returns:
        Dict: 处理结果 {status, message, error}
    """
    try:
        # 根据任务类型返回不同的处理结果
        if task.type == 'profile':
            # TODO: 这里应该调用实际的 GitHub 用户资料处理逻辑
            return {
                'status': 'success',
                'message': f'GitHub用户资料处理完成: {task.github_login or task.url}'
            }
        elif task.type == 'repo':
            # TODO: 这里应该调用实际的 GitHub 仓库处理逻辑
            return {
                'status': 'success',
                'message': f'GitHub仓库处理完成: {task.url}'
            }
        elif task.type == 'follow_scan':
            # TODO: 这里应该调用实际的关注者扫描逻辑
            return {
                'status': 'success',
                'message': f'GitHub关注者扫描完成: {task.github_login}'
            }
        else:
            return {
                'status': 'skip',
                'message': f'不支持的GitHub任务类型: {task.type}'
            }
            
    except Exception as e:
        logger.error(f"GitHub任务处理异常 {task.id}: {e}")
        return {
            'status': 'fail',
            'message': f'GitHub任务处理异常: {str(e)}',
            'error': str(e)
        }


def _count_pending_tasks(db: Session, source: str, task_types: Optional[List[str]] = None) -> int:
    """计算待处理任务数量"""
    conditions = [
        CrawlTask.source == source,
        CrawlTask.status == 'pending'
    ]
    
    if task_types:
        conditions.append(CrawlTask.type.in_(task_types))
    
    count = db.query(CrawlTask).filter(and_(*conditions)).count()
    return count


@router.get("/status")
async def get_github_crawl_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取GitHub爬虫状态
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 爬虫状态信息 {running, processed, pending}
    """
    # 获取当前进度统计
    stats = progress_tracker.get_round_stats('github')
    
    # 获取待处理任务数量
    pending = _count_pending_tasks(db, 'github')
    
    return {
        "running": stats.get('running', False),
        "processed": stats.get('processed', 0),
        "pending": pending,
        "success": stats.get('success', 0),
        "fail": stats.get('fail', 0),
        "skip": stats.get('skip', 0),
        "success_rate": stats.get('success_rate', 0.0)
    }


@router.post("/stop")
async def stop_github_crawl() -> Dict[str, str]:
    """
    停止GitHub爬虫
    
    Returns:
        Dict: 停止结果
    """
    stats = progress_tracker.get_round_stats('github')
    if stats.get('running', False):
        task_runner.stop()
        return {
            "status": "stopping",
            "message": "GitHub爬虫停止信号已发送"
        }
    else:
        return {
            "status": "not_running",
            "message": "GitHub爬虫未在运行"
        }