#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析控制器

提供解析任务启动和管理接口
Author: Spidermind
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import logging

from models.base import get_db, SessionLocal
from models.candidate import Candidate
from services.parse_service import parse_service
from services.progress_service import progress_tracker

router = APIRouter(prefix="/parse", tags=["解析管理"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    """解析请求参数"""
    batch_size: int = 10        # 每批处理数量
    max_candidates: Optional[int] = None  # 最大处理候选人数
    force_reparse: bool = False  # 是否强制重新解析


class ResetParseRequest(BaseModel):
    """重置解析请求参数"""
    candidate_ids: List[int]    # 候选人ID列表


@router.post("/start")
async def start_parsing(
    request: ParseRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动解析任务
    
    Args:
        request: 解析请求参数
        background_tasks: FastAPI后台任务
        db: 数据库会话
    
    Returns:
        Dict: 启动结果
    """
    try:
        # 查找待解析候选人
        candidates = parse_service.find_candidates_for_parsing(db, limit=request.max_candidates or 100)
        
        if not candidates:
            return {
                "status": "no_candidates",
                "message": "没有找到需要解析的候选人",
                "candidates_count": 0
            }
        
        # 检查是否已有运行中的解析任务
        current_stats = progress_tracker.get_current_stats('parse', 'tags_extraction')
        if current_stats and current_stats.get('status') == 'running':
            return {
                "status": "already_running",
                "message": "解析任务已在运行中",
                "current_batch": current_stats,
                "candidates_count": len(candidates)
            }
        
        # 开始新的批次
        batch_id = progress_tracker.start_batch(
            source='parse',
            task_type='tags_extraction'
        )
        
        # 在后台启动解析任务
        background_tasks.add_task(
            _run_parsing_task,
            batch_id=batch_id,
            candidates=candidates,
            batch_size=request.batch_size,
            force_reparse=request.force_reparse
        )
        
        return {
            "status": "started",
            "message": "解析任务已启动",
            "batch_id": batch_id,
            "candidates_count": len(candidates),
            "config": {
                "batch_size": request.batch_size,
                "max_candidates": request.max_candidates,
                "force_reparse": request.force_reparse
            }
        }
        
    except Exception as e:
        logger.error(f"启动解析任务失败: {e}")
        raise HTTPException(status_code=500, detail="启动解析任务失败")


@router.get("/status")
async def get_parsing_status(db: Session = Depends(get_db)):
    """
    获取解析任务状态
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 解析状态信息
    """
    try:
        # 获取当前运行状态
        current_stats = progress_tracker.get_current_stats('parse', 'tags_extraction')
        
        # 获取历史记录
        history = progress_tracker.get_batch_history('parse', 'tags_extraction', limit=5)
        
        # 获取解析统计
        statistics = parse_service.get_parsing_statistics(db)
        
        return {
            "task_type": "tags_extraction",
            "current_batch": current_stats,
            "recent_history": history,
            "statistics": statistics,
            "is_running": current_stats is not None and current_stats.get('status') == 'running'
        }
        
    except Exception as e:
        logger.error(f"获取解析状态失败: {e}")
        raise HTTPException(status_code=500, detail="获取解析状态失败")


@router.post("/stop")
async def stop_parsing():
    """
    停止解析任务
    
    Returns:
        Dict: 停止结果
    """
    try:
        # 获取当前状态
        current_stats = progress_tracker.get_current_stats('parse', 'tags_extraction')
        
        if not current_stats or current_stats.get('status') != 'running':
            return {
                "status": "not_running",
                "message": "解析任务当前未运行"
            }
        
        # 标记批次为完成状态
        progress_tracker.finish_batch('parse', 'tags_extraction')
        
        return {
            "status": "stopped",
            "message": "解析任务已停止",
            "final_stats": current_stats
        }
        
    except Exception as e:
        logger.error(f"停止解析任务失败: {e}")
        raise HTTPException(status_code=500, detail="停止解析任务失败")


@router.get("/review", response_class=HTMLResponse)
async def review_parsing_results(
    request: Request,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    查看解析结果页面
    
    Args:
        request: FastAPI请求对象
        page: 页码
        limit: 每页数量
        db: 数据库会话
    
    Returns:
        HTMLResponse: 解析结果页面
    """
    try:
        # 获取最近的解析结果
        recent_results = parse_service.get_recent_parsing_results(db, limit=limit * page)
        
        # 分页处理
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_results = recent_results[start_idx:end_idx]
        
        # 获取统计信息
        statistics = parse_service.get_parsing_statistics(db)
        
        # 分页信息
        total_count = len(recent_results)
        total_pages = (total_count + limit - 1) // limit
        has_prev = page > 1
        has_next = page < total_pages
        
        return templates.TemplateResponse("parse/review.html", {
            "request": request,
            "results": page_results,
            "statistics": statistics,
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_page": page - 1 if has_prev else None,
            "next_page": page + 1 if has_next else None
        })
        
    except Exception as e:
        logger.error(f"获取解析结果页面失败: {e}")
        raise HTTPException(status_code=500, detail="获取解析结果页面失败")


@router.post("/reset")
async def reset_parsing(
    request: ResetParseRequest,
    db: Session = Depends(get_db)
):
    """
    重置候选人解析状态
    
    Args:
        request: 重置请求参数
        db: 数据库会话
    
    Returns:
        Dict: 重置结果
    """
    try:
        if not request.candidate_ids:
            raise HTTPException(status_code=400, detail="候选人ID列表不能为空")
        
        results = []
        success_count = 0
        fail_count = 0
        
        for candidate_id in request.candidate_ids:
            result = parse_service.reset_candidate_parsing(candidate_id, db)
            results.append(result)
            
            if result['status'] == 'success':
                success_count += 1
            else:
                fail_count += 1
        
        return {
            "status": "completed",
            "message": f"重置完成: 成功 {success_count} 个, 失败 {fail_count} 个",
            "success_count": success_count,
            "fail_count": fail_count,
            "details": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置解析状态失败: {e}")
        raise HTTPException(status_code=500, detail="重置解析状态失败")


@router.get("/statistics")
async def get_parsing_statistics(db: Session = Depends(get_db)):
    """
    获取解析统计信息
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 统计信息
    """
    try:
        statistics = parse_service.get_parsing_statistics(db)
        return statistics
        
    except Exception as e:
        logger.error(f"获取解析统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取解析统计失败")


@router.get("/candidates/pending")
async def get_pending_candidates(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    获取待解析候选人列表
    
    Args:
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 待解析候选人列表
    """
    try:
        candidates = parse_service.find_candidates_for_parsing(db, limit)
        
        candidates_data = []
        for candidate in candidates:
            # 获取原文统计
            raw_texts = parse_service.get_candidate_raw_texts(candidate, db)
            combined_text = parse_service.combine_texts(raw_texts)
            
            candidates_data.append({
                "id": candidate.id,
                "name": candidate.name,
                "current_institution": candidate.current_institution,
                "llm_processed": candidate.llm_processed,
                "raw_texts_count": len(raw_texts),
                "combined_text_length": len(combined_text),
                "created_at": candidate.created_at.isoformat() if candidate.created_at else None
            })
        
        return {
            "candidates": candidates_data,
            "total_count": len(candidates_data)
        }
        
    except Exception as e:
        logger.error(f"获取待解析候选人列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取待解析候选人列表失败")


async def _run_parsing_task(
    batch_id: str,
    candidates: List[Candidate],
    batch_size: int = 10,
    force_reparse: bool = False
):
    """
    后台运行解析任务
    
    Args:
        batch_id: 批次ID
        candidates: 候选人列表
        batch_size: 批次大小
        force_reparse: 是否强制重新解析
    """
    try:
        logger.info(f"开始解析批次 {batch_id}, 候选人数: {len(candidates)}")
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        # 分批处理
        for i in range(0, len(candidates), batch_size):
            batch_candidates = candidates[i:i + batch_size]
            
            logger.info(f"处理批次 {i//batch_size + 1}, 候选人: {len(batch_candidates)}")
            
            for candidate in batch_candidates:
                try:
                    # 检查是否需要强制重新解析
                    if candidate.llm_processed and not force_reparse:
                        skip_count += 1
                        continue
                    
                    # 创建新的数据库会话
                    db = SessionLocal()
                    try:
                        result = parse_service.parse_candidate(candidate, db)
                        
                        if result['status'] == 'success':
                            success_count += 1
                        elif result['status'] == 'skip':
                            skip_count += 1
                        else:
                            fail_count += 1
                        
                        # 更新进度
                        progress_tracker.update_progress(
                            'parse', 
                            'tags_extraction',
                            processed=success_count + fail_count + skip_count,
                            total=len(candidates),
                            batch_id=batch_id
                        )
                        
                    finally:
                        db.close()
                        
                except Exception as e:
                    logger.error(f"解析候选人 {candidate.id} 失败: {e}")
                    fail_count += 1
            
            # 批次间短暂停顿
            if i + batch_size < len(candidates):
                await asyncio.sleep(0.5)
        
        # 完成批次
        progress_tracker.finish_batch('parse', 'tags_extraction', batch_id)
        
        logger.info(f"解析批次 {batch_id} 完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}")
        
    except Exception as e:
        # 记录批次失败
        progress_tracker.record_failure(
            'parse', 
            'tags_extraction', 
            f"批次执行异常: {str(e)}", 
            batch_id
        )
        
        # 结束批次
        progress_tracker.finish_batch('parse', 'tags_extraction', batch_id)
        
        logger.error(f"解析批次 {batch_id} 执行异常: {e}")