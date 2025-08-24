#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端演示脚本

演示完整的爬虫→解析→展示工作流程
Author: Spidermind
"""

import sys
import os
import time
import requests
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.base import SessionLocal
from models.crawl import CrawlTask
from models.candidate import Candidate

def print_header(title):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"🎯 {title}")
    print("=" * 60)

def print_step(step, description):
    """打印步骤"""
    print(f"\n📍 步骤 {step}: {description}")
    print("-" * 40)

def insert_demo_tasks():
    """插入演示任务"""
    print_step(1, "插入演示任务到数据库")
    
    db = SessionLocal()
    try:
        # GitHub演示任务
        github_tasks = [
            CrawlTask(
                source='github',
                type='profile',
                github_login='torvalds',
                status='pending'
            ),
            CrawlTask(
                source='github',
                type='profile', 
                github_login='gvanrossum',
                status='pending'
            ),
            CrawlTask(
                source='github',
                type='profile',
                github_login='yyx990803',
                status='pending'
            )
        ]
        
        # OpenReview演示任务
        openreview_tasks = [
            CrawlTask(
                source='openreview',
                type='forum',
                url='https://openreview.net/forum?id=example1',
                status='pending'
            ),
            CrawlTask(
                source='openreview',
                type='forum',
                url='https://openreview.net/forum?id=example2', 
                status='pending'
            )
        ]
        
        # Homepage演示任务
        homepage_tasks = [
            CrawlTask(
                source='homepage',
                type='homepage',
                url='https://karpathy.ai',
                status='pending'
            ),
            CrawlTask(
                source='homepage',
                type='homepage',
                url='https://colah.github.io',
                status='pending'
            )
        ]
        
        all_tasks = github_tasks + openreview_tasks + homepage_tasks
        
        for task in all_tasks:
            db.add(task)
        
        db.commit()
        
        print(f"✅ 成功插入 {len(all_tasks)} 个演示任务:")
        print(f"   📱 GitHub任务: {len(github_tasks)} 个")
        print(f"   📄 OpenReview任务: {len(openreview_tasks)} 个")
        print(f"   🌐 Homepage任务: {len(homepage_tasks)} 个")
        
        return len(all_tasks)
        
    except Exception as e:
        print(f"❌ 插入任务失败: {e}")
        db.rollback()
        return 0
    finally:
        db.close()

def check_server_status(base_url="http://localhost:8000"):
    """检查服务器状态"""
    print_step(2, "检查服务器状态")
    
    try:
        response = requests.get(f"{base_url}/dashboard/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ 服务器运行正常")
            print(f"   数据库状态: {health_data['data']['database_status']}")
            print(f"   系统状态: {health_data['data']['system_status']}")
            return True
        else:
            print(f"❌ 服务器响应异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 服务器连接失败: {e}")
        print(f"请确保服务器已启动: uvicorn main:app --host 0.0.0.0 --port 8000")
        return False

def start_crawler(source, config=None, base_url="http://localhost:8000"):
    """启动指定爬虫"""
    print(f"\n🚀 启动 {source.upper()} 爬虫")
    
    if config is None:
        config = {"batch_size": 5}
    
    try:
        if source == "github":
            config.update({"recent_n": 3, "star_n": 3, "follow_depth": 1})
            
        response = requests.post(
            f"{base_url}/crawl/{source}/start",
            json=config,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ {source.upper()} 爬虫启动成功")
            print(f"   批次ID: {result.get('batch_id', 'N/A')}")
            return True
        else:
            print(f"❌ {source.upper()} 爬虫启动失败: {response.status_code}")
            try:
                error_detail = response.json().get('detail', 'Unknown error')
                print(f"   错误详情: {error_detail}")
            except:
                pass
            return False
            
    except Exception as e:
        print(f"❌ {source.upper()} 爬虫启动异常: {e}")
        return False

def monitor_crawl_progress(max_wait_minutes=10, base_url="http://localhost:8000"):
    """监控爬虫进度"""
    print_step(3, f"监控爬虫进度 (最大等待 {max_wait_minutes} 分钟)")
    
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    
    while time.time() - start_time < max_wait_seconds:
        try:
            # 获取任务统计
            response = requests.get(f"{base_url}/dashboard/tasks", timeout=10)
            if response.status_code == 200:
                stats = response.json()['data']
                
                total_pending = stats['total']['pending']
                total_done = stats['total']['done'] 
                total_failed = stats['total']['failed']
                total_running = stats['total']['running']
                
                print(f"📊 任务状态: 待处理={total_pending}, 已完成={total_done}, 失败={total_failed}, 运行中={total_running}")
                
                # 如果没有待处理和运行中的任务，说明完成了
                if total_pending == 0 and total_running == 0:
                    print(f"✅ 所有爬虫任务执行完成!")
                    print(f"   总耗时: {time.time() - start_time:.1f} 秒")
                    return True
                
                # 按源显示详细进度
                for source in stats['sources']:
                    source_stats = stats['by_source'][source]
                    print(f"   {source}: 待处理={source_stats['by_status']['pending']}, "
                          f"已完成={source_stats['by_status']['done']}, "
                          f"失败={source_stats['by_status']['failed']}")
                
            time.sleep(10)  # 每10秒检查一次
            
        except Exception as e:
            print(f"⚠️ 监控异常: {e}")
            time.sleep(5)
    
    print(f"⏰ 达到最大等待时间 ({max_wait_minutes} 分钟)")
    return False

def check_candidates(base_url="http://localhost:8000"):
    """检查候选人数据"""
    print_step(4, "检查生成的候选人数据")
    
    try:
        # 获取候选人统计
        response = requests.get(f"{base_url}/dashboard/parsing", timeout=10)
        if response.status_code == 200:
            stats = response.json()['data']
            
            print(f"📊 候选人统计:")
            print(f"   总候选人数: {stats['total_candidates']}")
            print(f"   有原文数: {stats['candidates_with_texts']}")
            print(f"   已解析数: {stats['parsed_candidates']}")
            print(f"   待解析数: {stats['pending_parse']}")
            
            if stats['total_candidates'] > 0:
                print(f"✅ 成功发现 {stats['total_candidates']} 个候选人")
                return True
            else:
                print(f"⚠️ 未发现候选人，可能是爬虫还在运行或遇到问题")
                return False
        else:
            print(f"❌ 获取候选人统计失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 检查候选人数据异常: {e}")
        return False

def start_parsing(base_url="http://localhost:8000"):
    """启动解析任务"""
    print_step(5, "启动智能解析任务")
    
    try:
        config = {
            "batch_size": 5,
            "force_reparse": False
        }
        
        response = requests.post(
            f"{base_url}/parse/start",
            json=config,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 解析任务启动成功")
            print(f"   候选人数量: {result.get('candidates_count', 'N/A')}")
            print(f"   批次ID: {result.get('batch_id', 'N/A')}")
            return True
        else:
            print(f"❌ 解析任务启动失败: {response.status_code}")
            try:
                error_detail = response.json().get('detail', 'Unknown error')
                print(f"   错误详情: {error_detail}")
            except:
                pass
            return False
            
    except Exception as e:
        print(f"❌ 解析任务启动异常: {e}")
        return False

def check_field_coverage(base_url="http://localhost:8000"):
    """检查字段覆盖率"""
    print_step(6, "检查字段覆盖率统计")
    
    try:
        response = requests.get(f"{base_url}/dashboard/coverage", timeout=10)
        if response.status_code == 200:
            stats = response.json()['data']
            
            print(f"📊 字段覆盖率统计:")
            print(f"   总候选人数: {stats['total_candidates']}")
            print(f"   基础联系覆盖: {stats['basic_contact_coverage']} ({stats['basic_contact_percentage']:.1f}%)")
            
            print(f"\n📋 详细覆盖率:")
            coverage_fields = [
                ('email', '邮箱'),
                ('homepage', '主页'),
                ('github', 'GitHub'),
                ('institution', '机构'),
                ('raw_text', '原文')
            ]
            
            for field, name in coverage_fields:
                if field in stats['coverage_percentages']:
                    count = stats['coverage'][field]
                    percentage = stats['coverage_percentages'][field]
                    print(f"   {name}: {count} 人 ({percentage:.1f}%)")
            
            return True
            
    except Exception as e:
        print(f"❌ 检查字段覆盖率异常: {e}")
        return False

def show_final_summary(base_url="http://localhost:8000"):
    """显示最终总结"""
    print_step(7, "最终总结和访问指南")
    
    try:
        # 获取完整统计
        response = requests.get(f"{base_url}/dashboard/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()['data']
            
            print(f"🎉 演示完成! 系统已就绪")
            print(f"\n📈 系统统计:")
            print(f"   候选人总数: {stats['parsing']['total_candidates']}")
            print(f"   解析进度: {stats['parsing']['parse_progress']:.1f}%")
            print(f"   任务总数: {stats['tasks']['total']['total']}")
            print(f"   基础信息覆盖: {stats['coverage']['basic_contact_percentage']:.1f}%")
            
            print(f"\n🌐 访问链接:")
            print(f"   首页仪表盘: {base_url}/")
            print(f"   候选人列表: {base_url}/candidates")
            print(f"   解析管理: {base_url}/parse/review")
            print(f"   系统日志: {base_url}/logs")
            
            print(f"\n🔧 API端点:")
            print(f"   完整统计: GET {base_url}/dashboard/stats")
            print(f"   候选人数据: GET {base_url}/candidates")
            print(f"   启动GitHub爬虫: POST {base_url}/crawl/github/start")
            print(f"   启动解析: POST {base_url}/parse/start")
            
            return True
            
    except Exception as e:
        print(f"❌ 获取最终统计异常: {e}")
        return False

def main():
    """主演示流程"""
    print_header("Spidermind 端到端演示")
    
    print("🎯 本演示将展示完整的爬虫→解析→展示工作流程")
    print("📋 流程: 插入任务 → 运行爬虫 → 智能解析 → 数据展示")
    
    base_url = "http://localhost:8000"
    
    # 执行演示步骤
    steps = [
        ("插入演示任务", lambda: insert_demo_tasks()),
        ("检查服务器", lambda: check_server_status(base_url)),
        ("启动GitHub爬虫", lambda: start_crawler("github", base_url=base_url)),
        ("启动OpenReview爬虫", lambda: start_crawler("openreview", base_url=base_url)),
        ("启动Homepage爬虫", lambda: start_crawler("homepage", base_url=base_url)),
        ("监控爬虫进度", lambda: monitor_crawl_progress(5, base_url)),
        ("检查候选人数据", lambda: check_candidates(base_url)),
        ("启动智能解析", lambda: start_parsing(base_url)),
        ("检查字段覆盖率", lambda: check_field_coverage(base_url)),
        ("显示最终总结", lambda: show_final_summary(base_url))
    ]
    
    success_count = 0
    for i, (step_name, step_func) in enumerate(steps, 1):
        try:
            print(f"\n⏳ 执行步骤 {i}: {step_name}")
            if step_func():
                success_count += 1
                print(f"✅ 步骤 {i} 完成")
            else:
                print(f"⚠️ 步骤 {i} 遇到问题，但继续执行")
        except Exception as e:
            print(f"❌ 步骤 {i} 异常: {e}")
    
    print_header("演示结果")
    print(f"📊 执行结果: {success_count}/{len(steps)} 步骤成功")
    
    if success_count >= len(steps) * 0.7:  # 70%以上成功
        print("🎉 演示成功! 系统运行正常")
        print("\n🚀 下一步建议:")
        print("   1. 浏览器访问系统首页查看数据")
        print("   2. 尝试手动添加更多任务")
        print("   3. 测试候选人信息补录功能")
        print("   4. 查看实时日志和统计信息")
    else:
        print("⚠️ 演示部分成功，请检查错误信息")
        print("\n🔧 故障排除建议:")
        print("   1. 确保MySQL数据库正在运行")
        print("   2. 检查config/database.json配置")
        print("   3. 确保uvicorn服务器已启动")
        print("   4. 查看app.log日志文件")

if __name__ == "__main__":
    main()