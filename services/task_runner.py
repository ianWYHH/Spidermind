"""
通用任务消费器 - 按蓝图要求实现
"按钮触发→消费 pending→无任务即停"

Author: Spidermind
"""
from typing import Callable, Any, Dict, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import uuid

from models.base import SessionLocal
from models.crawl import CrawlTask, CrawlLog
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)


class TaskRunner:
    """通用任务消费器"""
    
    def __init__(self):
        self._stop_flag = False
    
    async def run_until_empty(
        self,
        source: str,
        handler: Callable[[CrawlTask], Dict[str, Any]],
        filter_types: Optional[List[str]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        消费 pending 任务直到队列为空
        
        Args:
            source: 爬虫来源 (github/openreview/homepage)
            handler: 任务处理函数 (task) -> {status, message, error?}
            filter_types: 可选的任务类型过滤
            trace_id: 跟踪ID
            
        Returns:
            Dict: 运行结果统计
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        logger.info(f"开始消费 {source} 任务，trace_id: {trace_id}")
        
        # 开始新一轮统计
        progress_tracker.start_round(source)
        
        self._stop_flag = False
        total_processed = 0
        
        try:
            while not self._stop_flag:
                # 在事务中获取并锁定一个任务
                task = self._get_next_task(source, filter_types)
                
                if task is None:
                    # 队列为空，退出循环
                    logger.info(f"{source} 任务队列为空，消费完成")
                    break
                
                # 处理任务
                result = await self._process_single_task(task, handler, trace_id)
                total_processed += 1
                
                # 更新进度统计
                progress_tracker.inc_processed(source)
                
                status = result.get('status', 'fail')
                if status == 'success':
                    progress_tracker.inc_success(source)
                elif status == 'skip':
                    progress_tracker.inc_skip(source)
                else:
                    progress_tracker.inc_fail(source)
                
                logger.debug(f"处理任务 {task.id} 完成: {status}")
        
        except Exception as e:
            logger.error(f"任务消费过程异常: {e}")
            raise
        
        finally:
            # 结束本轮统计
            progress_tracker.end_round(source)
        
        # 返回最终统计
        final_stats = progress_tracker.get_round_stats(source)
        final_stats.update({
            'trace_id': trace_id,
            'total_processed': total_processed,
            'stopped_by_flag': self._stop_flag
        })
        
        return final_stats
    
    def _get_next_task(self, source: str, filter_types: Optional[List[str]] = None) -> Optional[CrawlTask]:
        """
        事务性获取下一个待处理任务
        
        Args:
            source: 爬虫来源
            filter_types: 任务类型过滤
            
        Returns:
            CrawlTask: 待处理任务，如果队列为空则返回None
        """
        db = SessionLocal()
        try:
            # 构建查询条件
            conditions = [
                CrawlTask.source == source,
                CrawlTask.status == 'pending'
            ]
            
            if filter_types:
                conditions.append(CrawlTask.type.in_(filter_types))
            
            # 获取最老的一个任务（按优先级降序，创建时间升序）
            task = db.query(CrawlTask).filter(and_(*conditions))\
                .order_by(CrawlTask.priority.desc(), CrawlTask.created_at.asc())\
                .first()
            
            if task:
                # 原地更新状态为 running，避免重复处理
                task.status = 'running'
                db.commit()
                
            return task
            
        except Exception as e:
            db.rollback()
            logger.error(f"获取任务时发生异常: {e}")
            return None
        finally:
            db.close()
    
    async def _process_single_task(
        self, 
        task: CrawlTask, 
        handler: Callable[[CrawlTask], Dict[str, Any]], 
        trace_id: str
    ) -> Dict[str, Any]:
        """
        处理单个任务并写入日志
        
        Args:
            task: 任务对象
            handler: 处理函数
            trace_id: 跟踪ID
            
        Returns:
            Dict: 处理结果
        """
        db = SessionLocal()
        try:
            # 调用业务处理函数
            result = await handler(task)
            
            # 标准化结果
            status = result.get('status', 'fail')
            message = result.get('message', '处理完成')
            error = result.get('error', '')
            
            # 更新任务状态
            if status == 'success':
                task.status = 'done'
            elif status == 'skip':
                task.status = 'done'  # 跳过的任务也标记为已完成
            else:
                task.status = 'failed'
                task.retries = (task.retries or 0) + 1
            
            db.merge(task)
            
            # 写入处理日志
            log_entry = CrawlLog(
                task_id=task.id,
                source=task.source,
                task_type=task.type,
                url=task.url,
                status='success' if status in ['success', 'skip'] else 'fail',
                message=message,
                trace_id=trace_id
            )
            
            db.add(log_entry)
            db.commit()
            
            return result
            
        except Exception as e:
            db.rollback()
            
            # 异常情况下的日志记录
            error_msg = f"任务处理异常: {str(e)}"
            logger.error(f"处理任务 {task.id} 时发生异常: {e}")
            
            try:
                task.status = 'failed'
                task.retries = (task.retries or 0) + 1
                db.merge(task)
                
                log_entry = CrawlLog(
                    task_id=task.id,
                    source=task.source,
                    task_type=task.type,
                    url=task.url,
                    status='fail',
                    message=error_msg,
                    trace_id=trace_id
                )
                db.add(log_entry)
                db.commit()
            except Exception as log_error:
                logger.error(f"写入错误日志失败: {log_error}")
            
            return {
                'status': 'fail',
                'message': error_msg,
                'error': str(e)
            }
            
        finally:
            db.close()
    
    def stop(self) -> None:
        """停止任务消费"""
        self._stop_flag = True
        logger.info("收到停止信号，将在当前任务完成后停止")


# 全局单例
task_runner = TaskRunner()


def is_source_running(source: str) -> bool:
    """
    检查指定来源是否正在运行
    
    Args:
        source: 爬虫来源
        
    Returns:
        bool: 是否正在运行
    """
    stats = progress_tracker.get_round_stats(source)
    return stats.get('running', False)


class TaskBatchManager:
    """任务批次管理器 - 简化实现"""
    
    @staticmethod
    def get_task_stats(source: str) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Args:
            source: 爬虫来源
            
        Returns:
            Dict: 任务统计信息
        """
        db = SessionLocal()
        try:
            # 获取待处理任务数量
            pending_count = db.query(CrawlTask).filter(
                CrawlTask.source == source,
                CrawlTask.status == 'pending'
            ).count()
            
            # 获取总任务数量
            total_count = db.query(CrawlTask).filter(
                CrawlTask.source == source
            ).count()
            
            # 获取已完成任务数量
            done_count = db.query(CrawlTask).filter(
                CrawlTask.source == source,
                CrawlTask.status == 'done'
            ).count()
            
            # 获取失败任务数量
            failed_count = db.query(CrawlTask).filter(
                CrawlTask.source == source,
                CrawlTask.status == 'failed'
            ).count()
            
            return {
                'pending': pending_count,
                'total': total_count,
                'done': done_count,
                'failed': failed_count
            }
            
        except Exception as e:
            logger.error(f"获取任务统计失败: {e}")
            return {
                'pending': 0,
                'total': 0,
                'done': 0,
                'failed': 0
            }
        finally:
            db.close()
    
    @staticmethod
    def create_tasks(
        source: str,
        task_type: str,
        task_data_list: List[Dict[str, Any]],
        batch_id: Optional[str] = None,
        priority: int = 0
    ) -> List[int]:
        """
        批量创建任务
        
        Args:
            source: 爬虫来源
            task_type: 任务类型
            task_data_list: 任务数据列表
            batch_id: 批次ID
            priority: 优先级
            
        Returns:
            List[int]: 创建的任务ID列表
        """
        db = SessionLocal()
        created_ids = []
        
        try:
            for task_data in task_data_list:
                task = CrawlTask(
                    source=source,
                    type=task_type,
                    url=task_data.get('url'),
                    github_login=task_data.get('github_login'),
                    openreview_profile_id=task_data.get('openreview_profile_id'),
                    candidate_id=task_data.get('candidate_id'),
                    batch_id=batch_id,
                    priority=priority,
                    status='pending'
                )
                
                db.add(task)
                db.flush()  # 获取ID
                created_ids.append(task.id)
            
            db.commit()
            logger.info(f"批量创建 {len(created_ids)} 个 {source} 任务")
            
        except Exception as e:
            db.rollback()
            logger.error(f"批量创建任务失败: {e}")
            raise
        finally:
            db.close()
        
        return created_ids


# 最小化的桩函数，供测试使用
async def dummy_task_handler(task: CrawlTask) -> Dict[str, Any]:
    """
    最小桩函数 - 仅用于测试任务消费循环
    实际使用时应该注入具体的业务处理函数
    
    Args:
        task: 爬虫任务
        
    Returns:
        Dict: 固定返回成功结果
    """
    return {
        'status': 'success',
        'message': f'桩函数处理完成: {task.type} 任务 {task.id}'
    }