"""
README 获取模块
负责从 GitHub 仓库页面提取 README 内容
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .states import SUCCESS_FOUND, SUCCESS_NONE, FAIL_NO_README, FAIL_FETCH, classify_exception
from .targets import Target


logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """README 获取结果"""
    status: str                    # 内部状态 (SUCCESS_*, FAIL_*, SKIP_*)
    readme_content: str           # README 内容 (markdown 或 HTML)
    readme_url: str              # README 来源 URL
    content_type: str            # 内容类型: 'markdown' | 'html' | 'text'
    message: str                 # 状态消息
    meta: Dict[str, Any]         # 元数据


def fetch_readme(target: Target, session: requests.Session, args: Dict[str, Any]) -> FetchResult:
    """
    获取目标仓库的 README 内容
    
    Args:
        target: 目标仓库信息
        session: HTTP 会话对象
        args: 命令行参数字典
        
    Returns:
        FetchResult: 获取结果
    """
    timeout = args.get('timeout', 10)
    use_selenium = args.get('use_selenium', False)
    
    logger.debug(f"开始获取 README: {target.repo_full_name}")
    
    try:
        # 方法1: HTML 优先 - 从仓库主页提取 README
        result = _fetch_readme_from_repo_page(target, session, timeout)
        
        if result.status in [SUCCESS_FOUND, SUCCESS_NONE]:
            return result
        
        # 方法2: 如果启用 Selenium 且 HTML 方法失败，尝试 Selenium
        if use_selenium and result.status == FAIL_NO_README:
            logger.debug(f"HTML 方法失败，尝试 Selenium: {target.repo_full_name}")
            selenium_result = _fetch_readme_with_selenium(target, timeout)
            if selenium_result.status == SUCCESS_FOUND:
                return selenium_result
        
        return result
        
    except Exception as e:
        internal_status, message = classify_exception(e)
        logger.error(f"获取 README 异常 {target.repo_full_name}: {e}")
        
        return FetchResult(
            status=internal_status,
            readme_content="",
            readme_url=target.repo_url,
            content_type="",
            message=message,
            meta={'error': str(e)}
        )


def _fetch_readme_from_repo_page(target: Target, session: requests.Session, timeout: int) -> FetchResult:
    """
    从 GitHub 仓库页面提取 README 内容
    """
    repo_url = target.repo_url
    
    try:
        logger.debug(f"请求仓库页面: {repo_url}")
        response = session.get(repo_url, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 查找 README 容器的多种可能选择器
        readme_selectors = [
            # 标准 README 容器
            'div[data-target="readme-toc.content"]',
            'div#readme',
            'article.markdown-body',
            # Profile 仓库特殊容器
            'div.repository-content div.Box-body',
            'div.js-readme-container',
            # 更通用的选择器
            'div.markdown-body',
            '.readme .markdown-body',
            '[data-testid="readme"]'
        ]
        
        readme_element = None
        used_selector = ""
        
        for selector in readme_selectors:
            readme_element = soup.select_one(selector)
            if readme_element:
                used_selector = selector
                logger.debug(f"找到 README 元素，选择器: {selector}")
                break
        
        if not readme_element:
            # 尝试通过 README 标题查找
            readme_element = _find_readme_by_heading(soup)
            if readme_element:
                used_selector = "heading-based"
        
        if not readme_element:
            logger.debug(f"未找到 README 内容: {repo_url}")
            return FetchResult(
                status=FAIL_NO_README,
                readme_content="",
                readme_url=repo_url,
                content_type="",
                message="no_readme",
                meta={'selectors_tried': readme_selectors}
            )
        
        # 提取 README 内容
        readme_content = _extract_readme_content(readme_element)
        
        if not readme_content or len(readme_content.strip()) < 10:
            logger.debug(f"README 内容为空或过短: {repo_url}")
            return FetchResult(
                status=FAIL_NO_README,
                readme_content="",
                readme_url=repo_url,
                content_type="",
                message="empty_readme",
                meta={'selector_used': used_selector}
            )
        
        # 检测内容类型
        content_type = _detect_content_type(readme_element, readme_content)
        
        logger.info(f"成功获取 README: {repo_url}, 长度: {len(readme_content)}")
        
        return FetchResult(
            status=SUCCESS_FOUND,
            readme_content=readme_content,
            readme_url=repo_url,
            content_type=content_type,
            message="readme_found",
            meta={
                'selector_used': used_selector,
                'content_length': len(readme_content),
                'response_size': len(response.text)
            }
        )
        
    except requests.exceptions.RequestException as e:
        internal_status, message = classify_exception(e)
        return FetchResult(
            status=internal_status,
            readme_content="",
            readme_url=repo_url,
            content_type="",
            message=message,
            meta={'error': str(e)}
        )


def _find_readme_by_heading(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """
    通过 README 标题查找内容区域
    """
    # 查找包含 "README" 的标题
    readme_headings = soup.find_all(['h1', 'h2', 'h3'], string=re.compile(r'README', re.IGNORECASE))
    
    for heading in readme_headings:
        # 查找标题后的内容容器
        container = heading.find_parent(['div', 'section', 'article'])
        if container:
            content_div = container.find('div', class_=re.compile(r'markdown|content'))
            if content_div:
                return content_div
    
    return None


def _extract_readme_content(element: BeautifulSoup) -> str:
    """
    从 README 元素中提取文本内容
    """
    # 移除不需要的元素
    for tag in element.find_all(['script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    
    # 提取文本，保持一定的结构
    content_parts = []
    
    for child in element.descendants:
        if child.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = child.get_text().strip()
            if text:
                content_parts.append(f"\n\n# {text}\n")
        elif child.name == 'p':
            text = child.get_text().strip()
            if text:
                content_parts.append(f"{text}\n")
        elif child.name in ['li']:
            text = child.get_text().strip()
            if text:
                content_parts.append(f"- {text}\n")
        elif child.name in ['code', 'pre']:
            text = child.get_text().strip()
            if text:
                content_parts.append(f"`{text}`")
        elif child.name == 'a':
            text = child.get_text().strip()
            href = child.get('href', '')
            if text and href:
                content_parts.append(f"[{text}]({href})")
    
    # 如果结构化提取失败，使用简单文本提取
    if not content_parts:
        content = element.get_text(separator=' ', strip=True)
    else:
        content = ''.join(content_parts)
    
    # 清理空行和多余空格
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = re.sub(r'[ \t]+', ' ', content)
    
    return content.strip()


def _detect_content_type(element: BeautifulSoup, content: str) -> str:
    """
    检测内容类型
    """
    # 检查是否包含 HTML 标记
    if element.find(['p', 'div', 'h1', 'h2', 'h3', 'ul', 'ol', 'li']):
        return 'html'
    
    # 检查是否为 Markdown 格式
    if re.search(r'[#*`\[\]()]', content):
        return 'markdown'
    
    return 'text'


def _fetch_readme_with_selenium(target: Target, timeout: int) -> FetchResult:
    """
    使用 Selenium 获取 README (备用方案)
    
    注意: 这是一个 TODO 实现，需要安装 selenium 和对应的 webdriver
    """
    try:
        # TODO: 实现 Selenium 获取逻辑
        # 这里需要:
        # 1. 检查 selenium 是否可用
        # 2. 配置 webdriver (headless Chrome/Firefox)
        # 3. 访问页面并等待 README 加载
        # 4. 提取内容
        
        logger.warning("Selenium 支持尚未实现，跳过")
        
        return FetchResult(
            status=FAIL_NO_README,
            readme_content="",
            readme_url=target.repo_url,
            content_type="",
            message="selenium_not_implemented",
            meta={'selenium_attempted': True}
        )
        
    except ImportError:
        logger.warning("Selenium 未安装，跳过浏览器渲染")
        return FetchResult(
            status=FAIL_NO_README,
            readme_content="",
            readme_url=target.repo_url,
            content_type="",
            message="selenium_not_available",
            meta={'selenium_error': 'not_installed'}
        )
    except Exception as e:
        logger.error(f"Selenium 获取失败: {e}")
        internal_status, message = classify_exception(e)
        return FetchResult(
            status=internal_status,
            readme_content="",
            readme_url=target.repo_url,
            content_type="",
            message=f"selenium_error: {message}",
            meta={'selenium_error': str(e)}
        )


def validate_readme_content(content: str) -> bool:
    """
    验证 README 内容的有效性
    
    Args:
        content: README 内容
        
    Returns:
        bool: 是否为有效内容
    """
    if not content or not content.strip():
        return False
    
    # 内容长度检查
    if len(content.strip()) < 10:
        return False
    
    # 检查是否只包含无意义内容
    meaningless_patterns = [
        r'^[\s\n\r]*$',                    # 只有空白字符
        r'^[\s\n\r]*#[\s\n\r]*$',         # 只有井号
        r'^[\s\n\r]*-+[\s\n\r]*$',        # 只有横线
        r'^[\s\n\r]*\.+[\s\n\r]*$',       # 只有点号
    ]
    
    for pattern in meaningless_patterns:
        if re.match(pattern, content):
            return False
    
    return True