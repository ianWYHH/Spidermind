#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统快速验收脚本

快速检查系统各模块功能状态
Author: Spidermind
"""

import sys
import os
import time
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.base import SessionLocal
from models.crawl import CrawlTask, CrawlLog
from models.candidate import Candidate

def check_database_connection():
    """检查数据库连接"""
    print("🔍 检查数据库连接...")
    try:
        db = SessionLocal()
        # 简单查询测试连接
        count = db.query(Candidate).count()
        db.close()
        print(f"✅ 数据库连接正常，候选人数量: {count}")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False

def check_server_endpoints(base_url="http://localhost:8000"):
    """检查关键API端点"""
    print("🔍 检查关键API端点...")
    
    endpoints = [
        ("GET", "/", "首页"),
        ("GET", "/dashboard/stats", "仪表盘统计"),
        ("GET", "/candidates", "候选人列表"),
        ("GET", "/parse/review", "解析审查"),
        ("GET", "/logs", "日志页面")
    ]
    
    success_count = 0
    for method, path, name in endpoints:
        try:
            if method == "GET":
                response = requests.get(f"{base_url}{path}", timeout=5)
            else:
                response = requests.post(f"{base_url}{path}", timeout=5)
            
            if response.status_code in [200, 422]:  # 422表示缺少参数但端点存在
                print(f"  ✅ {name}: {response.status_code}")
                success_count += 1
            else:
                print(f"  ❌ {name}: {response.status_code}")
        except Exception as e:
            print(f"  ❌ {name}: 连接失败 ({str(e)[:50]})")
    
    print(f"📊 端点检查结果: {success_count}/{len(endpoints)} 正常")
    return success_count == len(endpoints)

def check_crawl_buttons():
    """检查爬虫按钮功能"""
    print("🔍 检查爬虫按钮功能...")
    
    base_url = "http://localhost:8000"
    crawlers = ["github", "openreview", "homepage"]
    
    success_count = 0
    for crawler in crawlers:
        try:
            # 检查状态端点
            response = requests.get(f"{base_url}/crawl/{crawler}/status", timeout=5)
            if response.status_code == 200:
                print(f"  ✅ {crawler.upper()} 爬虫状态正常")
                success_count += 1
            else:
                print(f"  ❌ {crawler.upper()} 爬虫状态异常: {response.status_code}")
        except Exception as e:
            print(f"  ❌ {crawler.upper()} 爬虫检查失败: {str(e)[:50]}")
    
    print(f"📊 爬虫检查结果: {success_count}/{len(crawlers)} 正常")
    return success_count == len(crawlers)

def check_log_windows():
    """检查日志窗口功能"""
    print("🔍 检查日志窗口功能...")
    
    db = SessionLocal()
    try:
        # 检查日志数量
        log_count = db.query(CrawlLog).count()
        
        # 检查最近日志
        recent_logs = db.query(CrawlLog).order_by(CrawlLog.created_at.desc()).limit(5).all()
        
        print(f"  📊 总日志数量: {log_count}")
        print(f"  📋 最近5条日志:")
        
        if recent_logs:
            for log in recent_logs:
                status_icon = "✅" if log.status == "success" else "❌" if log.status == "fail" else "⏭️"
                print(f"    {status_icon} [{log.source}] {log.status} - {log.message[:50]}...")
        else:
            print("    📝 暂无日志记录")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"  ❌ 日志检查失败: {e}")
        db.close()
        return False

def check_candidate_functionality():
    """检查候选人功能"""
    print("🔍 检查候选人功能...")
    
    db = SessionLocal()
    try:
        # 检查候选人数据
        candidate_count = db.query(Candidate).count()
        parsed_count = db.query(Candidate).filter(Candidate.llm_processed == True).count()
        
        print(f"  📊 候选人总数: {candidate_count}")
        print(f"  🧠 已解析数量: {parsed_count}")
        
        if candidate_count > 0:
            # 检查第一个候选人的详情
            first_candidate = db.query(Candidate).first()
            print(f"  👤 示例候选人: {first_candidate.name}")
            print(f"    - 邮箱: {first_candidate.primary_email or '未设置'}")
            print(f"    - GitHub: {first_candidate.github_login or '未设置'}")
            print(f"    - 机构: {first_candidate.current_institution or '未设置'}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"  ❌ 候选人检查失败: {e}")
        db.close()
        return False

def check_intelligent_parsing():
    """检查智能解析功能"""
    print("🔍 检查智能解析功能...")
    
    try:
        base_url = "http://localhost:8000"
        
        # 检查解析统计
        response = requests.get(f"{base_url}/parse/statistics", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"  📊 解析统计:")
            print(f"    - 总候选人: {stats.get('total_candidates', 0)}")
            print(f"    - 已解析: {stats.get('parsed_candidates', 0)}")
            print(f"    - 待解析: {stats.get('pending_candidates', 0)}")
            print(f"    - 研究标签覆盖: {stats.get('research_tags_coverage', 0):.1f}%")
            print(f"    - 技能标签覆盖: {stats.get('skill_tags_coverage', 0):.1f}%")
            return True
        else:
            print(f"  ❌ 解析统计获取失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ❌ 解析功能检查失败: {str(e)[:50]}")
        return False

def check_coverage_statistics():
    """检查覆盖率统计"""
    print("🔍 检查覆盖率统计...")
    
    try:
        base_url = "http://localhost:8000"
        
        response = requests.get(f"{base_url}/dashboard/coverage", timeout=5)
        if response.status_code == 200:
            stats = response.json()['data']
            
            print(f"  📊 字段覆盖率 (≥1条即覆盖):")
            coverage_fields = ['email', 'homepage', 'github', 'institution', 'raw_text']
            
            for field in coverage_fields:
                if field in stats['coverage_percentages']:
                    count = stats['coverage'][field]
                    percentage = stats['coverage_percentages'][field]
                    print(f"    - {field}: {count} 人 ({percentage:.1f}%)")
            
            print(f"  🎯 基础联系覆盖: {stats['basic_contact_percentage']:.1f}%")
            return True
        else:
            print(f"  ❌ 覆盖率统计获取失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ❌ 覆盖率检查失败: {str(e)[:50]}")
        return False

def run_quick_verification():
    """运行快速验证"""
    print("🎯 Spidermind 系统快速验收")
    print("=" * 50)
    
    checks = [
        ("数据库连接", check_database_connection),
        ("API端点", check_server_endpoints),
        ("爬虫按钮", check_crawl_buttons),
        ("日志窗口", check_log_windows),
        ("候选人功能", check_candidate_functionality),
        ("智能解析", check_intelligent_parsing),
        ("覆盖率统计", check_coverage_statistics)
    ]
    
    results = []
    for check_name, check_func in checks:
        print(f"\n📋 检查项目: {check_name}")
        try:
            result = check_func()
            results.append(result)
            if result:
                print(f"✅ {check_name} 检查通过")
            else:
                print(f"⚠️ {check_name} 检查未通过")
        except Exception as e:
            print(f"❌ {check_name} 检查异常: {e}")
            results.append(False)
    
    # 总结
    success_count = sum(results)
    total_count = len(results)
    success_rate = success_count / total_count * 100
    
    print("\n" + "=" * 50)
    print("🏁 验收总结")
    print("=" * 50)
    print(f"📊 检查结果: {success_count}/{total_count} 项通过 ({success_rate:.1f}%)")
    
    if success_rate >= 85:
        print("🎉 系统状态优秀! 可以正常使用")
        print("\n✨ 建议操作:")
        print("   1. 访问首页查看仪表盘: http://localhost:8000")
        print("   2. 运行完整演示: python demo_workflow.py")
        print("   3. 开始使用爬虫功能收集数据")
    elif success_rate >= 70:
        print("✅ 系统基本可用，部分功能可能需要调整")
        print("\n🔧 建议操作:")
        print("   1. 检查未通过的项目")
        print("   2. 查看系统日志排查问题")
        print("   3. 确认网络和权限配置")
    else:
        print("⚠️ 系统存在较多问题，建议排查后再使用")
        print("\n🛠️ 故障排除:")
        print("   1. 检查MySQL数据库是否正常运行")
        print("   2. 确认配置文件是否正确")
        print("   3. 查看应用日志: tail -f app.log")
        print("   4. 重启服务器: uvicorn main:app --reload")

if __name__ == "__main__":
    run_quick_verification()