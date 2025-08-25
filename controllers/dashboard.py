#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仪表盘控制器

提供系统统计和仪表盘功能
Author: Spidermind
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from models.base import get_db
from services.stats_service import stats_service
# from services.task_runner import task_runner  # 暂时注释，统一启动入口已在各自控制器实现

router = APIRouter(prefix="", tags=["仪表盘"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


class CrawlTaskRequest(BaseModel):
    """爬虫任务请求参数"""
    source: str                          # github/openreview/homepage
    recent_n: Optional[int] = 5         # GitHub: 最近仓库数
    star_n: Optional[int] = 5           # GitHub: star仓库数
    follow_depth: Optional[int] = 1     # GitHub: 关注深度
    batch_size: Optional[int] = 10      # 批次大小
    max_candidates: Optional[int] = None # 最大候选人数


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, db: Session = Depends(get_db)):
    """
    首页仪表盘
    
    Args:
        request: FastAPI请求对象
        db: 数据库会话
    
    Returns:
        HTMLResponse: 仪表盘页面
    """
    try:
        # 获取统计数据
        dashboard_stats = stats_service.get_dashboard_stats(db)
        
        return templates.TemplateResponse("dashboard/index.html", {
            "request": request,
            "stats": dashboard_stats
        })
        
    except Exception as e:
        logger.error(f"获取仪表盘页面失败: {e}")
        raise HTTPException(status_code=500, detail="获取仪表盘页面失败")


@router.get("/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    获取仪表盘统计数据API
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 统计数据
    """
    try:
        stats = stats_service.get_dashboard_stats(db)
        return {
            "status": "success",
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"获取仪表盘统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取仪表盘统计失败")


@router.get("/dashboard/tasks")
async def get_task_statistics(db: Session = Depends(get_db)):
    """
    获取任务统计信息
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 任务统计数据
    """
    try:
        task_stats = stats_service.get_task_statistics(db)
        return {
            "status": "success",
            "data": task_stats
        }
        
    except Exception as e:
        logger.error(f"获取任务统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取任务统计失败")


@router.get("/dashboard/parsing")
async def get_parsing_progress(db: Session = Depends(get_db)):
    """
    获取解析进度信息
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 解析进度数据
    """
    try:
        parse_progress = stats_service.get_candidate_parse_progress(db)
        return {
            "status": "success",
            "data": parse_progress
        }
        
    except Exception as e:
        logger.error(f"获取解析进度失败: {e}")
        raise HTTPException(status_code=500, detail="获取解析进度失败")


@router.get("/dashboard/coverage")
async def get_coverage_statistics(db: Session = Depends(get_db)):
    """
    获取字段覆盖率统计
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 覆盖率统计数据
    """
    try:
        coverage_stats = stats_service.get_field_coverage_statistics(db)
        return {
            "status": "success",
            "data": coverage_stats
        }
        
    except Exception as e:
        logger.error(f"获取覆盖率统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取覆盖率统计失败")


@router.get("/dashboard/activity")
async def get_recent_activity(limit: int = 20, db: Session = Depends(get_db)):
    """
    获取最近活动
    
    Args:
        limit: 返回数量限制
        db: 数据库会话
    
    Returns:
        Dict: 最近活动列表
    """
    try:
        activities = stats_service.get_recent_activity(db, limit)
        return {
            "status": "success",
            "data": activities
        }
        
    except Exception as e:
        logger.error(f"获取最近活动失败: {e}")
        raise HTTPException(status_code=500, detail="获取最近活动失败")


@router.get("/health/db")
async def get_database_health(db: Session = Depends(get_db)):
    """
    获取数据库健康状态和表计数
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 数据库状态和各表计数
    """
    try:
        # 导入所有模型以确保表定义完整
        from models.candidate import (
            Candidate, CandidateEmail, CandidateInstitution, 
            CandidateHomepage, CandidateFile, CandidateRepo, 
            CandidatePaper, RawText
        )
        from models.crawl import CrawlTask, CrawlLog, CrawlLogCandidate
        from models.mapping import GitHubUser, OpenReviewUser
        
        # 计算各表数量
        table_counts = {
            "candidates": db.query(Candidate).count(),
            "candidate_emails": db.query(CandidateEmail).count(),
            "candidate_institutions": db.query(CandidateInstitution).count(),
            "candidate_homepages": db.query(CandidateHomepage).count(),
            "candidate_files": db.query(CandidateFile).count(),
            "candidate_repos": db.query(CandidateRepo).count(),
            "candidate_papers": db.query(CandidatePaper).count(),
            "raw_texts": db.query(RawText).count(),
            "crawl_tasks": db.query(CrawlTask).count(),
            "crawl_logs": db.query(CrawlLog).count(),
            "crawl_log_candidates": db.query(CrawlLogCandidate).count(),
            "github_users": db.query(GitHubUser).count(),
            "openreview_users": db.query(OpenReviewUser).count(),
        }
        
        total_records = sum(table_counts.values())
        
        return {
            "status": "connected",
            "database": "MySQL",
            "total_tables": len(table_counts),
            "total_records": total_records,
            "table_counts": table_counts,
            "timestamp": db.execute("SELECT NOW()").scalar()
        }
        
    except Exception as e:
        logger.error(f"获取数据库健康状态失败: {e}")
        raise HTTPException(status_code=500, detail="数据库连接失败")


@router.get("/dashboard/health")
async def get_system_health(db: Session = Depends(get_db)):
    """
    获取系统健康状态
    
    Args:
        db: 数据库会话
    
    Returns:
        Dict: 系统健康状态
    """
    try:
        health = stats_service.get_system_health(db)
        return {
            "status": "success",
            "data": health
        }
        
    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统健康状态失败")


@router.post("/dashboard/crawl/start")
async def start_crawl_task(
    request: CrawlTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动爬虫任务
    
    Args:
        request: 爬虫任务请求
        background_tasks: 后台任务
        db: 数据库会话
    
    Returns:
        Dict: 启动结果
    """
    try:
        # 根据source启动对应的爬虫
        if request.source == "github":
            # 启动GitHub爬虫
            result = await _start_github_crawl(request, background_tasks, db)
        elif request.source == "openreview":
            # 启动OpenReview爬虫
            result = await _start_openreview_crawl(request, background_tasks, db)
        elif request.source == "homepage":
            # 启动首页爬虫
            result = await _start_homepage_crawl(request, background_tasks, db)
        else:
            raise HTTPException(status_code=400, detail="不支持的爬虫类型")
        
        return {
            "status": "success",
            "message": f"{request.source} 爬虫任务已启动",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动爬虫任务失败: {e}")
        raise HTTPException(status_code=500, detail="启动爬虫任务失败")


async def _start_github_crawl(
    request: CrawlTaskRequest, 
    background_tasks: BackgroundTasks, 
    db: Session
) -> Dict[str, Any]:
    """启动GitHub爬虫任务"""
    # 这里应该调用GitHub爬虫的启动逻辑
    # 由于GitHub爬虫在 /crawl/github/start，这里提供统一入口
    return {
        "source": "github",
        "config": {
            "recent_n": request.recent_n,
            "star_n": request.star_n,
            "follow_depth": request.follow_depth,
            "batch_size": request.batch_size
        },
        "redirect_url": "/crawl/github/start"
    }


async def _start_openreview_crawl(
    request: CrawlTaskRequest, 
    background_tasks: BackgroundTasks, 
    db: Session
) -> Dict[str, Any]:
    """启动OpenReview爬虫任务"""
    return {
        "source": "openreview",
        "config": {
            "batch_size": request.batch_size,
            "max_candidates": request.max_candidates
        },
        "redirect_url": "/crawl/openreview/start"
    }


async def _start_homepage_crawl(
    request: CrawlTaskRequest, 
    background_tasks: BackgroundTasks, 
    db: Session
) -> Dict[str, Any]:
    """启动Homepage爬虫任务"""
    return {
        "source": "homepage",
        "config": {
            "batch_size": request.batch_size,
            "max_candidates": request.max_candidates
        },
        "redirect_url": "/crawl/homepage/start"
    }