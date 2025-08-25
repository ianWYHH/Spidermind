"""
FastAPI 应用入口

Author: Spidermind
"""
from fastapi import FastAPI, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime

from config.settings import settings
from models.base import get_db
from controllers import dashboard

# 创建 FastAPI 应用
app = FastAPI(
    title="Spidermind - Academic Researcher Crawler",
    description="学术人才信息爬虫与解析系统",
    version="1.0.0"
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置 Jinja2 模板
templates = Jinja2Templates(directory="templates")

# 包含路由
app.include_router(dashboard.router)

# 导入新的控制器
from controllers import logs, crawl_github, crawl_openreview, crawl_homepage, candidates, parse_llm, progress

# 注册新路由
app.include_router(logs.router)
app.include_router(crawl_github.router)
app.include_router(crawl_openreview.router)
app.include_router(crawl_homepage.router)
app.include_router(candidates.router)
app.include_router(parse_llm.router)
app.include_router(progress.router)

# 健康检查端点
@app.get("/health/app")
async def health_check():
    """应用健康检查"""
    return {
        "ok": True,
        "version": "1.0.0",
        "time": datetime.now().isoformat()
    }

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    print("🚀 Spidermind 启动中...")
    print(f"🌍 运行环境: {settings.ENV}")
    print(f"📊 数据库: {settings.get_mysql_dsn()}")
    
    # 自动创建数据库表
    try:
        from models.base import create_all_tables, test_database_connection
        
        # 测试数据库连接
        connection_test = test_database_connection()
        if connection_test["status"] == "connected":
            print("✅ 数据库连接成功")
            
            # 仅在非生产环境下创建表
            if settings.ENV.lower() != "prod":
                # 导入所有模型以确保表结构注册
                import models  # 这会触发所有模型的导入
                
                # 创建所有表
                create_all_tables()
                print("✅ 数据库表创建/更新完成")
            else:
                print("🔒 生产环境，跳过自动建表")
            
        else:
            print(f"❌ 数据库连接失败: {connection_test['message']}")
            
    except Exception as e:
        print(f"❌ 数据库初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    print("🛑 Spidermind 正在关闭...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)