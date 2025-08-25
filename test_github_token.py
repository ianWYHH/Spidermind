#!/usr/bin/env python3
"""
测试GitHub Token是否有效
"""

import json
import requests

def test_github_token():
    """测试GitHub Token配置"""
    print("🧪 测试GitHub Token...")
    
    try:
        # 读取配置
        with open("config/tokens.github.json", 'r') as f:
            config = json.load(f)
        
        token = config['tokens'][0]['token']
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Spidermind-Crawler/1.0'
        }
        
        # 测试API调用
        print("  • 测试用户信息...")
        response = requests.get('https://api.github.com/user', headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
            rate_limit_limit = response.headers.get('X-RateLimit-Limit', 'unknown')
            
            print(f"✅ GitHub Token验证成功!")
            print(f"  • 用户: {user_data.get('login', 'unknown')}")
            print(f"  • 用户ID: {user_data.get('id', 'unknown')}")
            print(f"  • 用户类型: {user_data.get('type', 'unknown')}")
            print(f"  • API限制: {rate_limit_remaining}/{rate_limit_limit} 剩余")
            
            # 测试搜索API
            print("  • 测试搜索API...")
            search_response = requests.get('https://api.github.com/search/users?q=type:user+followers:>1000&per_page=1', headers=headers)
            if search_response.status_code == 200:
                print("✅ 搜索API测试成功!")
            else:
                print(f"⚠️  搜索API测试失败: {search_response.status_code}")
            
            return True
            
        elif response.status_code == 401:
            print(f"❌ Token验证失败: 未授权 (401)")
            print("  • 请检查token是否正确")
            print("  • 请确保token具有必要权限")
            return False
            
        elif response.status_code == 403:
            print(f"❌ Token验证失败: 被禁止 (403)")
            print("  • 可能是rate limit限制")
            print("  • 或者token权限不足")
            return False
            
        else:
            print(f"❌ Token验证失败: {response.status_code}")
            print(f"  错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔧 GitHub Token 验证测试")
    print("=" * 40)
    
    if test_github_token():
        print(f"\n🎉 配置成功! 现在可以使用爬虫功能了")
        print(f"\n📋 下一步操作:")
        print("  1. 停止当前的uvicorn服务 (Ctrl+C)")
        print("  2. 重新启动服务: uvicorn main:app --host 0.0.0.0 --port 8000")
        print("  3. 访问 http://127.0.0.1:8000")
        print("  4. 点击 'GitHub爬虫' 按钮测试")
    else:
        print(f"\n❌ Token配置有问题，请检查")