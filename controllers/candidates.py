#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
候选人控制器

实现候选人列表、详情页和人工补录功能
Author: Spidermind
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.base import get_db
from models.candidate import (
    Candidate, CandidateEmail, CandidateInstitution, 
    CandidateHomepage, CandidateRepo, CandidateFile, 
    CandidatePaper, RawText
)
from models.crawl import CrawlLog
from services.completeness_service import completeness_service

router = APIRouter(prefix="/candidates", tags=["候选人管理"])
templates = Jinja2Templates(directory="templates")


class AddContactRequest(BaseModel):
    """添加联系信息请求"""
    value: str
    source: str = "manual_input"
    is_primary: bool = False


@router.get("/", response_class=HTMLResponse)
async def candidates_list(
    request: Request,
    query: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    候选人列表页面
    
    Args:
        request: FastAPI请求对象
        query: 搜索查询（姓名/机构/邮箱）
        page: 页码
        limit: 每页数量
        db: 数据库会话
    
    Returns:
        HTMLResponse: 候选人列表页面
    """
    try:
        # 构建查询
        candidates_query = db.query(Candidate)
        
        # 搜索过滤
        if query and query.strip():
            search_term = f"%{query.strip()}%"
            
            # 搜索条件：姓名、机构、邮箱
            search_conditions = [
                Candidate.name.like(search_term),
                Candidate.primary_affiliation.like(search_term),
                Candidate.bio.like(search_term)
            ]
            
            # 在邮箱子表中搜索
            email_candidates = db.query(CandidateEmail.candidate_id).filter(
                CandidateEmail.email.like(search_term)
            ).subquery()
            
            # 在机构子表中搜索
            institution_candidates = db.query(CandidateInstitution.candidate_id).filter(
                CandidateInstitution.institution.like(search_term)
            ).subquery()
            
            # 组合搜索条件
            candidates_query = candidates_query.filter(
                or_(
                    *search_conditions,
                    Candidate.id.in_(email_candidates),
                    Candidate.id.in_(institution_candidates)
                )
            )
        
        # 分页
        offset = (page - 1) * limit
        total_count = candidates_query.count()
        candidates = candidates_query.order_by(desc(Candidate.updated_at)).offset(offset).limit(limit).all()
        
        # 批量计算完整度得分
        completeness_scores = completeness_service.batch_calculate_scores(candidates, db)
        
        # 获取每个候选人的主要联系信息
        candidates_data = []
        for candidate in candidates:
            # 获取主邮箱
            primary_email_str = candidate.primary_email
            if not primary_email_str:
                primary_email_obj = db.query(CandidateEmail).filter(
                    CandidateEmail.candidate_id == candidate.id
                ).first()
                primary_email_str = primary_email_obj.email if primary_email_obj else None
            
            # 获取当前机构
            current_institution = db.query(CandidateInstitution).filter(
                CandidateInstitution.candidate_id == candidate.id
            ).order_by(desc(CandidateInstitution.created_at)).first()
            
            # 完整度信息
            score_info = completeness_scores.get(candidate.id, {})
            
            candidates_data.append({
                'candidate': candidate,
                'primary_email': primary_email_str,
                'current_institution': current_institution.institution if current_institution else candidate.current_institution,
                'completeness_score': score_info.get('total_score', 0),
                'missing_summary': completeness_service.get_missing_items_summary(
                    score_info.get('missing_descriptions', [])
                ),
                'completeness_level': score_info.get('completeness_level', 'unknown')
            })
        
        # 分页信息
        total_pages = (total_count + limit - 1) // limit
        has_prev = page > 1
        has_next = page < total_pages
        
        return templates.TemplateResponse("candidates/list.html", {
            "request": request,
            "candidates_data": candidates_data,
            "query": query or "",
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
        logger.error(f"获取候选人列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取候选人列表失败")


@router.get("/{candidate_id}", response_class=HTMLResponse)
async def candidate_detail(
    candidate_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    候选人详情页面
    
    Args:
        candidate_id: 候选人ID
        request: FastAPI请求对象
        db: 数据库会话
    
    Returns:
        HTMLResponse: 候选人详情页面
    """
    try:
        # 获取候选人基本信息
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="候选人不存在")
        
        # 计算完整度得分
        completeness_info = completeness_service.calculate_completeness_score(candidate, db)
        
        # 获取各类子数据
        emails = db.query(CandidateEmail).filter(CandidateEmail.candidate_id == candidate_id).all()
        institutions = db.query(CandidateInstitution).filter(CandidateInstitution.candidate_id == candidate_id).all()
        homepages = db.query(CandidateHomepage).filter(CandidateHomepage.candidate_id == candidate_id).all()
        repos = db.query(CandidateRepo).filter(CandidateRepo.candidate_id == candidate_id).all()
        files = db.query(CandidateFile).filter(CandidateFile.candidate_id == candidate_id).all()
        papers = db.query(CandidatePaper).filter(CandidatePaper.candidate_id == candidate_id).all()
        raw_texts = db.query(RawText).filter(RawText.candidate_id == candidate_id).all()
        
        # 获取相关日志（最近20条）
        related_logs = db.query(CrawlLog).filter(
            or_(
                CrawlLog.candidate_id == candidate_id,
                CrawlLog.url.in_([homepage.url for homepage in homepages if homepage.url])
            )
        ).order_by(desc(CrawlLog.created_at)).limit(20).all()
        
        return templates.TemplateResponse("candidates/detail.html", {
            "request": request,
            "candidate": candidate,
            "completeness_info": completeness_info,
            "emails": emails,
            "institutions": institutions,
            "homepages": homepages,
            "repos": repos,
            "files": files,
            "papers": papers,
            "raw_texts": raw_texts,
            "related_logs": related_logs
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取候选人详情失败: {candidate_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail="获取候选人详情失败")


@router.post("/{candidate_id}/add_email")
async def add_email(
    candidate_id: int,
    email: str = Form(...),
    source: str = Form("manual_input"),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db)
):
    """
    添加邮箱地址
    
    Args:
        candidate_id: 候选人ID
        email: 邮箱地址
        source: 来源
        is_primary: 是否为主邮箱
        db: 数据库会话
    
    Returns:
        Dict: 操作结果
    """
    try:
        # 验证候选人存在
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="候选人不存在")
        
        # 验证邮箱格式
        if not email or '@' not in email:
            raise HTTPException(status_code=400, detail="邮箱格式无效")
        
        # 检查邮箱是否已存在
        existing_email = db.query(CandidateEmail).filter(
            and_(
                CandidateEmail.candidate_id == candidate_id,
                CandidateEmail.email == email
            )
        ).first()
        
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已存在")
        
        # 如果设置为主邮箱，更新候选人主邮箱字段
        if is_primary:
            candidate.primary_email = email
        
        # 添加新邮箱（根据模型定义，只有这些字段）
        new_email = CandidateEmail(
            candidate_id=candidate_id,
            email=email,
            source=source
        )
        db.add(new_email)
        
        # 写入操作日志
        log_entry = CrawlLog(
            source='manual',
            type='add_email',
            url=email,
            candidate_id=candidate_id,
            status='success',
            message=f'人工添加邮箱: {email}',
            created_at=datetime.now()
        )
        db.add(log_entry)
        
        db.commit()
        
        return {"status": "success", "message": "邮箱添加成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加邮箱失败: {candidate_id}, {email}, 错误: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="添加邮箱失败")


@router.post("/{candidate_id}/add_homepage")
async def add_homepage(
    candidate_id: int,
    url: str = Form(...),
    source: str = Form("manual_input"),
    db: Session = Depends(get_db)
):
    """
    添加主页链接
    
    Args:
        candidate_id: 候选人ID
        url: 主页URL
        source: 来源
        db: 数据库会话
    
    Returns:
        Dict: 操作结果
    """
    try:
        # 验证候选人存在
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="候选人不存在")
        
        # 验证URL格式
        if not url or not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="URL格式无效")
        
        # 检查URL是否已存在
        existing_homepage = db.query(CandidateHomepage).filter(
            and_(
                CandidateHomepage.candidate_id == candidate_id,
                CandidateHomepage.url == url
            )
        ).first()
        
        if existing_homepage:
            raise HTTPException(status_code=400, detail="主页链接已存在")
        
        # 添加新主页
        new_homepage = CandidateHomepage(
            candidate_id=candidate_id,
            url=url,
            source=source
        )
        db.add(new_homepage)
        
        # 写入操作日志
        log_entry = CrawlLog(
            source='manual',
            type='add_homepage',
            url=url,
            candidate_id=candidate_id,
            status='success',
            message=f'人工添加主页: {url}',
            created_at=datetime.now()
        )
        db.add(log_entry)
        
        db.commit()
        
        return {"status": "success", "message": "主页链接添加成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加主页失败: {candidate_id}, {url}, 错误: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="添加主页失败")


@router.post("/{candidate_id}/add_file")
async def add_file(
    candidate_id: int,
    file_url: str = Form(...),
    file_type: str = Form("pdf"),
    source: str = Form("manual_input"),
    db: Session = Depends(get_db)
):
    """
    添加文件链接
    
    Args:
        candidate_id: 候选人ID
        file_url: 文件URL
        file_type: 文件类型
        source: 来源
        db: 数据库会话
    
    Returns:
        Dict: 操作结果
    """
    try:
        # 验证候选人存在
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="候选人不存在")
        
        # 验证URL格式
        if not file_url or not file_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="文件URL格式无效")
        
        # 验证文件类型
        if file_type not in ['pdf', 'image']:
            raise HTTPException(status_code=400, detail="文件类型无效")
        
        # 检查文件是否已存在
        existing_file = db.query(CandidateFile).filter(
            and_(
                CandidateFile.candidate_id == candidate_id,
                CandidateFile.file_url_or_path == file_url
            )
        ).first()
        
        if existing_file:
            raise HTTPException(status_code=400, detail="文件链接已存在")
        
        # 添加新文件
        new_file = CandidateFile(
            candidate_id=candidate_id,
            file_url_or_path=file_url,
            file_type=file_type,
            status='unparsed',
            source=source
        )
        db.add(new_file)
        
        # 写入操作日志
        log_entry = CrawlLog(
            source='manual',
            type='add_file',
            url=file_url,
            candidate_id=candidate_id,
            status='success',
            message=f'人工添加文件: {file_type} - {file_url}',
            created_at=datetime.now()
        )
        db.add(log_entry)
        
        db.commit()
        
        return {"status": "success", "message": "文件链接添加成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加文件失败: {candidate_id}, {file_url}, 错误: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="添加文件失败")


@router.get("/{candidate_id}/completeness")
async def get_candidate_completeness(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """
    获取候选人完整度信息
    
    Args:
        candidate_id: 候选人ID
        db: 数据库会话
    
    Returns:
        Dict: 完整度信息
    """
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="候选人不存在")
        
        completeness_info = completeness_service.calculate_completeness_score(candidate, db)
        
        return {
            "candidate_id": candidate_id,
            "completeness_info": completeness_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取完整度信息失败: {candidate_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail="获取完整度信息失败")