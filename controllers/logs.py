"""
日志查看控制器 - 按蓝图要求实现增量拉取

实现 since_id 增量拉取API，供前端滚动显示
Author: Spidermind
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from models.base import get_db
from models.crawl import CrawlLog, CrawlLogCandidate

router = APIRouter(prefix="/logs", tags=["日志管理"])
logger = logging.getLogger(__name__)


@router.get("/{source}")
async def get_logs(
    source: str,
    since_id: int = Query(0, description="起始日志ID，返回ID大于此值的日志"),
    limit: int = Query(200, le=1000, description="返回数量限制，默认200，上限1000"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取指定来源的爬虫日志 (蓝图要求：since_id 增量拉取)
    
    Args:
        source: 爬虫来源 (github/openreview/homepage)
        since_id: 起始日志ID，返回ID大于此值的日志，默认0
        limit: 返回数量限制，默认200，上限1000
        db: 数据库会话
    
    Returns:
        Dict: 包含日志数组的响应，异常情况返回空数组
    """
    try:
        # 验证source参数
        valid_sources = ['github', 'openreview', 'homepage']
        if source not in valid_sources:
            logger.warning(f"无效的source参数: {source}")
            return {
                "logs": [],
                "error": f"Invalid source. Must be one of: {valid_sources}",
                "timestamp": datetime.now().isoformat()
            }
        
        # 构建查询条件 (蓝图要求：source + since_id)
        conditions = [
            CrawlLog.source == source,
            CrawlLog.id > since_id
        ]
        
        # 执行主查询：获取日志列表 (按 id ASC 排序)
        logs = db.query(CrawlLog).filter(and_(*conditions))\
            .order_by(CrawlLog.id.asc())\
            .limit(limit).all()
        
        if not logs:
            # 没有新日志
            return {
                "logs": [],
                "timestamp": datetime.now().isoformat()
            }
        
        # 收集所有日志ID，用于批量查询候选人关联
        log_ids = [log.id for log in logs]
        
        # 批量查询候选人关联 (蓝图要求：聚合 candidate_ids)
        candidate_relations = db.query(CrawlLogCandidate)\
            .filter(CrawlLogCandidate.log_id.in_(log_ids)).all()
        
        # 构建 log_id -> candidate_ids 的映射
        candidate_mapping = {}
        for relation in candidate_relations:
            log_id = relation.log_id
            if log_id not in candidate_mapping:
                candidate_mapping[log_id] = []
            candidate_mapping[log_id].append(relation.candidate_id)
        
        # 格式化返回数据 (蓝图要求的字段格式)
        result_logs = []
        for log in logs:
            candidate_ids = candidate_mapping.get(log.id, [])
            
            log_data = {
                "id": log.id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "source": log.source,
                "status": log.status,
                "url": log.url,
                "message": log.message,
                "candidate_ids": candidate_ids
            }
            result_logs.append(log_data)
        
        return {
            "logs": result_logs,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        # 蓝图要求：任何异常返回 200 + 空数组
        logger.error(f"获取 {source} 日志失败: {str(e)}", exc_info=True)
        return {
            "logs": [],
            "error": f"Internal error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/{source}/stats")
async def get_log_stats(
    source: str,
    hours: int = Query(24, le=168, description="统计时间范围（小时）"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取指定来源的日志统计信息
    
    Args:
        source: 爬虫来源
        hours: 统计时间范围（小时）
        db: 数据库会话
    
    Returns:
        Dict: 统计信息，异常情况返回错误信息
    """
    try:
        # 验证source参数
        valid_sources = ['github', 'openreview', 'homepage']
        if source not in valid_sources:
            return {
                "error": f"Invalid source. Must be one of: {valid_sources}",
                "timestamp": datetime.now().isoformat()
            }
        
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
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取 {source} 日志统计失败: {str(e)}", exc_info=True)
        return {
            "error": f"Internal error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/")
async def get_all_logs(
    since_id: int = Query(0, description="起始日志ID"),
    limit: int = Query(200, le=1000, description="返回数量限制"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取所有来源的最新日志（用于全局日志查看）
    
    Args:
        since_id: 起始日志ID
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 混合日志列表，异常情况返回空数组
    """
    try:
        # 构建查询条件
        conditions = [CrawlLog.id > since_id]
        
        # 执行查询 - 按 id ASC 排序
        logs = db.query(CrawlLog).filter(and_(*conditions))\
            .order_by(CrawlLog.id.asc())\
            .limit(limit).all()
        
        if not logs:
            return {
                "logs": [],
                "timestamp": datetime.now().isoformat()
            }
        
        # 收集所有日志ID
        log_ids = [log.id for log in logs]
        
        # 批量查询候选人关联
        candidate_relations = db.query(CrawlLogCandidate)\
            .filter(CrawlLogCandidate.log_id.in_(log_ids)).all()
        
        # 构建映射
        candidate_mapping = {}
        for relation in candidate_relations:
            log_id = relation.log_id
            if log_id not in candidate_mapping:
                candidate_mapping[log_id] = []
            candidate_mapping[log_id].append(relation.candidate_id)
        
        # 格式化返回数据
        result_logs = []
        for log in logs:
            candidate_ids = candidate_mapping.get(log.id, [])
            
            log_data = {
                "id": log.id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "source": log.source,
                "status": log.status,
                "url": log.url,
                "message": log.message,
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
        
    except Exception as e:
        logger.error(f"获取全局日志失败: {str(e)}", exc_info=True)
        return {
            "logs": [],
            "error": f"Internal error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/{source}/latest")
async def get_latest_log_id(
    source: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取指定来源的最新日志ID（供前端初始化 since_id 使用）
    
    Args:
        source: 爬虫来源
        db: 数据库会话
    
    Returns:
        Dict: 包含最新日志ID的响应
    """
    try:
        # 验证source参数
        valid_sources = ['github', 'openreview', 'homepage']
        if source not in valid_sources:
            return {
                "latest_id": 0,
                "error": f"Invalid source. Must be one of: {valid_sources}",
                "timestamp": datetime.now().isoformat()
            }
        
        # 查询最新的日志ID
        latest_log = db.query(CrawlLog.id).filter(CrawlLog.source == source)\
            .order_by(CrawlLog.id.desc()).first()
        
        latest_id = latest_log.id if latest_log else 0
        
        return {
            "source": source,
            "latest_id": latest_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取 {source} 最新日志ID失败: {str(e)}", exc_info=True)
        return {
            "latest_id": 0,
            "error": f"Internal error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }