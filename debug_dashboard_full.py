#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整调试仪表盘Web请求流程
"""

import traceback
from fastapi.templating import Jinja2Templates
from models.base import get_db
from services.stats_service import stats_service

def debug_full_dashboard():
    try:
        # 1. 数据库连接
        db = next(get_db())
        print("1. ✅ 数据库连接成功")
        
        # 2. 获取统计数据
        dashboard_stats = stats_service.get_dashboard_stats(db)
        print("2. ✅ 获取仪表盘数据成功")
        
        # 3. 检查关键字段
        print("3. 🔍 检查关键字段:")
        stats = dashboard_stats
        
        # 检查模板中使用的所有字段
        fields_to_check = [
            ("stats.parsing.total_candidates", lambda: stats['parsing']['total_candidates']),
            ("stats.parsing.candidates_with_texts", lambda: stats['parsing']['candidates_with_texts']),
            ("stats.tasks.total.total", lambda: stats['tasks']['total']['total']),
            ("stats.tasks.total.pending", lambda: stats['tasks']['total']['pending']),
            ("stats.tasks.total.running", lambda: stats['tasks']['total']['running']),
            ("stats.parsing.parse_progress", lambda: stats['parsing']['parse_progress']),
            ("stats.parsing.parsed_candidates", lambda: stats['parsing']['parsed_candidates']),
            ("stats.coverage.basic_contact_percentage", lambda: stats['coverage']['basic_contact_percentage']),
            ("stats.coverage.basic_contact_coverage", lambda: stats['coverage']['basic_contact_coverage']),
            ("stats.system_health.system_status", lambda: stats['system_health']['system_status']),
            ("stats.system_health.recent_errors", lambda: stats['system_health']['recent_errors']),
            ("stats.tasks.by_source.github.by_status.pending", lambda: stats['tasks']['by_source']['github']['by_status']['pending']),
            ("stats.tasks.by_source.github.by_status.done", lambda: stats['tasks']['by_source']['github']['by_status']['done']),
            ("stats.tasks.by_source.openreview.by_status.pending", lambda: stats['tasks']['by_source']['openreview']['by_status']['pending']),
            ("stats.tasks.by_source.openreview.by_status.done", lambda: stats['tasks']['by_source']['openreview']['by_status']['done']),
            ("stats.tasks.by_source.homepage.by_status.pending", lambda: stats['tasks']['by_source']['homepage']['by_status']['pending']),
            ("stats.tasks.by_source.homepage.by_status.done", lambda: stats['tasks']['by_source']['homepage']['by_status']['done']),
            ("stats.parsing.pending_parse", lambda: stats['parsing']['pending_parse']),
            ("stats.parsing.recent_parse_activity", lambda: stats['parsing']['recent_parse_activity']),
        ]
        
        for field_name, field_accessor in fields_to_check:
            try:
                value = field_accessor()
                print(f"   ✅ {field_name} = {value}")
            except Exception as e:
                print(f"   ❌ {field_name} = ERROR: {e}")
                return False
        
        # 4. 模拟模板渲染准备
        print("4. 🎨 模拟模板渲染准备:")
        template_context = {
            "request": None,  # 在实际中这会是FastAPI Request对象
            "stats": dashboard_stats
        }
        print(f"   ✅ 模板上下文准备完成，stats类型: {type(template_context['stats'])}")
        
        print("5. ✅ 所有检查通过！问题可能在其他地方")
        return True
        
    except Exception as e:
        print(f"❌ 错误在步骤中发生: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_full_dashboard()