"""
进度统计服务

内存态统计器，用于跟踪爬虫任务处理进度
Author: Spidermind
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from threading import Lock


class ProgressTracker:
    """进度跟踪器 - 单例模式"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # 统计数据存储: {source: {type: {batch_id: stats}}}
        self._stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
        
        # 当前运行状态: {source: {type: batch_id}}
        self._running: Dict[str, Dict[str, Optional[str]]] = {}
        
        # 数据访问锁
        self._data_lock = Lock()
        
        self._initialized = True
    
    def start_batch(self, source: str, task_type: str, batch_id: str = None) -> str:
        """
        开始一个新的处理批次
        
        Args:
            source: 爬虫来源 (github/openreview/homepage)
            task_type: 任务类型 (profile/repo/follow_scan/homepage)
            batch_id: 批次ID，如果为空则自动生成
        
        Returns:
            str: 批次ID
        """
        if batch_id is None:
            batch_id = f"{source}_{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        with self._data_lock:
            # 初始化数据结构
            if source not in self._stats:
                self._stats[source] = {}
                self._running[source] = {}
            
            if task_type not in self._stats[source]:
                self._stats[source][task_type] = {}
                self._running[source][task_type] = None
            
            # 设置当前运行状态
            self._running[source][task_type] = batch_id
            
            # 初始化批次统计
            self._stats[source][task_type][batch_id] = {
                "batch_id": batch_id,
                "source": source,
                "task_type": task_type,
                "status": "running",
                "start_time": datetime.now(),
                "end_time": None,
                "total_processed": 0,
                "success_count": 0,
                "fail_count": 0,
                "skip_count": 0,
                "error_details": []
            }
        
        return batch_id
    
    def finish_batch(self, source: str, task_type: str, batch_id: str = None):
        """
        结束处理批次
        
        Args:
            source: 爬虫来源
            task_type: 任务类型
            batch_id: 批次ID，如果为空则使用当前运行的批次
        """
        with self._data_lock:
            if source not in self._stats or task_type not in self._stats[source]:
                return
            
            # 如果未指定batch_id，使用当前运行的批次
            if batch_id is None:
                batch_id = self._running[source].get(task_type)
            
            if batch_id and batch_id in self._stats[source][task_type]:
                self._stats[source][task_type][batch_id]["status"] = "completed"
                self._stats[source][task_type][batch_id]["end_time"] = datetime.now()
                
                # 清除运行状态
                self._running[source][task_type] = None
    
    def record_success(self, source: str, task_type: str, batch_id: str = None):
        """记录成功处理"""
        self._record_result(source, task_type, "success", batch_id)
    
    def record_failure(self, source: str, task_type: str, error_msg: str = None, batch_id: str = None):
        """记录失败处理"""
        self._record_result(source, task_type, "fail", batch_id, error_msg)
    
    def record_skip(self, source: str, task_type: str, reason: str = None, batch_id: str = None):
        """记录跳过处理"""
        self._record_result(source, task_type, "skip", batch_id, reason)
    
    def _record_result(self, source: str, task_type: str, result_type: str, batch_id: str = None, message: str = None):
        """
        记录处理结果
        
        Args:
            source: 爬虫来源
            task_type: 任务类型
            result_type: 结果类型 (success/fail/skip)
            batch_id: 批次ID
            message: 错误或跳过原因
        """
        with self._data_lock:
            if source not in self._stats or task_type not in self._stats[source]:
                return
            
            # 如果未指定batch_id，使用当前运行的批次
            if batch_id is None:
                batch_id = self._running[source].get(task_type)
            
            if not batch_id or batch_id not in self._stats[source][task_type]:
                return
            
            stats = self._stats[source][task_type][batch_id]
            
            # 更新计数
            stats["total_processed"] += 1
            
            if result_type == "success":
                stats["success_count"] += 1
            elif result_type == "fail":
                stats["fail_count"] += 1
                if message:
                    stats["error_details"].append({
                        "timestamp": datetime.now(),
                        "error": message
                    })
            elif result_type == "skip":
                stats["skip_count"] += 1
                if message:
                    stats["error_details"].append({
                        "timestamp": datetime.now(),
                        "reason": message
                    })
    
    def get_current_stats(self, source: str, task_type: str) -> Optional[Dict[str, Any]]:
        """
        获取当前运行批次的统计信息
        
        Args:
            source: 爬虫来源
            task_type: 任务类型
        
        Returns:
            Dict: 统计信息，如果没有运行中的批次则返回None
        """
        with self._data_lock:
            if source not in self._running or task_type not in self._running[source]:
                return None
            
            batch_id = self._running[source][task_type]
            if not batch_id:
                return None
            
            if (source in self._stats and 
                task_type in self._stats[source] and 
                batch_id in self._stats[source][task_type]):
                
                stats = self._stats[source][task_type][batch_id].copy()
                
                # 计算额外的统计信息
                if stats["total_processed"] > 0:
                    stats["success_rate"] = (stats["success_count"] / stats["total_processed"]) * 100
                else:
                    stats["success_rate"] = 0
                
                # 计算运行时间
                if stats["start_time"]:
                    end_time = stats["end_time"] or datetime.now()
                    duration = end_time - stats["start_time"]
                    stats["duration_seconds"] = duration.total_seconds()
                    stats["duration_str"] = str(duration).split('.')[0]  # 去掉微秒
                
                return stats
            
            return None
    
    def get_batch_history(self, source: str, task_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取批次历史记录
        
        Args:
            source: 爬虫来源
            task_type: 任务类型
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 批次历史列表，按开始时间倒序
        """
        with self._data_lock:
            if (source not in self._stats or 
                task_type not in self._stats[source]):
                return []
            
            # 获取所有批次
            batches = list(self._stats[source][task_type].values())
            
            # 按开始时间倒序排序
            batches.sort(key=lambda x: x["start_time"], reverse=True)
            
            # 限制返回数量
            result = batches[:limit]
            
            # 为每个批次计算额外统计信息
            for stats in result:
                if stats["total_processed"] > 0:
                    stats["success_rate"] = (stats["success_count"] / stats["total_processed"]) * 100
                else:
                    stats["success_rate"] = 0
                
                if stats["start_time"]:
                    end_time = stats["end_time"] or datetime.now()
                    duration = end_time - stats["start_time"]
                    stats["duration_seconds"] = duration.total_seconds()
                    stats["duration_str"] = str(duration).split('.')[0]
            
            return result
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """
        获取全局统计信息
        
        Returns:
            Dict: 包含所有来源和类型的统计摘要
        """
        with self._data_lock:
            overall = {
                "total_batches": 0,
                "running_batches": 0,
                "total_processed": 0,
                "total_success": 0,
                "total_fail": 0,
                "total_skip": 0,
                "by_source": {}
            }
            
            for source in self._stats:
                source_stats = {
                    "total_batches": 0,
                    "running_batches": 0,
                    "total_processed": 0,
                    "total_success": 0,
                    "total_fail": 0,
                    "total_skip": 0,
                    "by_type": {}
                }
                
                for task_type in self._stats[source]:
                    type_stats = {
                        "total_batches": len(self._stats[source][task_type]),
                        "running_batches": 1 if self._running[source].get(task_type) else 0,
                        "total_processed": 0,
                        "total_success": 0,
                        "total_fail": 0,
                        "total_skip": 0
                    }
                    
                    # 汇总批次数据
                    for batch_stats in self._stats[source][task_type].values():
                        type_stats["total_processed"] += batch_stats["total_processed"]
                        type_stats["total_success"] += batch_stats["success_count"]
                        type_stats["total_fail"] += batch_stats["fail_count"]
                        type_stats["total_skip"] += batch_stats["skip_count"]
                    
                    source_stats["by_type"][task_type] = type_stats
                    
                    # 汇总到来源级别
                    source_stats["total_batches"] += type_stats["total_batches"]
                    source_stats["running_batches"] += type_stats["running_batches"]
                    source_stats["total_processed"] += type_stats["total_processed"]
                    source_stats["total_success"] += type_stats["total_success"]
                    source_stats["total_fail"] += type_stats["total_fail"]
                    source_stats["total_skip"] += type_stats["total_skip"]
                
                overall["by_source"][source] = source_stats
                
                # 汇总到全局级别
                overall["total_batches"] += source_stats["total_batches"]
                overall["running_batches"] += source_stats["running_batches"]
                overall["total_processed"] += source_stats["total_processed"]
                overall["total_success"] += source_stats["total_success"]
                overall["total_fail"] += source_stats["total_fail"]
                overall["total_skip"] += source_stats["total_skip"]
            
            # 计算全局成功率
            if overall["total_processed"] > 0:
                overall["success_rate"] = (overall["total_success"] / overall["total_processed"]) * 100
            else:
                overall["success_rate"] = 0
            
            return overall
    
    def clear_history(self, source: str = None, task_type: str = None):
        """
        清除历史记录
        
        Args:
            source: 指定来源，为空则清除所有
            task_type: 指定任务类型，为空则清除指定来源的所有类型
        """
        with self._data_lock:
            if source is None:
                # 清除所有历史
                self._stats.clear()
                self._running.clear()
            elif task_type is None:
                # 清除指定来源的所有历史
                if source in self._stats:
                    self._stats[source].clear()
                if source in self._running:
                    self._running[source].clear()
            else:
                # 清除指定来源和类型的历史
                if source in self._stats and task_type in self._stats[source]:
                    # 保留正在运行的批次
                    running_batch = self._running[source].get(task_type)
                    if running_batch:
                        running_stats = self._stats[source][task_type][running_batch]
                        self._stats[source][task_type].clear()
                        self._stats[source][task_type][running_batch] = running_stats
                    else:
                        self._stats[source][task_type].clear()


# 全局进度跟踪器实例
progress_tracker = ProgressTracker()