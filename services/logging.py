"""
统一 JSON 日志服务

提供统一的日志格式和 trace 跟踪功能
Author: Spidermind
"""
import json
import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4


class TraceFormatter(logging.Formatter):
    """支持 trace_id 的 JSON 日志格式化器"""
    
    def format(self, record):
        # 构建基础日志数据
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # 添加 trace_id（如果存在）
        if hasattr(record, 'trace_id') and record.trace_id:
            log_data['trace_id'] = record.trace_id
        
        # 添加额外的上下文数据
        if hasattr(record, 'extra_data') and record.extra_data:
            log_data['extra'] = record.extra_data
        
        # 添加异常信息（如果存在）
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class TraceLoggerAdapter(logging.LoggerAdapter):
    """支持 trace_id 的日志适配器"""
    
    def __init__(self, logger, trace_id: Optional[str] = None):
        super().__init__(logger, {})
        self.trace_id = trace_id
    
    def process(self, msg, kwargs):
        # 将 trace_id 添加到日志记录中
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        
        kwargs['extra']['trace_id'] = self.trace_id
        
        # 处理额外的数据
        if 'extra_data' in kwargs:
            kwargs['extra']['extra_data'] = kwargs.pop('extra_data')
        
        return msg, kwargs
    
    def with_extra(self, **extra_data):
        """添加额外的上下文数据到日志中"""
        def log_with_extra(level, msg, *args, **kwargs):
            if 'extra_data' not in kwargs:
                kwargs['extra_data'] = {}
            kwargs['extra_data'].update(extra_data)
            getattr(self, level)(msg, *args, **kwargs)
        return log_with_extra


def setup_json_logging():
    """设置 JSON 格式的日志输出"""
    # 获取根日志器
    root_logger = logging.getLogger()
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(TraceFormatter())
    
    # 设置日志级别
    root_logger.setLevel(logging.INFO)
    console_handler.setLevel(logging.INFO)
    
    # 添加处理器
    root_logger.addHandler(console_handler)


def get_logger(name: str, trace_id: Optional[str] = None) -> TraceLoggerAdapter:
    """
    获取支持 trace_id 的日志器
    
    Args:
        name: 日志器名称
        trace_id: 跟踪ID
    
    Returns:
        TraceLoggerAdapter: 支持 trace 的日志器
    """
    logger = logging.getLogger(name)
    return TraceLoggerAdapter(logger, trace_id)


def generate_trace_id() -> str:
    """生成新的 trace ID"""
    return str(uuid4())


def create_structured_log(
    level: str,
    message: str,
    trace_id: Optional[str] = None,
    source: Optional[str] = None,
    operation: Optional[str] = None,
    **extra_data
) -> Dict[str, Any]:
    """
    创建结构化日志数据
    
    Args:
        level: 日志级别
        message: 日志消息
        trace_id: 跟踪ID
        source: 来源
        operation: 操作类型
        **extra_data: 额外数据
    
    Returns:
        Dict: 结构化日志数据
    """
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'level': level.upper(),
        'message': message
    }
    
    if trace_id:
        log_data['trace_id'] = trace_id
    
    if source:
        log_data['source'] = source
    
    if operation:
        log_data['operation'] = operation
    
    if extra_data:
        log_data['extra'] = extra_data
    
    return log_data


# 初始化 JSON 日志格式（在模块导入时执行）
setup_json_logging()