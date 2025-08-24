"""
日志查看控制器

实现日志增量拉取API
Author: Spidermind
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime

from models.base import get_db
from models.crawl import CrawlLog, CrawlLogCandidate

router = APIRouter(prefix="/logs", tags=["日志管理"])


@router.get("/{source}")
async def get_logs(
    source: str,
    since_id: Optional[int] = Query(None, description="起始日志ID，用于增量拉取"),
    limit: int = Query(50, le=200, description="返回数量限制"),
    status: Optional[str] = Query(None, description="状态过滤: success/fail/skip"),
    db: Session = Depends(get_db)
):
    """
    获取指定来源的爬虫日志
    
    Args:
        source: 爬虫来源 (github/openreview/homepage)
        since_id: 起始日志ID，返回ID大于此值的日志
        limit: 返回数量限制，最大200
        status: 状态过滤
        db: 数据库会话
    
    Returns:
        Dict: 包含日志列表和分页信息
    """
    # 验证source参数
    valid_sources = ['github', 'openreview', 'homepage']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    # 构建查询条件
    conditions = [CrawlLog.source == source]
    
    # 增量拉取条件
    if since_id is not None:
        conditions.append(CrawlLog.id > since_id)
    
    # 状态过滤条件
    if status:
        valid_statuses = ['success', 'fail', 'skip']
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )
        conditions.append(CrawlLog.status == status)
    
    # 执行查询
    query = db.query(CrawlLog).filter(and_(*conditions))
    
    # 按ID倒序排列（最新的在前）
    logs = query.order_by(CrawlLog.id.desc()).limit(limit).all()
    
    # 格式化返回数据
    result_logs = []
    for log in logs:
        # 获取关联的候选人ID列表
        candidate_ids = []
        if log.log_candidates:
            candidate_ids = [lc.candidate_id for lc in log.log_candidates]
        
        log_data = {
            "id": log.id,
            "task_id": log.task_id,
            "source": log.source,
            "url": log.url,
            "status": log.status,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "candidate_ids": candidate_ids
        }
        result_logs.append(log_data)
    
    # 分页信息
    pagination_info = {
        "total_returned": len(result_logs),
        "limit": limit,
        "since_id": since_id,
        "has_more": len(result_logs) == limit,  # 如果返回数量等于limit，可能还有更多
        "latest_id": result_logs[0]["id"] if result_logs else None,
        "oldest_id": result_logs[-1]["id"] if result_logs else None
    }
    
    return {
        "logs": result_logs,
        "pagination": pagination_info,
        "filters": {
            "source": source,
            "status": status,
            "since_id": since_id
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/{source}/stats")
async def get_log_stats(
    source: str,
    hours: int = Query(24, le=168, description="统计时间范围（小时）"),
    db: Session = Depends(get_db)
):
    """
    获取指定来源的日志统计信息
    
    Args:
        source: 爬虫来源
        hours: 统计时间范围（小时）
        db: 数据库会话
    
    Returns:
        Dict: 统计信息
    """
    # 验证source参数
    valid_sources = ['github', 'openreview', 'homepage']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    # 计算时间范围
    from datetime import timedelta
    time_threshold = datetime.now() - timedelta(hours=hours)
    
    # 构建基础查询条件
    base_conditions = [
        CrawlLog.source == source,
        CrawlLog.created_at >= time_threshold
    ]
    
    # 统计各种状态的数量
    total_count = db.query(CrawlLog).filter(and_(*base_conditions)).count()
    
    success_count = db.query(CrawlLog).filter(
        and_(*base_conditions, CrawlLog.status == 'success')
    ).count()
    
    fail_count = db.query(CrawlLog).filter(
        and_(*base_conditions, CrawlLog.status == 'fail')
    ).count()
    
    skip_count = db.query(CrawlLog).filter(
        and_(*base_conditions, CrawlLog.status == 'skip')
    ).count()
    
    # 计算成功率
    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
    
    return {
        "source": source,
        "time_range_hours": hours,
        "stats": {
            "total": total_count,
            "success": success_count,
            "fail": fail_count,
            "skip": skip_count,
            "success_rate": round(success_rate, 2)
        },
        "time_range": {
            "from": time_threshold.isoformat(),
            "to": datetime.now().isoformat()
        }
    }


@router.get("/")
async def get_all_logs(
    since_id: Optional[int] = Query(None, description="起始日志ID"),
    limit: int = Query(50, le=200, description="返回数量限制"),
    db: Session = Depends(get_db)
):
    """
    获取所有来源的最新日志（用于全局日志查看）
    
    Args:
        since_id: 起始日志ID
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 混合日志列表
    """
    # 构建查询条件
    conditions = []
    
    if since_id is not None:
        conditions.append(CrawlLog.id > since_id)
    
    # 执行查询
    if conditions:
        query = db.query(CrawlLog).filter(and_(*conditions))
    else:
        query = db.query(CrawlLog)
    
    # 按ID倒序排列（最新的在前）
    logs = query.order_by(CrawlLog.id.desc()).limit(limit).all()
    
    # 格式化返回数据
    result_logs = []
    for log in logs:
        # 获取关联的候选人ID列表
        candidate_ids = []
        if log.log_candidates:
            candidate_ids = [lc.candidate_id for lc in log.log_candidates]
        
        log_data = {
            "id": log.id,
            "task_id": log.task_id,
            "source": log.source,
            "url": log.url,
            "status": log.status,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "candidate_ids": candidate_ids
        }
        result_logs.append(log_data)
    
    return {
        "logs": result_logs,
        "pagination": {
            "total_returned": len(result_logs),
            "limit": limit,
            "since_id": since_id,
            "has_more": len(result_logs) == limit
        },
        "timestamp": datetime.now().isoformat()
    }