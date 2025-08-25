"""
进度统计服务 - 轻量级实现
按蓝图要求提供本轮进度统计

Author: Spidermind
"""
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ProgressTracker:
    """轻量级进度跟踪器"""
    
    def __init__(self):
        # 内存中保存当前轮次的统计 {source: {processed, success, fail, skip, start_time}}
        self._current_round: Dict[str, Dict[str, Any]] = {}
    
    def start_round(self, source: str) -> None:
        """
        开始新一轮处理，自动清零之前的统计
        
        Args:
            source: 爬虫来源 (github/openreview/homepage)
        """
        self._current_round[source] = {
            'processed': 0,
            'success': 0,
            'fail': 0,
            'skip': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
        logger.info(f"开始新一轮 {source} 处理")
    
    def inc_processed(self, source: str) -> None:
        """增加处理总数"""
        if source in self._current_round:
            self._current_round[source]['processed'] += 1
    
    def inc_success(self, source: str) -> None:
        """增加成功数"""
        if source in self._current_round:
            self._current_round[source]['success'] += 1
    
    def inc_fail(self, source: str) -> None:
        """增加失败数"""
        if source in self._current_round:
            self._current_round[source]['fail'] += 1
    
    def inc_skip(self, source: str) -> None:
        """增加跳过数"""
        if source in self._current_round:
            self._current_round[source]['skip'] += 1
    
    def end_round(self, source: str) -> None:
        """结束本轮处理"""
        if source in self._current_round:
            self._current_round[source]['end_time'] = datetime.now()
            stats = self._current_round[source]
            duration = (stats['end_time'] - stats['start_time']).total_seconds()
            logger.info(f"完成 {source} 处理: processed={stats['processed']}, "
                       f"success={stats['success']}, fail={stats['fail']}, "
                       f"skip={stats['skip']}, duration={duration:.1f}s")
    
    def get_round_stats(self, source: str) -> Dict[str, Any]:
        """
        获取本轮统计数据
        
        Args:
            source: 爬虫来源
            
        Returns:
            Dict: 包含 processed/success/fail/skip 的统计数据
        """
        if source not in self._current_round:
            return {
                'processed': 0,
                'success': 0,
                'fail': 0,
                'skip': 0,
                'start_time': None,
                'end_time': None,
                'running': False
            }
        
        stats = self._current_round[source].copy()
        stats['running'] = stats['end_time'] is None
        
        # 计算成功率
        if stats['processed'] > 0:
            stats['success_rate'] = round(stats['success'] / stats['processed'] * 100, 1)
        else:
            stats['success_rate'] = 0.0
        
        return stats


# 全局单例
progress_tracker = ProgressTracker()