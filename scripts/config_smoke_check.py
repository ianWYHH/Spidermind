#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置桥烟雾测试 - 验证配置加载是否正常

仅用于开发自检，严格遵守安全要求:
- 打印脱敏后的 DSN (不暴露密码)
- 显示 tokens 数量 (不暴露实际 token 值)
- 检查 QWEN 关键字段是否存在 (不暴露 API key)
- 禁止打印任何敏感信息明文
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_mysql_dsn():
    """检查 MySQL DSN 配置"""
    print("=== MySQL DSN 检查 ===")
    
    try:
        from app.config import mysql_dsn, mask_dsn
        
        dsn = mysql_dsn()
        masked_dsn = mask_dsn(dsn)
        
        print(f"✅ DSN 获取成功: {masked_dsn}")
        
        # 验证 DSN 格式
        if dsn.startswith('mysql+pymysql://'):
            print("✅ DSN 格式正确")
        else:
            print(f"⚠️  DSN 格式异常: {masked_dsn}")
            
    except Exception as e:
        print(f"❌ MySQL DSN 检查失败: {e}")


def check_github_tokens():
    """检查 GitHub Tokens 配置"""
    print("\n=== GitHub Tokens 检查 ===")
    
    try:
        from app.config import github_tokens_cfg
        
        config = github_tokens_cfg()
        tokens_count = len(config.get('tokens', []))
        
        print(f"✅ GitHub tokens 加载成功")
        print(f"✅ Tokens 数量: {tokens_count}")
        print(f"✅ API Base: {config.get('api_base', 'N/A')}")
        print(f"✅ 请求间隔: {config.get('per_request_sleep_seconds', 'N/A')}s")
        print(f"✅ 重试限制: {config.get('retry_limit', 'N/A')}")
        
        # 验证必需字段
        required_keys = ['tokens', 'api_base', 'per_request_sleep_seconds', 
                        'rate_limit_backoff_seconds', 'retry_limit', 
                        'retry_delay_seconds', 'max_concurrent_requests']
        
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            print(f"⚠️  缺少配置键: {missing_keys}")
        else:
            print("✅ 所有必需配置键都存在")
            
    except Exception as e:
        print(f"❌ GitHub Tokens 检查失败: {e}")


def check_qwen_config():
    """检查 QWEN 配置"""
    print("\n=== QWEN 配置检查 ===")
    
    try:
        from app.config import qwen_cfg
        
        config = qwen_cfg()
        
        print(f"✅ QWEN 配置加载成功")
        print(f"✅ 模型: {config.get('model', 'N/A')}")
        print(f"✅ Provider: {config.get('provider', 'N/A')}")
        print(f"✅ Max Tokens: {config.get('max_tokens', 'N/A')}")
        print(f"✅ Temperature: {config.get('temperature', 'N/A')}")
        
        # 检查 API Key 是否存在 (不打印明文)
        api_key = config.get('api_key', '')
        if api_key and len(api_key) > 10:
            print(f"✅ API Key: 已设置 (长度: {len(api_key)})")
        else:
            print("⚠️  API Key: 未设置或过短")
        
        # 检查 Base URL
        base_url = config.get('base_url', '')
        if base_url.startswith('https://'):
            print(f"✅ Base URL: {base_url}")
        else:
            print(f"⚠️  Base URL 格式异常: {base_url}")
            
    except Exception as e:
        print(f"❌ QWEN 配置检查失败: {e}")


def check_env_loading():
    """检查环境变量加载"""
    print("\n=== 环境变量加载检查 ===")
    
    try:
        from app.config import read_env
        
        # 检查一些常见环境变量
        test_vars = ['DEBUG', 'ENV', 'MYSQL_DSN', 'QWEN_API_KEY']
        
        for var in test_vars:
            value = read_env(var)
            if value:
                # 对敏感变量进行脱敏显示
                if 'DSN' in var or 'KEY' in var or 'PASSWORD' in var:
                    display_value = f"****(长度:{len(str(value))})"
                else:
                    display_value = value
                print(f"✅ {var}: {display_value}")
            else:
                print(f"⚪ {var}: 未设置")
                
    except Exception as e:
        print(f"❌ 环境变量检查失败: {e}")


def check_mask_function():
    """检查脱敏函数"""
    print("\n=== 脱敏功能检查 ===")
    
    try:
        from app.config import mask_dsn
        
        # 测试各种 DSN 格式
        test_cases = [
            "mysql+pymysql://root:password123@localhost:3306/test",
            "mysql://user:secret@127.0.0.1/db",
            "postgresql://admin:pass@host:5432/db",
            "invalid-dsn-format"
        ]
        
        print("脱敏测试:")
        for dsn in test_cases:
            masked = mask_dsn(dsn)
            # 确保没有暴露密码
            has_password = any(pwd in masked for pwd in ['password123', 'secret', 'pass'])
            if has_password:
                print(f"❌ 脱敏失败: {dsn} -> {masked}")
            else:
                print(f"✅ 脱敏成功: {dsn[:20]}... -> {masked}")
                
    except Exception as e:
        print(f"❌ 脱敏功能检查失败: {e}")


def main():
    """主检查函数"""
    print("🔍 配置桥烟雾测试开始")
    print("=" * 50)
    
    check_mysql_dsn()
    check_github_tokens()
    check_qwen_config()
    check_env_loading()
    check_mask_function()
    
    print("\n" + "=" * 50)
    print("🏁 配置桥烟雾测试完成")
    print("\n⚠️  安全提醒:")
    print("   - 检查结果中不包含任何密码或 token 明文")
    print("   - 生产环境请使用环境变量或密钥管理系统")
    print("   - 确保 .env 和 config/*.json 不会提交到版本控制")


if __name__ == "__main__":
    main()