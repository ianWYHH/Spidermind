"""
纯文本抽取模块（原文入库模式）
从 README 内容中提取纯文本用于原文入库
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set
from bs4 import BeautifulSoup

from .states import SUCCESS_FOUND, SUCCESS_NONE, FAIL_PARSE, classify_exception
from .readme_fetch import FetchResult


logger = logging.getLogger(__name__)


@dataclass
class ContactFinding:
    """联系方式发现项（向后兼容）"""
    type: str                    # 联系方式类型
    value: str                   # 原始值
    normalized_value: str        # 规范化值
    context: str                 # 上下文信息
    confidence: float            # 置信度 (0-1)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractResult:
    """抽取结果（原文入库模式）"""
    status: str                         # 内部状态
    plain_text: str                     # 提取的纯文本
    message: str                        # 状态消息
    profile_info: Dict[str, Any] = field(default_factory=dict)  # 基础档案信息
    # 向后兼容字段
    findings: List[ContactFinding] = field(default_factory=list)  # 空列表（兼容）
    kind_summary: Set[str] = field(default_factory=set)          # 空集合（兼容）
    raw_content: str = ""                                        # 与plain_text相同（兼容）
    meta: Dict[str, Any] = field(default_factory=dict)


def extract_plain_text(fetch_result: FetchResult, args: Dict[str, Any] = None) -> ExtractResult:
    """
    从 README 内容中提取纯文本（原文入库模式）
    
    Args:
        fetch_result: README 获取结果
        args: 命令行参数（可选）
        
    Returns:
        ExtractResult: 抽取结果，包含纯文本
    """
    if fetch_result.status != SUCCESS_FOUND:
        return ExtractResult(
            status=fetch_result.status,
            plain_text="",
            message=fetch_result.message
        )
    
    content = fetch_result.readme_content
    if not content or not content.strip():
        return ExtractResult(
            status=SUCCESS_NONE,
            plain_text="",
            message="empty content"
        )
    
    logger.debug(f"开始抽取纯文本，内容长度: {len(content)}")
    
    try:
        # 提取纯文本：移除script/style标签，保留正文内容
        plain_text = _extract_clean_text(content)
        
        if plain_text and plain_text.strip():
            status = SUCCESS_FOUND
            message = "raw_saved"
            logger.info(f"纯文本抽取完成，长度: {len(plain_text)}")
        else:
            status = SUCCESS_NONE
            message = "no_content"
            logger.info("内容为空或无法提取纯文本")
        
        result = ExtractResult(
            status=status,
            plain_text=plain_text,
            message=message
        )
        
        # 设置向后兼容字段
        result.raw_content = plain_text
        
        return result
        
    except Exception as e:
        logger.error(f"纯文本抽取失败: {e}")
        internal_status = classify_exception(e)
        return ExtractResult(
            status=internal_status,
            plain_text="",
            message=f"parse_error: {e}"
        )


def _extract_clean_text(html_content: str) -> str:
    """
    从HTML内容中提取干净的纯文本
    
    Args:
        html_content: HTML内容
        
    Returns:
        str: 清理后的纯文本
    """
    try:
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # 移除script和style标签
        for script in soup(["script", "style"]):
            script.decompose()
        
        # 提取文本
        text = soup.get_text()
        
        # 清理文本：移除多余空白，保留基本格式
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
        
    except Exception as e:
        logger.warning(f"HTML解析失败，返回原始内容: {e}")
        # 如果解析失败，返回原始内容
        return html_content


# 保持向后兼容：主要接口函数
def extract_contacts(fetch_result: FetchResult, args: Dict[str, Any]) -> ExtractResult:
    """
    联系方式提取函数（向后兼容）
    在原文入库模式下，实际调用extract_plain_text
    
    Args:
        fetch_result: README 获取结果
        args: 命令行参数
        
    Returns:
        ExtractResult: 抽取结果（包含纯文本，联系方式字段为空）
    """
    logger.debug("原文入库模式：调用extract_plain_text替代联系方式提取")
    return extract_plain_text(fetch_result, args)