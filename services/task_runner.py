"""
通用任务运行器 - 严格按设计蓝图实现

实现通用的任务消费循环框架
Author: Spidermind
"""
import asyncio
from typing import Dict, Any, Callable, Optional, List, Awaitable
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
import logging

from models.base import SessionLocal
from models.crawl import CrawlTask, CrawlLog, CrawlLogCandidate
from services.progress_service import progress_tracker

logger = logging.getLogger(__name__)

# 模块级并发控制
_global_lock = asyncio.Lock()
_is_running: Dict[str, bool] = {}


def is_source_running(source: str) -> bool:
    """检查指定来源是否正在运行"""
    return _is_running.get(source, False)


def get_running_sources() -> List[str]:
    """获取所有正在运行的来源列表"""
    return [source for source, running in _is_running.items() if running]


class TaskRunner:
    """通用任务运行器"""
    
    def __init__(self):
        self.is_running = False
        self.should_stop = False
    
    async def run_until_empty(
        self,
        source: str,
        handler: Callable[[CrawlTask], Awaitable[Dict[str, Any]]],
        filter_types: Optional[List[str]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        循环拉取pending任务直到空为止 (蓝图核心方法)
        
        Args:
            source: 任务来源 (github/openreview/homepage)
            handler: 任务处理函数，接收CrawlTask，返回处理结果
            filter_types: 任务类型过滤列表，None表示处理所有类型
            trace_id: 跟踪ID
        
        Returns:
            Dict: 处理结果统计
        """
        async with _global_lock:
            # 检查是否已在运行
            if _is_running.get(source, False):
                logger.info(f"{source}任务已在运行中，快速返回")
                return {
                    'source': source,
                    'status': 'already_running',
                    'message': f'{source}任务已在运行中',
                    'total_processed': 0,
                    'success_count': 0,
                    'fail_count': 0,
                    'skip_count': 0
                }
            
            # 标记为运行中
            _is_running[source] = True
        
        self.should_stop = False
        
        # 启动进度跟踪
        batch_id = progress_tracker.start_batch(source, 'mixed' if filter_types is None else '_'.join(filter_types))
        
        stats = {
            'source': source,
            'batch_id': batch_id,
            'total_processed': 0,
            'success_count': 0,
            'fail_count': 0,
            'skip_count': 0,
            'start_time': datetime.now()
        }
        
        try:
            logger.info(f"开始消费{source}任务，过滤类型: {filter_types}")
            
            while not self.should_stop:
                # 拉取待处理任务
                tasks = self._get_pending_tasks_by_source(source, filter_types, limit=10)
                
                if not tasks:
                    logger.info(f"没有更多{source}待处理任务，消费完成")
                    break
                
                logger.info(f"拉取到{len(tasks)}个{source}任务，开始处理")
                
                # 逐个处理任务
                for task in tasks:
                    if self.should_stop:
                        break
                    
                    result = await self._process_single_task(task, handler, source, batch_id, trace_id)
                    
                    # 更新统计
                    stats['total_processed'] += 1
                    if result['status'] == 'success':
                        stats['success_count'] += 1
                    elif result['status'] == 'fail':
                        stats['fail_count'] += 1
                    elif result['status'] == 'skip':
                        stats['skip_count'] += 1
                    
                    # 短暂延迟
                    await asyncio.sleep(0.1)
            
            stats['end_time'] = datetime.now()
            stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            logger.info(f"{source}任务消费完成: 处理{stats['total_processed']}, "
                       f"成功{stats['success_count']}, 失败{stats['fail_count']}, "
                       f"跳过{stats['skip_count']}")
            
        except Exception as e:
            logger.error(f"{source}任务消费异常: {e}")
            progress_tracker.record_failure(source, 'mixed', f"消费异常: {str(e)}", batch_id)
            raise
        
        finally:
            # 清理运行状态
            async with _global_lock:
                _is_running[source] = False
            progress_tracker.finish_batch(source, 'mixed', batch_id)
        
        return stats
    
    async def run_batch(
        self,
        task_filters: Dict[str, Any],
        processor: Callable[[Any], Awaitable[Dict[str, Any]]],
        batch_size: int = 10,
        max_tasks: Optional[int] = None,
        progress_source: str = None,
        progress_type: str = None,
        batch_id: str = None
    ):
        """
        运行任务批次处理 (保留向后兼容)
        
        Args:
            task_filters: 任务过滤条件 {source, type, status, priority, ...}
            processor: 任务处理函数，接收task参数，返回处理结果字典
            batch_size: 每批处理数量
            max_tasks: 最大处理任务数，None表示处理所有
            progress_source: 进度跟踪来源
            progress_type: 进度跟踪类型
            batch_id: 批次ID
        """
        self.is_running = True
        self.should_stop = False
        
        processed_count = 0
        
        try:
            while not self.should_stop:
                # 获取待处理任务
                tasks = self._get_pending_tasks(task_filters, batch_size)
                
                if not tasks:
                    logger.info(f"没有更多待处理任务，批次完成。已处理: {processed_count}")
                    break
                
                # 检查是否达到最大处理数量
                if max_tasks and processed_count >= max_tasks:
                    logger.info(f"达到最大处理数量 {max_tasks}，批次结束。")
                    break
                
                logger.info(f"开始处理批次，任务数量: {len(tasks)}")
                
                # 处理当前批次
                batch_results = await self._process_batch(
                    tasks, 
                    processor,
                    progress_source,
                    progress_type,
                    batch_id
                )
                
                processed_count += len(batch_results)
                
                # 输出批次处理结果
                success_count = sum(1 for r in batch_results if r.get('status') == 'success')
                fail_count = sum(1 for r in batch_results if r.get('status') == 'fail')
                skip_count = sum(1 for r in batch_results if r.get('status') == 'skip')
                
                logger.info(f"批次处理完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}")
                
                # 短暂延迟避免过于频繁的数据库查询
                await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"任务运行器异常: {e}")
            if progress_source and progress_type:
                progress_tracker.record_failure(
                    progress_source, 
                    progress_type, 
                    f"运行器异常: {str(e)}", 
                    batch_id
                )
            raise
        
        finally:
            self.is_running = False
            if progress_source and progress_type and batch_id:
                progress_tracker.finish_batch(progress_source, progress_type, batch_id)
            
            logger.info(f"任务批次完成，总计处理: {processed_count}")
    
    def _get_pending_tasks_by_source(
        self, 
        source: str, 
        filter_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[CrawlTask]:
        """
        按来源获取待处理任务 (蓝图核心方法)
        
        Args:
            source: 任务来源
            filter_types: 类型过滤列表
            limit: 数量限制
            
        Returns:
            List[CrawlTask]: 任务列表
        """
        db = SessionLocal()
        try:
            conditions = [
                CrawlTask.source == source,
                CrawlTask.status == 'pending'
            ]
            
            # 类型过滤
            if filter_types:
                conditions.append(CrawlTask.type.in_(filter_types))
            
            tasks = db.query(CrawlTask).filter(and_(*conditions))\
                .order_by(CrawlTask.priority.desc(), CrawlTask.created_at.asc())\
                .limit(limit).all()
            
            return tasks
            
        finally:
            db.close()
    
    async def _process_single_task(
        self,
        task: CrawlTask,
        handler: Callable[[CrawlTask], Awaitable[Dict[str, Any]]],
        source: str,
        batch_id: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理单个任务并写日志 (蓝图核心方法)
        
        Args:
            task: 爬虫任务
            handler: 处理函数
            source: 来源
            batch_id: 批次ID
            trace_id: 跟踪ID
        
        Returns:
            Dict: 处理结果
        """
        task_info = f"{task.type}:{task.url or task.github_login or task.openreview_profile_id}"
        
        try:
            # 更新任务状态为运行中
            self._update_task_status(task.id, 'running')
            
            logger.info(f"开始处理{source}任务: {task_info}")
            
            # 调用处理函数
            result = await handler(task)
            
            # 标准化处理结果
            status = result.get('status', 'fail')
            message = result.get('message', '')
            error = result.get('error', '')
            
            # 更新任务状态
            if status == 'success':
                self._update_task_status(task.id, 'done')
                progress_tracker.record_success(source, task.type, batch_id)
            elif status == 'skip':
                self._update_task_status(task.id, 'done')  # 跳过也标记为完成
                progress_tracker.record_skip(source, task.type, message, batch_id)
            else:
                # 失败时增加重试次数
                self._increment_task_retries(task.id)
                self._update_task_status(task.id, 'failed')
                progress_tracker.record_failure(source, task.type, error or message, batch_id)
            
            # 记录处理日志 (蓝图要求：每处理一条写crawl_logs)
            log_id = self._create_task_log(
                task_id=task.id,
                source=source,
                task_type=task.type,
                url=task.url,
                status=status,
                message=message or error,
                trace_id=trace_id
            )
            
            # 如果有关联的候选人，记录关联关系
            if task.candidate_id and log_id:
                self._create_log_candidate_link(log_id, task.candidate_id)
            
            logger.info(f"完成{source}任务: {task_info}, 状态: {status}")
            
            return {
                'task_id': task.id,
                'status': status,
                'message': message,
                'error': error,
                'log_id': log_id
            }
            
        except Exception as e:
            error_message = f"处理{source}任务 {task_info} 异常: {str(e)}"
            logger.error(error_message)
            
            # 记录异常
            self._increment_task_retries(task.id)
            self._update_task_status(task.id, 'failed')
            progress_tracker.record_failure(source, task.type, error_message, batch_id)
            
            # 记录错误日志
            log_id = self._create_task_log(
                task_id=task.id,
                source=source,
                task_type=task.type,
                url=task.url,
                status='fail',
                message=error_message,
                trace_id=trace_id
            )
            
            return {
                'task_id': task.id,
                'status': 'fail',
                'message': error_message,
                'error': str(e),
                'log_id': log_id
            }
    
    def _get_pending_tasks(self, filters: Dict[str, Any], limit: int) -> List[CrawlTask]:
        """
        获取待处理任务 (保留向后兼容)
        
        Args:
            filters: 过滤条件
            limit: 数量限制
            
        Returns:
            List[CrawlTask]: 任务列表
        """
        db = SessionLocal()
        try:
            query = db.query(CrawlTask)
            
            # 应用过滤条件
            conditions = []
            
            if 'source' in filters:
                conditions.append(CrawlTask.source == filters['source'])
            
            if 'type' in filters:
                conditions.append(CrawlTask.type == filters['type'])
            
            if 'status' in filters:
                conditions.append(CrawlTask.status == filters['status'])
            
            if 'priority' in filters:
                conditions.append(CrawlTask.priority >= filters['priority'])
            
            if 'candidate_id' in filters:
                conditions.append(CrawlTask.candidate_id == filters['candidate_id'])
            
            if 'batch_id' in filters:
                conditions.append(CrawlTask.batch_id == filters['batch_id'])
            
            # 应用条件
            if conditions:
                query = query.filter(and_(*conditions))
            
            # 按优先级和创建时间排序
            tasks = query.order_by(
                CrawlTask.priority.desc(),
                CrawlTask.created_at.asc()
            ).limit(limit).all()
            
            return tasks
            
        finally:
            db.close()
    
    async def _process_batch(
        self,
        tasks: List[CrawlTask],
        processor: Callable[[Any], Awaitable[Dict[str, Any]]],
        progress_source: str = None,
        progress_type: str = None,
        batch_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        处理任务批次 (保留向后兼容)
        
        Args:
            tasks: 任务列表
            processor: 处理函数
            progress_source: 进度来源
            progress_type: 进度类型
            batch_id: 批次ID
            
        Returns:
            List[Dict]: 处理结果列表
        """
        results = []
        
        for task in tasks:
            if self.should_stop:
                break
                
            try:
                # 更新任务状态为处理中
                self._update_task_status(task.id, 'running')
                
                # 调用处理函数
                result = await processor(task)
                
                # 处理结果
                status = result.get('status', 'fail')
                message = result.get('message', '')
                error = result.get('error', '')
                
                # 更新任务状态
                if status == 'success':
                    self._update_task_status(task.id, 'done')
                    if progress_source and progress_type:
                        progress_tracker.record_success(progress_source, progress_type, batch_id)
                elif status == 'skip':
                    self._update_task_status(task.id, 'done')  # 跳过也标记为完成
                    if progress_source and progress_type:
                        progress_tracker.record_skip(progress_source, progress_type, message, batch_id)
                else:
                    # 失败时增加重试次数
                    self._increment_task_retries(task.id)
                    self._update_task_status(task.id, 'failed')
                    if progress_source and progress_type:
                        progress_tracker.record_failure(progress_source, progress_type, error or message, batch_id)
                
                # 记录处理日志
                log_id = self._create_task_log(
                    task_id=task.id,
                    source=task.source,
                    task_type=task.type,
                    url=task.url,
                    status=status,
                    message=message or error
                )
                
                # 如果有关联的候选人，记录关联关系
                if task.candidate_id and log_id:
                    self._create_log_candidate_link(log_id, task.candidate_id)
                
                results.append({
                    'task_id': task.id,
                    'status': status,
                    'message': message,
                    'error': error,
                    'log_id': log_id
                })
                
            except Exception as e:
                error_message = f"处理任务 {task.id} 时发生异常: {str(e)}"
                logger.error(error_message)
                
                # 记录异常
                self._increment_task_retries(task.id)
                self._update_task_status(task.id, 'failed')
                
                if progress_source and progress_type:
                    progress_tracker.record_failure(progress_source, progress_type, error_message, batch_id)
                
                # 记录错误日志
                log_id = self._create_task_log(
                    task_id=task.id,
                    source=task.source,
                    task_type=task.type,
                    url=task.url,
                    status='fail',
                    message=error_message
                )
                
                results.append({
                    'task_id': task.id,
                    'status': 'fail',
                    'message': error_message,
                    'error': str(e),
                    'log_id': log_id
                })
        
        return results
    
    def _update_task_status(self, task_id: int, status: str):
        """更新任务状态"""
        db = SessionLocal()
        try:
            task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
            if task:
                task.status = status
                task.updated_at = datetime.now()
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"更新任务状态失败: {e}")
        finally:
            db.close()
    
    def _increment_task_retries(self, task_id: int):
        """增加任务重试次数"""
        db = SessionLocal()
        try:
            task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
            if task:
                task.retries = (task.retries or 0) + 1
                task.updated_at = datetime.now()
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"更新任务重试次数失败: {e}")
        finally:
            db.close()
    
    def _create_task_log(
        self, 
        task_id: int, 
        source: str,
        task_type: str,
        url: Optional[str], 
        status: str, 
        message: str,
        trace_id: Optional[str] = None
    ) -> Optional[int]:
        """创建任务日志 (蓝图要求：规范message格式)"""
        db = SessionLocal()
        try:
            log = CrawlLog(
                task_id=task_id,
                source=source,
                task_type=task_type,
                url=url,
                status=status,
                message=message,
                trace_id=trace_id,
                created_at=datetime.now()
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id
        except Exception as e:
            db.rollback()
            logger.error(f"创建任务日志失败: {e}")
            return None
        finally:
            db.close()
    
    def _create_log_candidate_link(self, log_id: int, candidate_id: int):
        """创建日志与候选人的关联"""
        db = SessionLocal()
        try:
            # 检查是否已存在关联
            existing = db.query(CrawlLogCandidate).filter(
                CrawlLogCandidate.log_id == log_id,
                CrawlLogCandidate.candidate_id == candidate_id
            ).first()
            
            if not existing:
                link = CrawlLogCandidate(
                    log_id=log_id,
                    candidate_id=candidate_id
                )
                db.add(link)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"创建日志候选人关联失败: {e}")
        finally:
            db.close()
    
    def stop(self):
        """停止任务运行器"""
        self.should_stop = True
        logger.info("任务运行器收到停止信号")


class TaskBatchManager:
    """任务批次管理器"""
    
    @staticmethod
    def create_tasks(
        source: str,
        task_type: str,
        task_data_list: List[Dict[str, Any]],
        batch_id: str = None,
        priority: int = 0
    ) -> List[int]:
        """
        批量创建任务
        
        Args:
            source: 任务来源
            task_type: 任务类型
            task_data_list: 任务数据列表
            batch_id: 批次ID
            priority: 优先级
            
        Returns:
            List[int]: 创建的任务ID列表
        """
        db = SessionLocal()
        created_task_ids = []
        
        try:
            for task_data in task_data_list:
                # 检查是否已存在相同任务（根据去重键）
                existing_task = db.query(CrawlTask).filter(
                    CrawlTask.source == source,
                    CrawlTask.type == task_type,
                    CrawlTask.url == task_data.get('url', ''),
                    CrawlTask.github_login == task_data.get('github_login', ''),
                    CrawlTask.openreview_profile_id == task_data.get('openreview_profile_id', '')
                ).first()
                
                if existing_task:
                    logger.info(f"任务已存在，跳过: {task_data}")
                    continue
                
                # 创建新任务
                task = CrawlTask(
                    source=source,
                    type=task_type,
                    url=task_data.get('url'),
                    github_login=task_data.get('github_login'),
                    openreview_profile_id=task_data.get('openreview_profile_id'),
                    candidate_id=task_data.get('candidate_id'),
                    depth=task_data.get('depth', 0),
                    status='pending',
                    priority=priority,
                    batch_id=batch_id,
                    retries=0,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                db.add(task)
                db.flush()  # 获取ID但不提交
                created_task_ids.append(task.id)
            
            db.commit()
            logger.info(f"批量创建任务完成，创建数量: {len(created_task_ids)}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"批量创建任务失败: {e}")
            raise
        finally:
            db.close()
        
        return created_task_ids
    
    @staticmethod
    def get_task_stats(source: str = None, task_type: str = None) -> Dict[str, int]:
        """
        获取任务统计信息
        
        Args:
            source: 来源过滤
            task_type: 类型过滤
            
        Returns:
            Dict: 统计信息
        """
        db = SessionLocal()
        try:
            query = db.query(CrawlTask)
            
            if source:
                query = query.filter(CrawlTask.source == source)
            if task_type:
                query = query.filter(CrawlTask.type == task_type)
            
            # 统计各状态数量
            from sqlalchemy import func
            
            stats = db.query(
                CrawlTask.status,
                func.count(CrawlTask.id).label('count')
            ).filter(
                *([CrawlTask.source == source] if source else []),
                *([CrawlTask.type == task_type] if task_type else [])
            ).group_by(CrawlTask.status).all()
            
            result = {
                'pending': 0,
                'running': 0,
                'done': 0,
                'failed': 0,
                'total': 0
            }
            
            for status, count in stats:
                result[status] = count
                result['total'] += count
            
            return result
            
        finally:
            db.close()


# 全局任务运行器实例
task_runner = TaskRunner()