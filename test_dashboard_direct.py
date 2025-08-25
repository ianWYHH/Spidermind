#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试dashboard_home函数
"""

import traceback
from fastapi import Request
from fastapi.templating import Jinja2Templates
from models.base import get_db
from controllers.dashboard import dashboard_home
from services.stats_service import stats_service

# 创建一个虚假的Request对象
class FakeRequest:
    def __init__(self):
        self.url = "http://localhost:8000/"
        self.method = "GET"
        self.headers = {}

def test_dashboard_home():
    try:
        print("1. 创建虚假Request对象...")
        fake_request = FakeRequest()
        
        print("2. 获取数据库会话...")
        db = next(get_db())
        
        print("3. 直接调用dashboard_home函数...")
        # 注意：这可能会失败，因为缺少真正的Request对象
        result = dashboard_home(fake_request, db)
        
        print("4. ✅ dashboard_home调用成功！")
        print(f"   返回类型: {type(result)}")
        
    except Exception as e:
        print(f"❌ dashboard_home调用失败: {e}")
        traceback.print_exc()
        
        # 尝试直接测试stats_service
        print("\n5. 🔄 尝试直接测试stats_service...")
        try:
            db = next(get_db())
            stats = stats_service.get_dashboard_stats(db)
            print("   ✅ stats_service正常")
            
            # 尝试模板渲染
            print("6. 🎨 尝试模板渲染...")
            templates = Jinja2Templates(directory="templates")
            
            # 检查模板文件是否存在
            import os
            template_path = "templates/dashboard/index.html"
            if os.path.exists(template_path):
                print(f"   ✅ 模板文件存在: {template_path}")
            else:
                print(f"   ❌ 模板文件不存在: {template_path}")
                
        except Exception as e2:
            print(f"   ❌ stats_service失败: {e2}")
            traceback.print_exc()

if __name__ == "__main__":
    test_dashboard_home()