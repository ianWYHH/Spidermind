#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试FastAPI模板渲染问题
"""

import traceback
from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from models.base import get_db
from services.stats_service import stats_service

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/debug")
async def debug_dashboard(request: Request, db: Session = Depends(get_db)):
    """调试仪表盘"""
    try:
        print("开始调试...")
        
        # 获取统计数据
        dashboard_stats = stats_service.get_dashboard_stats(db)
        print("获取统计数据成功")
        
        # 检查关键字段
        basic_contact_percentage = dashboard_stats['coverage']['basic_contact_percentage']
        print(f"basic_contact_percentage: {basic_contact_percentage}")
        
        # 准备模板上下文
        context = {
            "request": request,
            "stats": dashboard_stats
        }
        print("准备模板上下文成功")
        
        # 尝试渲染模板
        return templates.TemplateResponse("dashboard/index.html", context)
        
    except Exception as e:
        print(f"错误: {e}")
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)