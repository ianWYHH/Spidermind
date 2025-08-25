#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright兜底抓取器

处理JavaScript重度页面的内容提取
Author: Spidermind
"""

import logging
import asyncio
import trafilatura
from typing import Dict, Any, Optional

# 可选依赖检查
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    raise RuntimeError("Playwright not installed. Install with: pip install playwright && playwright install")

logger = logging.getLogger(__name__)


class PlaywrightFetcher:
    """Playwright兜底抓取器"""
    
    def __init__(self):
        """初始化Playwright抓取器"""
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.timeout = 30000  # 30秒
        self.wait_after_load = 2000  # 页面加载后等待2秒
        self.viewport_size = {"width": 1280, "height": 720}
        self._playwright = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self._close_browser()
    
    async def _start_browser(self):
        """启动浏览器"""
        try:
            self._playwright = await async_playwright().start()
            
            # 启动Chromium浏览器
            self.browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport=self.viewport_size,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            
            logger.debug("Playwright browser started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Playwright browser: {e}")
            raise
    
    async def _close_browser(self):
        """关闭浏览器"""
        try:
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            logger.debug("Playwright browser closed successfully")
            
        except Exception as e:
            logger.warning(f"Error closing Playwright browser: {e}")
    
    async def fetch_content(self, url: str) -> Dict[str, Any]:
        """
        使用Playwright抓取页面内容
        
        Args:
            url: 目标URL
            
        Returns:
            Dict: 包含HTML、提取的正文、元数据等信息
        """
        result = {
            'success': False,
            'url': url,
            'html': '',
            'text': '',
            'title': '',
            'author': '',
            'date': '',
            'language': '',
            'error': '',
            'status_code': None,
            'content_length': 0,
            'is_redirect': False,
            'final_url': url,
            'javascript_executed': True  # 标识使用了JavaScript渲染
        }
        
        if not self.browser or not self.context:
            result['error'] = 'Browser not initialized'
            return result
        
        page: Optional[Page] = None
        
        try:
            # 创建新页面
            page = await self.context.new_page()
            
            # 设置页面事件监听
            await self._setup_page_handlers(page)
            
            # 导航到目标URL
            response = await page.goto(
                url,
                wait_until='domcontentloaded',
                timeout=self.timeout
            )
            
            if response:
                result['status_code'] = response.status
                result['final_url'] = response.url
                result['is_redirect'] = response.url != url
            
            # 等待页面完全加载
            await page.wait_for_timeout(self.wait_after_load)
            
            # 等待网络空闲（可选）
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except:
                # 如果等待网络空闲超时，继续执行
                pass
            
            # 获取页面HTML
            html_content = await page.content()
            result['html'] = html_content
            result['content_length'] = len(html_content)
            
            # 获取页面标题
            title = await page.title()
            result['title'] = title
            
            # 使用trafilatura提取正文
            extracted_data = self._extract_content_with_trafilatura(html_content, url)
            result.update(extracted_data)
            
            # 如果trafilatura提取失败，尝试其他方法
            if not result['text'] or len(result['text'].strip()) < 100:
                fallback_text = await self._extract_text_fallback(page)
                if fallback_text and len(fallback_text) > len(result['text']):
                    result['text'] = fallback_text
            
            # 判断提取是否成功
            if result['text'] and len(result['text'].strip()) > 0:
                result['success'] = True
            else:
                result['error'] = 'No content extracted from rendered page'
            
            logger.debug(f"Playwright extracted {len(result['text'])} characters from {url}")
            
        except Exception as e:
            logger.error(f"Error fetching content with Playwright from {url}: {e}")
            result['error'] = str(e)
        
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass
        
        return result
    
    async def _setup_page_handlers(self, page: Page):
        """设置页面事件处理器"""
        
        # 拦截不必要的资源请求以提高性能
        async def handle_route(route):
            resource_type = route.request.resource_type
            if resource_type in ['image', 'media', 'font', 'stylesheet']:
                await route.abort()
            else:
                await route.continue_()
        
        await page.route('**/*', handle_route)
        
        # 处理页面错误
        page.on('pageerror', lambda error: logger.warning(f"Page error: {error}"))
        
        # 处理控制台消息（可选，用于调试）
        # page.on('console', lambda msg: logger.debug(f"Console: {msg.text}"))
    
    def _extract_content_with_trafilatura(self, html: str, url: str) -> Dict[str, Any]:
        """
        使用trafilatura提取正文内容
        
        Args:
            html: 渲染后的HTML
            url: 原始URL
            
        Returns:
            Dict: 提取的内容和元数据
        """
        extracted = {
            'text': '',
            'author': '',
            'date': '',
            'language': ''
        }
        
        try:
            # 使用trafilatura提取正文
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_formatting=False,
                favor_precision=True
            )
            
            if text:
                extracted['text'] = text.strip()
            
            # 提取元数据
            metadata = trafilatura.extract_metadata(html, fast=True)
            if metadata:
                extracted['author'] = metadata.author or ''
                extracted['date'] = metadata.date or ''
                extracted['language'] = metadata.language or ''
            
        except Exception as e:
            logger.warning(f"Error extracting content with trafilatura: {e}")
        
        return extracted
    
    async def _extract_text_fallback(self, page: Page) -> str:
        """
        备用文本提取方法
        
        Args:
            page: Playwright页面对象
            
        Returns:
            str: 提取的文本内容
        """
        try:
            # 移除不需要的元素
            await page.evaluate("""
                () => {
                    const elementsToRemove = ['script', 'style', 'nav', 'header', 'footer', '.sidebar', '.menu'];
                    elementsToRemove.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => el.remove());
                    });
                }
            """)
            
            # 获取主要内容区域的文本
            text_selectors = [
                'main', 'article', '.content', '.main-content',
                '.post-content', '.entry-content', 'body'
            ]
            
            for selector in text_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.inner_text()
                        if text and len(text.strip()) > 100:
                            return text.strip()
                except:
                    continue
            
            # 如果以上都失败，获取body的文本
            body_text = await page.evaluate('document.body.innerText')
            return body_text.strip() if body_text else ''
            
        except Exception as e:
            logger.warning(f"Error in fallback text extraction: {e}")
            return ''


class PlaywrightManager:
    """Playwright管理器，支持同步接口"""
    
    def __init__(self):
        self.fetcher = None
    
    def fetch_content_sync(self, url: str) -> Dict[str, Any]:
        """
        同步方式抓取内容
        
        Args:
            url: 目标URL
            
        Returns:
            Dict: 抓取结果
        """
        return asyncio.run(self._async_fetch_content(url))
    
    async def _async_fetch_content(self, url: str) -> Dict[str, Any]:
        """异步抓取内容的实现"""
        async with PlaywrightFetcher() as fetcher:
            return await fetcher.fetch_content(url)


# 全局实例
playwright_manager = PlaywrightManager()