#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub API 客户端

实现GitHub API调用，支持token轮换、错误处理和速率限制
Author: Spidermind
"""

import json
import time
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class GitHubTokenManager:
    """GitHub Token管理器，支持轮换和冷却"""
    
    def __init__(self, tokens_config_path: str = "config/tokens.github.json"):
        """
        初始化Token管理器
        
        Args:
            tokens_config_path: token配置文件路径
        """
        self.config_path = tokens_config_path
        self.tokens_config = self._load_config()
        self.current_index = self.tokens_config.get("current_index", 0)
        self.sleep_between_requests = self.tokens_config.get("sleep_between_requests", 0.1)
        self.max_retries = self.tokens_config.get("max_retries", 2)
        self.retry_delay = self.tokens_config.get("retry_delay", 1.0)
        self.exponential_backoff = self.tokens_config.get("exponential_backoff", True)
        
    def _load_config(self) -> Dict[str, Any]:
        """加载token配置"""
        try:
            config_path = Path(self.config_path)
            if not config_path.exists():
                logger.warning(f"Token配置文件不存在: {self.config_path}")
                return {"tokens": [], "current_index": 0}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载token配置失败: {e}")
            return {"tokens": [], "current_index": 0}
    
    def _save_config(self):
        """保存token配置"""
        try:
            self.tokens_config["current_index"] = self.current_index
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.tokens_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存token配置失败: {e}")
    
    def get_active_token(self) -> Optional[Dict[str, Any]]:
        """获取当前可用的token"""
        tokens = self.tokens_config.get("tokens", [])
        if not tokens:
            logger.error("没有可用的GitHub tokens")
            return None
        
        # 检查所有token的冷却状态
        now = datetime.now()
        for i, token_info in enumerate(tokens):
            cooldown_until = token_info.get("cooldown_until")
            if cooldown_until:
                try:
                    cooldown_time = datetime.fromisoformat(cooldown_until)
                    if now < cooldown_time:
                        continue  # 仍在冷却中
                    else:
                        # 冷却结束，重新激活
                        token_info["cooldown_until"] = None
                        token_info["active"] = True
                        logger.info(f"Token {i} 冷却结束，重新激活")
                except:
                    pass
        
        # Round-Robin选择可用token
        start_index = self.current_index
        for _ in range(len(tokens)):
            token_info = tokens[self.current_index]
            if token_info.get("active", True) and not token_info.get("cooldown_until"):
                return token_info
            
            # 轮换到下一个token
            self.current_index = (self.current_index + 1) % len(tokens)
        
        # 如果没有可用token，返回第一个（即使在冷却中）
        self.current_index = start_index
        logger.warning("所有token都在冷却中，使用第一个token")
        return tokens[0] if tokens else None
    
    def mark_token_rate_limited(self, token: str, reset_time: Optional[datetime] = None):
        """标记token为速率限制状态"""
        tokens = self.tokens_config.get("tokens", [])
        for i, token_info in enumerate(tokens):
            if token_info.get("token") == token:
                cooldown_minutes = 60  # 默认冷却60分钟
                if reset_time:
                    cooldown_until = reset_time
                else:
                    cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
                
                token_info["cooldown_until"] = cooldown_until.isoformat()
                token_info["active"] = False
                token_info["remaining"] = 0
                
                logger.warning(f"Token {i} 达到速率限制，冷却至 {cooldown_until}")
                
                # 切换到下一个token
                self.current_index = (self.current_index + 1) % len(tokens)
                self._save_config()
                break
    
    def update_token_stats(self, token: str, remaining: int, reset_time: Optional[datetime] = None):
        """更新token统计信息"""
        tokens = self.tokens_config.get("tokens", [])
        for token_info in tokens:
            if token_info.get("token") == token:
                token_info["remaining"] = remaining
                if reset_time:
                    token_info["reset_time"] = reset_time.isoformat()
                self._save_config()
                break


class GitHubClient:
    """GitHub API客户端"""
    
    def __init__(self, tokens_config_path: str = "config/tokens.github.json"):
        """
        初始化GitHub客户端
        
        Args:
            tokens_config_path: token配置文件路径
        """
        self.token_manager = GitHubTokenManager(tokens_config_path)
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Spidermind-Academic-Crawler/1.0'
        })
    
    def _get_headers(self) -> Optional[Dict[str, str]]:
        """获取包含认证的请求头"""
        token_info = self.token_manager.get_active_token()
        if not token_info:
            return None
        
        headers = self.session.headers.copy()
        headers['Authorization'] = f"token {token_info['token']}"
        return headers
    
    def _handle_rate_limit(self, response: requests.Response) -> bool:
        """
        处理速率限制响应
        
        Args:
            response: HTTP响应对象
            
        Returns:
            bool: 是否应该重试
        """
        if response.status_code == 403:
            # 检查是否是速率限制
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
            if rate_limit_remaining == '0':
                # 解析重置时间
                reset_timestamp = response.headers.get('X-RateLimit-Reset')
                reset_time = None
                if reset_timestamp:
                    try:
                        reset_time = datetime.fromtimestamp(int(reset_timestamp))
                    except:
                        pass
                
                # 标记当前token为速率限制
                headers = self._get_headers()
                if headers and 'Authorization' in headers:
                    token = headers['Authorization'].replace('token ', '')
                    self.token_manager.mark_token_rate_limited(token, reset_time)
                    return True  # 可以重试其他token
        
        return False
    
    def _update_rate_limit_stats(self, response: requests.Response):
        """更新速率限制统计信息"""
        remaining = response.headers.get('X-RateLimit-Remaining')
        reset_timestamp = response.headers.get('X-RateLimit-Reset')
        
        if remaining is not None:
            headers = self._get_headers()
            if headers and 'Authorization' in headers:
                token = headers['Authorization'].replace('token ', '')
                reset_time = None
                if reset_timestamp:
                    try:
                        reset_time = datetime.fromtimestamp(int(reset_timestamp))
                    except:
                        pass
                
                self.token_manager.update_token_stats(token, int(remaining), reset_time)
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """
        发起HTTP请求，包含重试和错误处理
        
        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 其他请求参数
            
        Returns:
            requests.Response: 成功的响应，或None
        """
        headers = self._get_headers()
        if not headers:
            logger.error("没有可用的GitHub token")
            return None
        
        kwargs['headers'] = headers
        
        for attempt in range(self.token_manager.max_retries + 1):
            try:
                # 请求间延迟
                if attempt > 0 or self.token_manager.sleep_between_requests > 0:
                    delay = self.token_manager.sleep_between_requests
                    if attempt > 0 and self.token_manager.exponential_backoff:
                        delay = self.token_manager.retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                
                response = self.session.request(method, url, **kwargs)
                
                # 更新速率限制统计
                self._update_rate_limit_stats(response)
                
                # 处理成功响应
                if response.status_code == 200:
                    return response
                
                # 处理404 - 用户或仓库不存在
                if response.status_code == 404:
                    logger.debug(f"资源不存在: {url}")
                    return response  # 返回404响应，让调用者处理
                
                # 处理速率限制
                if self._handle_rate_limit(response):
                    # 获取新的headers并重试
                    headers = self._get_headers()
                    if headers:
                        kwargs['headers'] = headers
                        continue
                
                # 其他错误
                logger.warning(f"请求失败 {response.status_code}: {url}")
                
                # 如果是最后一次尝试，返回响应
                if attempt == self.token_manager.max_retries:
                    return response
                
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 (尝试 {attempt + 1}): {e}")
                if attempt == self.token_manager.max_retries:
                    return None
        
        return None
    
    def get_user(self, login: str) -> Optional[Dict[str, Any]]:
        """
        获取用户信息
        
        Args:
            login: GitHub用户名
            
        Returns:
            Dict: 用户信息，或None
        """
        url = f"{self.base_url}/users/{login}"
        response = self._make_request("GET", url)
        
        if response and response.status_code == 200:
            try:
                return response.json()
            except:
                logger.error(f"解析用户信息失败: {login}")
        
        return None
    
    def get_user_orgs(self, login: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """
        获取用户所属组织
        
        Args:
            login: GitHub用户名
            per_page: 每页数量
            
        Returns:
            List[Dict]: 组织列表
        """
        url = f"{self.base_url}/users/{login}/orgs"
        response = self._make_request("GET", url, params={'per_page': per_page})
        
        if response and response.status_code == 200:
            try:
                return response.json()
            except:
                logger.error(f"解析用户组织失败: {login}")
        
        return []
    
    def get_user_repos(self, login: str, per_page: int = 100, sort: str = "updated") -> List[Dict[str, Any]]:
        """
        获取用户仓库列表
        
        Args:
            login: GitHub用户名
            per_page: 每页数量
            sort: 排序方式 (created, updated, pushed, full_name)
            
        Returns:
            List[Dict]: 仓库列表
        """
        repos = []
        page = 1
        
        while True:
            url = f"{self.base_url}/users/{login}/repos"
            params = {
                'per_page': per_page,
                'page': page,
                'sort': sort,
                'type': 'all'  # owner, all, public, private, member
            }
            
            response = self._make_request("GET", url, params=params)
            
            if not response or response.status_code != 200:
                break
            
            try:
                page_repos = response.json()
                if not page_repos:  # 没有更多数据
                    break
                
                repos.extend(page_repos)
                
                # 如果返回的数量少于per_page，说明是最后一页
                if len(page_repos) < per_page:
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"解析用户仓库失败: {login}, 页码: {page}, 错误: {e}")
                break
        
        return repos
    
    def get_readme(self, owner: str, repo: str) -> Optional[str]:
        """
        获取仓库README内容
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            
        Returns:
            str: README内容，或None
        """
        # 尝试不同的README文件名
        readme_files = ['README.md', 'readme.md', 'README.txt', 'readme.txt', 'README', 'readme']
        
        for readme_file in readme_files:
            url = f"{self.base_url}/repos/{owner}/{repo}/contents/{readme_file}"
            response = self._make_request("GET", url)
            
            if response and response.status_code == 200:
                try:
                    content_data = response.json()
                    if content_data.get('content'):
                        import base64
                        content = base64.b64decode(content_data['content']).decode('utf-8', errors='ignore')
                        return content
                except Exception as e:
                    logger.debug(f"解析README失败: {owner}/{repo}/{readme_file}, 错误: {e}")
                    continue
        
        return None
    
    def get_user_followers(self, login: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """
        获取用户粉丝列表
        
        Args:
            login: GitHub用户名
            per_page: 每页数量
            
        Returns:
            List[Dict]: 粉丝列表
        """
        url = f"{self.base_url}/users/{login}/followers"
        response = self._make_request("GET", url, params={'per_page': per_page})
        
        if response and response.status_code == 200:
            try:
                return response.json()
            except:
                logger.error(f"解析用户粉丝失败: {login}")
        
        return []
    
    def get_user_following(self, login: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """
        获取用户关注列表
        
        Args:
            login: GitHub用户名
            per_page: 每页数量
            
        Returns:
            List[Dict]: 关注列表
        """
        url = f"{self.base_url}/users/{login}/following"
        response = self._make_request("GET", url, params={'per_page': per_page})
        
        if response and response.status_code == 200:
            try:
                return response.json()
            except:
                logger.error(f"解析用户关注失败: {login}")
        
        return []
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        获取当前token的速率限制状态
        
        Returns:
            Dict: 速率限制信息
        """
        url = f"{self.base_url}/rate_limit"
        response = self._make_request("GET", url)
        
        if response and response.status_code == 200:
            try:
                return response.json()
            except:
                pass
        
        return {"core": {"remaining": 0, "limit": 5000}}


# 全局实例
github_client = GitHubClient()