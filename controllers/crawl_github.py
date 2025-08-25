"""
GitHub爬虫控制器 - 严格按设计蓝图实现

实现GitHub爬虫任务启动和管理，接入通用消费器
Author: Spidermind
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio
import logging

from models.base import get_db
from models.crawl import CrawlTask
from services.progress_service import progress_tracker
from services.task_runner import task_runner, TaskBatchManager, is_source_running
from services.github_service import github_service
from services.logging import generate_trace_id, get_logger

router = APIRouter(prefix="/crawl/github", tags=["GitHub爬虫"])
logger = logging.getLogger(__name__)


class GitHubCrawlRequest(BaseModel):
    """GitHub爬虫请求参数 (蓝图规范)"""
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
    pending_count = _count_pending_tasks('github', request.task_types)
    if pending_count == 0:
        return {
            "status": "no_tasks",
            "message": "没有待处理的GitHub任务",
            "pending_count": 0,
            "task_types": request.task_types
        }
    
    logger.info(f"启动GitHub爬虫: 待处理任务 {pending_count} 个，类型过滤 {request.task_types}")
    
    # 生成 trace_id
    trace_id = generate_trace_id()
    
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
    # 创建带 trace_id 的日志器
    trace_logger = get_logger(__name__, trace_id)
    
    try:
        trace_logger.info("开始执行GitHub爬虫任务", extra_data={"trace_id": trace_id})
        
        # 设置GitHub服务配置
        github_service.set_config({
            'recent_n': request.recent_n,
            'star_n': request.star_n,
            'follow_depth': request.follow_depth,
            'max_tasks': request.max_tasks
        })
        
        # 使用通用消费器运行 (蓝图要求)
        result = await task_runner.run_until_empty(
            source='github',
            handler=_github_task_handler,
            filter_types=request.task_types,
            trace_id=trace_id
        )
        
        trace_logger.info("GitHub爬虫完成", extra_data=result)
        
    except Exception as e:
        trace_logger.error("GitHub爬虫执行失败", extra_data={"error": str(e)})
        progress_tracker.record_failure('github', 'mixed', f"爬虫执行异常: {str(e)}")


async def _github_task_handler(task: CrawlTask) -> Dict[str, Any]:
    """
    GitHub任务处理函数 (蓝图规范：规范message格式)
    
    Args:
        task: 爬虫任务
    
    Returns:
        Dict: 处理结果 {status, message, error}
    """
    try:
        if task.type == 'profile':
            result = await github_service.process_profile_task(task)
        elif task.type == 'repo':
            result = await github_service.process_repo_task(task)
        elif task.type == 'follow_scan':
            result = await github_service.process_follow_scan_task(task)
        else:
            return {
                'status': 'skip',
                'message': f'不支持的GitHub任务类型: {task.type}'
            }
        
        # 标准化返回结果
        if result.get('skipped'):
            return {
                'status': 'skip',
                'message': result.get('message', '任务已跳过')
            }
        elif result.get('success'):
            return {
                'status': 'success',
                'message': result.get('message', 'GitHub任务处理成功')
            }
        else:
            return {
                'status': 'fail',
                'message': result.get('message', 'GitHub任务处理失败'),
                'error': result.get('error', '')
            }
            
    except Exception as e:
        logger.error(f"GitHub任务处理异常 {task.id}: {e}")
        return {
            'status': 'fail',
            'message': f'GitHub任务处理异常: {str(e)}',
            'error': str(e)
        }


def _count_pending_tasks(source: str, task_types: Optional[List[str]] = None) -> int:
    """计算待处理任务数量"""
    from models.base import SessionLocal
    from sqlalchemy import and_
    
    db = SessionLocal()
    try:
        conditions = [
            CrawlTask.source == source,
            CrawlTask.status == 'pending'
        ]
        
        if task_types:
            conditions.append(CrawlTask.type.in_(task_types))
        
        count = db.query(CrawlTask).filter(and_(*conditions)).count()
        return count
    finally:
        db.close()


@router.get("/status")
async def get_github_crawl_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取GitHub爬虫状态
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 爬虫状态信息 {running, processed, pending}
    """
    # 获取运行状态
    running = is_source_running('github')
    
    # 获取当前进度统计
    current_stats = progress_tracker.get_current_stats('github', 'mixed')
    processed = current_stats.get('processed', 0) if current_stats else 0
    
    # 获取待处理任务统计
    task_stats = TaskBatchManager.get_task_stats('github')
    pending = task_stats.get('pending', 0)
    
    return {
        "running": running,
        "processed": processed,
        "pending": pending
    }


@router.get("/pending")
async def get_pending_github_tasks(
    task_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取待处理的GitHub任务列表
    
    Args:
        task_type: 任务类型过滤
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 待处理任务列表
    """
    try:
        conditions = [
            CrawlTask.source == 'github',
            CrawlTask.status == 'pending'
        ]
        
        if task_type:
            conditions.append(CrawlTask.type == task_type)
        
        from sqlalchemy import and_
        tasks = db.query(CrawlTask).filter(and_(*conditions))\
            .order_by(CrawlTask.priority.desc(), CrawlTask.created_at.asc())\
            .limit(limit).all()
        
        # 格式化任务信息
        formatted_tasks = []
        for task in tasks:
            task_info = {
                "id": task.id,
                "type": task.type,
                "url": task.url,
                "github_login": task.github_login,
                "candidate_id": task.candidate_id,
                "priority": task.priority,
                "retries": task.retries,
                "batch_id": task.batch_id,
                "created_at": task.created_at.isoformat() if task.created_at else None
            }
            formatted_tasks.append(task_info)
        
        # 统计信息
        task_counts = {}
        for task in tasks:
            task_counts[task.type] = task_counts.get(task.type, 0) + 1
        
        return {
            "source": "github",
            "filter": {"task_type": task_type} if task_type else None,
            "total_returned": len(formatted_tasks),
            "limit": limit,
            "task_counts_by_type": task_counts,
            "tasks": formatted_tasks
        }
        
    except Exception as e:
        logger.error(f"获取待处理GitHub任务失败: {e}")
        raise HTTPException(status_code=500, detail="获取待处理任务失败")


@router.post("/stop")
async def stop_github_crawl() -> Dict[str, str]:
    """
    停止GitHub爬虫
    
    Returns:
        Dict: 停止结果
    """
    if is_source_running('github'):
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


@router.post("/tasks/create")
async def create_github_tasks(
    task_data: Dict[str, Any],
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    手动创建GitHub爬虫任务
    
    Args:
        task_data: 任务创建数据
        db: 数据库会话
    
    Returns:
        Dict: 创建结果
    """
    try:
        task_list = task_data.get('tasks', [])
        if not task_list:
            raise HTTPException(status_code=400, detail="tasks字段不能为空")
        
        task_type = task_data.get('type', 'profile')
        batch_id = task_data.get('batch_id')
        priority = task_data.get('priority', 0)
        
        created_ids = TaskBatchManager.create_tasks(
            source='github',
            task_type=task_type,
            task_data_list=task_list,
            batch_id=batch_id,
            priority=priority
        )
        
        return {
            "status": "created",
            "created_count": len(created_ids),
            "created_task_ids": created_ids,
            "task_type": task_type,
            "batch_id": batch_id
        }
        
    except Exception as e:
        logger.error(f"创建GitHub任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")