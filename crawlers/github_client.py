#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub API客户端 - 支持多token轮换、冷却、退避和并发安全

实现GitHub API数据抓取，包括用户profile和仓库信息
Author: Spidermind
"""

import json
import logging
import time
import asyncio
from collections import deque
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class TokenState:
    """GitHub Token状态"""
    value: str
    cooldown_until: Optional[float] = None  # epoch秒，token冷却到此时间
    disabled: bool = False  # token是否被禁用（如认证失败）
    last_used_at: Optional[float] = None  # 上次使用时间
    remaining: int = 5000  # 剩余请求次数
    reset_time: Optional[str] = None  # 限额重置时间

    def is_available(self) -> bool:
        """检查token是否可用"""
        if self.disabled:
            return False
        if self.cooldown_until and time.time() < self.cooldown_until:
            return False
        return True
    
    def get_masked_value(self) -> str:
        """获取掩码后的token值（只显示最后4位）"""
        if len(self.value) > 4:
            return f"...{self.value[-4:]}"
        return self.value


class GitHubClient:
    """GitHub API客户端 - 支持多token轮换、冷却、退避和并发安全"""
    
    def __init__(self):
        """初始化GitHub客户端"""
        # 从统一配置获取GitHub配置
        try:
            self.config = settings.get_github_tokens_config()
        except ValueError as e:
            logger.error(f"GitHub配置加载失败: {e}")
            raise
        
        # Token管理
        self.token_queue: deque[TokenState] = deque()
        self.lock = asyncio.Lock()  # 并发安全锁
        
        # HTTP客户端
        self.client: Optional[httpx.AsyncClient] = None
        
        # 请求配置
        self.api_base = self.config["api_base"]
        self.per_request_sleep = self.config["per_request_sleep_seconds"]
        self.rate_limit_backoff = self.config["rate_limit_backoff_seconds"]
        self.max_retries = 5  # 最多重试5次
        self.max_backoff = 60  # 最大退避时间60秒
        
        # 初始化
        self._initialize_tokens()
        self._setup_client()
    
    def _initialize_tokens(self):
        """初始化token队列"""
        tokens_config = self.config.get("tokens", [])
        
        if not tokens_config:
            raise ValueError("没有找到有效的GitHub token配置")
        
        # 转换为TokenState对象
        for token_data in tokens_config:
            token_state = TokenState(
                value=token_data["value"],
                disabled=(token_data.get("status", "active") != "active"),
                remaining=token_data.get("remaining", 5000),
                reset_time=token_data.get("reset_time"),
                last_used_at=token_data.get("last_used_at")
            )
            
            # 处理cooldown_until
            if token_data.get("cooldown_until"):
                if isinstance(token_data["cooldown_until"], (int, float)):
                    token_state.cooldown_until = float(token_data["cooldown_until"])
            
            self.token_queue.append(token_state)
        
        logger.info(f"已初始化 {len(self.token_queue)} 个GitHub token")
        
        # 记录初始状态
        available_count = sum(1 for token in self.token_queue if token.is_available())
        logger.info(f"可用token数量: {available_count}/{len(self.token_queue)}")
    
    def _setup_client(self):
        """设置HTTP客户端"""
        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=15.0,  # 设置15秒超时
            headers={
                'User-Agent': 'SpidermindBot',
                'Accept': 'application/vnd.github.v3+json'
            }
        )
    
    async def acquire_token(self) -> TokenState:
        """
        获取可用的token (Round-Robin策略)
        
        Returns:
            TokenState: 可用的token状态
            
        Raises:
            RuntimeError: 所有token都不可用时
        """
        async with self.lock:
            # 寻找可用的token
            for _ in range(len(self.token_queue)):
                token = self.token_queue.popleft()
                
                if token.is_available():
                    # 更新使用时间
                    token.last_used_at = time.time()
                    # 移动到队尾（Round-Robin）
                    self.token_queue.append(token)
                    
                    # 结构化日志
                    logger.info(json.dumps({
                        "event": "rotate_token",
                        "token_tail": token.get_masked_value(),
                        "reason": "normal",
                        "remaining": token.remaining
                    }))
                    
                    return token
                else:
                    # 重新放回队尾
                    self.token_queue.append(token)
            
            # 如果没有可用token，计算等待时间
            return await self._wait_for_available_token()
    
    async def _wait_for_available_token(self) -> TokenState:
        """等待token变为可用"""
        # 找到最早将要解除冷却的token
        available_tokens = []
        for token in self.token_queue:
            if not token.disabled and token.cooldown_until:
                available_tokens.append(token.cooldown_until)
        
        if not available_tokens:
            # 所有token都被禁用
            disabled_count = sum(1 for t in self.token_queue if t.disabled)
            raise RuntimeError(f"所有GitHub token都不可用 (禁用: {disabled_count}, 总数: {len(self.token_queue)})")
        
        # 等待最早的冷却时间
        min_cooldown = min(available_tokens)
        wait_time = max(0, min_cooldown - time.time())
        
        if wait_time > 0:
            logger.warning(json.dumps({
                "event": "waiting_for_token",
                "wait_seconds": round(wait_time, 1),
                "reason": "all_tokens_cooling"
            }))
            await asyncio.sleep(wait_time)
        
        # 递归重试
        return await self.acquire_token()
    
    async def _make_request_with_retries(self, method: str, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        发起HTTP请求并处理重试逻辑
        
        Args:
            method: HTTP方法
            path: API路径
            params: 查询参数
            
        Returns:
            Dict: JSON响应数据
            
        Raises:
            RuntimeError: 请求最终失败时
        """
        last_exception = None
        backoff_seconds = 1  # 初始退避时间
        
        for attempt in range(self.max_retries + 1):
            try:
                # 获取可用token
                token = await self.acquire_token()
                
                # 请求间延迟
                if attempt == 0:  # 第一次请求才休眠
                    await asyncio.sleep(self.per_request_sleep)
                
                # 设置请求头
                headers = {
                    'Authorization': f'token {token.value}',
                    'User-Agent': 'SpidermindBot',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                # 发起请求
                response = await self.client.request(
                    method=method,
                    url=path,
                    params=params,
                    headers=headers
                )
                
                # 处理响应
                result = await self._handle_response(response, token, attempt)
                if result is not None:
                    return result
                
                # 如果返回None，说明需要重试
                continue
                
            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries + 1}): {path}")
                
            except httpx.RequestError as e:
                last_exception = e
                logger.warning(f"网络错误 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"未知错误 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
            
            # 指数退避
            if attempt < self.max_retries:
                backoff_seconds = min(backoff_seconds * 2, self.max_backoff)
                logger.warning(json.dumps({
                    "event": "request_retry",
                    "attempt": attempt + 1,
                    "backoff_seconds": backoff_seconds,
                    "path": path
                }))
                await asyncio.sleep(backoff_seconds)
        
        # 所有重试都失败了
        logger.error(f"请求最终失败: {path}, 最后错误: {last_exception}")
        raise RuntimeError(f"GitHub API请求失败: {path}") from last_exception
    
    async def _handle_response(self, response: httpx.Response, token: TokenState, attempt: int) -> Optional[Dict[str, Any]]:
        """
        处理API响应
        
        Args:
            response: HTTP响应
            token: 使用的token状态
            attempt: 当前尝试次数
            
        Returns:
            Optional[Dict]: 成功时返回JSON数据，需要重试时返回None
        """
        # 更新token状态
        async with self.lock:
            # 读取速率限制信息
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining:
                token.remaining = int(remaining)
            if reset_time:
                token.reset_time = reset_time
        
        # 处理不同状态码
        if response.status_code == 200:
            # 成功响应
            try:
                return response.json()
            except json.JSONDecodeError:
                logger.error("响应JSON解析失败")
                return None
        
        elif response.status_code == 401:
            # 认证失败
            response_text = response.text.lower()
            async with self.lock:
                if 'rate limit' in response_text or 'api rate limit exceeded' in response_text:
                    # 速率限制
                    reset_ts = int(reset_time) if reset_time else time.time() + self.rate_limit_backoff
                    token.cooldown_until = reset_ts + 1
                    
                    logger.warning(json.dumps({
                        "event": "rate_limit_hit",
                        "token_tail": token.get_masked_value(),
                        "reset_timestamp": reset_ts,
                        "reason": "401_rate_limit"
                    }))
                    
                    # 轮换到下一个token
                    logger.info(json.dumps({
                        "event": "rotate_token",
                        "token_tail": token.get_masked_value(),
                        "reason": "rate_limit"
                    }))
                else:
                    # Token无效
                    token.disabled = True
                    logger.error(json.dumps({
                        "event": "token_disabled",
                        "token_tail": token.get_masked_value(),
                        "reason": "auth_failed"
                    }))
            
            return None  # 需要重试
        
        elif response.status_code == 403:
            # 权限不足或速率限制
            response_text = response.text.lower()
            async with self.lock:
                if 'rate limit' in response_text or 'api rate limit exceeded' in response_text or token.remaining == 0:
                    # 速率限制
                    reset_ts = int(reset_time) if reset_time else time.time() + self.rate_limit_backoff
                    token.cooldown_until = reset_ts + 1
                    
                    logger.warning(json.dumps({
                        "event": "rate_limit_hit",
                        "token_tail": token.get_masked_value(),
                        "reset_timestamp": reset_ts,
                        "reason": "403_rate_limit"
                    }))
                    
                    # 轮换到下一个token
                    logger.info(json.dumps({
                        "event": "rotate_token",
                        "token_tail": token.get_masked_value(),
                        "reason": "rate_limit"
                    }))
                else:
                    logger.warning(f"Token权限不足: {response.status_code} - {response.text[:100]}")
            
            return None  # 需要重试
        
        elif response.status_code == 429:
            # 明确的速率限制
            async with self.lock:
                reset_ts = int(reset_time) if reset_time else time.time() + self.rate_limit_backoff
                token.cooldown_until = reset_ts + 1
                
                logger.warning(json.dumps({
                    "event": "rate_limit_hit",
                    "token_tail": token.get_masked_value(),
                    "reset_timestamp": reset_ts,
                    "reason": "429_too_many_requests"
                }))
            
            return None  # 需要重试
        
        elif response.status_code >= 500:
            # 服务器错误
            async with self.lock:
                token.cooldown_until = time.time() + 30  # 30秒冷却
            
            logger.warning(json.dumps({
                "event": "server_error",
                "status_code": response.status_code,
                "token_tail": token.get_masked_value(),
                "cooldown_seconds": 30
            }))
            
            return None  # 需要重试
        
        else:
            # 其他客户端错误
            logger.error(f"未预期的响应状态: {response.status_code} - {response.text[:200]}")
            return None
    
    async def get_json(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        GET请求并返回JSON数据
        
        Args:
            path: API路径
            params: 查询参数
            
        Returns:
            Dict: JSON响应数据
            
        Raises:
            RuntimeError: 请求失败时
        """
        return await self._make_request_with_retries('GET', path, params)
    
    async def get(self, path: str, params: Optional[Dict] = None) -> httpx.Response:
        """
        GET请求并返回响应对象
        
        Args:
            path: API路径
            params: 查询参数
            
        Returns:
            httpx.Response: 原始响应对象
            
        Note:
            这个方法主要用于需要访问响应头或状态码的场景
            对于大多数情况，建议使用 get_json() 方法
        """
        # 获取token并发起请求
        token = await self.acquire_token()
        
        # 请求间延迟
        await asyncio.sleep(self.per_request_sleep)
        
        # 设置请求头
        headers = {
            'Authorization': f'token {token.value}',
            'User-Agent': 'SpidermindBot',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # 发起请求
        response = await self.client.request(
            method='GET',
            url=path,
            params=params,
            headers=headers
        )
        
        # 更新token状态（不包含错误处理，因为调用方可能需要处理特定状态码）
        async with self.lock:
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining:
                token.remaining = int(remaining)
            
            reset_time = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                token.reset_time = reset_time
        
        return response
    
    async def close(self):
        """关闭HTTP客户端"""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
    
    def get_token_status(self) -> Dict[str, Any]:
        """
        获取当前token状态统计
        
        Returns:
            Dict: token状态统计信息
        """
        total = len(self.token_queue)
        available = sum(1 for token in self.token_queue if token.is_available())
        disabled = sum(1 for token in self.token_queue if token.disabled)
        cooling = sum(1 for token in self.token_queue if token.cooldown_until and token.cooldown_until > time.time())
        
        return {
            "total": total,
            "available": available,
            "disabled": disabled,
            "cooling": cooling,
            "config": {
                "api_base": self.api_base,
                "per_request_sleep": self.per_request_sleep,
                "rate_limit_backoff": self.rate_limit_backoff,
                "max_retries": self.max_retries
            }
        }


# 传统兼容API类（保持向后兼容）
class GitHubAPIClient:
    """GitHub API客户端 - 兼容旧版本API"""
    
    def __init__(self, tokens_config_path: str = "config/tokens.github.json"):
        """
        初始化兼容版本的GitHub客户端
        
        Args:
            tokens_config_path: 已废弃，保持兼容性
        """
        logger.warning("GitHubAPIClient已废弃，请使用新的GitHubClient")
        self._client = GitHubClient()
    
    async def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """获取用户基本信息"""
        try:
            return await self._client.get_json(f"/users/{username}")
        except Exception as e:
            logger.error(f"获取用户信息失败: {username}, 错误: {e}")
            return None
    
    async def get_user_repos(self, username: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """获取用户仓库列表"""
        try:
            return await self._client.get_json(f"/users/{username}/repos", {
                "per_page": per_page,
                "sort": "updated"
            })
        except Exception as e:
            logger.error(f"获取用户仓库失败: {username}, 错误: {e}")
            return []
    
    async def close(self):
        """关闭客户端"""
        await self._client.close()


# 全局实例
github_client = GitHubClient()