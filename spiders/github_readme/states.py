"""
内部细分状态定义与映射助手
用于将内部详细状态映射到 crawl_logs.status 的三值枚举
"""

# 内部细分状态常量
SUCCESS_FOUND = "SUCCESS_FOUND"      # 找到联系方式
SUCCESS_NONE = "SUCCESS_NONE"        # 成功处理但无联系方式
FAIL_NO_README = "FAIL_NO_README"    # 仓库无README或为空
FAIL_FETCH = "FAIL_FETCH"            # 网络请求失败
FAIL_PARSE = "FAIL_PARSE"            # 解析异常
SKIP_DUP = "SKIP_DUP"                # 跳过重复内容
ABORT = "ABORT"                      # 用户中断或信号停止

# 所有有效的内部状态
ALL_INTERNAL_STATES = {
    SUCCESS_FOUND, SUCCESS_NONE, FAIL_NO_README, 
    FAIL_FETCH, FAIL_PARSE, SKIP_DUP, ABORT
}


def map_to_crawl_logs(internal_status: str) -> str:
    """
    将内部细分状态映射到 crawl_logs.status 的三值枚举
    
    Args:
        internal_status: 内部状态常量
        
    Returns:
        str: 'success' | 'fail' | 'skip'
        
    Raises:
        ValueError: 当传入未知的内部状态时
    """
    mapping = {
        SUCCESS_FOUND: "success",     # 找到联系方式 → 成功
        SUCCESS_NONE: "success",      # 无联系方式但处理成功 → 成功
        FAIL_NO_README: "fail",       # 无README → 失败
        FAIL_FETCH: "fail",           # 获取失败 → 失败
        FAIL_PARSE: "fail",           # 解析失败 → 失败
        SKIP_DUP: "skip",             # 重复跳过 → 跳过
        ABORT: "fail",                # 中断 → 失败
    }
    
    if internal_status not in mapping:
        raise ValueError(f"未知的内部状态: {internal_status}")
    
    return mapping[internal_status]


def classify_exception(exception: Exception) -> tuple[str, str]:
    """
    根据异常类型分类为内部状态
    
    Args:
        exception: 捕获的异常对象
        
    Returns:
        tuple: (internal_status, message)
    """
    import requests
    from requests.exceptions import RequestException
    
    if isinstance(exception, requests.exceptions.Timeout):
        return FAIL_FETCH, f"timeout: {str(exception)}"
    
    elif isinstance(exception, requests.exceptions.ConnectionError):
        return FAIL_FETCH, f"connection_error: {str(exception)}"
    
    elif isinstance(exception, requests.exceptions.HTTPError):
        return FAIL_FETCH, f"http_error: {str(exception)}"
    
    elif isinstance(exception, (requests.exceptions.RequestException, RequestException)):
        return FAIL_FETCH, f"request_error: {str(exception)}"
    
    elif isinstance(exception, (ValueError, TypeError, AttributeError)):
        return FAIL_PARSE, f"parse_error: {str(exception)}"
    
    elif isinstance(exception, KeyboardInterrupt):
        return ABORT, "abort by signal"
    
    else:
        # 其他未分类异常默认为解析错误
        return FAIL_PARSE, f"unknown_error: {type(exception).__name__}: {str(exception)}"


def get_status_message(internal_status: str, details: dict = None) -> str:
    """
    根据内部状态生成标准化的 message
    
    Args:
        internal_status: 内部状态
        details: 可选的详细信息字典
        
    Returns:
        str: 标准化的消息文本
    """
    details = details or {}
    
    if internal_status == SUCCESS_FOUND:
        found_count = details.get('found_count', 0)
        found_types = details.get('found_types', [])
        if found_types:
            types_str = ','.join(sorted(found_types))
            return f"found {found_count} contacts: {types_str}"
        else:
            return f"found {found_count} contacts"
    
    elif internal_status == SUCCESS_NONE:
        return "none"
    
    elif internal_status == FAIL_NO_README:
        return "no_readme"
    
    elif internal_status == FAIL_FETCH:
        return details.get('error', 'fetch_failed')
    
    elif internal_status == FAIL_PARSE:
        return details.get('error', 'parse_failed')
    
    elif internal_status == SKIP_DUP:
        return details.get('reason', 'dup')
    
    elif internal_status == ABORT:
        return "abort by signal"
    
    else:
        return f"unknown_status: {internal_status}"


def is_failure_status(internal_status: str) -> bool:
    """判断是否为失败状态"""
    return internal_status in {FAIL_NO_README, FAIL_FETCH, FAIL_PARSE, ABORT}


def is_success_status(internal_status: str) -> bool:
    """判断是否为成功状态"""
    return internal_status in {SUCCESS_FOUND, SUCCESS_NONE}


def is_skip_status(internal_status: str) -> bool:
    """判断是否为跳过状态"""
    return internal_status == SKIP_DUP