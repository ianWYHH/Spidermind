"""
进度查看控制器 - 严格按设计蓝图实现

提供任务处理进度的API查询
Author: Spidermind
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime

from services.progress_service import progress_tracker

router = APIRouter(prefix="/progress", tags=["进度管理"])


@router.get("/{source}")
async def get_progress_stats(
    source: str,
    task_type: Optional[str] = Query(None, description="任务类型过滤")
) -> Dict[str, Any]:
    """
    获取指定来源的进度统计 (蓝图要求)
    
    Args:
        source: 爬虫来源 (github/openreview/homepage)
        task_type: 可选的任务类型过滤
    
    Returns:
        Dict: 包含processed/success/fail/skip统计的进度信息
    """
    # 验证source参数
    valid_sources = ['github', 'openreview', 'homepage']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    try:
        if task_type:
            # 获取指定类型的当前统计
            current_stats = progress_tracker.get_current_stats(source, task_type)
            
            if current_stats:
                return {
                    "source": source,
                    "task_type": task_type,
                    "status": current_stats.get('status', 'idle'),
                    "batch_id": current_stats.get('batch_id'),
                    "progress": {
                        "total_processed": current_stats.get('total_processed', 0),
                        "success_count": current_stats.get('success_count', 0),
                        "fail_count": current_stats.get('fail_count', 0),
                        "skip_count": current_stats.get('skip_count', 0),
                        "success_rate": current_stats.get('success_rate', 0),
                    },
                    "timing": {
                        "start_time": current_stats.get('start_time').isoformat() if current_stats.get('start_time') else None,
                        "end_time": current_stats.get('end_time').isoformat() if current_stats.get('end_time') else None,
                        "duration_seconds": current_stats.get('duration_seconds', 0),
                        "duration_str": current_stats.get('duration_str', '0:00:00')
                    },
                    "recent_errors": current_stats.get('error_details', [])[-5:],  # 最近5个错误
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "source": source,
                    "task_type": task_type,
                    "status": "idle",
                    "batch_id": None,
                    "progress": {
                        "total_processed": 0,
                        "success_count": 0,
                        "fail_count": 0,
                        "skip_count": 0,
                        "success_rate": 0,
                    },
                    "timing": None,
                    "recent_errors": [],
                    "timestamp": datetime.now().isoformat()
                }
        else:
            # 获取source下所有类型的汇总统计
            overall_stats = progress_tracker.get_overall_stats()
            source_stats = overall_stats.get('by_source', {}).get(source, {})
            
            if source_stats:
                return {
                    "source": source,
                    "task_type": "all",
                    "status": "running" if source_stats.get('running_batches', 0) > 0 else "idle",
                    "summary": {
                        "total_batches": source_stats.get('total_batches', 0),
                        "running_batches": source_stats.get('running_batches', 0),
                        "total_processed": source_stats.get('total_processed', 0),
                        "total_success": source_stats.get('total_success', 0),
                        "total_fail": source_stats.get('total_fail', 0),
                        "total_skip": source_stats.get('total_skip', 0),
                    },
                    "by_type": source_stats.get('by_type', {}),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "source": source,
                    "task_type": "all",
                    "status": "idle",
                    "summary": {
                        "total_batches": 0,
                        "running_batches": 0,
                        "total_processed": 0,
                        "total_success": 0,
                        "total_fail": 0,
                        "total_skip": 0,
                    },
                    "by_type": {},
                    "timestamp": datetime.now().isoformat()
                }
                
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve progress stats: {str(e)}"
        )


@router.get("/{source}/{task_type}/history")
async def get_progress_history(
    source: str,
    task_type: str,
    limit: int = Query(10, le=50, description="返回数量限制")
) -> Dict[str, Any]:
    """
    获取指定来源和类型的批次历史记录
    
    Args:
        source: 爬虫来源
        task_type: 任务类型
        limit: 返回数量限制
    
    Returns:
        Dict: 批次历史列表
    """
    # 验证参数
    valid_sources = ['github', 'openreview', 'homepage']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    try:
        history = progress_tracker.get_batch_history(source, task_type, limit)
        
        # 格式化历史记录
        formatted_history = []
        for batch in history:
            formatted_batch = {
                "batch_id": batch.get('batch_id'),
                "status": batch.get('status'),
                "progress": {
                    "total_processed": batch.get('total_processed', 0),
                    "success_count": batch.get('success_count', 0),
                    "fail_count": batch.get('fail_count', 0),
                    "skip_count": batch.get('skip_count', 0),
                    "success_rate": batch.get('success_rate', 0),
                },
                "timing": {
                    "start_time": batch.get('start_time').isoformat() if batch.get('start_time') else None,
                    "end_time": batch.get('end_time').isoformat() if batch.get('end_time') else None,
                    "duration_seconds": batch.get('duration_seconds', 0),
                    "duration_str": batch.get('duration_str', '0:00:00')
                },
                "error_count": len(batch.get('error_details', []))
            }
            formatted_history.append(formatted_batch)
        
        return {
            "source": source,
            "task_type": task_type,
            "total_batches": len(formatted_history),
            "history": formatted_history,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve batch history: {str(e)}"
        )


@router.get("/")
async def get_overall_progress() -> Dict[str, Any]:
    """
    获取全局进度统计
    
    Returns:
        Dict: 全局统计信息
    """
    try:
        overall_stats = progress_tracker.get_overall_stats()
        
        # 格式化返回数据
        formatted_stats = {
            "global_summary": {
                "total_batches": overall_stats.get('total_batches', 0),
                "running_batches": overall_stats.get('running_batches', 0),
                "total_processed": overall_stats.get('total_processed', 0),
                "total_success": overall_stats.get('total_success', 0),
                "total_fail": overall_stats.get('total_fail', 0),
                "total_skip": overall_stats.get('total_skip', 0),
                "success_rate": overall_stats.get('success_rate', 0),
            },
            "by_source": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # 格式化各来源的统计
        for source, source_stats in overall_stats.get('by_source', {}).items():
            formatted_stats["by_source"][source] = {
                "summary": {
                    "total_batches": source_stats.get('total_batches', 0),
                    "running_batches": source_stats.get('running_batches', 0),
                    "total_processed": source_stats.get('total_processed', 0),
                    "total_success": source_stats.get('total_success', 0),
                    "total_fail": source_stats.get('total_fail', 0),
                    "total_skip": source_stats.get('total_skip', 0),
                },
                "by_type": source_stats.get('by_type', {}),
                "status": "running" if source_stats.get('running_batches', 0) > 0 else "idle"
            }
        
        return formatted_stats
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve overall progress: {str(e)}"
        )


@router.post("/{source}/clear")
async def clear_progress_history(
    source: str,
    task_type: Optional[str] = Query(None, description="可选的任务类型，为空则清除该来源所有历史")
) -> Dict[str, str]:
    """
    清除进度历史记录
    
    Args:
        source: 爬虫来源
        task_type: 可选的任务类型过滤
    
    Returns:
        Dict: 操作结果
    """
    # 验证source参数
    valid_sources = ['github', 'openreview', 'homepage']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {valid_sources}"
        )
    
    try:
        progress_tracker.clear_history(source, task_type)
        
        clear_scope = f"{source}/{task_type}" if task_type else source
        return {
            "status": "success",
            "message": f"Progress history cleared for: {clear_scope}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear progress history: {str(e)}"
        )