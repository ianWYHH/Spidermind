#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试仪表盘问题
"""

import traceback
from models.base import get_db
from services.stats_service import stats_service

def debug_dashboard():
    try:
        db = next(get_db())
        print("1. 数据库连接成功")
        
        result = stats_service.get_dashboard_stats(db)
        print("2. 获取仪表盘数据成功")
        
        print("3. 数据结构检查:")
        print(f"   - 顶级键: {list(result.keys())}")
        print(f"   - coverage键: {list(result['coverage'].keys())}")
        
        basic_contact_percentage = result['coverage']['basic_contact_percentage']
        print(f"4. basic_contact_percentage: {basic_contact_percentage}")
        
        # 模拟模板渲染
        print("5. 模拟模板访问:")
        stats = result
        test_value = stats['coverage']['basic_contact_percentage']
        print(f"   - stats.coverage.basic_contact_percentage = {test_value}")
        
        print("✅ 所有测试通过!")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    debug_dashboard()