"""
Homepage爬虫控制器 - 严格按设计蓝图实现

实现Homepage爬虫任务启动和管理，接入通用消费器
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
from services.homepage_service import homepage_service
from services.logging import generate_trace_id, get_logger

router = APIRouter(prefix="/crawl/homepage", tags=["Homepage爬虫"])
logger = logging.getLogger(__name__)


class HomepageCrawlRequest(BaseModel):
    """Homepage爬虫请求参数 (蓝图规范)"""
    task_types: Optional[List[str]] = None  # 任务类型过滤 ['homepage']
    batch_id: Optional[str] = None  # 自定义批次ID
    max_tasks: Optional[int] = None  # 最大处理任务数限制
    enable_playwright: bool = True  # 是否启用Playwright兜底


@router.post("/start")
async def start_homepage_crawl(
    request: HomepageCrawlRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    启动Homepage爬虫任务 (蓝图要求：接入通用消费器)
    
    Args:
        request: 爬虫请求参数
        db: 数据库会话
    
    Returns:
        Dict: 启动结果
    """
    # 检查是否有待处理的Homepage任务
    pending_count = _count_pending_tasks('homepage', request.task_types)
    if pending_count == 0:
        return {
            "status": "no_tasks",
            "message": "没有待处理的Homepage任务",
            "pending_count": 0,
            "task_types": request.task_types
        }
    
    logger.info(f"启动Homepage爬虫: 待处理任务 {pending_count} 个，类型过滤 {request.task_types}")
    
    # 生成 trace_id
    trace_id = generate_trace_id()
    
    # 创建异步后台任务
    asyncio.create_task(_run_homepage_crawl_task(request, trace_id))
    
    return {
        "status": "started",
        "message": "Homepage爬虫已启动",
        "pending_count": pending_count,
        "config": {
            "task_types": request.task_types,
            "batch_id": request.batch_id,
            "max_tasks": request.max_tasks,
            "enable_playwright": request.enable_playwright
        },
        "progress_endpoint": "/progress/homepage"
    }


async def _run_homepage_crawl_task(request: HomepageCrawlRequest, trace_id: str):
    """
    执行Homepage爬虫任务 (蓝图核心：run_until_empty消费模式)
    
    Args:
        request: 爬虫配置请求
        trace_id: 跟踪ID
    """
    # 创建带 trace_id 的日志器
    trace_logger = get_logger(__name__, trace_id)
    
    try:
        trace_logger.info("开始执行Homepage爬虫任务", extra_data={"trace_id": trace_id})
        
        # 设置Homepage服务配置
        homepage_service.set_config({
            'enable_playwright': request.enable_playwright,
            'max_tasks': request.max_tasks
        })
        
        # 使用通用消费器运行 (蓝图要求)
        result = await task_runner.run_until_empty(
            source='homepage',
            handler=_homepage_task_handler,
            filter_types=request.task_types,
            trace_id=trace_id
        )
        
        trace_logger.info("Homepage爬虫完成", extra_data=result)
        
    except Exception as e:
        trace_logger.error("Homepage爬虫执行失败", extra_data={"error": str(e)})
        progress_tracker.record_failure('homepage', 'mixed', f"爬虫执行异常: {str(e)}")


async def _homepage_task_handler(task: CrawlTask) -> Dict[str, Any]:
    """
    Homepage任务处理函数 (蓝图规范：规范message格式)
    
    Args:
        task: 爬虫任务
    
    Returns:
        Dict: 处理结果 {status, message, error}
    """
    try:
        if task.type == 'homepage':
            result = await homepage_service.process_homepage_task(task)
        else:
            return {
                'status': 'skip',
                'message': f'不支持的Homepage任务类型: {task.type}'
            }
        
        # 标准化返回结果
        if result.get('skipped'):
            return {
                'status': 'skip',
                'message': result.get('message', '任务已跳过')
            }
        elif result.get('success'):
            # 检查是否使用了兜底机制 (蓝图要求：日志标注兜底标记)
            message = result.get('message', 'Homepage任务处理成功')
            if result.get('used_playwright'):
                message += ' [兜底:Playwright]'
            elif result.get('used_fallback'):
                message += ' [兜底:备用方案]'
            
            return {
                'status': 'success',
                'message': message
            }
        else:
            return {
                'status': 'fail',
                'message': result.get('message', 'Homepage任务处理失败'),
                'error': result.get('error', '')
            }
            
    except Exception as e:
        logger.error(f"Homepage任务处理异常 {task.id}: {e}")
        return {
            'status': 'fail',
            'message': f'Homepage任务处理异常: {str(e)}',
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
async def get_homepage_crawl_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取Homepage爬虫状态
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 爬虫状态信息 {running, processed, pending}
    """
    # 获取运行状态
    running = is_source_running('homepage')
    
    # 获取当前进度统计
    current_stats = progress_tracker.get_current_stats('homepage', 'mixed')
    processed = current_stats.get('processed', 0) if current_stats else 0
    
    # 获取待处理任务统计
    task_stats = TaskBatchManager.get_task_stats('homepage')
    pending = task_stats.get('pending', 0)
    
    return {
        "running": running,
        "processed": processed,
        "pending": pending
    }


@router.get("/pending")
async def get_pending_homepage_tasks(
    limit: int = 50,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取待处理的Homepage任务列表
    
    Args:
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 待处理任务列表
    """
    try:
        conditions = [
            CrawlTask.source == 'homepage',
            CrawlTask.status == 'pending'
        ]
        
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
                "candidate_id": task.candidate_id,
                "priority": task.priority,
                "retries": task.retries,
                "batch_id": task.batch_id,
                "created_at": task.created_at.isoformat() if task.created_at else None
            }
            formatted_tasks.append(task_info)
        
        return {
            "source": "homepage",
            "total_returned": len(formatted_tasks),
            "limit": limit,
            "tasks": formatted_tasks
        }
        
    except Exception as e:
        logger.error(f"获取待处理Homepage任务失败: {e}")
        raise HTTPException(status_code=500, detail="获取待处理任务失败")


@router.post("/stop")
async def stop_homepage_crawl() -> Dict[str, str]:
    """
    停止Homepage爬虫
    
    Returns:
        Dict: 停止结果
    """
    if is_source_running('homepage'):
        task_runner.stop()
        return {
            "status": "stopping",
            "message": "Homepage爬虫停止信号已发送"
        }
    else:
        return {
            "status": "not_running",
            "message": "Homepage爬虫未在运行"
        }


@router.post("/tasks/create")
async def create_homepage_tasks(
    task_data: Dict[str, Any],
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    手动创建Homepage爬虫任务
    
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
        
        task_type = task_data.get('type', 'homepage')
        batch_id = task_data.get('batch_id')
        priority = task_data.get('priority', 0)
        
        created_ids = TaskBatchManager.create_tasks(
            source='homepage',
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
        logger.error(f"创建Homepage任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")